import type {
  TransitionPresentation,
  TransitionPresentationComponentProps,
} from '@remotion/transitions';
import {dissolve} from '@remotion/transitions/dissolve';
import {dreamyZoom} from '@remotion/transitions/dreamy-zoom';
import {fade} from '@remotion/transitions/fade';
import {linearBlur} from '@remotion/transitions/linear-blur';
import {slide} from '@remotion/transitions/slide';
import {wipe} from '@remotion/transitions/wipe';
import React from 'react';
import {AbsoluteFill} from 'remotion';
import type {SegmentoTransicion} from './cues';

/**
 * "difuso": fundido cruzado con desenfoque y un leve cambio de escala, en CSS puro.
 * Sale la escena vieja desenfocándose mientras la nueva se enfoca encima.
 * Funciona en cualquier navegador y con canvas WebGL adentro.
 */
type PropsDifuso = {desenfoque: number; escala: number};

const Difuso: React.FC<TransitionPresentationComponentProps<PropsDifuso>> = ({
  children,
  presentationDirection,
  presentationProgress: p,
  passedProps,
}) => {
  const entrando = presentationDirection === 'entering';
  const blur = (entrando ? 1 - p : p) * passedProps.desenfoque;
  const escala = entrando ? 1 + (1 - p) * passedProps.escala : 1 + p * passedProps.escala * 0.5;
  return (
    <AbsoluteFill
      style={{
        opacity: entrando ? p : 1,
        filter: blur > 0.1 ? `blur(${blur.toFixed(2)}px)` : undefined,
        scale: escala,
      }}
    >
      {children}
    </AbsoluteFill>
  );
};

export const difuso = (props: Partial<PropsDifuso> = {}): TransitionPresentation<PropsDifuso> => ({
  component: Difuso,
  props: {desenfoque: 18, escala: 0.035, ...props},
});

const DIRECCION = {
  izquierda: 'from-right',
  derecha: 'from-left',
  arriba: 'from-bottom',
  abajo: 'from-top',
} as const;

/**
 * Tipo de la hoja de cues → presentación de @remotion/transitions.
 * zoomOnirico / disolucion / desenfoque usan shaders "HTML-in-canvas" de Remotion
 * (capturan las dos escenas como texturas). Ver README: probados en el contenedor.
 */
export const presentacion = (
  t: Pick<SegmentoTransicion, 'tipo' | 'direccion'>,
): TransitionPresentation<Record<string, unknown>> => {
  const p = (() => {
    switch (t.tipo) {
      case 'fundido':
        return fade();
      case 'difuso':
        return difuso();
      case 'barrido':
        return wipe({direction: DIRECCION[t.direccion ?? 'izquierda']});
      case 'deslizar':
        return slide({direction: DIRECCION[t.direccion ?? 'izquierda']});
      case 'zoomOnirico':
        return dreamyZoom({rotation: 4, scale: 1.15});
      case 'disolucion':
        return dissolve({});
      case 'desenfoque':
        return linearBlur({intensity: 0.08});
      default:
        return fade();
    }
  })();
  return p as unknown as TransitionPresentation<Record<string, unknown>>;
};
