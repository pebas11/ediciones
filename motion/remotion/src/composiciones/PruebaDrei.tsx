import {ContactShadows, Environment, Lightformer, RoundedBox} from '@react-three/drei';
import {ThreeCanvas} from '@remotion/three';
import React from 'react';
import {AbsoluteFill, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {estadoCamara} from '../lib/camara';
import {CamaraRig} from '../three/CamaraRig';
import {Postproceso} from '../three/Postproceso';
import {Texto3D} from '../three/Texto3D';

/**
 * Prueba de componentes de drei que son deterministas con <ThreeCanvas>:
 *  - <Environment frames={1}> con <Lightformer>: mapa de entorno procedural (sin bajar
 *    HDRs de internet), se calcula una vez al montar.
 *  - <RoundedBox>: geometría.
 *  - <ContactShadows>: sombra de contacto (se recalcula en cada cuadro, sin reloj).
 *  - <Texto3D>: drei <Text> esperando a troika (ver Texto3D.tsx).
 * NO usar los de drei que animan con el reloj (Float, Sparkles, Stars con speed, Cloud,
 * MeshDistortMaterial, MeshWobbleMaterial, etc.): no son reproducibles cuadro a cuadro.
 */
export const PruebaDrei: React.FC = () => {
  const frame = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const t = frame / fps;
  const camara = estadoCamara(t, {
    claves: [
      {t: 0, posicion: [3.2, 1.6, 4.2], objetivo: [0, 0.6, 0], fov: 35},
      {t: 2, posicion: [-2.6, 1.9, 4.4], objetivo: [0, 0.6, 0], fov: 33, curva: 'respiro'},
    ],
  });
  return (
    <AbsoluteFill style={{backgroundColor: '#1b1712'}}>
      <ThreeCanvas width={width} height={height} gl={{antialias: false}}>
        <CamaraRig estado={camara} />
        <color attach="background" args={['#1b1712']} />
        <Environment frames={1} resolution={256}>
          <Lightformer form="rect" intensity={3} position={[0, 4, 2]} scale={[6, 2, 1]} color="#ffe3bd" />
          <Lightformer form="ring" intensity={1.5} position={[-4, 1, -2]} scale={2} color="#9fb7d6" />
          <Lightformer form="rect" intensity={0.6} position={[4, 0.5, 0]} scale={[2, 4, 1]} color="#c9a46a" />
        </Environment>
        <RoundedBox args={[1.2, 1.2, 1.2]} radius={0.18} smoothness={6} position={[0, 0.62, 0]} rotation={[0, t * 0.4, 0]}>
          <meshStandardMaterial color="#b88a5a" metalness={0.85} roughness={0.25} />
        </RoundedBox>
        <ContactShadows position={[0, 0, 0]} scale={8} blur={2.4} far={3} opacity={0.65} resolution={512} />
        <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.001, 0]}>
          <planeGeometry args={[30, 30]} />
          <meshStandardMaterial color="#2b241d" roughness={1} />
        </mesh>
        <Texto3D
          fuente={staticFile('fuentes/league-spartan-latin-800-normal.woff')}
          position={[0, 1.75, -0.6]}
          fontSize={0.42}
          color="#f3eadb"
          anchorX="center"
          anchorY="middle"
        >
          Texto en 3D
        </Texto3D>
        <Postproceso msaa={4} tono="agx" grano={{intensidad: 0.04}} />
      </ThreeCanvas>
    </AbsoluteFill>
  );
};
