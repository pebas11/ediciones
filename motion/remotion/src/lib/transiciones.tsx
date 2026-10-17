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
  const escala = entrando
    ? 1 + (1 - p) * passedProps.escala
    : 1 + p * passedProps.escala * 0.5;
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

export const difuso = (
  props: Partial<PropsDifuso> = {},
): TransitionPresentation<PropsDifuso> => ({
  component: Difuso,
  props: {desenfoque: 18, escala: 0.035, ...props},
});

/**
 * "zoomOnirico" en CSS (misma idea que DreamyZoom de gl-transitions): la escena vieja
 * se acerca, gira y se aclara hasta un destello en la mitad; la nueva sale del destello
 * acercada y girada al revés y se asienta. Funciona en cualquier navegador, con o sin GPU
 * (la versión con shader de Remotion no se aplica en Chrome headless sin GPU).
 */
type PropsZoom = {escala: number; giro: number; brillo: number};

const ZoomOnirico: React.FC<
  TransitionPresentationComponentProps<PropsZoom>
> = ({
  children,
  presentationDirection,
  presentationProgress: p,
  passedProps,
}) => {
  const entrando = presentationDirection === 'entering';
  const e = 1 - Math.abs(2 * p - 1); // 0 en los bordes, 1 en la mitad
  const opacidad = entrando ? Math.min(1, Math.max(0, (p - 0.45) * 10)) : 1;
  const escala = 1 + e * (passedProps.escala - 1);
  const giro = (entrando ? -1 : 1) * passedProps.giro * e;
  const brillo = 1 + e * (passedProps.brillo - 1);
  return (
    <AbsoluteFill
      style={{
        opacity: opacidad,
        scale: escala,
        rotate: `${giro.toFixed(3)}deg`,
        filter: brillo > 1.01 ? `brightness(${brillo.toFixed(3)})` : undefined,
      }}
    >
      {children}
    </AbsoluteFill>
  );
};

export const zoomOnirico = (
  props: Partial<PropsZoom> = {},
): TransitionPresentation<PropsZoom> => ({
  component: ZoomOnirico,
  props: {escala: 1.2, giro: 6, brillo: 2.2, ...props},
});

const DIRECCION = {
  izquierda: 'from-right',
  derecha: 'from-left',
  arriba: 'from-bottom',
  abajo: 'from-top',
} as const;

/**
 * Tipo de la hoja de cues → presentación.
 * - fundido, difuso, barrido, deslizar, zoomOnirico: CSS, verificados en el contenedor.
 * - zoomShader, disolucionShader, desenfoqueShader: shaders "HTML-in-canvas" de Remotion.
 *   EXPERIMENTALES: en Chrome headless sin GPU no se aplican (la escena nueva tapa a la
 *   vieja, como un corte, sin error). Verificar en la máquina de render antes de usarlos.
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
        return zoomOnirico();
      case 'zoomShader':
        return dreamyZoom({rotation: 4, scale: 1.15});
      case 'disolucionShader':
        return dissolve({});
      case 'desenfoqueShader':
        return linearBlur({intensity: 0.08});
      default:
        return fade();
    }
  })();
  return p as unknown as TransitionPresentation<Record<string, unknown>>;
};
