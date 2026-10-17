import React, {useEffect, useLayoutEffect, useMemo} from 'react';
import * as THREE from 'three';
import {crearAzar} from '../lib/azar';
import {crearGeometriaParticulas, crearMaterialParticulas} from './materiales';
import type {UniformsCapa} from './PaseCapa';

/**
 * Campo de partículas instanciadas (un quad por partícula, ~50k sin problema).
 * El movimiento se calcula en el vertex shader a partir de uTiempo: no hay estado en
 * la CPU, por eso cualquier cuadro se puede renderizar sin haber pasado por los anteriores.
 */
export const Particulas: React.FC<{
  readonly tiempo: number;
  readonly cantidad?: number;
  readonly caja?: readonly [number, number, number];
  readonly centro?: readonly [number, number, number];
  readonly semilla?: string;
  readonly color?: string;
  readonly tamano?: number;
  readonly opacidad?: number;
  readonly brillo?: number;
  /** Distancia de la cámara al plano de foco (unidades de mundo). */
  readonly enfoque?: number;
  readonly rangoEnfoque?: number;
  readonly subida?: number;
  /** Uniforms de la capa posterior al DOF (ver PaseCapa). null = escena principal. */
  readonly capa?: UniformsCapa | null;
}> = ({
  tiempo,
  cantidad = 50000,
  caja = [24, 10, 24],
  centro = [0, 3, 0],
  semilla = 'particulas',
  color = '#f1e2c6',
  tamano = 0.022,
  opacidad = 0.85,
  brillo = 1,
  enfoque = 6,
  rangoEnfoque = 6,
  subida = 0.12,
  capa = null,
}) => {
  const geometria = useMemo(
    () => crearGeometriaParticulas(cantidad, caja, crearAzar(semilla)),
    // caja como string para no recrear la geometría por un array nuevo en cada render
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [cantidad, semilla, caja.join(',')],
  );
  const {material, uniforms} = useMemo(
    () => crearMaterialParticulas(color, capa),
    [color, capa],
  );

  useLayoutEffect(() => {
    uniforms.uTiempo.value = tiempo;
    uniforms.uTamano.value = tamano;
    uniforms.uOpacidad.value = opacidad;
    uniforms.uBrillo.value = brillo;
    uniforms.uEnfoque.value = enfoque;
    uniforms.uRangoEnfoque.value = rangoEnfoque;
    uniforms.uSubida.value = subida;
    uniforms.uCaja.value.set(caja[0], caja[1], caja[2]);
  });

  useEffect(() => () => geometria.dispose(), [geometria]);
  useEffect(() => () => material.dispose(), [material]);

  return (
    <mesh
      geometry={geometria}
      material={material}
      position={centro as unknown as THREE.Vector3Tuple}
      frustumCulled={false}
      renderOrder={2}
    />
  );
};
