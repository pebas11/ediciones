import {noise2D, noise3D} from '@remotion/noise';
import {Easing, interpolate, spring, type SpringConfig} from 'remotion';

/**
 * Presets de movimiento independientes del estilo.
 * Curvas y duraciones: motion/docs/APPLE-MOTION.md (las mismas que usa lib/stage.js).
 * Todo es función pura del cuadro: sirve igual en el Studio, en un render completo y en
 * un render por tramos que arranca a mitad de camino.
 */

// ---------------------------------------------------------------------------
// Curvas (cubic-bezier)
// ---------------------------------------------------------------------------
export const CURVAS = {
  /** Curva de la casa: desplazamientos, cambios de estado, cámara. */
  apple: Easing.bezier(0.4, 0, 0.6, 1),
  /** Entradas y revelados: arranca rápido y frena largo. */
  appleOut: Easing.bezier(0, 0, 0.2, 1),
  /** Salidas: arranca lento y se va. */
  appleIn: Easing.bezier(0.4, 0, 1, 1),
  /** Seno ida y vuelta: movimientos lentos y continuos (respiración, flotación). */
  respiro: Easing.bezier(0.37, 0, 0.63, 1),
  /** Frenado muy largo (expo out): llegadas de cámara, fundidos largos. */
  llegada: Easing.bezier(0.16, 1, 0.3, 1),
  lineal: Easing.linear,
} as const;

export type NombreCurva = keyof typeof CURVAS;

// ---------------------------------------------------------------------------
// Duraciones (segundos)
// ---------------------------------------------------------------------------
export const D = {
  micro: 0.24,
  rapido: 0.4,
  base: 0.5,
  revelado: 0.8,
  escena: 1.0,
  /** Quietud mínima después de construir un beat. */
  sostener: 1.5,
  /** Tope del escalonado total de un grupo (se lee como un solo beat). */
  escalonadoMax: 0.5,
} as const;

/** Las salidas duran entre el 60 % y el 70 % de su entrada. */
export const duracionSalida = (entrada: number, factor = 0.65) => entrada * factor;

// ---------------------------------------------------------------------------
// Springs
// ---------------------------------------------------------------------------

/**
 * Spring definido como en SwiftUI (duración percibida + rebote) → config de Remotion.
 * stiffness = (2π/d)², damping = 4π(1−rebote)/d, masa 1 (WWDC23 «Animate with springs»).
 */
export const springSwiftUI = ({duracion = 0.5, rebote = 0}: {duracion?: number; rebote?: number}) =>
  ({
    mass: 1,
    stiffness: (2 * Math.PI / duracion) ** 2,
    damping: (4 * Math.PI * (1 - rebote)) / duracion,
    overshootClamping: false,
  }) satisfies Partial<SpringConfig>;

export const SPRINGS = {
  /** Default de SwiftUI: vivo, sin rebote. */
  vivo: springSwiftUI({duracion: 0.5, rebote: 0}),
  /** Rebote apenas perceptible: un número o ícono que "aterriza". */
  aterriza: springSwiftUI({duracion: 0.5, rebote: 0.15}),
  /** Revelado de titulares. */
  suave: springSwiftUI({duracion: 0.8, rebote: 0}),
  /** Movimientos grandes y de cámara. */
  lento: springSwiftUI({duracion: 1.2, rebote: 0}),
  /** Flotación onírica: muy lento, sin rebote. */
  onirico: springSwiftUI({duracion: 2.4, rebote: 0}),
} as const;

export type NombreSpring = keyof typeof SPRINGS;

/** spring() de Remotion con preset y arranque en segundos. */
export const resorte = (
  frame: number,
  fps: number,
  {
    inicio = 0,
    preset = 'vivo',
    desde = 0,
    hasta = 1,
  }: {inicio?: number; preset?: NombreSpring; desde?: number; hasta?: number} = {},
): number =>
  spring({
    frame: frame - Math.round(inicio * fps),
    fps,
    config: SPRINGS[preset],
    from: desde,
    to: hasta,
  });

// ---------------------------------------------------------------------------
// Progresos con curva
// ---------------------------------------------------------------------------

