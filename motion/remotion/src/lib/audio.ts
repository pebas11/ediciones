import React, {createContext, useContext} from 'react';
import {staticFile, useVideoConfig} from 'remotion';
import {useJSON} from './datos';
import {ultimoIndiceHasta, useCuadroAbsoluto} from './tiempo';

/**
 * Reacción al audio SIN FFT en tiempo de render.
 *
 * `scripts/envolventes.py` precalcula por cuadro (a los fps del video):
 *   - el nivel (RMS en dB, normalizado 0..1) de la voz y de cada stem,
 *   - bandas opcionales (graves / medios / agudos),
 *   - onsets (ataques) por pista,
 *   - beats y downbeats de la música (desde cues.json con bpm y downbeats),
 * y lo guarda en un JSON compacto. Acá se lee y se consulta en O(1) por cuadro.
 *
 * Todas las consultas usan cuadros ABSOLUTOS (ver tiempo.ts).
 */

export type PistaEnvolvente = {
  /** Nivel 0..1 por cuadro (dB mapeados linealmente desde rangoDb[0] a rangoDb[1]). */
  readonly nivel: Float32Array;
  readonly rangoDb: readonly [number, number];
  /** Cuadros con ataques detectados, ordenados. */
  readonly onsets: readonly number[];
  /** Fuerza 0..1 de cada onset. */
  readonly fuerzaOnsets: readonly number[];
  /** Bandas opcionales (0..1 por cuadro), p. ej. graves, medios, agudos. */
  readonly bandas: Readonly<Record<string, Float32Array>>;
};

export type DatosMusica = {
  readonly bpm: number;
  readonly compas: number;
  /** Cuadros de cada pulso. */
  readonly beats: readonly number[];
  /** Cuadros de cada primer tiempo de compás. */
  readonly downbeats: readonly number[];
};

export type Envolventes = {
  readonly fps: number;
  readonly cuadros: number;
  readonly pistas: Readonly<Record<string, PistaEnvolvente>>;
  readonly musica: DatosMusica | null;
};

const decodificarU8 = (b64: string): Float32Array => {
  const bin = atob(b64);
  const out = new Float32Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i) / 255;
  return out;
};

const aSerie = (v: unknown): Float32Array => {
  if (typeof v === 'string') return decodificarU8(v);
  if (Array.isArray(v)) return Float32Array.from(v as number[]);
  return new Float32Array(0);
};

type Crudo = Record<string, unknown>;

export const crearEnvolventes = (crudo: unknown): Envolventes => {
  const o = crudo as Crudo;
  if (!o || typeof o !== 'object' || !o.pistas) {
    throw new Error('El JSON de envolventes no tiene "pistas". ¿Lo generó scripts/envolventes.py?');
  }
  const pistas: Record<string, PistaEnvolvente> = {};
  for (const [nombre, p] of Object.entries(o.pistas as Record<string, Crudo>)) {
    const bandas: Record<string, Float32Array> = {};
    for (const [b, serie] of Object.entries((p.bandas as Crudo | undefined) ?? {})) {
      bandas[b] = aSerie(serie);
    }
    pistas[nombre] = {
      nivel: aSerie(p.nivel),
      rangoDb: (p.rangoDb as [number, number]) ?? [-48, 0],
      onsets: (p.onsets as number[]) ?? [],
      fuerzaOnsets: (p.fuerzaOnsets as number[]) ?? [],
      bandas,
    };
  }
  const m = o.musica as Crudo | null | undefined;
  return {
    fps: Number(o.fps),
    cuadros: Number(o.cuadros),
    pistas,
    musica: m
      ? {
          bpm: Number(m.bpm),
          compas: Number(m.compas ?? 4),
          beats: (m.beats as number[]) ?? [],
          downbeats: (m.downbeats as number[]) ?? [],
        }
      : null,
  };
};

/** Carga public/datos/envolventes.json (o la ruta indicada; null = sin envolventes). */
export const useEnvolventes = (src: string | null = staticFile('datos/envolventes.json')) =>
  useJSON(src, crearEnvolventes);

