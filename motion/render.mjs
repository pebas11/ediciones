// Render cuadro a cuadro: Chromium (Playwright) → ffmpeg (H.264, BT.709)
//
//   node render.mjs <escena>                       → renders/<escena>_FONDO.mp4 y _VERDE.mp4 (final, 60 fps)
//   node render.mjs <escena> --modes fondo         → solo una versión
//   node render.mjs <escena> --draft               → previa rápida 960×540 a 30 fps (renders/draft/)
//   node render.mjs <escena> --sheet 16            → hoja de contacto 1920×1080 (16 cuadros de 480×270)
//   node render.mjs <escena> --stills 2.5,6.1      → PNG sueltos (agregar --scale 0.5 para mitad de tamaño)
//   node render.mjs <escena> --stills 6.1 --crop 600,300,640,360   → recorte a resolución completa
//   --workers N   navegadores en paralelo (por defecto: núcleos − 1)
//
// Audio (si la escena carga lib/audio.js y usa M.sfx / audio.bed; guía: docs/AUDIO.md): tras el MP4 FONDO
// se sintetiza el sonido a NIVEL FIJO CALIBRADO (no se normaliza: todas las escenas quedan parejas y listas
// para ir a 0 dB bajo una voz a −16 LUFS) y se muxea (AAC 256k, cortado al largo del video con fundido de
// 0,2 s). renders/<escena>_AUDIO.wav lleva además la cola (reverb, impactos) de hasta 3 s después del final.
//   node render.mjs <escena> --audio-only          → no re-renderiza cuadros: regenera audio y remuxea el MP4 existente
//   node render.mjs <escena> --no-audio            → video mudo
//   node render.mjs <escena> --bed-only [--dur 95] → solo la cama de la escena → renders/<escena>_BED.wav (una
//                                                    cama continua para toda la serie, en su propia pista)
//   --no-bed      sin la cama de la escena (solo efectos)
//   --gain -3     ganancia fija en dB sobre el nivel calibrado (por defecto 0)
//   --lufs -16    en vez de nivel fijo, normalizar el loudness integrado (rompe la paridad entre escenas)
//   Limitador de seguridad solo si el true peak supera −1,5 dBTP (techo −2 dBTP).
//
// <escena> = nombre del archivo en scenes/ sin .html (ej: 01-balance)
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn, execFileSync, spawnSync } from 'node:child_process';
import { ROOT, FFMPEG, startServer, launch, openScene, capture, sceneExists } from './lib/harness.mjs';

const args = process.argv.slice(2);
const scene = args[0];
const opt = (k, d) => { const i = args.indexOf('--' + k); return i >= 0 ? args[i + 1] : d; };
const flag = (k) => args.includes('--' + k);
const draft = flag('draft');
const modes = opt('modes', 'fondo,verde').split(',');
const fps = +opt('fps', draft ? 30 : 60);
const stills = opt('stills', null);
const sheet = opt('sheet', null);
const scale = +opt('scale', 1);
const crop = opt('crop', null);
const workers = Math.max(1, +opt('workers', Math.max(1, os.cpus().length - 1)));
const audioOnly = flag('audio-only'), noAudio = flag('no-audio'), bedOnly = flag('bed-only'), noBed = flag('no-bed');
const GAIN = +opt('gain', 0), LUFS = opt('lufs', null) === null ? null : +opt('lufs');
const TAIL = 3, FADE_MP4 = 0.2, TP_TRIG = -1.5, TP_CEIL = -2;   // techo 0,5 dB bajo el disparo: margen para el sobrepico del AAC
if (!scene || !sceneExists(scene)) { console.error('escena inexistente:', scene); process.exit(1); }
const videoPath = (mode) => draft
  ? path.join(ROOT, 'renders', 'draft', `${scene}_${mode.toUpperCase()}_draft.mp4`)
  : path.join(ROOT, 'renders', `${scene}_${mode.toUpperCase()}.mp4`);
const wavPath = () => draft ? path.join(ROOT, 'renders', 'draft', `${scene}_AUDIO_draft.wav`) : path.join(ROOT, 'renders', `${scene}_AUDIO.wav`);

const server = await startServer();
const browser = await launch();
fs.mkdirSync(path.join(ROOT, 'stills'), { recursive: true });
fs.mkdirSync(path.join(ROOT, 'renders', 'draft'), { recursive: true });

const ff = (a) => execFileSync(FFMPEG, ['-y', '-loglevel', 'error', ...a]);

