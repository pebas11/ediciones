import React, {useEffect, useLayoutEffect, useMemo} from 'react';
import {crearMaterialCielo} from './materiales';

/** Domo de fondo con shader propio (degradé vertical + nubosidad muy suave). */
export const Cielo: React.FC<{
  readonly tiempo: number;
  readonly arriba?: string;
  readonly horizonte?: string;
}> = ({tiempo, arriba = '#2b2620', horizonte = '#5a4d3e'}) => {
  const {material, uniforms} = useMemo(
    () => crearMaterialCielo({arriba, horizonte}),
    [arriba, horizonte],
  );
  useLayoutEffect(() => {
    uniforms.uTiempo.value = tiempo;
  });
  useEffect(() => () => material.dispose(), [material]);
  return (
    <mesh material={material} renderOrder={-1} frustumCulled={false}>
      <sphereGeometry args={[90, 32, 16]} />
    </mesh>
  );
};
