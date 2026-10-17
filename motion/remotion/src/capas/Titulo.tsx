import React from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {FUENTES} from '../lib/fuentes';
import {D, duracionSalida, escalonado, progreso} from '../lib/movimiento';

/**
 * Titular con revelado por palabra (máscara + subida), estilo APPLE-MOTION.md:
 * entrada appleOut 0,8 s, escalonado total ≤ 0,5 s, salida appleIn al 65 %.
 * Tiempos en segundos LOCALES de la Sequence que lo contiene.
 * Texto en pantalla mínimo (skill motion-copy): ≤ 5 palabras.
 */
export const Titulo: React.FC<{
  readonly texto: string;
  readonly entra: number;
  readonly sale: number;
  readonly tamano?: number;
  readonly color?: string;
  readonly peso?: number;
  readonly style?: React.CSSProperties;
}> = ({
  texto,
  entra,
  sale,
  tamano = 128,
  color = '#f3eadb',
  peso = 800,
  style,
}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const palabras = texto.split(/\s+/).filter(Boolean);
  const salida = progreso(frame, fps, {
    inicio: sale,
    duracion: duracionSalida(D.revelado),
    curva: 'appleIn',
  });
  return (
    <div
      style={{
        fontFamily: FUENTES.titular,
        fontWeight: peso,
        fontSize: tamano,
        lineHeight: 1.12,
        letterSpacing: '-0.03em',
        color,
        display: 'flex',
        flexWrap: 'wrap',
        gap: `0 ${tamano * 0.24}px`,
        opacity: 1 - salida,
        translate: `0 ${-salida * tamano * 0.25}px`,
        ...style,
      }}
    >
      {palabras.map((p, i) => {
        const e = progreso(frame, fps, {
          inicio: entra + escalonado(i, palabras.length),
          duracion: D.revelado,
          curva: 'appleOut',
        });
        return (
          // Máscara con padding vertical: no corta tildes ni descendentes.
          <span
            key={i}
            style={{
              display: 'inline-block',
              overflow: 'hidden',
              padding: '0.08em 0 0.12em',
            }}
          >
            <span
              style={{
                display: 'inline-block',
                translate: `0 ${(1 - e) * 110}%`,
                opacity: 0.1 + 0.9 * e,
              }}
            >
              {p}
            </span>
          </span>
        );
      })}
    </div>
  );
};
