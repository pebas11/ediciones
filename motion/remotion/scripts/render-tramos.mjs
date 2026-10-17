// Render por TRAMOS, reanudable, para videos largos.
//
//   node scripts/render-tramos.mjs <Composicion> [opciones]
//
// Opciones:
//   --props '<json>' | --props @archivo.json   props de la composición
//   --tramo 30            segundos por tramo (por defecto 30)
//   --por-escena          cortar en los inicios de escena de la hoja de cues (props.hoja);
//                         las escenas largas se subdividen con --tramo
//   --min-tramo 3         segundos: tramos más cortos se unen al anterior
//   --rango 0-3599        renderizar solo esos cuadros
//   --procesos 1          tramos en paralelo (cada uno con su navegador)
//   --concurrencia 2      pestañas por proceso
//   --perfil intermedio   intermedio (H.264 CRF 10) | final (CRF 17 slow) | prores (422 HQ)
//   --salida out/tramos/<Composicion>
//   --solo 3,7            volver a renderizar esos tramos
//   --conservar           no rehacer tramos viejos aunque haya cambiado el código
//   --rehacer             borrar los tramos y empezar de cero
//   --sin-audio           no generar audio
//   --no-unir             no unir al final
//   --youtube             al terminar, codificar youtube.mp4
//   --reusar              reusar build/ sin reempaquetar
//
// Cómo se reanuda: cada tramo se escribe como .part y se renombra solo si tiene la
// cantidad exacta de cuadros y de muestras. manifiesto.json guarda el plan, la firma
// (composición, fps, rango, props, perfil) y un hash del código (src/ + public/) por
// tramo. Si se corta (Ctrl+C, reinicio, error), correr el mismo comando: rinde solo
// lo que falta. Si cambió el código, rehace los tramos con hash viejo (salvo --conservar).
import {spawn} from 'node:child_process';
import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import {openBrowser, selectComposition} from '@remotion/renderer';
import {RAIZ, empaquetar, leerArgs} from './comun.mjs';
import {concurrencia, opcionesNavegador} from './entorno.mjs';
import {unirTramos} from './unir.mjs';

const a = leerArgs();
const comp = a._[0];
if (!comp) {
  console.error('Uso: node scripts/render-tramos.mjs <Composicion> [--tramo 30] [--por-escena] [--procesos 1] ...');
  process.exit(1);
}
const props = a.props
  ? JSON.parse(String(a.props).startsWith('@') ? fs.readFileSync(String(a.props).slice(1), 'utf8') : a.props)
  : {};
const perfil = a.perfil ?? 'intermedio';
const ext = perfil === 'prores' ? 'mov' : 'ts';
const dir = path.resolve(a.salida ?? path.join(RAIZ, 'out/tramos', comp));
const procesos = Math.max(1, Number(a.procesos ?? 1));
const conc = a.concurrencia ? Number(a.concurrencia) : concurrencia();
const conAudio = !a['sin-audio'];
const reintentos = Number(a.reintentos ?? 2);
const sha = (s) => crypto.createHash('sha256').update(s).digest('hex').slice(0, 16);

/** Hash del código y los datos: src/ completo; public/ por contenido (archivos chicos) o tamaño+fecha. */
const hashFuente = () => {
  const h = crypto.createHash('sha256');
  const recorrer = (base, contenidoMax) => {
    if (!fs.existsSync(base)) return;
    const archivos = fs.readdirSync(base, {recursive: true, withFileTypes: true})
      .filter((d) => d.isFile())
      .map((d) => path.join(d.parentPath ?? d.path, d.name))
      .sort();
    for (const f of archivos) {
      const st = fs.statSync(f);
      h.update(path.relative(RAIZ, f));
      h.update(st.size <= contenidoMax ? fs.readFileSync(f) : `${st.size}:${st.mtimeMs}`);
    }
  };
  recorrer(path.join(RAIZ, 'src'), Infinity);
  recorrer(path.join(RAIZ, 'public'), 2 * 1024 * 1024);
  return h.digest('hex').slice(0, 16);
};

const escribirManifiesto = (man) => {
  const tmp = path.join(dir, 'manifiesto.json.tmp');
  fs.writeFileSync(tmp, JSON.stringify(man, null, 2));
  fs.renameSync(tmp, path.join(dir, 'manifiesto.json'));
};

