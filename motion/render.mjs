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
// <escena> = nombre del archivo en scenes/ sin .html (ej: 01-balance)
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn, execFileSync } from 'node:child_process';
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
if (!scene || !sceneExists(scene)) { console.error('escena inexistente:', scene); process.exit(1); }

const server = await startServer();
const browser = await launch();
fs.mkdirSync(path.join(ROOT, 'stills'), { recursive: true });
fs.mkdirSync(path.join(ROOT, 'renders', 'draft'), { recursive: true });

const ff = (a) => execFileSync(FFMPEG, ['-y', '-loglevel', 'error', ...a]);

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
  const out = draft
    ? path.join(ROOT, 'renders', 'draft', `${scene}_${mode.toUpperCase()}_draft.mp4`)
    : path.join(ROOT, 'renders', `${scene}_${mode.toUpperCase()}.mp4`);
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
  for (const b of browsers) await b.close();
}

await browser.close();
server.close();
