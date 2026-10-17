import React from 'react';
import {AbsoluteFill} from 'remotion';

/**
 * Viñeta radial. `radio`: dónde empieza a oscurecer (0 = centro, 1 = esquinas).
 * Va por encima del 3D y por debajo del texto, para no apagar la tipografía.
 */
export const Vineta: React.FC<{
  readonly intensidad?: number;
  readonly radio?: number;
  readonly color?: string;
}> = ({intensidad = 0.55, radio = 0.55, color = '0, 0, 0'}) => (
  <AbsoluteFill
    style={{
      pointerEvents: 'none',
      // Capa propia: Chrome la rasteriza una vez y la reutiliza (sin GPU, un degradé a
      // pantalla completa re-rasterizado en cada cuadro cuesta ~230 ms). Es seguro solo
      // porque la viñeta NUNCA cambia: en capas que se mueven, will-change hace que el
      // resultado dependa de los cuadros anteriores.
      willChange: 'transform',
      background: `radial-gradient(ellipse 75% 75% at 50% 50%, rgba(${color}, 0) ${radio * 100}%, rgba(${color}, ${intensidad}) 100%)`,
    }}
  />
);
