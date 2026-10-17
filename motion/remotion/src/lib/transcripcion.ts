import React, {createContext, useContext, useMemo} from 'react';
import {staticFile, useVideoConfig} from 'remotion';
import {useJSON} from './datos';
import {segundosACuadro, ultimoIndiceHasta, useCuadroAbsoluto} from './tiempo';

/**
 * Transcripción palabra por palabra de la voz en off.
 *
 * Formato de entrada (cualquiera de estos):
 *   [{"word": "Hola", "start": 0.52, "end": 0.81}, ...]
 *   {"words": [...]}                         (whisper / whisper-timestamped)
 *   {"segments": [{"words": [...]}, ...]}    (WhisperX, faster-whisper)
 * También acepta "text" en lugar de "word" y "inicio"/"fin" en lugar de "start"/"end".
 * Tiempos en segundos, absolutos respecto del comienzo de la voz (= del video).
 */
export type Palabra = {
  readonly word: string;
  readonly start: number;
  readonly end: number;
};

export type PalabraIndexada = Palabra & {
  /** Índice global en la transcripción. */
  readonly i: number;
  /** Forma normalizada para buscar: minúsculas, sin tildes ni puntuación. */
  readonly norma: string;
};

export type Frase = {
  readonly i: number;
  readonly texto: string;
  readonly start: number;
  readonly end: number;
  readonly palabras: readonly PalabraIndexada[];
};

export type Transcripcion = {
  readonly palabras: readonly PalabraIndexada[];
  readonly frases: readonly Frase[];
  readonly duracion: number;
};

export type OpcionesFrases = {
  /** Silencio (s) que corta una frase. */
  readonly pausa?: number;
  /** Máximo de palabras por frase. */
  readonly maxPalabras?: number;
  /** Máxima duración (s) de una frase. */
  readonly maxDuracion?: number;
};

