// Une los tramos de un render SIN recomprimir y arma el intermedio maestro.
//
//   node scripts/unir.mjs out/tramos/VideoEjemplo
//
// Lee manifiesto.json de esa carpeta y produce:
//   intermedio.mov  = video de los tramos (copiado, sin recomprimir) + audio PCM
//                     (unión de los WAV de cada tramo, exacta a la muestra)
// Video:
//   - H.264 en MPEG-TS (perfiles intermedio/final): protocolo concat: de ffmpeg, como
//     Remotion Lambda (los .ts se pueden pegar byte a byte), y "-r fps" al muxear.
//   - ProRes en .mov: demuxer concat.
// También se puede llamar desde otro script: import {unirTramos} from './unir.mjs'.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {contarCuadros, contarMuestras, correr} from './comun.mjs';

export function unirTramos(dir, {salida = 'intermedio.mov'} = {}) {
  const man = JSON.parse(fs.readFileSync(path.join(dir, 'manifiesto.json'), 'utf8'));
  const tramos = [...man.tramos].sort((a, b) => a.desde - b.desde);
  const faltan = tramos.filter((t) => t.estado !== 'listo' || !fs.existsSync(path.join(dir, t.video)));
  if (faltan.length) {
    throw new Error(`Faltan tramos: ${faltan.map((t) => t.i).join(', ')}. Correr render-tramos.mjs otra vez.`);
  }
  // Continuidad: cada tramo empieza donde terminó el anterior.
  for (let k = 1; k < tramos.length; k++) {
    if (tramos[k].desde !== tramos[k - 1].hasta + 1) {
      throw new Error(`Hueco o solapamiento entre el tramo ${tramos[k - 1].i} y el ${tramos[k].i}`);
    }
  }
  const esperados = tramos.at(-1).hasta - tramos[0].desde + 1;
  const conAudio = tramos.every((t) => t.audio && fs.existsSync(path.join(dir, t.audio)));
  const fps = String(man.fps);
  const args = ['-hide_banner', '-v', 'error', '-y'];

  if (tramos[0].video.endsWith('.ts')) {
    args.push('-i', `concat:${tramos.map((t) => t.video).join('|')}`);
  } else {
    const lista = tramos.map((t) => `file '${t.video.replace(/'/g, "'\\''")}'`).join('\n');
    fs.writeFileSync(path.join(dir, 'lista-video.txt'), lista + '\n');
    args.push('-f', 'concat', '-safe', '0', '-i', 'lista-video.txt');
  }
  if (conAudio) {
    const lista = tramos.map((t) => `file '${t.audio.replace(/'/g, "'\\''")}'`).join('\n');
    fs.writeFileSync(path.join(dir, 'lista-audio.txt'), lista + '\n');
    args.push('-f', 'concat', '-safe', '0', '-i', 'lista-audio.txt');
  }
  args.push('-map', '0:v:0');
  if (conAudio) args.push('-map', '1:a:0');
  args.push('-c', 'copy', '-r', fps, salida);
  correr('ffmpeg', args, {cwd: dir});

  const final = path.join(dir, salida);
  const cuadros = contarCuadros(final);
  if (cuadros !== esperados) {
    throw new Error(`${salida} tiene ${cuadros} cuadros y se esperaban ${esperados}`);
  }
  let resumen = `${salida}: ${cuadros} cuadros (${(cuadros / man.fps).toFixed(3)} s)`;
  if (conAudio) {
    const {muestras, sampleRate} = contarMuestras(final);
    const esperadas = Math.round((esperados / man.fps) * sampleRate);
    if (muestras !== esperadas) {
      throw new Error(`El audio tiene ${muestras} muestras y se esperaban ${esperadas}`);
    }
    resumen += `, audio PCM ${muestras} muestras a ${sampleRate} Hz (exacto)`;
  }
  return {archivo: final, cuadros, resumen};
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const dir = process.argv[2];
  if (!dir) {
    console.error('Uso: node scripts/unir.mjs <carpeta de tramos>');
    process.exit(1);
  }
  const r = unirTramos(path.resolve(dir), {salida: process.argv[3] ?? 'intermedio.mov'});
  console.log(r.resumen);
}
