import {Audio} from '@remotion/media';
import {linearTiming, TransitionSeries} from '@remotion/transitions';
import React, {createContext, useContext, useMemo} from 'react';
import {
  AbsoluteFill,
  getRemotionEnvironment,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
  type CalculateMetadataFunction,
} from 'remotion';
import {z} from 'zod';
import {
  ProveedorAudio,
  useEnvolventes,
  volumenConDucking,
  type Envolventes,
} from '../lib/audio';
import {cargarJSON} from '../lib/datos';
import {
  resolverLinea,
  validarHoja,
  type HojaDeCues,
  type PistaCue,
  type SegmentoEscena,
} from '../lib/cues';
import {presentacion} from '../lib/transiciones';
import {
  ProveedorTiempoAbsoluto,
  segundosACuadro,
  useCuadroAbsoluto,
} from '../lib/tiempo';
import {ProveedorTranscripcion, useTranscripcion} from '../lib/transcripcion';

/**
 * LÍNEA DE TIEMPO MAESTRA: arma el video completo desde una hoja de cues (JSON).
 * - Cada escena es un componente del registro (src/escenas/registro.tsx) según su "tipo".
 * - La duración de la composición sale de la hoja (calculateMetadata).
 * - Las pistas de audio de la hoja se mezclan acá (con ducking si hay envolventes).
 */

export type PropsEscena = {
  readonly params: Record<string, unknown>;
  readonly segmento: SegmentoEscena;
};

export type RegistroEscenas = Readonly<
  Record<string, React.ComponentType<PropsEscena>>
>;

// --- Contexto de escena: tiempo relativo al INICIO NOMINAL (el de la hoja) -----------
const CtxEscena = createContext<SegmentoEscena | null>(null);

/**
 * Datos de la escena actual. `t` = segundos desde el inicio nominal de la escena
 * (negativo durante la mitad previa de la transición de entrada); `progreso` = 0..1
 * a lo largo de su duración nominal. Fuera de una línea de tiempo (escena suelta en el
 * Studio) usa el cuadro local y la duración de la composición; `segmento` es null.
 */
export const useEscena = () => {
  const seg = useContext(CtxEscena);
  const {fps, durationInFrames} = useVideoConfig();
  const abs = useCuadroAbsoluto();
  const propio = useCurrentFrame();
  if (!seg) {
    // Escena suelta (composición propia en el Studio): su cuadro local y su duración.
    return {
      segmento: null,
      cuadro: propio,
      t: propio / fps,
      duracion: durationInFrames / fps,
      progreso: Math.min(1, Math.max(0, propio / durationInFrames)),
    };
  }
  const local = abs - seg.inicioCuadro;
  return {
    segmento: seg,
    cuadro: local,
    t: local / fps,
    duracion: (seg.finCuadro - seg.inicioCuadro) / fps,
    progreso: Math.min(
      1,
      Math.max(0, local / (seg.finCuadro - seg.inicioCuadro)),
    ),
  };
};

const EscenaFaltante: React.FC<PropsEscena> = ({segmento}) => {
  if (getRemotionEnvironment().isRendering) {
    throw new Error(
      `No hay componente registrado para el tipo de escena "${segmento.tipo}" (${segmento.id}).`,
    );
  }
  return (
    <AbsoluteFill
      style={{
        justifyContent: 'center',
        alignItems: 'center',
        color: '#e33',
        fontFamily: 'monospace',
        fontSize: 42,
        background:
          'repeating-linear-gradient(45deg,#111 0 20px,#1a1a1a 20px 40px)',
      }}
    >
      Falta el tipo "{segmento.tipo}" ({segmento.id})
    </AbsoluteFill>
  );
};

const Escena: React.FC<{
  readonly segmento: SegmentoEscena;
  readonly registro: RegistroEscenas;
}> = ({segmento, registro}) => {
  const Componente = segmento.hueco
    ? null
    : (registro[segmento.tipo] ?? EscenaFaltante);
  return (
    <CtxEscena.Provider value={segmento}>
      {Componente ? (
        <Componente params={segmento.params} segmento={segmento} />
      ) : null}
    </CtxEscena.Provider>
  );
};

// --- Audio de la hoja -------------------------------------------------------------
/**
 * Una pista de la hoja: volumen fijo × ducking (si hay envolventes) × fundidos.
 * El fundido de salida termina al final del video (o en `fin` de la pista, si existe).
 */
