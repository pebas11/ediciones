import {z} from 'zod';
import {segundosACuadro} from './tiempo';

/**
 * HOJA DE CUES: toda la estructura del video definida con datos (JSON en public/datos).
 *
 * {
 *   "version": 1,
 *   "titulo": "...",
 *   "duracion": 612.4,                     // opcional: si falta, termina con la última escena
 *   "fondo": "#0e0c0a",                    // color entre escenas / huecos
 *   "transcripcion": "datos/transcripcion.json",
 *   "envolventes": "datos/envolventes.json",
 *   "audio": [ {"id": "voz", "src": "audio/voz.wav", "inicio": 0, "volumen": 1},
 *              {"id": "pad", "src": "audio/pad.wav", "volumen": 0.6,
 *               "ducking": {"fuente": "voz", "reduccion": 0.5}, "fundidoSalida": 2} ],
 *   "escenas": [
 *     {"id": "intro", "tipo": "mundo3d", "inicio": 0, "fin": 14.2, "params": {...}},
 *     {"id": "idea1", "tipo": "trazos", "inicio": 14.2, "fin": 31.0,
 *      "transicion": {"tipo": "difuso", "duracion": 1.2}, "params": {...}}
 *   ]
 * }
 *
 * Tiempos en segundos ABSOLUTOS de la voz en off. `transicion` es la entrada desde la
 * escena anterior y queda CENTRADA en el corte: con 1,2 s empieza 0,6 s antes de
 * `inicio` y termina 0,6 s después. Así las escenas siguen alineadas con la voz aunque
 * haya transiciones (TransitionSeries solapa escenas y acortaría el total).
 * Huecos entre escenas (o antes de la primera) se rellenan con el color de fondo.
 */

export const TIPOS_TRANSICION = [
  'corte',
  'fundido',
  'difuso',
  'barrido',
  'deslizar',
  'zoomOnirico',
  'disolucion',
  'desenfoque',
] as const;

export const esquemaTransicion = z.object({
  tipo: z.enum(TIPOS_TRANSICION).default('fundido'),
  duracion: z.number().min(0).default(1),
  direccion: z.enum(['izquierda', 'derecha', 'arriba', 'abajo']).optional(),
});

export const esquemaEscena = z
  .object({
    id: z.string().min(1),
    tipo: z.string().min(1),
    inicio: z.number().min(0),
    fin: z.number(),
    params: z.record(z.string(), z.unknown()).default({}),
    transicion: esquemaTransicion.optional(),
    nota: z.string().optional(),
  })
  .refine((e) => e.fin > e.inicio, {message: '"fin" tiene que ser mayor que "inicio"'});

export const esquemaPista = z.object({
  id: z.string().min(1),
  src: z.string().min(1),
  inicio: z.number().default(0),
  /** Segundos (absolutos) en que termina la pista; por defecto, al final del video. */
  fin: z.number().optional(),
  volumen: z.number().min(0).default(1),
  fundidoEntrada: z.number().min(0).default(0),
  fundidoSalida: z.number().min(0).default(0),
  ducking: z
    .object({
      fuente: z.string().default('voz'),
      reduccion: z.number().min(0).max(1).default(0.5),
    })
    .optional(),
});

export const esquemaHoja = z.object({
  version: z.literal(1).default(1),
  titulo: z.string().optional(),
  fps: z.number().positive().default(60),
  duracion: z.number().positive().optional(),
  fondo: z.string().default('#000000'),
  transcripcion: z.string().optional(),
  envolventes: z.string().optional(),
  audio: z.array(esquemaPista).default([]),
  escenas: z.array(esquemaEscena).min(1),
});

export type HojaDeCues = z.infer<typeof esquemaHoja>;
export type EscenaCue = z.infer<typeof esquemaEscena>;
export type TransicionCue = z.infer<typeof esquemaTransicion>;
export type PistaCue = z.infer<typeof esquemaPista>;

/** Valida y completa defaults. Los errores dicen qué escena está mal. */
export const validarHoja = (crudo: unknown): HojaDeCues => {
  const r = esquemaHoja.safeParse(crudo);
  if (!r.success) {
    const detalle = r.error.issues
      .map((i) => `  - ${i.path.join('.') || '(raíz)'}: ${i.message}`)
      .join('\n');
    throw new Error(`Hoja de cues inválida:\n${detalle}`);
  }
  return r.data;
};

export type SegmentoEscena = {
  readonly clase: 'escena';
  readonly id: string;
  readonly tipo: string;
  readonly params: Record<string, unknown>;
  /** Es relleno (hueco entre escenas). */
  readonly hueco: boolean;
  /** Inicio y fin nominales (absolutos, en cuadros): los de la hoja. */
  readonly inicioCuadro: number;
  readonly finCuadro: number;
  /** Cuadro absoluto en que arranca la Sequence (incluye la mitad de la transición de entrada). */
  readonly desdeCuadro: number;
  /** Duración de la Sequence (incluye las mitades de las transiciones). */
  readonly duracion: number;
};

