import {createPortal} from '@react-three/fiber';
import React, {useMemo} from 'react';
import * as THREE from 'three';
import {crearAzar, entre} from '../lib/azar';
import {distancia, type EstadoCamara, type Vec3} from '../lib/camara';
import type {AjustesCalidad} from './calidad';
import {CamaraRig} from './CamaraRig';
import {Cielo} from './Cielo';
import {Ensueno} from './Ensueno';
import {crearUniformsCapa} from './PaseCapa';
import {Particulas} from './Particulas';
import {Postproceso, type Tono} from './Postproceso';

/**
 * Mundo 3D de PRUEBA TÉCNICA (no es un diseño): ejercita luces y sombras, un material
 * con shader propio, ~50k partículas instanciadas, niebla, DOF + tone mapping en
 * postproceso y cámara en movimiento. Va dentro de un <ThreeCanvas shadows>.
 * Recibe todo por props (tiempo, cámara, niveles de audio): nada depende de un reloj.
 */
export type Paleta = {
  niebla: string;
  cieloArriba: string;
  suelo: string;
  piedra: string;
  ensueno: string;
  ensuenoB: string;
  borde: string;
  aro: string;
  luz: string;
  relleno: string;
  particulas: string;
};

export const PALETA_PRUEBA: Paleta = {
  niebla: '#4b4034',
  cieloArriba: '#211c17',
  suelo: '#3a3027',
  piedra: '#6e5c49',
  ensueno: '#b4885a',
  ensuenoB: '#e8d2ab',
  borde: '#8fb0d8',
  aro: '#cdb38f',
  luz: '#ffe3bd',
  relleno: '#9fb7d6',
  particulas: '#f1e2c6',
};

export const CENTRO_ENSUENO: Vec3 = [0, 1.55, 0];

type Piedra = {
  pos: THREE.Vector3Tuple;
  escala: THREE.Vector3Tuple;
  rot: THREE.Vector3Tuple;
  tono: number;
};

const crearPiedras = (cantidad: number): Piedra[] => {
  const azar = crearAzar('piedras');
  return Array.from({length: cantidad}, (_, i) => {
    const ang = (i / cantidad) * Math.PI * 2 + entre(azar, -0.25, 0.25);
    const r = entre(azar, 3.8, 9.5);
    const alto = entre(azar, 0.9, 3.4);
    const ancho = entre(azar, 0.45, 0.9);
    // Dodecaedro de radio 1 escalado: se entierra un 15 % para que no "flote".
    return {
      pos: [Math.cos(ang) * r, alto * 0.85, Math.sin(ang) * r],
      escala: [ancho, alto, ancho * entre(azar, 0.7, 1.2)],
      rot: [
        entre(azar, -0.12, 0.12),
        entre(azar, 0, Math.PI),
        entre(azar, -0.12, 0.12),
      ],
      tono: entre(azar, 0.8, 1.15),
    };
  });
};