// --- 1. Empaquetar y leer la composición ---------------------------------------
fs.mkdirSync(dir, {recursive: true});
console.log(`Empaquetando…`);
// Bundle propio por composición: otro render en paralelo no pisa el de este.
const serveUrl = await empaquetar({outDir: path.join(RAIZ, 'build', comp), reusar: Boolean(a.reusar)});
const nav = opcionesNavegador();
const browser = await openBrowser('chrome', {...nav, logLevel: 'error'});
const composition = await selectComposition({
  serveUrl,
  id: comp,
  inputProps: props,
  puppeteerInstance: browser,
  logLevel: 'error',
});
await browser.close({silent: true});
const {fps, durationInFrames: dur} = composition;
const [r0, r1] = a.rango ? String(a.rango).split('-').map(Number) : [0, dur - 1];
if (!(r0 >= 0 && r1 < dur && r1 >= r0)) throw new Error(`Rango inválido ${r0}-${r1} (la composición tiene ${dur} cuadros)`);

// --- 2. Plan de tramos ----------------------------------------------------------
const maxTramo = Math.max(1, Math.round(Number(a.tramo ?? 30) * fps));
const minTramo = Math.round(Number(a['min-tramo'] ?? 3) * fps);
let cortes = [r0];
if (a['por-escena']) {
  const hoja = composition.props?.hoja;
  if (!hoja?.escenas) throw new Error('--por-escena necesita una composición con hoja de cues (props.hoja)');
  for (const e of hoja.escenas) cortes.push(Math.round(e.inicio * fps));
}
cortes = [...new Set(cortes)].filter((c) => c >= r0 && c <= r1).sort((x, y) => x - y);
cortes.push(r1 + 1);
let bloques = [];
for (let k = 0; k < cortes.length - 1; k++) {
  const [ini, fin] = [cortes[k], cortes[k + 1] - 1];
  if (bloques.length && fin - ini + 1 < minTramo) bloques.at(-1)[1] = fin; // muy corto: al anterior
  else bloques.push([ini, fin]);
}
const plan = [];
for (const [ini, fin] of bloques) {
  const n = fin - ini + 1;
  const partes = Math.ceil(n / maxTramo);
  for (let p = 0; p < partes; p++) {
    plan.push([ini + Math.floor((p * n) / partes), ini + Math.floor(((p + 1) * n) / partes) - 1]);
  }
}

// --- 3. Manifiesto (reanudar o empezar) ----------------------------------------
const firma = {
  composicion: comp,
  fps,
  duracion: dur,
  rango: [r0, r1],
  perfil,
  props: sha(JSON.stringify(props)),
  audio: conAudio,
  plan: sha(JSON.stringify(plan)),
};
const rutaMan = path.join(dir, 'manifiesto.json');
let man = fs.existsSync(rutaMan) ? JSON.parse(fs.readFileSync(rutaMan, 'utf8')) : null;
if (man && a.rehacer) {
  for (const f of fs.readdirSync(dir)) if (/^tramo-|^manifiesto|^lista-/.test(f)) fs.rmSync(path.join(dir, f));
  man = null;
}
if (man && JSON.stringify(man.firma) !== JSON.stringify(firma)) {
  const dif = Object.keys(firma).filter((k) => JSON.stringify(firma[k]) !== JSON.stringify(man.firma[k]));
  console.error(
    `Los tramos de ${path.relative(RAIZ, dir)} son de otro render (cambió: ${dif.join(', ')}).\n` +
      `Usá --rehacer para empezar de cero o --salida para otra carpeta.`,
  );
  process.exit(2);
}
const fuente = hashFuente();
const pad = (i) => String(i).padStart(3, '0');
if (!man) {
  man = {
    firma,
    creado: new Date().toISOString(),
    fps,
    tramos: plan.map(([desde, hasta], i) => ({
      i,
      desde,
      hasta,
      video: `tramo-${pad(i)}.${ext}`,
      audio: conAudio ? `tramo-${pad(i)}.wav` : null,
      estado: 'pendiente',
    })),
  };
}
const solo = a.solo ? String(a.solo).split(',').map(Number) : null;
for (const t of man.tramos) {
  const existe = fs.existsSync(path.join(dir, t.video)) && (!t.audio || fs.existsSync(path.join(dir, t.audio)));
  if (t.estado === 'listo' && !existe) t.estado = 'pendiente';
  if (t.estado === 'listo' && t.fuente !== fuente && !a.conservar) {
    console.log(`  tramo ${t.i}: el código cambió desde que se renderizó → se rehace (--conservar para evitarlo)`);
    t.estado = 'pendiente';
  }
  if (solo?.includes(t.i)) t.estado = 'pendiente';
}
escribirManifiesto(man);
const pendientes = man.tramos.filter((t) => t.estado !== 'listo');
const totalCuadros = r1 - r0 + 1;
console.log(
  `${comp}: ${totalCuadros} cuadros (${(totalCuadros / fps).toFixed(1)} s) en ${man.tramos.length} tramos; ` +
    `pendientes ${pendientes.length}. Procesos ${procesos} × pestañas ${conc}, perfil ${perfil}.`,
);

