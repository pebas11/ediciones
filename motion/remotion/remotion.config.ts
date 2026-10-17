/**
 * Configuración del CLI y del Studio. Las APIs de Node no la leen: los scripts
 * de `scripts/` toman los mismos valores de `scripts/entorno.mjs`.
 *
 * Opciones: https://remotion.dev/docs/config
 */
import {Config} from '@remotion/cli/config';
import {concurrencia, modoGL, navegador} from './scripts/entorno.mjs';

const exe = navegador();
if (exe) {
  Config.setBrowserExecutable(exe);
}
Config.setChromiumOpenGlRenderer(modoGL() as Parameters<typeof Config.setChromiumOpenGlRenderer>[0]);
Config.setConcurrency(concurrencia());

// Bundler más rápido que webpack; probado con three/drei/postprocessing.
Config.setRspack(true);

// Cuadros: JPEG 95 es ~3× más rápido que PNG y no se distingue después de x264.
Config.setVideoImageFormat('jpeg');
Config.setJpegQuality(95);

// Video: H.264 yuv420p con espacio de color BT.709 declarado (evita corrimientos de color en YouTube).
Config.setCodec('h264');
Config.setPixelFormat('yuv420p');
Config.setColorSpace('bt709');
Config.setCrf(16);

// El primer cuadro de una escena 3D compila shaders; con SwiftShader puede tardar.
Config.setDelayRenderTimeoutInMilliseconds(120000);
Config.setOverwriteOutput(true);