/** 0 → 1 entre `inicio` y `inicio + duracion` (segundos), con curva y sin salirse. */
export const progreso = (
  frame: number,
  fps: number,
  {inicio = 0, duracion = D.base, curva = 'apple'}: {inicio?: number; duracion?: number; curva?: NombreCurva} = {},
): number =>
  interpolate(frame, [inicio * fps, (inicio + Math.max(duracion, 1e-3)) * fps], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: CURVAS[curva],
  });

/**
 * Sube con `curvaEntrada`, se queda en 1 y baja con `curvaSalida`.
 * Por defecto la salida dura el 65 % de la entrada.
 */
export const entradaSalida = (
  frame: number,
  fps: number,
  {
    entra,
    sale,
    duracionEntrada = D.revelado,
    duracionSalida: dSalida = duracionSalida(duracionEntrada),
    curvaEntrada = 'appleOut',
    curvaSalida = 'appleIn',
  }: {
    entra: number;
    sale: number;
    duracionEntrada?: number;
    duracionSalida?: number;
    curvaEntrada?: NombreCurva;
    curvaSalida?: NombreCurva;
  },
): number =>
  progreso(frame, fps, {inicio: entra, duracion: duracionEntrada, curva: curvaEntrada}) *
  (1 - progreso(frame, fps, {inicio: sale, duracion: dSalida, curva: curvaSalida}));

/** Retardo (s) del elemento i de n para que el escalonado total no pase de `maximo`. */
export const escalonado = (i: number, n: number, {paso = 0.08, maximo = D.escalonadoMax} = {}) =>
  n <= 1 ? 0 : i * Math.min(paso, maximo / (n - 1));

// ---------------------------------------------------------------------------
// Ruido sembrado (deriva suave)
// ---------------------------------------------------------------------------
// Ojo: @remotion/noise guarda en caché solo 10 semillas. Para muchas variantes, usar una
// semilla fija y desplazar la coordenada (como hacen estas funciones), no una semilla
// distinta por elemento.

/** Ruido fractal 1D en [-1, 1] aprox. `t` en segundos. */
export const fbm = (
  semilla: string,
  t: number,
  {frecuencia = 0.2, octavas = 3, persistencia = 0.5, canal = 0}: {
    frecuencia?: number;
    octavas?: number;
    persistencia?: number;
    canal?: number;
  } = {},
): number => {
  let suma = 0;
  let amp = 1;
  let f = frecuencia;
  let norma = 0;
  for (let o = 0; o < octavas; o++) {
    suma += amp * noise2D(semilla, t * f, canal * 31.7 + o * 7.13);
    norma += amp;
    amp *= persistencia;
    f *= 2;
  }
  return suma / norma;
};

/** Deriva 2D [x, y] en unidades de `amplitud`. Determinista para (semilla, t). */
export const deriva2 = (
  semilla: string,
  t: number,
  {amplitud = 1, frecuencia = 0.15, octavas = 2}: {amplitud?: number; frecuencia?: number; octavas?: number} = {},
): [number, number] => [
  amplitud * fbm(semilla, t, {frecuencia, octavas, canal: 0}),
  amplitud * fbm(semilla, t, {frecuencia, octavas, canal: 1}),
];

/** Deriva 3D [x, y, z]; `amplitud` puede ser un número o un vector por eje. */
export const deriva3 = (
  semilla: string,
  t: number,
  {
    amplitud = 1,
    frecuencia = 0.12,
    octavas = 2,
  }: {amplitud?: number | readonly [number, number, number]; frecuencia?: number; octavas?: number} = {},
): [number, number, number] => {
  const a = typeof amplitud === 'number' ? [amplitud, amplitud, amplitud] : amplitud;
  return [
    a[0] * fbm(semilla, t, {frecuencia, octavas, canal: 0}),
    a[1] * fbm(semilla, t, {frecuencia, octavas, canal: 1}),
    a[2] * fbm(semilla, t, {frecuencia, octavas, canal: 2}),
  ];
};

/** Campo de ruido 3D en un punto (para desplazar elementos según su posición). */
export const campo = (semilla: string, x: number, y: number, t: number, escala = 1): number =>
  noise3D(semilla, x * escala, y * escala, t);