/* ---------------- audio: síntesis en la página (float) → WAV 16 bits → mux ---------------- */
// ffmpeg con salida de diagnóstico (stderr) — para loudnorm / ebur128
const ffErr = (a) => {
  const r = spawnSync(FFMPEG, ['-hide_banner', '-nostats', '-y', ...a], { encoding: 'utf8', maxBuffer: 64 << 20 });
  if (r.status !== 0) throw new Error('ffmpeg falló:\n' + r.stderr.slice(-2000));
  return r.stderr;
};
const lastJson = (txt) => JSON.parse(txt.slice(txt.lastIndexOf('{'), txt.lastIndexOf('}') + 1));
const ebur = (input, af = '') => {
  const e = ffErr([...input, '-af', `${af}ebur128=peak=true`, '-f', 'null', '-']).split('Summary:')[1] || '';
  const n = (re) => +(re.exec(e) || [])[1];
  return { I: n(/I:\s+(-?[\d.]+) LUFS/), thresh: n(/Threshold:\s+(-?[\d.]+) LUFS/), LRA: n(/LRA:\s+(-?[\d.]+) LU/), TP: n(/Peak:\s+(-?[\d.]+) dBFS/) };
};
const f1 = (v) => (Math.round(v * 10) / 10).toFixed(1).replace('.', ',').replace('-', '−');
const sg = (v) => (v > 0 ? '+' : '') + f1(v);
const rel = (p) => path.relative(ROOT, p);
const hasAudio = (v) => /Stream #\S+.*Audio:/.test(spawnSync(FFMPEG, ['-hide_banner', '-i', v], { encoding: 'utf8' }).stderr);

/** Trae el render de la página en float32 (por tramos: clips largos no entran en un solo mensaje). */
async function pullAudio(page, dur, o = {}) {
  const meta = await page.evaluate((o) => (window.__renderAudio ? window.__renderAudio({ ...o, keep: true }) : null), { duration: dur, tail: TAIL, ...o });
  if (!meta) return null;
  const n = meta.frames, data = new Float32Array(n * 2), view = Buffer.from(data.buffer);
  const CH = 1 << 19;
  for (let i0 = 0; i0 < n; i0 += CH) {
    const b64 = await page.evaluate(([i0, k]) => window.MAudio.chunk(window.__audioResult, i0, k), [i0, CH]);
    Buffer.from(b64, 'base64').copy(view, i0 * 8);
  }
  await page.evaluate(() => { window.__audioResult = null; });
  return { ...meta, data };
}

/** Float → WAV 16 bits (dither triangular). Nivel fijo (+ --gain) o --lufs; limitador solo si hace falta.
    La cola se recorta donde cae 72 dB bajo el pico. Devuelve null si es silencio. */
