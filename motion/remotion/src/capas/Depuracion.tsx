import React from 'react';
import {AbsoluteFill, useVideoConfig} from 'remotion';
import {useCuadroAbsoluto} from '../lib/tiempo';

/**
 * Overlays de verificación técnica (no van en el video final).
 *
 * <CodigoDeCuadro>: el número de cuadro absoluto en binario (20 bits = hasta 1.048.575
 * cuadros, 4,8 h a 60 fps) en una fila de celdas de 16×16 px, abajo a la izquierda.
 * `scripts/verificar-sync.py` lo lee del MP4 final y comprueba que no falte ni se
 * repita ningún cuadro (por ejemplo, en las uniones entre tramos).
 *
 * Formato de la fila (23 celdas): [blanco][20 bits, MSB primero][negro][marca sync].
 * La última celda es la <MarcaSync>: blanca solo en los cuadros con clic en el audio.
 */
export const CELDA = 16;
export const BITS = 20;

export const CodigoDeCuadro: React.FC<{
  readonly cuadrosSync?: readonly number[];
}> = ({cuadrosSync = []}) => {
  const {height} = useVideoConfig();
  const cuadro = useCuadroAbsoluto();
  const celdas: boolean[] = [true];
  for (let b = BITS - 1; b >= 0; b--) celdas.push(((cuadro >> b) & 1) === 1);
  celdas.push(false);
  celdas.push(cuadrosSync.includes(cuadro));
  return (
    <AbsoluteFill style={{pointerEvents: 'none'}}>
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: height - CELDA,
          display: 'flex',
          height: CELDA,
        }}
      >
        {celdas.map((on, i) => (
          <div
            key={i}
            style={{
              width: CELDA,
              height: CELDA,
              backgroundColor: on ? '#ffffff' : '#000000',
            }}
          />
        ))}
      </div>
    </AbsoluteFill>
  );
};
