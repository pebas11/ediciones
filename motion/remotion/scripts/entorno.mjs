// Ajustes de render compartidos por remotion.config.ts (CLI y Studio) y por los scripts de Node.
// Una sola fuente de verdad para navegador, modo GL y concurrencia.
//
// Variables de entorno que pisan los valores por defecto:
//   REMOTION_BROWSER       ruta a un Chrome/Chromium (headless shell) propio
//   REMOTION_GL            angle | swangle | swiftshader | egl | vulkan | angle-egl
//   REMOTION_CONCURRENCY   pestañas en paralelo por proceso (número o "50%")
//
// Nota: no usar import.meta acá. remotion.config.ts se empaqueta a CommonJS y
// import.meta.url queda vacío.
import fs from 'node:fs';
import path from 'node:path';

/** Headless shell que baja Remotion (`npx remotion browser ensure`). */
export const rutaShellRemotion = (raiz = process.cwd()) =>
  path.join(
    raiz,
    'node_modules/.remotion/chrome-headless-shell/linux64/chrome-headless-shell-linux64/chrome-headless-shell',
  );

/** Headless shell preinstalado por Playwright en el contenedor (Chromium 141). */
export const SHELL_PLAYWRIGHT =
  '/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell';

/**
 * Navegador a usar. `null` = que Remotion use (o baje) su propio Chrome Headless Shell.
 * - Windows/macOS: siempre null (Remotion baja su Chrome la primera vez).
 * - Linux: si Remotion ya bajó el suyo, null; si no (proxy sin salida), el de Playwright.
 */
export function navegador(raiz = process.cwd()) {
  if (process.env.REMOTION_BROWSER) return process.env.REMOTION_BROWSER;
  if (process.platform !== 'linux') return null;
  if (fs.existsSync(rutaShellRemotion(raiz))) return null;
  if (fs.existsSync(SHELL_PLAYWRIGHT)) return SHELL_PLAYWRIGHT;
  return null;
}

/**
 * Modo de WebGL.
 * - Linux sin GPU (este contenedor): "swangle" = ANGLE sobre SwiftShader (CPU). Medido en README.
 * - Windows/macOS con GPU: "angle" = ANGLE sobre D3D11/Metal (GPU real).
 */
export function modoGL() {
  if (process.env.REMOTION_GL) return process.env.REMOTION_GL;
  return process.platform === 'linux' ? 'swangle' : 'angle';
}

/** Pestañas por proceso. En el contenedor de 4 núcleos compartido: 2 como máximo. */
export function concurrencia() {
  const v = process.env.REMOTION_CONCURRENCY;
  if (v) return /%$/.test(v) ? v : Number(v);
  return process.platform === 'linux' ? 2 : '50%';
}

/** Opciones listas para las APIs de Node (@remotion/renderer). */
export function opcionesNavegador(raiz = process.cwd()) {
  return {
    browserExecutable: navegador(raiz),
    chromiumOptions: {gl: modoGL()},
  };
}