function writeWav(a, wav) {
  const SR = a.sampleRate, d = a.data, N = d.length / 2, sceneN = a.sceneFrames;
  let pk = 0; for (let i = 0; i < d.length; i++) { const v = Math.abs(d[i]); if (v > pk) pk = v; }
  if (pk < 1e-5) return null;                                       // < −100 dBFS: silencio
  const thr = pk * Math.pow(10, -72 / 20);
  let last = sceneN;
  for (let i = N - 1; i >= sceneN; i--) if (Math.abs(d[2 * i]) > thr || Math.abs(d[2 * i + 1]) > thr) { last = i; break; }
  const n = Math.min(N, Math.max(sceneN, last + Math.round(0.1 * SR)));
  // lo que el MP4 pierde al cortar en el final de la escena: RMS de los primeros 300 ms de cola
  const m = Math.min(n, sceneN + Math.round(0.3 * SR)) - sceneN;
  let e = 0; for (let i = 2 * sceneN; i < 2 * (sceneN + m); i++) e += d[i] * d[i];
  const lostRaw = m > 0 ? 10 * Math.log10(e / (2 * m) + 1e-30) : -Infinity;
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'maudio-'));
  try {
    const raw = path.join(tmp, 'raw.f32');
    fs.writeFileSync(raw, Buffer.from(d.buffer, d.byteOffset, n * 8));
    const IN = ['-f', 'f32le', '-ar', String(SR), '-ac', '2', '-i', raw];
    let pre, gain, limited = 0, mode;
    if (LUFS === null) {
      // nivel fijo: el WAV sale como lo calibra el motor (+ --gain); limitador solo si el pico lo pide
      gain = GAIN; mode = `nivel fijo, ganancia ${sg(GAIN)} dB`;
      pre = `volume=${GAIN.toFixed(2)}dB,`;
      const m0 = ebur(IN, pre);
      if (m0.TP > TP_TRIG) {
        limited = m0.TP - TP_CEIL;
        pre += `aresample=192000,alimiter=limit=${Math.pow(10, TP_CEIL / 20).toFixed(5)}:attack=1:release=60:level=false:latency=true,aresample=${SR},`;
      }
      ff([...IN, '-af', `${pre}aresample=${SR}:osf=s16:dither_method=triangular`, '-c:a', 'pcm_s16le', wav]);
    } else {
      // --lufs: loudnorm en modo lineal (ganancia fija, sin compresión). Se mide con ebur128 (el medidor de
      // referencia: el interno de loudnorm se desvía ~0,4 LU en clips cortos y ralos).
      const raw0 = ebur(IN); let m0 = raw0, gPre = 0; pre = '';
      // limitador (×4, lookahead compensado) si la ganancia lineal llevaría el pico sobre el techo. El
      // limitador también baja el integrado (en escenas ralas, bastante): se reajusta hasta que entre.
      let room = TP_CEIL - LUFS - 0.8;
      for (let k = 0; k < 5 && m0.TP + (LUFS - m0.I) > TP_CEIL - 0.2; k++) {
        const ceil = raw0.I + room, g = -3 - ceil;
        limited = raw0.TP - ceil; gPre = g;
        pre = `volume=${g.toFixed(2)}dB,aresample=192000,alimiter=limit=${Math.pow(10, -3 / 20).toFixed(5)}:attack=1:release=60:level=false:latency=true,aresample=${SR},`;
        m0 = ebur(IN, pre);
        room -= Math.max(0.3, m0.TP + (LUFS - m0.I) - (TP_CEIL - 0.5));
      }
      const ln = `loudnorm=I=${LUFS}:TP=${TP_CEIL}:LRA=50:measured_I=${m0.I}:measured_TP=${m0.TP}:measured_LRA=${Math.max(0.1, m0.LRA)}:measured_thresh=${m0.thresh}:linear=true:print_format=json`;
      const res = lastJson(ffErr([...IN, '-af', `${pre}${ln},aresample=${SR}:osf=s16:dither_method=triangular`, '-c:a', 'pcm_s16le', wav]));
      if (res.normalization_type !== 'linear') console.warn('audio: loudnorm pasó a modo dinámico (revisar picos)');
      gain = gPre + LUFS - m0.I; mode = `normalizado a ${f1(LUFS)} LUFS (${sg(gain)} dB)`;
    }
    const w = ebur(['-i', wav]);
    return { wav, n, sceneN, SR, tail: (n - sceneN) / SR, lost: lostRaw + gain, limited, mode, w };
  } finally { fs.rmSync(tmp, { recursive: true, force: true }); }
}

/** Mux: video tal cual + AAC del WAV, cortado al largo de la escena con fundido de 0,2 s (sin clic). */
function mux(video, r) {
  const tmpMp4 = video.replace(/\.mp4$/, '.tmp.mp4'), F = Math.min(r.sceneN, Math.round(FADE_MP4 * r.SR));
  ff(['-i', video, '-i', r.wav, '-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy',
    '-af', `atrim=end_sample=${r.sceneN},afade=t=out:start_sample=${r.sceneN - F}:nb_samples=${F}:curve=qsin`,
    '-c:a', 'aac', '-b:a', '256k', '-ar', String(r.SR), '-movflags', '+faststart', tmpMp4]);
  fs.renameSync(tmpMp4, video);
  return ebur(['-i', video, '-map', '0:a:0']);
}

/** Escena sin sonido: que no quede audio viejo (WAV suelto ni pista AAC en el MP4). */
function dropAudio(video, wav, why) {
  const done = [];
  if (fs.existsSync(wav)) { fs.unlinkSync(wav); done.push('borrado ' + rel(wav)); }
  if (video && fs.existsSync(video) && hasAudio(video)) {
    const tmpMp4 = video.replace(/\.mp4$/, '.tmp.mp4');
    ff(['-i', video, '-map', '0:v:0', '-c:v', 'copy', '-an', '-movflags', '+faststart', tmpMp4]);
    fs.renameSync(tmpMp4, video);
    done.push('pista de audio quitada de ' + rel(video));
  }
  console.log(`audio: ${why} → video mudo` + (done.length ? ` (${done.join(' · ')})` : ''));
}

