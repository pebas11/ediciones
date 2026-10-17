// Mide fps de render de PruebaTecnica con distintos ajustes.
//
//   node scripts/bench.mjs                                  # casos por defecto
//   node scripts/bench.mjs --casos final-c1,final-c2,final-p2 --cuadros 300-359
//   node scripts/bench.mjs --lista                           # ver casos disponibles
//
// Cada caso lanza uno o más procesos render-rango.mjs (cada proceso = un navegador)
// y mide el tiempo de pared. "fps" = cuadros / tiempo total (incluye arranque);
// "fps estable" descuenta el arranque (abrir navegador, cargar página, compilar shaders).
import {spawn} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {RAIZ, empaquetar, leerArgs} from './comun.mjs';
import {SHELL_PLAYWRIGHT} from './entorno.mjs';

const FINAL = {calidad: 'final', depuracion: false, tono: 'agx'};
const CASOS = {
  'final-c1': {props: FINAL, concurrencia: 1, procesos: 1},
  'final-c2': {props: FINAL, concurrencia: 2, procesos: 1},
  'final-p2': {props: FINAL, concurrencia: 1, procesos: 2},
  'borrador-c2': {props: {...FINAL, calidad: 'borrador'}, concurrencia: 2, procesos: 1},
  'sin-msaa-c1': {props: {...FINAL, perfil: {msaa: 0}}, concurrencia: 1, procesos: 1},
  'sin-dof-c1': {props: {...FINAL, perfil: {dof: false}}, concurrencia: 1, procesos: 1},
  'sin-post-c1': {props: {...FINAL, perfil: {postproceso: false}}, concurrencia: 1, procesos: 1},
  'sin-particulas-c1': {props: {...FINAL, perfil: {particulas: 0}}, concurrencia: 1, procesos: 1},
  'sombra1024-c1': {props: {...FINAL, perfil: {sombra: 1024}}, concurrencia: 1, procesos: 1},
  'sin-grano-c1': {props: {...FINAL, perfil: {grano: false}}, concurrencia: 1, procesos: 1},
  'solo-2d-c1': {props: {...FINAL, perfil: {sin3d: true}}, concurrencia: 1, procesos: 1},
  'solo-2d-sin-grano-c1': {props: {...FINAL, perfil: {sin3d: true, grano: false}}, concurrencia: 1, procesos: 1},
  'solo-2d-png-c1': {props: {...FINAL, perfil: {sin3d: true}}, concurrencia: 1, procesos: 1, imagen: 'png'},
  '2d-solo-vineta-c1': {props: {...FINAL, perfil: {sin3d: true, grano: false, trazos: false, texto: false}}, concurrencia: 1, procesos: 1},
  '2d-solo-trazos-c1': {props: {...FINAL, perfil: {sin3d: true, grano: false, vineta: false, texto: false}}, concurrencia: 1, procesos: 1},
  '2d-solo-texto-c1': {props: {...FINAL, perfil: {sin3d: true, grano: false, vineta: false, trazos: false}}, concurrencia: 1, procesos: 1},
  '2d-nada-c1': {props: {...FINAL, perfil: {sin3d: true, grano: false, vineta: false, trazos: false, texto: false}}, concurrencia: 1, procesos: 1},
  'vacia-c1': {props: {}, concurrencia: 1, procesos: 1, comp: 'Vacia'},
  'png-c1': {props: FINAL, concurrencia: 1, procesos: 1, imagen: 'png'},
  'msaa2-c1': {props: {...FINAL, perfil: {msaa: 2}}, concurrencia: 1, procesos: 1},
  'dof035-c1': {props: {...FINAL, perfil: {dofEscala: 0.35}}, concurrencia: 1, procesos: 1},
  'bufer8-c1': {props: {...FINAL, perfil: {bufer8: true}}, concurrencia: 1, procesos: 1},
  'rapido-c1': {props: {...FINAL, perfil: {msaa: 2, dofEscala: 0.35, bufer8: true}}, concurrencia: 1, procesos: 1},
  'rapido-c2': {props: {...FINAL, perfil: {msaa: 2, dofEscala: 0.35, bufer8: true}}, concurrencia: 2, procesos: 1},
  'rapido-p2': {props: {...FINAL, perfil: {msaa: 2, dofEscala: 0.35, bufer8: true}}, concurrencia: 1, procesos: 2},
  'dpr075-c1': {props: {...FINAL, perfil: {dpr: 0.75}}, concurrencia: 1, procesos: 1},
  'solo-2d-c2': {props: {...FINAL, perfil: {sin3d: true}}, concurrencia: 2, procesos: 1},
  'granocss-c1': {props: {...FINAL, perfil: {granoCss: true}}, concurrencia: 1, procesos: 1},
  'playwright-c1': {props: FINAL, concurrencia: 1, procesos: 1, navegador: SHELL_PLAYWRIGHT},
  'default-gl-c1': {props: FINAL, concurrencia: 1, procesos: 1, gl: 'default'},
  'final-perfil-final-c2': {props: FINAL, concurrencia: 2, procesos: 1, perfil: 'final'},
};

