import {useThree} from '@react-three/fiber';
import React, {useLayoutEffect} from 'react';
import type {PerspectiveCamera} from 'three';
import type {EstadoCamara} from '../lib/camara';

/**
 * Aplica un EstadoCamara (src/lib/camara.ts) a la cámara por defecto del canvas.
 * Se actualiza en useLayoutEffect: corre antes del useEffect en el que <ThreeCanvas>
 * dibuja el cuadro, así la cámara nunca va un cuadro atrasada.
 */
export const CamaraRig: React.FC<{
  readonly estado: EstadoCamara;
  readonly cerca?: number;
  readonly lejos?: number;
}> = ({estado, cerca = 0.1, lejos = 200}) => {
  const camera = useThree((s) => s.camera) as PerspectiveCamera;
  useLayoutEffect(() => {
    camera.up.set(0, 1, 0);
    camera.position.set(
      estado.posicion[0],
      estado.posicion[1],
      estado.posicion[2],
    );
    camera.lookAt(estado.objetivo[0], estado.objetivo[1], estado.objetivo[2]);
    if (estado.rolido) camera.rotateZ(estado.rolido);
    camera.fov = estado.fov;
    camera.near = cerca;
    camera.far = lejos;
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();
  });
  return null;
};