// --- 4. Render en paralelo con reintentos ---------------------------------------
const avance = new Map();
let ultimoReporte = 0;
const reportar = (forzar = false) => {
  if (!forzar && Date.now() - ultimoReporte < 10000) return;
  ultimoReporte = Date.now();
  const hechos = man.tramos.filter((t) => t.estado === 'listo').reduce((s, t) => s + t.hasta - t.desde + 1, 0);
  const enCurso = [...avance.values()].reduce((s, v) => s + v, 0);
  const pct = (((hechos + enCurso) / totalCuadros) * 100).toFixed(1);
  console.log(`  ${pct}% (${hechos + enCurso}/${totalCuadros} cuadros)`);
};

const renderTramo = (t) =>
  new Promise((resolve) => {
    const argv = [
      path.join(RAIZ, 'scripts/render-rango.mjs'),
      '--serve-url', serveUrl,
      '--comp', comp,
      '--desde', String(t.desde),
      '--hasta', String(t.hasta),
      '--salida', path.join(dir, t.video),
      '--perfil', perfil,
      '--concurrencia', String(conc),
      '--props', JSON.stringify(props),
    ];
    if (t.audio) argv.push('--audio', path.join(dir, t.audio));
    const p = spawn(process.execPath, argv, {stdio: ['ignore', 'pipe', 'pipe']});
    let fin = null;
    let error = '';
    p.stdout.on('data', (b) => {
      for (const l of b.toString().split('\n')) {
        if (!l.startsWith('{')) continue;
        const o = JSON.parse(l);
        if (o.evento === 'progreso') {
          avance.set(t.i, o.renderizados);
          reportar();
        }
        if (o.evento === 'listo') fin = o;
        if (o.evento === 'error') error = o.mensaje;
      }
    });
    p.stderr.on('data', (b) => (error += b.toString()));
    p.on('close', (code) => {
      avance.delete(t.i);
      resolve(code === 0 && fin ? {ok: true, fin} : {ok: false, error: error.slice(-1500)});
    });
  });

const t0 = Date.now();
const cola = [...pendientes];
const intentos = new Map();
let fallidos = 0;
await new Promise((resolve) => {
  let activos = 0;
  const lanzar = () => {
    if (cola.length === 0 && activos === 0) return resolve();
    while (activos < procesos && cola.length) {
      const t = cola.shift();
      activos++;
      renderTramo(t).then((r) => {
        activos--;
        if (r.ok) {
          Object.assign(t, {
            estado: 'listo',
            fuente,
            ms: r.fin.ms,
            fpsEstable: r.fin.fpsEstable && +r.fin.fpsEstable.toFixed(3),
            terminado: new Date().toISOString(),
          });
          escribirManifiesto(man);
          console.log(`  ✓ tramo ${t.i} (${t.desde}–${t.hasta}) en ${(r.fin.ms / 1000).toFixed(1)} s`);
        } else {
          const n = (intentos.get(t.i) ?? 0) + 1;
          intentos.set(t.i, n);
          console.log(`  ✗ tramo ${t.i} falló (intento ${n}): ${r.error.split('\n').slice(-4).join(' | ')}`);
          if (n <= reintentos) cola.push(t);
          else fallidos++;
        }
        lanzar();
      });
    }
  };
  lanzar();
});
reportar(true);
const seg = (Date.now() - t0) / 1000;
const hechos = pendientes.reduce((s, t) => s + (t.estado === 'listo' ? t.hasta - t.desde + 1 : 0), 0);
console.log(`Render: ${hechos} cuadros en ${seg.toFixed(0)} s (${(hechos / Math.max(seg, 1e-3)).toFixed(2)} fps)`);
if (fallidos) {
  console.error(`${fallidos} tramo(s) fallaron. Corregir y volver a correr el mismo comando (reanuda).`);
  process.exit(1);
}

// --- 5. Unión sin recomprimir (+ YouTube) --------------------------------------
if (!a['no-unir']) {
  const r = unirTramos(dir);
  console.log(r.resumen);
  if (a.youtube) {
    const p = spawn(
      process.execPath,
      [
        path.join(RAIZ, 'scripts/codificar-youtube.mjs'),
        r.archivo,
        path.join(dir, 'youtube.mp4'),
        // Con el perfil "final" el video ya está en calidad de entrega: solo audio a AAC.
        ...(perfil === 'final' ? ['--copiar-video'] : []),
      ],
      {stdio: 'inherit'},
    );
    await new Promise((res) => p.on('close', res));
  }
}