// ---------------------------------------------------------------------------
// Consultas puras
// ---------------------------------------------------------------------------

const serieDe = (env: Envolventes, pista: string, banda?: string): Float32Array => {
  const p = env.pistas[pista];
  if (!p) {
    throw new Error(`No hay envolvente para la pista "${pista}". Hay: ${Object.keys(env.pistas).join(', ')}`);
  }
  if (!banda) return p.nivel;
  const b = p.bandas[banda];
  if (!b) throw new Error(`La pista "${pista}" no tiene la banda "${banda}" (correr envolventes.py con --bandas).`);
  return b;
};

const muestra = (serie: Float32Array, cuadro: number): number => {
  if (serie.length === 0) return 0;
  const k = Math.min(serie.length - 1, Math.max(0, Math.round(cuadro)));
  return serie[k];
};

/** Nivel 0..1 en el cuadro (sin suavizar). */
export const nivel = (env: Envolventes, pista: string, cuadro: number, banda?: string): number =>
  muestra(serieDe(env, pista, banda), cuadro);

/** Promedio triangular de ±radio cuadros (no causal: mira también el futuro). */
export const nivelSuave = (
  env: Envolventes,
  pista: string,
  cuadro: number,
  radio = 4,
  banda?: string,
): number => {
  const s = serieDe(env, pista, banda);
  let suma = 0;
  let peso = 0;
  for (let d = -radio; d <= radio; d++) {
    const w = radio + 1 - Math.abs(d);
    suma += muestra(s, cuadro + d) * w;
    peso += w;
  }
  return suma / peso;
};

const cacheAR = new WeakMap<Float32Array, Map<string, Float32Array>>();

/**
 * Envolvente con ataque y relajación (segundos), como un compresor: sube rápido y baja
 * lento. Se calcula una sola vez por pista y parámetros (O(n)) y después es O(1).
 */
export const envolventeAR = (
  env: Envolventes,
  pista: string,
  {ataque = 0.03, relajacion = 0.35, banda}: {ataque?: number; relajacion?: number; banda?: string} = {},
): Float32Array => {
  const s = serieDe(env, pista, banda);
  let porSerie = cacheAR.get(s);
  if (!porSerie) {
    porSerie = new Map();
    cacheAR.set(s, porSerie);
  }
  const clave = `${ataque}|${relajacion}`;
  const hecho = porSerie.get(clave);
  if (hecho) return hecho;
  const a = Math.exp(-1 / Math.max(1e-3, ataque * env.fps));
  const r = Math.exp(-1 / Math.max(1e-3, relajacion * env.fps));
  const out = new Float32Array(s.length);
  let y = 0;
  for (let i = 0; i < s.length; i++) {
    const x = s[i];
    const c = x > y ? a : r;
    y = c * y + (1 - c) * x;
    out[i] = y;
  }
  porSerie.set(clave, out);
  return out;
};

export const nivelAR = (
  env: Envolventes,
  pista: string,
  cuadro: number,
  opciones?: {ataque?: number; relajacion?: number; banda?: string},
): number => muestra(envolventeAR(env, pista, opciones), cuadro);

export type UltimoEvento = {readonly indice: number; readonly cuadro: number; readonly desde: number};

/** Último evento (onset, beat, downbeat) en o antes del cuadro. */
export const ultimoEvento = (eventos: readonly number[], cuadro: number): UltimoEvento | null => {
  const k = ultimoIndiceHasta(eventos, cuadro, (e) => e);
  if (k < 0) return null;
  return {indice: k, cuadro: eventos[k], desde: cuadro - eventos[k]};
};

/**
 * Pulso que salta a 1 en cada evento y cae exponencialmente (caida = cuadros hasta ~37 %).
 * `anticipo` cuadros de subida previa, para que el golpe visual no llegue tarde.
 */
export const pulso = (
  eventos: readonly number[],
  cuadro: number,
  {caida = 12, anticipo = 0}: {caida?: number; anticipo?: number} = {},
): number => {
  const ev = ultimoEvento(eventos, cuadro);
  let v = ev ? Math.exp(-ev.desde / Math.max(caida, 1e-3)) : 0;
  if (anticipo > 0) {
    const k = ev ? ev.indice + 1 : 0;
    const prox = eventos[k];
    if (prox !== undefined && prox - cuadro <= anticipo) {
      v = Math.max(v, 1 - (prox - cuadro) / anticipo);
    }
  }
  return v;
};

