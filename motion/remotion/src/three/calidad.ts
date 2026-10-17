import React, {createContext, useContext} from 'react';

/**
 * Presets de calidad del 3D. "final" para el render de entrega, "borrador" para
 * previsualizar rápido (Studio sin GPU, hojas de contacto, pruebas de timing).
 * Se elige por prop de la composición: --props='{"calidad":"borrador"}'.
 */
export type Calidad = 'final' | 'borrador';

export type AjustesCalidad = {
  /** Muestras MSAA del EffectComposer (SwiftShader admite hasta 4). */
  readonly msaa: number;
  /** Lado del shadow map en píxeles. */
  readonly sombra: number;
  /** Profundidad de campo en postproceso. */
  readonly dof: boolean;
  /** Postproceso completo (si es false, render directo con tone mapping del renderer). */
  readonly postproceso: boolean;
  /** Factor sobre la cantidad de partículas pedida. */
  readonly particulas: number;
  /** Resolución interna del canvas 3D (1 = 1920×1080). */
  readonly dpr: number;
  /** Factor de subdivisión de las mallas procedurales. */
  readonly detalle: number;
  /** Grano + viñeta dentro del postproceso (WebGL). */
  readonly grano: boolean;
  /** Resolución del desenfoque del DOF. */
  readonly dofEscala: number;
  /** Buffers de postproceso de 8 bits (más rápido; recorta luces > 1). */
  readonly bufer8: boolean;
};

export const CALIDAD: Record<Calidad, AjustesCalidad> = {
  final: {
    msaa: 4,
    sombra: 2048,
    dof: true,
    postproceso: true,
    particulas: 1,
    dpr: 1,
    detalle: 1,
    grano: true,
    dofEscala: 0.5,
    bufer8: false,
  },
  borrador: {
    msaa: 0,
    sombra: 1024,
    dof: false,
    postproceso: false,
    particulas: 0.25,
    dpr: 0.5,
    detalle: 0.4,
    grano: false,
    dofEscala: 0.5,
    bufer8: true,
  },
};

const CtxCalidad = createContext<Calidad>('final');

/** Publica la calidad elegida para todas las escenas de abajo. */
export const ProveedorCalidad: React.FC<{
  readonly calidad: Calidad;
  readonly children: React.ReactNode;
}> = ({calidad, children}) =>
  React.createElement(CtxCalidad.Provider, {value: calidad}, children);

export const useCalidad = (): AjustesCalidad => CALIDAD[useContext(CtxCalidad)];