export const MundoPrueba: React.FC<{
  readonly tiempo: number;
  readonly camara: EstadoCamara;
  readonly calidad: AjustesCalidad;
  /** Nivel de la música 0..1 (deforma la forma central). */
  readonly energia?: number;
  /** Pulso 0..1 en los downbeats (brillo de partículas). */
  readonly pulso?: number;
  readonly paleta?: Paleta;
  readonly particulas?: number;
  readonly tono?: Tono;
}> = ({
  tiempo,
  camara,
  calidad,
  energia = 0,
  pulso = 0,
  paleta = PALETA_PRUEBA,
  particulas = 50000,
  tono = 'agx',
}) => {
  const piedras = useMemo(() => crearPiedras(9), []);
  // Con postproceso, las partículas van en una escena aparte que se dibuja DESPUÉS del
  // DOF (con bokeh propio y oclusión suave). Sin postproceso, en la escena principal.
  const capa = useMemo(
    () => ({escena: new THREE.Scene(), uniforms: crearUniformsCapa()}),
    [],
  );
  const enCapa = calidad.postproceso;
  const colorPiedra = useMemo(
    () => new THREE.Color(paleta.piedra),
    [paleta.piedra],
  );
  const enfoque = distancia(camara.posicion, CENTRO_ENSUENO);

  return (
    <>
      <CamaraRig estado={camara} cerca={0.1} lejos={120} />
      <color attach="background" args={[paleta.niebla]} />
      <fogExp2 attach="fog" args={[paleta.niebla, 0.06]} />
      <Cielo
        tiempo={tiempo}
        arriba={paleta.cieloArriba}
        horizonte={paleta.niebla}
      />

      <hemisphereLight args={[paleta.luz, paleta.suelo, 0.55]} />
      <directionalLight
        position={[6, 9, 4]}
        color={paleta.luz}
        intensity={2.6}
        castShadow
        shadow-mapSize={[calidad.sombra, calidad.sombra]}
        shadow-camera-left={-11}
        shadow-camera-right={11}
        shadow-camera-top={11}
        shadow-camera-bottom={-11}
        shadow-camera-near={1}
        shadow-camera-far={32}
        shadow-bias={-0.0004}
        shadow-normalBias={0.03}
      />
      <pointLight
        position={[-4, 3, -5]}
        color={paleta.relleno}
        intensity={7}
        distance={22}
        decay={2}
      />

      {/* Suelo */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <planeGeometry args={[90, 90]} />
        <meshStandardMaterial
          color={paleta.suelo}
          roughness={0.95}
          metalness={0}
        />
      </mesh>

      {/* Piedras: dan escala, profundidad para el DOF y sombras largas */}
      {piedras.map((p, i) => (
        <mesh
          key={i}
          position={p.pos}
          scale={p.escala}
          rotation={p.rot}
          castShadow
          receiveShadow
        >
          <dodecahedronGeometry args={[1, 0]} />
          <meshStandardMaterial
            color={colorPiedra.clone().multiplyScalar(p.tono)}
            roughness={0.85}
            flatShading
          />
        </mesh>
      ))}

      {/* Aro vertical detrás de la forma */}
      <mesh position={[0, 2.1, -2.6]} castShadow receiveShadow>
        <torusGeometry
          args={[2.25, 0.055, 24, Math.round(220 * calidad.detalle)]}
        />
        <meshStandardMaterial
          color={paleta.aro}
          metalness={0.35}
          roughness={0.35}
        />
      </mesh>

      <Ensueno
        tiempo={tiempo}
        posicion={CENTRO_ENSUENO as THREE.Vector3Tuple}
        radio={1}
        amplitud={0.09 + energia * 0.1}
        frecuencia={1.1}
        color={paleta.ensueno}
        colorB={paleta.ensuenoB}
        colorBorde={paleta.borde}
        segmentos={Math.max(32, Math.round(160 * calidad.detalle))}
      />

      {(() => {
        const p = (
          <Particulas
            tiempo={tiempo}
            cantidad={Math.round(particulas * calidad.particulas)}
            caja={[40, 12, 40]}
            centro={[0, 5.4, 0]}
            color={paleta.particulas}
            tamano={0.014}
            opacidad={0.7}
            brillo={1 + pulso * 0.8}
            enfoque={enfoque}
            rangoEnfoque={5}
            capa={enCapa ? capa.uniforms : null}
          />
        );
        return enCapa ? createPortal(p, capa.escena) : p;
      })()}

      {calidad.postproceso ? (
        <Postproceso
          msaa={calidad.msaa}
          tono={tono}
          dof={calidad.dof ? {distancia: enfoque, rango: 3.2, bokeh: 3} : null}
          dofEscala={calidad.dofEscala}
          bufer8={calidad.bufer8}
          capa={capa}
          grano={
            calidad.grano
              ? {
                  intensidad: 0.05,
                  escala: 1.5,
                  cadencia: 2,
                  vineta: 0.55,
                  radio: 0.45,
                }
              : null
          }
        />
      ) : null}
    </>
  );
};