export type SegmentoTransicion = {
  readonly clase: 'transicion';
  readonly tipo: Exclude<TransicionCue['tipo'], 'corte'>;
  readonly duracion: number;
  readonly direccion?: TransicionCue['direccion'];
};

export type LineaResuelta = {
  readonly fps: number;
  readonly duracion: number;
  readonly items: ReadonlyArray<SegmentoEscena | SegmentoTransicion>;
  readonly escenas: readonly SegmentoEscena[];
  readonly avisos: readonly string[];
};

/**
 * Pasa la hoja a cuadros y arma la lista para <TransitionSeries>.
 * Garantiza: la duración total = duración de la hoja, y cada escena arranca su contenido
 * nominal en `inicioCuadro` (el corte cae donde dice la hoja).
 */
export const resolverLinea = (hoja: HojaDeCues, fps: number): LineaResuelta => {
  const avisos: string[] = [];
  const escenas = [...hoja.escenas].sort((a, b) => a.inicio - b.inicio);

  // 1) Segmentos nominales, con huecos explícitos.
  type Nominal = {
    id: string;
    tipo: string;
    params: Record<string, unknown>;
    hueco: boolean;
    b: number;
    e: number;
    trans?: TransicionCue;
  };
  const segs: Nominal[] = [];
  let cursor = 0;
  escenas.forEach((s, k) => {
    const b = segundosACuadro(s.inicio, fps);
    const e = segundosACuadro(s.fin, fps);
    if (e <= b) throw new Error(`La escena "${s.id}" dura menos de un cuadro.`);
    if (b < cursor) {
      const ant = escenas[k - 1];
      throw new Error(
        `La escena "${s.id}" (inicio ${s.inicio}s) se superpone con "${ant?.id}" (fin ${ant?.fin}s).`,
      );
    }
    if (b > cursor) {
      segs.push({id: `hueco-${segs.length}`, tipo: 'hueco', params: {}, hueco: true, b: cursor, e: b});
    }
    segs.push({id: s.id, tipo: s.tipo, params: s.params, hueco: false, b, e, trans: s.transicion});
    cursor = e;
  });
  const total = Math.max(cursor, hoja.duracion ? segundosACuadro(hoja.duracion, fps) : 0);
  if (total > cursor) {
    segs.push({id: `hueco-${segs.length}`, tipo: 'hueco', params: {}, hueco: true, b: cursor, e: total});
  }

  // 2) Duraciones de transición (en cuadros), recortadas si no entran.
  const trans: number[] = segs.map((s, k) => {
    if (k === 0 || !s.trans || s.trans.tipo === 'corte') return 0;
    return Math.max(0, segundosACuadro(s.trans.duracion, fps));
  });
  for (let k = 1; k < segs.length; k++) {
    if (!trans[k]) continue;
    const largoAnt = segs[k - 1].e - segs[k - 1].b;
    const largo = segs[k].e - segs[k].b;
    // La mitad de la transición tiene que caber en cada lado, sin pisar la otra transición.
    const maxAnt = (largoAnt - Math.ceil((trans[k - 1] ?? 0) / 2)) * 2;
    const maxSig = (largo - Math.floor((trans[k + 1] ?? 0) / 2)) * 2;
    const max = Math.max(0, Math.min(maxAnt, maxSig));
    if (trans[k] > max) {
      avisos.push(`Transición hacia "${segs[k].id}" recortada de ${trans[k]} a ${max} cuadros.`);
      trans[k] = max;
    }
  }

  // 3) Sequences extendidas: la transición k queda centrada en el corte b_k.
  const items: Array<SegmentoEscena | SegmentoTransicion> = [];
  const resueltas: SegmentoEscena[] = [];
  segs.forEach((s, k) => {
    const antes = Math.floor((trans[k] ?? 0) / 2); // se adelanta el inicio
    const despues = (trans[k + 1] ?? 0) - Math.floor((trans[k + 1] ?? 0) / 2); // se estira el final
    if (k > 0 && trans[k] > 0) {
      const t = s.trans as TransicionCue;
      items.push({
        clase: 'transicion',
        tipo: t.tipo as SegmentoTransicion['tipo'],
        duracion: trans[k],
        direccion: t.direccion,
      });
    }
    const esc: SegmentoEscena = {
      clase: 'escena',
      id: s.id,
      tipo: s.tipo,
      params: s.params,
      hueco: s.hueco,
      inicioCuadro: s.b,
      finCuadro: s.e,
      desdeCuadro: s.b - antes,
      duracion: s.e - s.b + antes + despues,
    };
    items.push(esc);
    resueltas.push(esc);
  });

  return {fps, duracion: total, items, escenas: resueltas, avisos};
};

/** Escena activa (nominal) en un cuadro absoluto. */
export const escenaEn = (linea: LineaResuelta, cuadro: number): SegmentoEscena | null =>
  linea.escenas.find((s) => cuadro >= s.inicioCuadro && cuadro < s.finCuadro) ?? null;