async function makeAudio(page, video, dur) {
  const t0 = Date.now(), wav = wavPath();
  const a = await pullAudio(page, dur, noBed ? { bed: false } : {});
  if (!a) return dropAudio(video, wav, 'la escena no tiene sonido (cargar lib/audio.js y usar M.sfx / audio.bed)');
  const r = writeWav(a, wav);
  if (!r) return dropAudio(video, wav, 'silencio');
  const fin = mux(video, r);
  console.log(`audio: ${rel(wav)} (${(r.sceneN / r.SR).toFixed(2).replace('.', ',')} s + cola ${r.tail.toFixed(2).replace('.', ',')} s · ${f1(r.w.I)} LUFS · TP ${f1(r.w.TP)} dBTP · ${r.mode})`
    + ` + muxeado en ${rel(video)} (AAC: ${f1(fin.I)} LUFS · TP ${f1(fin.TP)} dBTP · LRA ${f1(fin.LRA)} LU)`
    + (r.limited > 0 ? ` · limitador −${f1(r.limited)} dB en picos` : '') + ` · ${((Date.now() - t0) / 1000).toFixed(1)}s`);
  if (r.lost > -45) console.warn(`audio: AVISO: el MP4 corta una cola (${f1(r.lost)} dBFS RMS en los 300 ms después del final). El WAV la trae completa: usarlo en CapCut, o adelantar el cue.`);
  if (fin.TP > -1) console.warn(`audio: true peak del AAC ${fin.TP} dBTP > −1`);
}

/* ---------------- --bed-only: una cama continua (para toda la serie) ---------------- */
if (bedOnly) {
  const { page, duration } = await openScene(browser, server, scene, 'fondo');
  const dur = +opt('dur', duration), out = path.join(ROOT, 'renders', `${scene}_BED.wav`);
  const a = await pullAudio(page, dur, { bedOnly: true });
  if (!a) { console.error('la escena no carga lib/audio.js'); process.exit(1); }
  const r = writeWav(a, out);
  console.log(`cama: ${rel(out)} (${dur.toFixed(2).replace('.', ',')} s + cola ${r.tail.toFixed(2).replace('.', ',')} s · ${f1(r.w.I)} LUFS · TP ${f1(r.w.TP)} dBTP · ${r.mode})`);
  await browser.close(); server.close();
  process.exit(0);
}

/* ---------------- --audio-only: regenerar el audio sin re-renderizar cuadros ---------------- */
if (audioOnly) {
  const video = videoPath('fondo');
  if (!fs.existsSync(video)) { console.error('no existe', rel(video), '— renderizá primero el video'); process.exit(1); }
  const info = spawnSync(FFMPEG, ['-hide_banner', '-i', video], { encoding: 'utf8' }).stderr;
  const vfps = +(/, ([\d.]+) fps/.exec(info) || [])[1] || fps;
  const { page, duration } = await openScene(browser, server, scene, 'fondo');
  await makeAudio(page, video, Math.round(duration * vfps) / vfps);
  await browser.close(); server.close();
  process.exit(0);
}

