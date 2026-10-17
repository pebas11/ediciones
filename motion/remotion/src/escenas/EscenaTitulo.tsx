import React from 'react';
import {AbsoluteFill, Sequence} from 'remotion';
import {Grano} from '../capas/Grano';
import {Titulo} from '../capas/Titulo';
import {Vineta} from '../capas/Vineta';
import type {PropsEscena} from '../composiciones/LineaDeTiempo';
import {useEscena} from '../composiciones/LineaDeTiempo';

/**
 * Escena de ejemplo "titulo": un titular (≤ 5 palabras, skill motion-copy).
 * params: { texto: string, tamano?: number, fondo?: string }
 * El titular entra 0,3 s después del inicio nominal y sale 0,9 s antes del final.
 */
export const EscenaTitulo: React.FC<PropsEscena> = ({params, segmento}) => {
  const escena = useEscena();
  const texto = typeof params.texto === 'string' ? params.texto : 'Título';
  const tamano = typeof params.tamano === 'number' ? params.tamano : 150;
  const fondo = typeof params.fondo === 'string' ? params.fondo : '#2a231c';
  const dur = escena?.duracion ?? 3;
  // La Sequence empieza en el inicio nominal: dentro, useCurrentFrame() = 0 en el corte.
  const desfase = segmento.inicioCuadro - segmento.desdeCuadro;
  return (
    <AbsoluteFill style={{backgroundColor: fondo}}>
      <Sequence from={desfase} layout="none">
        <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center'}}>
          <Titulo texto={texto} entra={0.3} sale={Math.max(0.8, dur - 0.9)} tamano={tamano} />
        </AbsoluteFill>
      </Sequence>
      <Vineta intensidad={0.5} />
      <Grano intensidad={0.12} />
    </AbsoluteFill>
  );
};
