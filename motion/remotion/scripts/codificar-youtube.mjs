// Codificación final para YouTube desde el intermedio maestro.
//
//   node scripts/codificar-youtube.mjs out/tramos/VideoEjemplo/intermedio.mov [salida.mp4]
//     [--crf 17] [--preset slow] [--audio-kbps 320] [--copiar-video]
//
// H.264 High, 1080p60, yuv420p, CRF 17, preset slow, GOP cerrado de medio segundo
// (30 cuadros) con 2 B-frames (recomendación de YouTube), BT.709 declarado,
// AAC-LC 320 kbps 48 kHz estéreo y +faststart (el índice al principio del archivo).
// --copiar-video: si los tramos ya se renderizaron con el perfil "final", solo
// codifica el audio a AAC y copia el video tal cual.
import path from 'node:path';
import {contarCuadros, correr, ffprobe, leerArgs} from './comun.mjs';

const a = leerArgs();
const entrada = a._[0];
if (!entrada) {
  console.error('Uso: node scripts/codificar-youtube.mjs <intermedio> [salida.mp4] [--crf 17] [--preset slow]');
  process.exit(1);
}
const salida = a._[1] ?? path.join(path.dirname(entrada), 'youtube.mp4');
const info = ffprobe(entrada, ['-show_streams']);
const v = info.streams.find((s) => s.codec_type === 'video');
const tieneAudio = info.streams.some((s) => s.codec_type === 'audio');
const [num, den] = String(v.r_frame_rate).split('/').map(Number);
const fps = Math.round(num / (den || 1));
const gop = String(Math.round(fps / 2));

const video = a['copiar-video']
  ? ['-c:v', 'copy']
  : [
      '-c:v', 'libx264',
      '-preset', String(a.preset ?? 'slow'),
      '-crf', String(a.crf ?? 17),
      '-profile:v', 'high',
      '-level:v', fps > 30 ? '4.2' : '4.1',
      '-pix_fmt', 'yuv420p',
      '-g', gop,
      '-keyint_min', gop,
      '-bf', '2',
      '-flags', '+cgop',
      '-sc_threshold', '0',
      '-colorspace', 'bt709',
      '-color_primaries', 'bt709',
      '-color_trc', 'bt709',
      '-color_range', 'tv',
    ];
const audio = tieneAudio
  ? ['-c:a', 'aac', '-b:a', `${a['audio-kbps'] ?? 320}k`, '-ar', '48000', '-ac', '2']
  : [];

const t0 = Date.now();
correr('ffmpeg', [
  '-hide_banner', '-v', 'error', '-stats', '-y',
  '-i', entrada,
  '-map', '0:v:0', ...(tieneAudio ? ['-map', '0:a:0'] : []),
  ...video,
  ...audio,
  '-movflags', '+faststart',
  salida,
]);
const seg = (Date.now() - t0) / 1000;
const cuadros = contarCuadros(salida);
console.log(`${salida}: ${cuadros} cuadros, codificado en ${seg.toFixed(1)} s (${(cuadros / seg).toFixed(1)} fps)`);