/**
 * Segundos de CPU consumidos por los procesos hijos ya terminados (y sus descendientes):
 * campos cutime + cstime de /proc/self/stat. En una máquina compartida es una medida de
 * COSTO mucho más estable que el tiempo de pared. Solo Linux (en otros SO devuelve null).
 */
const TICKS = 100;
const cpuHijos = () => {
  if (process.platform !== 'linux') return null;
  const campos = fs.readFileSync('/proc/self/stat', 'utf8').split(') ')[1].split(' ');
  return (Number(campos[13]) + Number(campos[14])) / TICKS;
};

const args = leerArgs();
if (args.lista) {
  console.log(Object.keys(CASOS).join('\n'));
  process.exit(0);
}
const elegidos = (args.casos ?? 'final-c1,final-c2,final-p2,borrador-c2').split(',');
const [desde, hasta] = (args.cuadros ?? '300-359').split('-').map(Number);
const comp = args.comp ?? 'PruebaTecnica';
const salida = path.join(RAIZ, 'out/bench');
fs.mkdirSync(salida, {recursive: true});

const serveUrl = await empaquetar({outDir: path.join(RAIZ, 'build/bench'), reusar: Boolean(args.reusar)});

const correrWorker = (caso, d, h, sufijo) =>
  new Promise((resolve, reject) => {
    const argv = [
      path.join(RAIZ, 'scripts/render-rango.mjs'),
      '--serve-url', serveUrl,
      '--comp', caso.comp ?? comp,
      '--desde', String(d),
      '--hasta', String(h),
      '--salida', path.join(salida, `${sufijo}.${caso.perfil === 'prores' ? 'mov' : 'ts'}`),
      '--concurrencia', String(caso.concurrencia),
      '--props', JSON.stringify(caso.props),
      '--perfil', caso.perfil ?? 'intermedio',
    ];
    if (caso.imagen) argv.push('--imagen', caso.imagen);
    if (caso.navegador) argv.push('--navegador', caso.navegador);
    if (caso.gl) argv.push('--gl', caso.gl);
    const p = spawn(process.execPath, argv, {stdio: ['ignore', 'pipe', 'pipe']});
    let fin = null;
    let err = '';
    p.stdout.on('data', (b) => {
      for (const l of b.toString().split('\n')) {
        if (!l.startsWith('{')) continue;
        const o = JSON.parse(l);
        if (o.evento === 'listo') fin = o;
        if (o.evento === 'error') err = o.mensaje;
      }
    });
    p.stderr.on('data', (b) => (err += b.toString()));
    p.on('close', (code) => (code === 0 && fin ? resolve(fin) : reject(new Error(err.slice(-800)))));
  });

const resultados = [];
for (const nombre of elegidos) {
  const caso = CASOS[nombre];
  if (!caso) {
    console.log(`(caso desconocido: ${nombre})`);
    continue;
  }
  const n = hasta - desde + 1;
  const partes = Array.from({length: caso.procesos}, (_, k) => {
    const a = desde + Math.floor((k * n) / caso.procesos);
    const b = desde + Math.floor(((k + 1) * n) / caso.procesos) - 1;
    return [a, b];
  });
  const carga = os.loadavg()[0];
  const cpu0 = cpuHijos();
  const t0 = Date.now();
  try {
    const fins = await Promise.all(partes.map(([a, b], k) => correrWorker(caso, a, b, `${nombre}-${k}`)));
    const ms = Date.now() - t0;
    const arranque = Math.max(...fins.map((f) => f.primerCuadroMs ?? 0));
    const cpu = cpu0 === null ? null : cpuHijos() - cpu0;
    const r = {
      caso: nombre,
      cuadros: n,
      segundos: +(ms / 1000).toFixed(1),
      fps: +(n / (ms / 1000)).toFixed(2),
      fpsEstable: +((n - caso.procesos) / ((ms - arranque) / 1000)).toFixed(2),
      arranqueS: +(arranque / 1000).toFixed(1),
      cargaAntes: +carga.toFixed(2),
      cpuS: cpu === null ? null : +cpu.toFixed(1),
      cpuPorCuadroS: cpu === null ? null : +(cpu / n).toFixed(2),
    };
    resultados.push(r);
    console.log(
      `${nombre.padEnd(22)} ${String(r.fps).padStart(6)} fps  estable ${String(r.fpsEstable).padStart(6)}  ` +
        `CPU ${r.cpuPorCuadroS ?? '-'} s/cuadro  (${r.segundos}s, arranque ${r.arranqueS}s, carga ${r.cargaAntes})`,
    );
  } catch (e) {
    console.log(`${nombre.padEnd(22)} ERROR ${String(e.message).split('\n').slice(-3).join(' ')}`);
    resultados.push({caso: nombre, error: String(e.message).slice(0, 500)});
  }
  fs.writeFileSync(path.join(salida, 'bench.json'), JSON.stringify(resultados, null, 2));
}
console.log(`\nResultados en out/bench/bench.json`);
