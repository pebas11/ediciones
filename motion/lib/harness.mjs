// Infra compartida por render.mjs y qa.mjs: servidor estático + Chromium + apertura de escenas.
import { chromium } from 'playwright';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

export const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..');
export const FFMPEG = execFileSync('python3', ['-c', 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())']).toString().trim();

const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.svg': 'image/svg+xml', '.woff2': 'font/woff2', '.png': 'image/png', '.json': 'application/json' };

export async function startServer() {
  const server = http.createServer((req, res) => {
    const p = path.join(ROOT, decodeURIComponent(req.url.split('?')[0]));
    if (!p.startsWith(ROOT) || !fs.existsSync(p) || fs.statSync(p).isDirectory()) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'Content-Type': MIME[path.extname(p)] || 'application/octet-stream' });
    fs.createReadStream(p).pipe(res);
  });
  await new Promise((r) => server.listen(0, '127.0.0.1', r));
  return server;
}

// --disable-gpu: raster por software en el propio proceso (medido: ~20 % más rápido en este contenedor)
export async function launch() {
  return chromium.launch({
    args: ['--force-color-profile=srgb', '--disable-lcd-text', '--font-render-hinting=none', '--hide-scrollbars', '--disable-gpu'],
  });
}

/** Abre una escena y espera a que esté lista. Devuelve { page, duration, errors, cdp }. */
export async function openScene(browser, server, scene, mode, { width = 1920, height = 1080, dsf = 1 } = {}) {
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: dsf });
  const errors = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  await page.goto(`http://127.0.0.1:${server.address().port}/scenes/${scene}.html?mode=${mode}`);
  await page.waitForFunction(() => window.__ready === true, null, { timeout: 30000 }).catch(() => {});
  const ready = await page.evaluate(() => window.__ready === true);
  if (!ready) throw new Error(`La escena ${scene} (${mode}) no cargó.\n${errors.join('\n')}`);
  const duration = await page.evaluate(() => M.duration);
  const cdp = await page.context().newCDPSession(page);
  return { page, duration, errors, cdp };
}

/** Captura rápida vía CDP (sin el overhead de page.screenshot). */
export async function capture(cdp, format = 'png', quality = 95) {
  const r = await cdp.send('Page.captureScreenshot', format === 'png'
    ? { format: 'png', optimizeForSpeed: true }
    : { format, quality, optimizeForSpeed: true });
  return Buffer.from(r.data, 'base64');
}

export function sceneExists(scene) { return fs.existsSync(path.join(ROOT, 'scenes', scene + '.html')); }