/** Fase 0..1 entre el evento anterior y el siguiente (p. ej. avance dentro del compás). */
export const faseEntre = (
  eventos: readonly number[],
  cuadro: number,
): {readonly indice: number; readonly fase: number} => {
  const ev = ultimoEvento(eventos, cuadro);
  if (!ev) return {indice: -1, fase: 0};
  const prox = eventos[ev.indice + 1];
  if (prox === undefined) return {indice: ev.indice, fase: 0};
  return {indice: ev.indice, fase: (cuadro - ev.cuadro) / (prox - ev.cuadro)};
};

/**
 * Volumen con "ducking": baja la música cuando habla la voz. Devuelve la función para el
 * prop `volume` de <Audio>. Ese callback recibe cuadros RELATIVOS al inicio del <Audio>:
 * `desde` = cuadro absoluto en que empieza ese <Audio>.
 */
export const volumenConDucking = (
  env: Envolventes,
  {
    fuente = 'voz',
    base = 1,
    reduccion = 0.5,
    ataque = 0.06,
    relajacion = 0.5,
    desde = 0,
  }: {
    fuente?: string;
    base?: number;
    /** Fracción que se quita con voz a nivel 1 (0.5 = la mitad). */
    reduccion?: number;
    ataque?: number;
    relajacion?: number;
    desde?: number;
  } = {},
) => {
  const env2 = envolventeAR(env, fuente, {ataque, relajacion});
  return (f: number): number => base * (1 - reduccion * muestra(env2, f + desde));
};

// ---------------------------------------------------------------------------
// Contexto + hooks (cuadro absoluto implícito)
// ---------------------------------------------------------------------------

const CtxEnvolventes = createContext<Envolventes | null>(null);

export const ProveedorAudio: React.FC<{
  readonly envolventes: Envolventes | null;
  readonly children: React.ReactNode;
}> = ({envolventes, children}) =>
  React.createElement(CtxEnvolventes.Provider, {value: envolventes}, children);

export const useDatosAudio = (): Envolventes | null => useContext(CtxEnvolventes);

/** Nivel 0..1 de una pista en el cuadro actual; 0 si todavía no hay datos. */
export const useNivel = (
  pista: string,
  opciones?: {ataque?: number; relajacion?: number; banda?: string},
): number => {
  const env = useDatosAudio();
  const cuadro = useCuadroAbsoluto();
  if (!env) return 0;
  return opciones ? nivelAR(env, pista, cuadro, opciones) : nivel(env, pista, cuadro);
};

/** Pulso en los beats, downbeats o en los onsets de una pista. */
export const usePulso = (
  fuente: 'beats' | 'downbeats' | {onsets: string},
  opciones?: {caida?: number; anticipo?: number},
): number => {
  const env = useDatosAudio();
  const cuadro = useCuadroAbsoluto();
  if (!env) return 0;
  const eventos =
    typeof fuente === 'string'
      ? (env.musica?.[fuente] ?? [])
      : (env.pistas[fuente.onsets]?.onsets ?? []);
  return pulso(eventos, cuadro, opciones);
};

/** Avance 0..1 dentro del compás actual (requiere downbeats). */
export const useFaseCompas = (): number => {
  const env = useDatosAudio();
  const cuadro = useCuadroAbsoluto();
  if (!env?.musica) return 0;
  return faseEntre(env.musica.downbeats, cuadro).fase;
};

/** Cuadros por segundo de los datos de audio; valida que coincidan con el video. */
export const useValidarFpsAudio = (): void => {
  const env = useDatosAudio();
  const {fps} = useVideoConfig();
  if (env && env.fps !== fps) {
    throw new Error(`Las envolventes se calcularon a ${env.fps} fps y el video va a ${fps} fps. Regenerar con --fps ${fps}.`);
  }
};
