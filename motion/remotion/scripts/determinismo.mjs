// Verifica que cada cuadro sea idéntico (bit a bit, en PNG) sin importar cómo se llega a él:
//   A) still en una pestaña recién montada (como el primer cuadro de un tramo),
//   B) lo mismo en OTRO navegador (otro proceso),
//   C) a mitad de una secuencia (la pestaña ya renderizó los cuadros anteriores),
//   D) primer cuadro de una secuencia (renderFrames en frío: como arranca cada tramo).
// Lo que importa para el render por tramos es C = D (renderMedia usa renderFrames).
// A = B muestra que el resultado no depende del proceso.
//
//   node scripts/determinismo.mjs [--comp PruebaTecnica] [--cuadros 150,300] [--props '{...}'] [--reusar]
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {openBrowser, renderFrames, renderStill, selectComposition} from '@remotion/renderer';
import {RAIZ, empaquetar, leerArgs} from './comun.mjs';
import {opcionesNavegador} from './entorno.mjs';

const a = leerArgs();
const comp = a.comp ?? 'PruebaTecnica';
const cuadros = String(a.cuadros ?? '150,300').split(',').map(Number);
const inputProps = a.props ? JSON.parse(a.props) : {calidad: 'final', depuracion: true, tono: 'agx'};
const dir = path.join(RAIZ, 'out/determinismo');
fs.rmSync(dir, {recursive: true, force: true});
fs.mkdirSync(dir, {recursive: true});
const md5 = (f) => crypto.createHash('md5').update(fs.readFileSync(f)).digest('hex');

const serveUrl = await empaquetar({outDir: path.join(RAIZ, 'build/determinismo'), reusar: Boolean(a.reusar)});
const nav = opcionesNavegador();

const conNavegador = async (fn) => {
  const browser = await openBrowser('chrome', {...nav, logLevel: 'error'});
  try {
    const composition = await selectComposition({serveUrl, id: comp, inputProps, puppeteerInstance: browser, logLevel: 'error'});
    return await fn(browser, composition);
  } finally {
    await browser.close({silent: true}).catch(() => {});
  }
};

const stills = async (etiqueta) =>
  conNavegador(async (browser, composition) => {
    const r = {};
    for (const f of cuadros) {
      const out = path.join(dir, `${etiqueta}-${f}.png`);
      await renderStill({serveUrl, composition, inputProps, frame: f, output: out, imageFormat: 'png', puppeteerInstance: browser, logLevel: 'error'});
      r[f] = md5(out);
    }
    return r;
  });

const A = await stills('A');
const B = await stills('B');
const secuencia = (etiqueta, previos) =>
  conNavegador(async (browser, composition) => {
    const r = {};
    for (const f of cuadros) {
      const sub = path.join(dir, `${etiqueta}-${f}`);
      fs.mkdirSync(sub, {recursive: true});
      await renderFrames({
        serveUrl,
        composition,
        inputProps,
        frameRange: [Math.max(0, f - previos), f],
        outputDir: sub,
        imageFormat: 'png',
        concurrency: 1,
        puppeteerInstance: browser,
        onStart: () => {},
        onFrameUpdate: () => {},
        logLevel: 'error',
      });
      const archivo = fs.readdirSync(sub).filter((n) => n.endsWith('.png')).sort().at(-1);
      r[f] = md5(path.join(sub, archivo));
    }
    return r;
  });

// C: la pestaña llega "caliente" (3 cuadros antes). D: arranca en frío en el cuadro.
const C = await secuencia('C', 3);
const D = await secuencia('D', 0);

let ok = true;
for (const f of cuadros) {
  const tramos = C[f] === D[f];
  const procesos = A[f] === B[f];
  ok &&= tramos && procesos;
  console.log(
    `cuadro ${f}: A ${A[f].slice(0, 8)} B ${B[f].slice(0, 8)} C ${C[f].slice(0, 8)} D ${D[f].slice(0, 8)}  ` +
      `procesos ${procesos ? '✓' : '✗'}  frío=caliente ${tramos ? '✓' : '✗'}  still=secuencia ${A[f] === C[f] ? '✓' : '≠'}`,
  );
}
console.log(ok ? 'DETERMINISMO OK' : 'DETERMINISMO FALLA');
process.exit(ok ? 0 : 1);