const Pista: React.FC<{
  readonly pista: PistaCue;
  readonly env: Envolventes | null;
}> = ({pista, env}) => {
  const {fps, durationInFrames} = useVideoConfig();
  const desde = segundosACuadro(pista.inicio, fps);
  const finAbs =
    pista.fin !== undefined
      ? segundosACuadro(pista.fin, fps)
      : durationInFrames;
  const volumen = useMemo(() => {
    const duck =
      pista.ducking && env
        ? volumenConDucking(env, {
            fuente: pista.ducking.fuente,
            reduccion: pista.ducking.reduccion,
            base: 1,
            desde,
          })
        : () => 1;
    const fe = pista.fundidoEntrada * fps;
    const fs = pista.fundidoSalida * fps;
    const finRel = finAbs - desde;
    return (f: number) =>
      pista.volumen *
      duck(f) *
      (fe > 0
        ? interpolate(f, [0, fe], [0, 1], {extrapolateRight: 'clamp'})
        : 1) *
      (fs > 0
        ? interpolate(f, [finRel - fs, finRel], [1, 0], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          })
        : 1);
  }, [pista, env, fps, desde, finAbs]);
  return (
    <Audio
      src={staticFile(pista.src)}
      from={desde}
      durationInFrames={Math.max(1, finAbs - desde)}
      volume={volumen}
      name={pista.id}
    />
  );
};

// --- Composición ----------------------------------------------------------------
export const esquemaLinea = z.object({
  /** Ruta de la hoja dentro de public/. */
  hojaSrc: z.string(),
  /** Hoja ya cargada y validada (la completa calculateMetadata). */
  hoja: z.any().optional(),
});

/** Props serializables de la composición (el registro NO va acá: no es JSON). */
export type PropsLinea = {
  readonly hojaSrc: string;
  readonly hoja?: HojaDeCues;
};

/**
 * Componente genérico. Cada video registra su propia composición que lo envuelve con
 * su registro de escenas: `(p) => <LineaDeTiempo {...p} registro={MI_REGISTRO} />`.
 */
export const LineaDeTiempo: React.FC<
  PropsLinea & {readonly registro: RegistroEscenas}
> = ({hoja, registro}) => {
  const {fps} = useVideoConfig();
  if (!hoja)
    throw new Error(
      'LineaDeTiempo necesita la hoja (calculateMetadata la carga desde hojaSrc).',
    );
  const linea = useMemo(() => resolverLinea(hoja, fps), [hoja, fps]);
  const env = useEnvolventes(
    hoja.envolventes ? staticFile(hoja.envolventes) : null,
  );
  const voz = useTranscripcion(
    hoja.transcripcion ? staticFile(hoja.transcripcion) : null,
  );

  return (
    <ProveedorTiempoAbsoluto>
      <ProveedorTranscripcion transcripcion={voz}>
        <ProveedorAudio envolventes={env}>
          <AbsoluteFill style={{backgroundColor: hoja.fondo}}>
            <TransitionSeries>
              {linea.items.map((it, k) =>
                it.clase === 'escena' ? (
                  <TransitionSeries.Sequence
                    key={`e-${it.id}`}
                    durationInFrames={it.duracion}
                    name={it.id}
                  >
                    <Escena segmento={it} registro={registro} />
                  </TransitionSeries.Sequence>
                ) : (
                  <TransitionSeries.Transition
                    key={`t-${k}`}
                    presentation={presentacion(it)}
                    timing={linearTiming({durationInFrames: it.duracion})}
                  />
                ),
              )}
            </TransitionSeries>
          </AbsoluteFill>
          {hoja.audio.map((p) => (
            <Pista key={p.id} pista={p} env={env} />
          ))}
        </ProveedorAudio>
      </ProveedorTranscripcion>
    </ProveedorTiempoAbsoluto>
  );
};

/**
 * calculateMetadata: carga y valida la hoja; la duración y los fps del video salen de
 * ella. Genérica para que la use cualquier composición que extienda PropsLinea.
 */
export const metadatosLinea = async <P extends PropsLinea>({
  props,
}: Parameters<CalculateMetadataFunction<P>>[0]): Promise<{
  durationInFrames: number;
  fps: number;
  props: P;
}> => {
  const hoja = validarHoja(await cargarJSON(staticFile(props.hojaSrc)));
  const linea = resolverLinea(hoja, hoja.fps);
  for (const a of linea.avisos) {
    console.warn(a);
  }
  return {
    durationInFrames: linea.duracion,
    fps: hoja.fps,
    props: {...props, hoja},
  };
};
