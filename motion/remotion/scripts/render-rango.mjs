// Worker: renderiza UN rango de cuadros de una composición ya empaquetada.
// Lo usan render-tramos.mjs y bench.mjs (un proceso = un navegador propio).
//
//   node scripts/render-rango.mjs --serve-url build --comp PruebaTecnica \
//     --desde 0 --hasta 149 --salida out/t/tramo-000.ts [--audio out/t/tramo-000.wav] \
//     [--perfil intermedio|final|prores] [--concurrencia 1] [--props '{"calidad":"final"}']
//
// - Escribe en archivos .part y los renombra al terminar: un tramo a medias nunca queda
//   con el nombre final (así el render por tramos se puede reanudar sin miedo).
// - Valida la cantidad exacta de cuadros (ffprobe) y de muestras de audio.
// - Imprime líneas JSON en stdout ({"evento": ...}) para el orquestador.
import fs from 'node:fs';
import path from 'node:path';
import {openBrowser, renderMedia, selectComposition} from '@remotion/renderer';
import {contarCuadros, contarMuestras, leerArgs} from './comun.mjs';
import {concurrencia as concurrenciaPorDefecto, opcionesNavegador} from './entorno.mjs';

/** Perfiles de salida de cada tramo (todos sin recomprimir al unir). */
export const PERFILES = {
  // Intermedio de alta calidad: H.264 casi sin pérdida, rápido de codificar.
  intermedio: {codec: 'h264-ts', crf: 10, x264Preset: 'veryfast', ext: 'ts'},
  // Directo a calidad de entrega: x264 slow trabaja mientras el navegador renderiza (sin
  // GPU el encoder espera cuadros, así que no suma tiempo). GOP de 30 = recomendación de
  // YouTube. Después: codificar-youtube.mjs --copiar-video (solo audio a AAC).
  // -sc_threshold 0: sin keyframes extra por "cortes" (el grano los dispara cada 4 cuadros).
  final: {
    codec: 'h264-ts',
    crf: 17,
    x264Preset: 'slow',
    gopSize: 30,
    x264Extra: ['-sc_threshold', '0', '-bf', '2'],
    ext: 'ts',
  },
  // ProRes 422 HQ: intra-frame, ideal para editar; ~3 GB por minuto a 1080p60.
  prores: {codec: 'prores', proResProfile: 'hq', ext: 'mov'},
};

const emitir = (o) => process.stdout.write(JSON.stringify(o) + '\n');

const main = async () => {
  const a = leerArgs();
  const desde = Number(a.desde);
  const hasta = Number(a.hasta);
  if (!a['serve-url'] || !a.comp || !Number.isInteger(desde) || !Number.isInteger(hasta) || !a.salida) {
    throw new Error('Faltan --serve-url, --comp, --desde, --hasta o --salida');
  }
  const perfil = PERFILES[a.perfil ?? 'intermedio'];
  if (!perfil) throw new Error(`Perfil desconocido: ${a.perfil}`);
  let inputProps = {};
  if (a.props) {
    inputProps = JSON.parse(a.props.startsWith('@') ? fs.readFileSync(a.props.slice(1), 'utf8') : a.props);
  }
  const nav = opcionesNavegador();
  if (a.gl) nav.chromiumOptions.gl = a.gl === 'default' ? null : a.gl;
  if (a.navegador) nav.browserExecutable = a.navegador === 'remotion' ? null : a.navegador;
  const conc = a.concurrencia ? Number(a.concurrencia) : concurrenciaPorDefecto();

  const salida = path.resolve(a.salida);
  const parte = salida.replace(/(\.[^.]+)$/, '.part$1');
  const audio = a.audio ? path.resolve(a.audio) : null;
  const audioParte = audio ? audio.replace(/(\.[^.]+)$/, '.part$1') : null;
  fs.mkdirSync(path.dirname(salida), {recursive: true});

  const t0 = Date.now();
  let primerCuadro = null;
  let fpsComp = 60;
  const browser = await openBrowser('chrome', {...nav, logLevel: 'error'});
  try {
    const composition = await selectComposition({
      serveUrl: a['serve-url'],
      id: a.comp,
      inputProps,
      puppeteerInstance: browser,
      logLevel: 'error',
    });
    fpsComp = composition.fps;
    let ultimo = -1;
    await renderMedia({
      serveUrl: a['serve-url'],
      composition,
      inputProps,
      puppeteerInstance: browser,
      ...nav,
      codec: perfil.codec,
      crf: perfil.crf,
      x264Preset: perfil.x264Preset,
      proResProfile: perfil.proResProfile,
      gopSize: perfil.gopSize,
      // Opciones de x264 que Remotion no expone: se agregan antes del archivo de salida,
      // solo en el comando de ffmpeg que codifica con libx264.
      ffmpegOverride: perfil.x264Extra
        ? ({args}) => (args.includes('libx264') ? [...args.slice(0, -1), ...perfil.x264Extra, args.at(-1)] : args)
        : undefined,
      pixelFormat: perfil.codec === 'prores' ? 'yuv422p10le' : 'yuv420p',
      colorSpace: 'bt709',
      imageFormat: a.imagen ?? 'jpeg',
      jpegQuality: a.imagen === 'png' ? undefined : 95,
      frameRange: [desde, hasta],
      compositionStart: 0,
      outputLocation: parte,
      concurrency: conc,
      muted: !audio,
      enforceAudioTrack: Boolean(audio),
      audioCodec: audio ? 'pcm-16' : undefined,
      separateAudioTo: audioParte ?? undefined,
      forSeamlessAacConcatenation: false,
      timeoutInMilliseconds: 180000,
      overwrite: true,
      logLevel: a.log ?? 'error',
      onProgress: ({renderedFrames, encodedFrames}) => {
        if (renderedFrames > 0 && primerCuadro === null) primerCuadro = Date.now() - t0;
        if (renderedFrames !== ultimo) {
          ultimo = renderedFrames;
          emitir({evento: 'progreso', renderizados: renderedFrames, codificados: encodedFrames, ms: Date.now() - t0});
        }
      },
    });
  } finally {
    await browser.close({silent: true}).catch(() => {});
  }

  // Validación estricta antes de dar el tramo por bueno.
  const esperados = hasta - desde + 1;
  const cuadros = contarCuadros(parte);
  if (cuadros !== esperados) throw new Error(`El tramo tiene ${cuadros} cuadros y se esperaban ${esperados}`);
  if (audioParte) {
    const {muestras, sampleRate} = contarMuestras(audioParte);
    const esperadas = Math.round((esperados * sampleRate) / fpsComp);
    if (Math.abs(muestras - esperadas) > 0) {
      throw new Error(`El audio del tramo tiene ${muestras} muestras y se esperaban ${esperadas}`);
    }
    fs.renameSync(audioParte, audio);
  }
  fs.renameSync(parte, salida);
  const ms = Date.now() - t0;
  emitir({
    evento: 'listo',
    cuadros,
    ms,
    primerCuadroMs: primerCuadro,
    fps: cuadros / (ms / 1000),
    fpsEstable: primerCuadro ? (cuadros - 1) / ((ms - primerCuadro) / 1000) : null,
  });
};

main().catch((e) => {
  emitir({evento: 'error', mensaje: String(e?.stack ?? e).slice(0, 2000)});
  process.exit(1);
});
