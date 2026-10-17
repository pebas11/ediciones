import {ThreeCanvas} from '@remotion/three';
import React from 'react';
import {AbsoluteFill, useVideoConfig} from 'remotion';
import {Grano} from '../capas/Grano';
import {Vineta} from '../capas/Vineta';
import {nivelAR, pulso, useDatosAudio} from '../lib/audio';
import {estadoCamara, type OpcionesRig, type Vec3} from '../lib/camara';
import {useCuadroAbsoluto} from '../lib/tiempo';
import type {PropsEscena} from '../composiciones/LineaDeTiempo';
import {useEscena} from '../composiciones/LineaDeTiempo';
import {useCalidad} from '../three/calidad';
import {MundoPrueba, PALETA_PRUEBA} from '../three/MundoPrueba';

/**
 * Escena de ejemplo "mundo3d" para la línea de tiempo (NO es un diseño final).
 * params: { orbita?: number (grados que gira la cámara), distancia?: number,
 *           altura?: number, particulas?: number }
 */
const num = (v: unknown, d: number) => (typeof v === 'number' && Number.isFinite(v) ? v : d);

export const EscenaMundo3D: React.FC<PropsEscena> = ({params}) => {
  const {width, height, fps} = useVideoConfig();
  const escena = useEscena();
  const q = useCalidad();
  const env = useDatosAudio();
  const abs = useCuadroAbsoluto();

  const t = escena?.t ?? 0;
  const dur = escena?.duracion ?? 5;
  const orbita = (num(params.orbita, 40) * Math.PI) / 180;
  const dist = num(params.distancia, 9);
  const alto = num(params.altura, 2.2);
  const a0 = num(params.angulo, 35) * (Math.PI / 180);
  const pos = (a: number): Vec3 => [Math.sin(a) * dist, alto, Math.cos(a) * dist];
  const rig: OpcionesRig = {
    claves: [
      {t: -1, posicion: pos(a0 - orbita * 0.1), objetivo: [0, 1.5, 0], fov: 34},
      {t: dur + 1, posicion: pos(a0 + orbita), objetivo: [0, 1.6, 0], fov: 31, curva: 'lineal'},
    ],
    respiracion: {amplitud: [0.05, 0.035, 0.05], frecuencia: 0.25},
  };

  return (
    <AbsoluteFill>
      <ThreeCanvas
        width={width}
        height={height}
        shadows
        dpr={q.dpr}
        gl={{antialias: !q.postproceso}}
        camera={{fov: 34, near: 0.1, far: 120}}
      >
        <MundoPrueba
          tiempo={abs / fps}
          camara={estadoCamara(t, rig)}
          calidad={q}
          energia={env ? nivelAR(env, 'musica', abs, {banda: 'graves', relajacion: 0.3}) : 0}
          pulso={env?.musica ? pulso(env.musica.downbeats, abs, {caida: 18}) : 0}
          particulas={num(params.particulas, 50000)}
          paleta={PALETA_PRUEBA}
        />
      </ThreeCanvas>
      <Vineta intensidad={0.55} radio={0.5} />
      <Grano intensidad={0.12} />
    </AbsoluteFill>
  );
};
