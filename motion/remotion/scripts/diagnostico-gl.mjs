// Prueba cada modo de WebGL (--gl) con cada navegador disponible y reporta
// si hay WebGL2, qué renderer usa y cuánto tarda un still con R3F.
//
//   node scripts/diagnostico-gl.mjs                 # todos los modos
//   node scripts/diagnostico-gl.mjs --modos swangle,angle --navegadores remotion
import fs from 'node:fs';
import path from 'node:path';
import {openBrowser, renderStill, selectComposition} from '@remotion/renderer';
import {RAIZ, empaquetar, leerArgs} from './comun.mjs';
import {SHELL_PLAYWRIGHT, rutaShellRemotion} from './entorno.mjs';

const args = leerArgs();
const MODOS = (args.modos ?? 'default,angle,swangle,swiftshader,egl,vulkan,angle-egl').split(',');
// "remotion" = el Chrome Headless Shell que maneja Remotion (en Windows/macOS lo baja
// solo: browserExecutable null). "playwright" = el Chromium del contenedor.
const NAVS = {
  remotion: {
    disponible: process.platform !== 'linux' || fs.existsSync(rutaShellRemotion(RAIZ)),
    exe: process.platform === 'linux' ? rutaShellRemotion(RAIZ) : null,
  },
  playwright: {disponible: fs.existsSync(SHELL_PLAYWRIGHT), exe: SHELL_PLAYWRIGHT},
};
const navsElegidos = (args.navegadores ?? 'remotion,playwright')
  .split(',')
  .filter((n) => NAVS[n]?.disponible);

// Cuando un modo no tiene WebGL, el navegador se cae y deja promesas sueltas
// ("Target closed"): se registran y se sigue con el próximo modo.
process.on('unhandledRejection', (e) => {
  console.log(`  (aviso: ${String(e?.message ?? e).split('\n')[0].slice(0, 120)})`);
});

const salida = path.join(RAIZ, 'out/diagnostico');
fs.mkdirSync(salida, {recursive: true});

const serveUrl = await empaquetar({outDir: path.join(RAIZ, 'build/diagnostico'), reusar: Boolean(args.reusar)});
const filas = [];

for (const nav of navsElegidos) {
  for (const modo of MODOS) {
    const gl = modo === 'default' ? null : modo;
    const logs = [];
    const fila = {nav, modo, ok: false, webgl2: null, renderer: null, ms: null, error: null};
    let browser = null;
    const t0 = Date.now();
    try {
      browser = await openBrowser('chrome', {
        browserExecutable: NAVS[nav].exe,
        chromiumOptions: {gl},
        logLevel: 'error',
      });
      const onBrowserLog = (l) => logs.push(l.text);
      const composition = await selectComposition({
        serveUrl,
        id: 'DiagnosticoGL',
        puppeteerInstance: browser,
        logLevel: 'error',
        onBrowserLog,
      });
      await renderStill({
        serveUrl,
        composition,
        frame: 30,
        output: path.join(salida, `${nav}-${modo}.png`),
        puppeteerInstance: browser,
        timeoutInMilliseconds: 90000,
        logLevel: 'error',
        onBrowserLog,
      });
      fila.ms = Date.now() - t0;
      const linea = logs.find((t) => t.startsWith('DIAG_GL '));
      if (linea) {
        const info = JSON.parse(linea.slice(8));
        fila.webgl2 = info.webgl2;
        fila.renderer = info.renderer;
        fila.maxSamples = info.maxSamples;
        fila.halfFloatRT = info.halfFloatRT;
      }
      fila.ok = Boolean(fila.webgl2);
    } catch (e) {
      fila.error = String(e.message ?? e).split('\n')[0].slice(0, 160);
      fila.ms = Date.now() - t0;
    } finally {
      await browser?.close({silent: true}).catch(() => {});
    }
    filas.push(fila);
    console.log(
      `${nav.padEnd(10)} ${modo.padEnd(12)} ${fila.ok ? 'OK ' : '-- '} ${String(fila.ms).padStart(6)} ms  ` +
        `${fila.renderer ?? ''} ${fila.maxSamples != null ? 'MSAA≤' + fila.maxSamples : ''} ${fila.error ?? ''}`,
    );
  }
}

fs.writeFileSync(path.join(salida, 'diagnostico.json'), JSON.stringify(filas, null, 2));
console.log(`\nResultados en ${path.relative(RAIZ, salida)}/diagnostico.json`);
