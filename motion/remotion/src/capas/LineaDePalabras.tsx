import React from 'react';
import {interpolate, useVideoConfig} from 'remotion';
import {FUENTES} from '../lib/fuentes';
import {useCuadroAbsoluto} from '../lib/tiempo';
import {fraseEn, type Transcripcion} from '../lib/transcripcion';

/**
 * Frase actual de la voz con la palabra dicha resaltada (prueba de los hooks de
 * transcripción; no es un diseño de subtítulos). Usa el tiempo ABSOLUTO.
 */
export const LineaDePalabras: React.FC<{
  readonly transcripcion: Transcripcion | null;
  readonly tamano?: number;
  readonly color?: string;
  readonly style?: React.CSSProperties;
}> = ({transcripcion, tamano = 46, color = '#f3eadb', style}) => {
  const {fps} = useVideoConfig();
  const cuadro = useCuadroAbsoluto();
  if (!transcripcion) return null;
  const t = cuadro / fps;
  const estado = fraseEn(transcripcion, t, {mantener: true});
  if (!estado) return null;
  const {frase} = estado;
  // Aparece 0,15 s antes de la frase y se va 0,4 s después de su última palabra.
  const visible = interpolate(
    t,
    [frase.start - 0.25, frase.start - 0.05, frase.end + 0.3, frase.end + 0.6],
    [0, 1, 1, 0],
    {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'},
  );
  if (visible <= 0) return null;
  return (
    <div
      style={{
        fontFamily: FUENTES.cuerpo,
        fontWeight: 500,
        fontSize: tamano,
        lineHeight: 1.25,
        color,
        opacity: visible,
        textAlign: 'center',
        textWrap: 'balance',
        ...style,
      }}
    >
      {frase.palabras.map((p, k) => {
        const dicha = t >= p.start;
        const brillo = interpolate(
          t,
          [p.start - 0.02, p.start + 0.12],
          [0.32, 1],
          {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          },
        );
        return (
          <span key={p.i} style={{opacity: dicha ? brillo : 0.32}}>
            {p.word}
            {k < frase.palabras.length - 1 ? ' ' : ''}
          </span>
        );
      })}
    </div>
  );
};