/** minúsculas, sin tildes, sin signos: "¿Cerebro?" → "cerebro". La ñ se conserva. */
export const normalizar = (s: string): string =>
  s
    .toLowerCase()
    .replace(/ñ/g, '\u0000')
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .replace(/\u0000/g, 'ñ')
    .replace(/[^\p{L}\p{N}\s'-]/gu, '')
    .trim();

type Crudo = Record<string, unknown>;

const aPalabra = (w: Crudo): Palabra | null => {
  const word = String(w.word ?? w.text ?? w.palabra ?? '').trim();
  const start = Number(w.start ?? w.inicio);
  const end = Number(w.end ?? w.fin);
  if (!word || !Number.isFinite(start) || !Number.isFinite(end)) return null;
  return {word, start, end: Math.max(end, start)};
};

/** Acepta los formatos habituales y devuelve palabras ordenadas y sin huecos inválidos. */
export const normalizarTranscripcion = (crudo: unknown): Palabra[] => {
  let lista: unknown[] = [];
  if (Array.isArray(crudo)) lista = crudo;
  else if (crudo && typeof crudo === 'object') {
    const o = crudo as Crudo;
    if (Array.isArray(o.words)) lista = o.words;
    else if (Array.isArray(o.palabras)) lista = o.palabras;
    else if (Array.isArray(o.segments)) {
      lista = (o.segments as Crudo[]).flatMap((s) =>
        Array.isArray(s.words) ? s.words : [],
      );
    }
  }
  const palabras = lista
    .map((w) => (w && typeof w === 'object' ? aPalabra(w as Crudo) : null))
    .filter((w): w is Palabra => w !== null)
    .sort((a, b) => a.start - b.start);
  if (palabras.length === 0) {
    throw new Error('La transcripción no tiene palabras con word/start/end.');
  }
  return palabras;
};

const FIN_DE_FRASE = /[.?!…;:]["»”)]*$/;
const COMA = /[,—–]["»”)]*$/;

/**
 * Agrupa palabras en frases (para subtítulos o para animar por idea).
 * Corta en puntuación fuerte, en silencios largos y al pasar el máximo de palabras o de
 * duración (en ese caso intenta cortar en la última coma).
 */
export const agruparEnFrases = (
  palabras: readonly PalabraIndexada[],
  {pausa = 0.6, maxPalabras = 14, maxDuracion = 6}: OpcionesFrases = {},
): Frase[] => {
  const frases: Frase[] = [];
  let actual: PalabraIndexada[] = [];
  const cerrar = (hasta = actual.length) => {
    const tomadas = actual.slice(0, hasta);
    if (tomadas.length) {
      frases.push({
        i: frases.length,
        texto: tomadas.map((p) => p.word).join(' '),
        start: tomadas[0].start,
        end: tomadas[tomadas.length - 1].end,
        palabras: tomadas,
      });
    }
    actual = actual.slice(hasta);
  };
  palabras.forEach((p, k) => {
    const sig = palabras[k + 1];
    actual.push(p);
    const silencio = sig ? sig.start - p.end : Infinity;
    if (FIN_DE_FRASE.test(p.word) || silencio >= pausa) {
      cerrar();
      return;
    }
    const dur = p.end - actual[0].start;
    if (actual.length >= maxPalabras || dur >= maxDuracion) {
      let corte = -1;
      for (let j = actual.length - 1; j > 0; j--) {
        if (COMA.test(actual[j].word)) {
          corte = j + 1;
          break;
        }
      }
      cerrar(corte > 0 ? corte : actual.length);
    }
  });
  cerrar();
  return frases;
};

export const crearTranscripcion = (
  crudo: unknown,
  opciones?: OpcionesFrases,
): Transcripcion => {
  const palabras = normalizarTranscripcion(crudo).map((p, i) => ({
    ...p,
    i,
    norma: normalizar(p.word),
  }));
  return {
    palabras,
    frases: agruparEnFrases(palabras, opciones),
    duracion: palabras[palabras.length - 1].end,
  };
};

/** Carga la transcripción desde public/ (por defecto public/datos/transcripcion.json; null = ninguna). */
export const useTranscripcion = (
  src: string | null = staticFile('datos/transcripcion.json'),
  opciones?: OpcionesFrases,
): Transcripcion | null =>
  useJSON(src, (crudo) => crearTranscripcion(crudo, opciones));

const CtxTranscripcion = createContext<Transcripcion | null>(null);

/** La línea de tiempo maestra publica la transcripción de la hoja para todas las escenas. */
export const ProveedorTranscripcion: React.FC<{
  readonly transcripcion: Transcripcion | null;
  readonly children: React.ReactNode;
}> = ({transcripcion, children}) =>
  React.createElement(
    CtxTranscripcion.Provider,
    {value: transcripcion},
    children,
  );

/** Transcripción del video (la de la hoja de cues), o null si no hay. */
export const useTranscripcionDelVideo = (): Transcripcion | null =>
  useContext(CtxTranscripcion);

// ---------------------------------------------------------------------------
// Consultas puras (sirven fuera de React, p. ej. en calculateMetadata)
// ---------------------------------------------------------------------------

export type EstadoPalabra = {
  readonly palabra: PalabraIndexada;
  /** 0 → 1 dentro de la palabra (se queda en 1 durante el silencio que sigue). */
  readonly progreso: number;
  /** true mientras la palabra suena (start <= t < end). */
  readonly sonando: boolean;
};

/**
 * Palabra en el instante t. Con `mantener` (default) devuelve la última palabra dicha
 * también durante los silencios; sin `mantener`, null fuera de las palabras.
 * `adelanto` (s) adelanta la consulta: útil para que el texto aparezca un poco antes.
 */
export const palabraEn = (
  t: Transcripcion,
  segundos: number,
  {mantener = true, adelanto = 0}: {mantener?: boolean; adelanto?: number} = {},
): EstadoPalabra | null => {
  const x = segundos + adelanto;
  const k = ultimoIndiceHasta(t.palabras, x, (p) => p.start);
  if (k < 0) return null;
  const palabra = t.palabras[k];
  const sonando = x < palabra.end;
  if (!sonando && !mantener) return null;
  const dur = Math.max(palabra.end - palabra.start, 1e-6);
  return {palabra, sonando, progreso: Math.min(1, (x - palabra.start) / dur)};
};

export type EstadoFrase = {
  readonly frase: Frase;
  readonly progreso: number;
  /** Índice dentro de la frase de la palabra actual (-1 antes de la primera). */
  readonly palabraEnFrase: number;
  readonly sonando: boolean;
};

export const fraseEn = (
  t: Transcripcion,
  segundos: number,
  {mantener = true, adelanto = 0}: {mantener?: boolean; adelanto?: number} = {},
): EstadoFrase | null => {
  const x = segundos + adelanto;
  const k = ultimoIndiceHasta(t.frases, x, (f) => f.start);
  if (k < 0) return null;
  const frase = t.frases[k];
  const sonando = x < frase.end;
  if (!sonando && !mantener) return null;
  const palabraEnFrase = ultimoIndiceHasta(frase.palabras, x, (p) => p.start);
  const dur = Math.max(frase.end - frase.start, 1e-6);
  return {
    frase,
    sonando,
    palabraEnFrase,
    progreso: Math.min(1, (x - frase.start) / dur),
  };
};

export type Coincidencia = {
  /** Índice de la primera palabra de la coincidencia. */
  readonly i: number;
  readonly start: number;
  readonly end: number;
  readonly texto: string;
};

/**
 * Busca una palabra o expresión (sin importar tildes ni mayúsculas).
 * - "hongo" coincide con "Hongo," y "hongó".
 * - "cerebro entrópico" busca las dos palabras seguidas.
 * - Con `prefijo`, "neuro" coincide con "neuronas".
 * - Una RegExp se prueba contra cada palabra normalizada.
 */
export const buscarPalabras = (
  t: Transcripcion,
  consulta: string | RegExp,
  {prefijo = false}: {prefijo?: boolean} = {},
): Coincidencia[] => {
  const res: Coincidencia[] = [];
  if (consulta instanceof RegExp) {
    t.palabras.forEach((p) => {
      if (consulta.test(p.norma))
        res.push({i: p.i, start: p.start, end: p.end, texto: p.word});
    });
    return res;
  }
  const partes = normalizar(consulta).split(/\s+/).filter(Boolean);
  if (partes.length === 0) return res;
  const coincide = (norma: string, parte: string, ultima: boolean) =>
    prefijo && ultima ? norma.startsWith(parte) : norma === parte;
  for (let i = 0; i + partes.length <= t.palabras.length; i++) {
    let ok = true;
    for (let j = 0; j < partes.length; j++) {
      if (
        !coincide(t.palabras[i + j].norma, partes[j], j === partes.length - 1)
      ) {
        ok = false;
        break;
      }
    }
    if (ok) {
      const ultima = t.palabras[i + partes.length - 1];
      res.push({
        i,
        start: t.palabras[i].start,
        end: ultima.end,
        texto: t.palabras
          .slice(i, i + partes.length)
          .map((p) => p.word)
          .join(' '),
      });
    }
  }
  return res;
};

/**
 * Cuadro en el que se dice una palabra clave. Tira error si no existe: mejor fallar al
 * renderizar que animar en el momento equivocado.
 */
export const cuadroDePalabra = (
  t: Transcripcion,
  consulta: string | RegExp,
  fps: number,
  {
    ocurrencia = 0,
    borde = 'inicio',
    prefijo = false,
  }: {
    ocurrencia?: number;
    borde?: 'inicio' | 'fin';
    prefijo?: boolean;
  } = {},
): number => {
  const todas = buscarPalabras(t, consulta, {prefijo});
  const c = todas[ocurrencia < 0 ? todas.length + ocurrencia : ocurrencia];
  if (!c) {
    throw new Error(
      `"${String(consulta)}" no aparece en la transcripción (ocurrencia ${ocurrencia}, hay ${todas.length}).`,
    );
  }
  return segundosACuadro(borde === 'inicio' ? c.start : c.end, fps);
};

// ---------------------------------------------------------------------------
// Hooks (usan el tiempo ABSOLUTO: ver ProveedorTiempoAbsoluto en tiempo.ts)
// ---------------------------------------------------------------------------

export const usePalabraActual = (
  t: Transcripcion | null,
  opciones?: {mantener?: boolean; adelanto?: number},
): EstadoPalabra | null => {
  const {fps} = useVideoConfig();
  const cuadro = useCuadroAbsoluto();
  if (!t) return null;
  return palabraEn(t, cuadro / fps, opciones);
};

export const useFraseActual = (
  t: Transcripcion | null,
  opciones?: {mantener?: boolean; adelanto?: number},
): EstadoFrase | null => {
  const {fps} = useVideoConfig();
  const cuadro = useCuadroAbsoluto();
  if (!t) return null;
  return fraseEn(t, cuadro / fps, opciones);
};

/** Cuadros (absolutos) de todas las apariciones de una palabra clave. Memorizado. */
export const useCuadrosDePalabra = (
  t: Transcripcion | null,
  consulta: string,
  opciones?: {prefijo?: boolean},
): number[] => {
  const {fps} = useVideoConfig();
  const prefijo = opciones?.prefijo ?? false;
  return useMemo(
    () =>
      t
        ? buscarPalabras(t, consulta, {prefijo}).map((c) =>
            segundosACuadro(c.start, fps),
          )
        : [],
    [t, consulta, prefijo, fps],
  );
};