for (const mode of modes) {
  /* ---------------- cuadros sueltos / hoja de contacto ---------------- */
  if (stills || sheet) {
    const { page, duration, errors, cdp } = await openScene(browser, server, scene, mode);
    if (errors.length) console.error('Errores en la página:\n' + errors.join('\n'));
    const times = stills
      ? stills.split(',').map(Number)
      : Array.from({ length: +sheet }, (_, i) => +(((i + 0.5) / +sheet) * duration).toFixed(2));
    const files = [];
    for (const t of times) {
      await page.evaluate((t) => window.__seek(t), t);
      const f = path.join(ROOT, 'stills', `${scene}_${mode}_${t.toFixed(2)}.png`);
      fs.writeFileSync(f, await capture(cdp, 'png'));
      if (crop) { const [x, y, w, h] = crop.split(',').map(Number); ff(['-i', f, '-vf', `crop=${w}:${h}:${x}:${y}`, f + '.tmp.png']); fs.renameSync(f + '.tmp.png', f); }
      else if (scale !== 1 && stills) { ff(['-i', f, '-vf', `scale=${Math.round(1920 * scale)}:-2:flags=lanczos`, f + '.tmp.png']); fs.renameSync(f + '.tmp.png', f); }
      files.push(f);
    }
    if (sheet) {
      // celdas 480×270 → hoja de 1920×(270·filas): ~2,8k tokens para 16 cuadros
      const cols = 4, cw = 480, chh = 270;
      const out = path.join(ROOT, 'stills', `${scene}_${mode}_SHEET.png`);
      const layout = files.map((_, i) => `${(i % cols) * cw}_${Math.floor(i / cols) * chh}`).join('|');
      const filt = files.map((_, i) => `[${i}:v]scale=${cw}:${chh}:flags=lanczos[v${i}]`).join(';') + ';' + files.map((_, i) => `[v${i}]`).join('') + `xstack=inputs=${files.length}:layout=${layout}:fill=black[out]`;
      ff([...files.flatMap((f) => ['-i', f]), '-filter_complex', filt, '-map', '[out]', out]);
      files.forEach((f) => fs.unlinkSync(f));
      console.log('hoja:', out, '\ntiempos (fila por fila):', times.join(', '));
    } else console.log(files.join('\n'));
    await page.close();
    continue;
  }

  /* ---------------- video: N páginas en paralelo → un solo ffmpeg ---------------- */
  // un navegador por worker: las páginas de un mismo Chromium comparten el compositor y no escalan
  const browsers = await Promise.all(Array.from({ length: workers }, () => launch()));
  const pages = await Promise.all(browsers.map((b) => openScene(b, server, scene, mode, draft ? { dsf: 0.5 } : undefined)));
  if (pages[0].errors.length) console.error('Errores en la página:\n' + pages[0].errors.join('\n'));
  const duration = pages[0].duration;
  const total = Math.round(duration * fps);
  // FONDO: JPEG q95 (2,5× más rápido que PNG; el H.264 final ya es con pérdida).
  // VERDE: PNG, para que los bordes contra el verde queden sin artefactos.
  const fmt = mode === 'fondo' ? 'jpeg' : 'png';
  const out = videoPath(mode);
  const vf = [draft ? 'scale=960:540:flags=bicubic' : null, 'scale=in_range=full:out_range=tv:out_color_matrix=bt709', 'format=yuv420p'].filter(Boolean).join(','); // (el scale es no-op si ya viene a 960)
  const enc = spawn(FFMPEG, [
    '-y', '-loglevel', 'error',
    '-f', 'image2pipe', '-framerate', String(fps), '-c:v', fmt === 'png' ? 'png' : 'mjpeg', '-i', '-',
    '-vf', vf,
    '-c:v', 'libx264', '-preset', draft ? 'veryfast' : 'slow', '-crf', draft ? '23' : (mode === 'verde' ? '12' : '14'),
    '-tune', 'animation', '-profile:v', 'high', '-pix_fmt', 'yuv420p',
    '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
    '-r', String(fps), '-movflags', '+faststart', out,
  ], { stdio: ['pipe', 'inherit', 'inherit'] });

  const t0 = Date.now();
  const ready = new Map();
  let next = 0;
  const flush = async () => {
    while (ready.has(next)) {
      const buf = ready.get(next); ready.delete(next); next++;
      if (!enc.stdin.write(buf)) await new Promise((r) => enc.stdin.once('drain', r));
      if (next % 120 === 0) process.stdout.write(`\r${mode}: ${next}/${total} (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
    }
  };
  let flushing = Promise.resolve();
  await Promise.all(pages.map(async ({ page, cdp }, k) => {
    for (let i = k; i < total; i += workers) {
      // no adelantarse demasiado al encoder (memoria acotada)
      while (i - next > workers * 8) await new Promise((r) => setTimeout(r, 5));
      await page.evaluate((t) => window.__seek(t), i / fps);
      ready.set(i, await capture(cdp, fmt, 95));
      flushing = flushing.then(flush);
    }
  }));
  await flushing;
  enc.stdin.end();
  await new Promise((r) => enc.on('close', r));
  const secs = (Date.now() - t0) / 1000;
  console.log(`\r${mode}: ${total}/${total} → ${path.relative(ROOT, out)} (${secs.toFixed(0)}s, ${(secs * 1000 / total).toFixed(0)} ms/cuadro, ${workers} workers)`);
  // el audio va solo en FONDO (el chroma se superpone a un video que ya tiene su sonido)
  if (mode === 'fondo' && !noAudio) await makeAudio(pages[0].page, out, total / fps);
  for (const b of browsers) await b.close();
}

await browser.close();
server.close();
