import React, {useEffect, useLayoutEffect, useMemo} from 'react';
import * as THREE from 'three';
import {crearMaterialEnsueno} from './materiales';

/**
 * Forma orgánica con shader propio (desplazamiento por ruido + borde fresnel) que
 * proyecta y recibe sombras con su forma real (material de profundidad a juego).
 */
export const Ensueno: React.FC<{
  readonly tiempo: number;
  readonly posicion?: THREE.Vector3Tuple;
  readonly radio?: number;
  readonly amplitud?: number;
  readonly frecuencia?: number;
  readonly velocidad?: number;
  readonly color?: string;
  readonly colorB?: string;
  readonly colorBorde?: string;
  readonly intensidadBorde?: number;
  /** Segmentos de la esfera base (alto = más suave y más caro). */
  readonly segmentos?: number;
}> = ({
  tiempo,
  posicion = [0, 1.4, 0],
  radio = 1,
  amplitud = 0.18,
  frecuencia = 1.4,
  velocidad = 0.25,
  color = '#b88a5a',
  colorB = '#e6cfa8',
  colorBorde = '#9fb7d6',
  intensidadBorde = 0.45,
  segmentos = 160,
}) => {
  const {material, profundidad, uniforms} = useMemo(
    () => crearMaterialEnsueno({color, colorB, colorBorde}),
    [color, colorB, colorBorde],
  );
  const geometria = useMemo(
    () => new THREE.SphereGeometry(1, segmentos, Math.round(segmentos * 0.75)),
    [segmentos],
  );

  useLayoutEffect(() => {
    uniforms.uTiempo.value = tiempo;
    uniforms.uAmplitud.value = amplitud;
    uniforms.uFrecuencia.value = frecuencia;
    uniforms.uVelocidad.value = velocidad;
    uniforms.uIntensidadBorde.value = intensidadBorde;
  });

  useEffect(() => () => geometria.dispose(), [geometria]);
  useEffect(
    () => () => {
      material.dispose();
      profundidad.dispose();
    },
    [material, profundidad],
  );

  return (
    <mesh
      geometry={geometria}
      material={material}
      customDepthMaterial={profundidad}
      position={posicion}
      scale={radio}
      castShadow
      receiveShadow
    />
  );
};
