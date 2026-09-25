// Render cuadro a cuadro: Chromium (Playwright) → ffmpeg (H.264, BT.709)
//
//   node render.mjs <escena> [--modes fondo,verde] [--fps 60]
//   node render.mjs <escena> --stills 0.5,2,4.2 [--modes fondo]   → PNGs en stills/
//   node render.mjs <escena> --sheet 16                             → hoja de contacto en stills/
//
// <escena> = nombre del archivo en scenes/ sin .html (ej: 01-balance)
import { chromium } from 'playwright';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { spawn, execFileSync } from 'node:child_process';

const ROOT = path.dirname(new URL(import.meta.url).pathname);
const FFMPEG = execFileSync('python3', ['-c', 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())']).toString().trim();

const args = process.argv.slice(2);
const scene = args[0];
const opt = (k, d) => { const i = args.indexOf('--' + k); return i >= 0 ? args[i + 1] : d; };
const modes = opt('modes', 'fondo,verde').split(',');
const fps = +opt('fps', 60);
const stills = opt('stills', null);
const sheet = opt('sheet', null);
if (!scene || !fs.existsSync(path.join(ROOT, 'scenes', scene + '.html'))) { console.error('escena inexistente:', scene); process.exit(1); }

// servidor estático local (para fuentes / íconos / fetch)
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.png': 'image/png' };
const server = http.createServer((req, res) => {
  const p = path.join(ROOT, decodeURIComponent(req.url.split('?')[0]));
  if (!p.startsWith(ROOT) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'Content-Type': MIME[path.extname(p)] || 'application/octet-stream' });
  fs.createReadStream(p).pipe(res);
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const port = server.address().port;

const browser = await chromium.launch({
  args: ['--force-color-profile=srgb', '--disable-lcd-text', '--font-render-hinting=none', '--hide-scrollbars', '--disable-gpu-vsync'],
});

async function openPage(mode) {
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(`http://127.0.0.1:${port}/scenes/${scene}.html?mode=${mode}`);
  await page.waitForFunction(() => window.__ready === true, null, { timeout: 30000 }).catch(() => {});
  if (errors.length) { console.error('Errores en la página:\n' + errors.join('\n')); }
  const ready = await page.evaluate(() => window.__ready === true);
  if (!ready) throw new Error('La escena no terminó de cargar (window.__ready)');
  const duration = await page.evaluate(() => M.duration);
  return { page, duration };
}

const shot = (page) => page.screenshot({ type: 'png', animations: 'allow', caret: 'initial' });

fs.mkdirSync(path.join(ROOT, 'stills'), { recursive: true });
fs.mkdirSync(path.join(ROOT, 'renders'), { recursive: true });

for (const mode of modes) {
  const { page, duration } = await openPage(mode);

  if (stills || sheet) {
    const times = stills
      ? stills.split(',').map(Number)
      : Array.from({ length: +sheet }, (_, i) => +(((i + 0.5) / +sheet) * duration).toFixed(2));
    const files = [];
    for (const t of times) {
      await page.evaluate((t) => window.__seek(t), t);
      const f = path.join(ROOT, 'stills', `${scene}_${mode}_${t.toFixed(2)}.png`);
      fs.writeFileSync(f, await shot(page));
      files.push(f);
    }
    if (sheet) {
      const cols = 4, rows = Math.ceil(files.length / cols);
      const out = path.join(ROOT, 'stills', `${scene}_${mode}_SHEET.png`);
      const inputs = files.flatMap((f) => ['-i', f]);
      const layout = Array.from({ length: files.length }, (_, i) => `${(i % cols) * 640}_${Math.floor(i / cols) * 360}`).join('|');
      const filt = files.map((_, i) => `[${i}:v]scale=640:360[v${i}]`).join(';') + ';' + files.map((_, i) => `[v${i}]`).join('') + `xstack=inputs=${files.length}:layout=${layout}:fill=black[out]`;
      execFileSync(FFMPEG, ['-y', '-loglevel', 'error', ...inputs, '-filter_complex', filt, '-map', '[out]', out]);
      files.forEach((f) => fs.unlinkSync(f));
      console.log('hoja:', out, 'tiempos:', times.join(', '));
    } else console.log(files.join('\n'));
    await page.close();
    continue;
  }

  const total = Math.round(duration * fps);
  const out = path.join(ROOT, 'renders', `${scene}_${mode.toUpperCase()}.mp4`);
  const ff = spawn(FFMPEG, [
    '-y', '-loglevel', 'error',
    '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'png', '-i', '-',
    '-vf', 'scale=in_range=full:out_range=tv:out_color_matrix=bt709,format=yuv420p',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', mode === 'verde' ? '12' : '14',
    '-tune', 'animation', '-profile:v', 'high', '-pix_fmt', 'yuv420p',
    '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-color_range', 'tv',
    '-r', String(fps), '-movflags', '+faststart', out,
  ], { stdio: ['pipe', 'inherit', 'inherit'] });
  const t0 = Date.now();
  for (let i = 0; i < total; i++) {
    await page.evaluate((t) => window.__seek(t), i / fps);
    const buf = await shot(page);
    if (!ff.stdin.write(buf)) await new Promise((r) => ff.stdin.once('drain', r));
    if (i % 120 === 0) process.stdout.write(`\r${mode}: ${i}/${total} (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
  }
  ff.stdin.end();
  await new Promise((r) => ff.on('close', r));
  console.log(`\r${mode}: ${total}/${total} → ${out} (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
  await page.close();
}

await browser.close();
server.close();
