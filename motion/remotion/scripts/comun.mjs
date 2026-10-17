// Utilidades compartidas por los scripts de render (solo Node, no se empaquetan).
import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {bundle} from '@remotion/bundler';

export const RAIZ = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

/** Lee `--clave valor` y `--bandera` de argv. */
export function leerArgs(argv = process.argv.slice(2)) {
  const args = {_: []};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) {
      args._.push(a);
      continue;
    }
    const [k, v] = a.slice(2).split('=');
    if (v !== undefined) args[k] = v;
    else if (argv[i + 1] !== undefined && !argv[i + 1].startsWith('--')) args[k] = argv[++i];
    else args[k] = true;
  }
  return args;
}

/**
 * Empaqueta el proyecto (rspack) una sola vez. Si ya existe `build/` y se pasa
 * `reusar`, devuelve esa carpeta sin recompilar.
 */
export async function empaquetar({outDir = path.join(RAIZ, 'build'), reusar = false} = {}) {
  if (reusar && fs.existsSync(path.join(outDir, 'index.html'))) return outDir;
  let ultimo = -1;
  const serveUrl = await bundle({
    entryPoint: path.join(RAIZ, 'src/index.ts'),
    outDir,
    rspack: true,
    enableCaching: true,
    onProgress: (p) => {
      const d = Math.floor(p / 25) * 25;
      if (d !== ultimo) {
        ultimo = d;
        process.stdout.write(`  empaquetando ${d}%\r`);
      }
    },
  });
  process.stdout.write('\n');
  return serveUrl;
}

const cacheBinarios = {};

/**
 * Ruta de ffmpeg / ffprobe:
 *  1. variable FFMPEG / FFPROBE,
 *  2. el del sistema si está en el PATH,
 *  3. el que trae Remotion (@remotion/compositor-<plataforma>), que incluye libx264,
 *     prores_ks, aac y libfdk_aac. Así funciona también en Windows sin instalar nada.
 */
export function binario(nombre) {
  if (cacheBinarios[nombre]) return cacheBinarios[nombre];
  const env = process.env[nombre.toUpperCase()];
  let ruta = env ?? null;
  if (!ruta && spawnSync(nombre, ['-version'], {stdio: 'ignore'}).status === 0) ruta = nombre;
  if (!ruta) {
    const plat = {
      linux: 'compositor-linux-x64-gnu',
      win32: 'compositor-win32-x64-msvc',
      darwin: process.arch === 'arm64' ? 'compositor-darwin-arm64' : 'compositor-darwin-x64',
    }[process.platform];
    const exe = path.join(RAIZ, 'node_modules/@remotion', plat ?? '', nombre + (process.platform === 'win32' ? '.exe' : ''));
    if (fs.existsSync(exe)) ruta = exe;
  }
  if (!ruta) throw new Error(`No encuentro ${nombre}. Instalalo o definí la variable ${nombre.toUpperCase()}.`);
  cacheBinarios[nombre] = ruta;
  return ruta;
}

/** ffprobe → JSON. */
export function ffprobe(archivo, args = []) {
  const r = spawnSync(
    binario('ffprobe'),
    ['-v', 'error', '-print_format', 'json', ...args, archivo],
    {encoding: 'utf8', maxBuffer: 1 << 28},
  );
  if (r.status !== 0) throw new Error(`ffprobe falló en ${archivo}: ${r.stderr}`);
  return JSON.parse(r.stdout);
}

/** Cantidad exacta de cuadros de video (decodifica el stream). */
export function contarCuadros(archivo) {
  const j = ffprobe(archivo, [
    '-count_frames',
    '-select_streams',
    'v:0',
    '-show_entries',
    'stream=nb_read_frames',
  ]);
  return Number(j.streams?.[0]?.nb_read_frames ?? NaN);
}

/** Cantidad de muestras de audio de un WAV/PCM (por canal). */
export function contarMuestras(archivo) {
  const j = ffprobe(archivo, [
    '-select_streams',
    'a:0',
    '-show_entries',
    'stream=duration_ts,sample_rate,channels,codec_name',
  ]);
  const s = j.streams?.[0] ?? {};
  return {
    muestras: Number(s.duration_ts),
    sampleRate: Number(s.sample_rate),
    canales: Number(s.channels),
    codec: s.codec_name,
  };
}

/** Corre un comando y corta si falla. `cmd` = 'ffmpeg' | 'ffprobe' usa binario(). */
export function correr(cmd, args, {silencioso = false, cwd} = {}) {
  const exe = cmd === 'ffmpeg' || cmd === 'ffprobe' ? binario(cmd) : cmd;
  const r = spawnSync(exe, args, {stdio: silencioso ? 'pipe' : 'inherit', encoding: 'utf8', cwd});
  if (r.status !== 0) {
    throw new Error(`${cmd} ${args.join(' ')}\n${r.stderr ?? ''}`);
  }
  return r;
}

export const seg = (ms) => (ms / 1000).toFixed(1) + ' s';
