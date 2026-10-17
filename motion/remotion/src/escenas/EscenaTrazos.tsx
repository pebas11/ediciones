import React, {useMemo} from 'react';
import {AbsoluteFill, useVideoConfig} from 'remotion';
import {Grano} from '../capas/Grano';
import {pathSuave, Trazo} from '../capas/Trazo';
import type {PropsEscena} from '../composiciones/LineaDeTiempo';
import {useEscena} from '../composiciones/LineaDeTiempo';
import {usePulso} from '../lib/audio';
import {crearAzar, entre} from '../lib/azar';
import {fbm, progreso} from '../lib/movimiento';

/**
 * Escena de ejemplo "trazos" (2D puro): líneas orgánicas que se dibujan escalonadas.
 * params: { cantidad?: number, color?: string, fondo?: string, semilla?: string }
 */
export const EscenaTrazos: React.FC<PropsEscena> = ({params}) => {
  const {width, height, fps} = useVideoConfig();
  const escena = useEscena();
  const golpe = usePulso('downbeats', {caida: 20});
  const cantidad = typeof params.cantidad === 'number' ? params.cantidad : 9;
  const color = typeof params.color === 'string' ? params.color : '#e8d2ab';
  const fondo = typeof params.fondo === 'string' ? params.fondo : '#1d1914';
  const semilla = typeof params.semilla === 'string' ? params.semilla : 'trazos';

  const caminos = useMemo(() => {
    const azar = crearAzar(semilla);
    return Array.from({length: cantidad}, (_, k) => {
      const y0 = entre(azar, 0.2, 0.8) * height;
      const pts: Array<[number, number]> = [];
      for (let i = 0; i <= 16; i++) {
        const x = -60 + (i / 16) * (width + 120);
        pts.push([x, y0 + fbm(semilla, i * 0.3, {frecuencia: 0.9, octavas: 3, canal: k}) * 160]);
      }
      return pathSuave(pts);
    });
  }, [cantidad, semilla, width, height]);

  // Tiempo relativo al inicio nominal de la escena (negativo durante la transición).
  const frameLocal = Math.round((escena?.t ?? 0) * fps);
  return (
    <AbsoluteFill style={{backgroundColor: fondo}}>
      <svg width={width} height={height}>
        {caminos.map((d, k) => (
          <Trazo
            key={k}
            d={d}
            progreso={progreso(frameLocal, fps, {inicio: k * 0.06, duracion: 1.6, curva: 'apple'})}
            color={color}
            grosor={1.5 + (k % 3) + golpe * 1.5}
            opacidad={0.35 + (k % 4) * 0.15}
          />
        ))}
      </svg>
      <Grano intensidad={0.12} />
    </AbsoluteFill>
  );
};
