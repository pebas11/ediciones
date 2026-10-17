# Remotion: base de render para videos largos

Infraestructura para un video de YouTube de 5 a 20 minutos en 1920×1080 a 60 fps. Combina 3D real (Three.js con React Three Fiber), capas 2D, la voz en off con transcripción palabra por palabra y música en stems.

**El estilo visual todavía no está definido.** Todo lo que se ve en las composiciones de prueba es técnico: sirve para medir y validar capacidades, no como propuesta estética.

- Remotion **4.0.528** (fijado; coincide con la versión de las skills `remotion:*`).
- React 19.2.3, three 0.186.1, @react-three/fiber 9.8.1, drei 10.7.9 y postprocessing 6.39.5.
- `npx remotion versions` da "All packages have the correct version".

---

## 1. Instalación

### Linux (este contenedor)
```bash
cd motion/remotion
npm ci                        # o npm install
npx remotion browser ensure   # baja Chrome Headless Shell 149 (pasa por el proxy)
python3 -c "import numpy, scipy"   # para scripts/envolventes.py y verificar-sync.py
```
- Si el proxy bloquea la descarga del navegador, `scripts/entorno.mjs` usa solo el Chromium 141 de Playwright: `/opt/pw-browsers/chromium_headless_shell-1194/chrome-linux/headless_shell`.
- También podés forzar cualquier navegador con `REMOTION_BROWSER=/ruta/al/headless_shell`.

### Windows (con GPU)
1. Instalar Node 22 LTS y Python 3.12+ (con `pip install numpy scipy`).
2. Correr:
   ```powershell
   cd motion\remotion
   npm ci
   npx remotion browser ensure
   ```
   Remotion baja su propio Chrome Headless Shell para win64.
3. ffmpeg no hace falta: los scripts usan el que trae Remotion (`node_modules/@remotion/compositor-win32-x64-msvc/ffmpeg.exe`) si no hay uno en el PATH.
4. Verificar que WebGL use la GPU:
   ```powershell
   node scripts/diagnostico-gl.mjs --modos angle,default --navegadores remotion
   ```
   La columna renderer tiene que nombrar la placa (por ejemplo, `ANGLE (NVIDIA, ... Direct3D11 ...)`). Si dice `SwiftShader`, está renderizando por CPU.

## 2. Estructura

```
remotion.config.ts        CLI y Studio (navegador, GL, JPEG 95, H.264 yuv420p BT.709)
scripts/entorno.mjs       ÚNICA fuente de navegador / modo GL / concurrencia (CLI + scripts)
src/Root.tsx              composiciones
src/composiciones/
  PruebaTecnica.tsx       prueba de 10 s: 3D + 2D + overlay + audio + depuración
  LineaDeTiempo.tsx       línea de tiempo maestra desde una hoja de cues (JSON)
  DiagnosticoGL.tsx       qué WebGL hay en el navegador de render
  PruebaDrei.tsx          componentes de drei deterministas (entorno, sombras, texto 3D)
  PruebaGoogleFonts.tsx   diagnóstico de @remotion/google-fonts
src/escenas/              escenas de EJEMPLO + registro "tipo de la hoja → componente"
src/lib/
  tiempo.ts               cuadro absoluto (ProveedorTiempoAbsoluto), segundos ↔ cuadros
  transcripcion.ts        palabras, frases, palabra/frase actual, búsqueda de palabras clave
  cues.ts                 esquema (zod) y resolución de la hoja de cues a cuadros
  transiciones.tsx        tipo de transición de la hoja → presentación de @remotion/transitions
  audio.ts                envolventes precalculadas: nivel, bandas, onsets, beats, ducking
  movimiento.ts           curvas, springs (estilo SwiftUI), duraciones, ruido sembrado
  camara.ts               rig de cámara puro + proyección 3D→2D + parallax
  azar.ts                 azar determinista (random() de Remotion)
  datos.ts                carga de JSON con delayRender y caché
  fuentes.ts              League Spartan / DM Sans / DM Mono locales (public/fuentes)
src/three/                CamaraRig, Postproceso (composer propio), PaseCapa, EfectoGrano,
                          materiales con shader propio, Particulas, Ensueno, Cielo, Texto3D
src/capas/                Grano y Viñeta CSS, CapaParallax, Trazo (SVG), Titulo,
                          LineaDePalabras, Depuracion (código de cuadro)
scripts/                  bench, diagnóstico GL, render por tramos, unir, YouTube,
                          envolventes.py, verificar-sync.py, generar-prueba.py
public/                   audio/, datos/ (JSON), fuentes/
```

## 3. Comandos

| Qué | Linux | Windows (PowerShell) |
|---|---|---|
| Studio (preview) | `npx remotion studio` | igual |
| Un cuadro | `npx remotion still PruebaTecnica out/f300.png --frame=300` | igual |
| Varios cuadros | `npx remotion render PruebaTecnica out/hoja --sequence --frames=0,150,300` | igual |
| Video corto directo | `npx remotion render PruebaTecnica out/prueba.mp4` | igual |
| Video largo por tramos | `node scripts/render-tramos.mjs VideoEjemplo --por-escena --perfil final --youtube` | igual |
| Borrador rápido | `npx remotion render VideoEjemplo out/borrador.mp4 --props='{"hojaSrc":"datos/cues-ejemplo.json","calidad":"borrador"}' --scale=0.5` | `--props` con comillas escapadas o `--props=props.json` |
| Diagnóstico de GL | `node scripts/diagnostico-gl.mjs` | igual |
| Benchmark | `node scripts/bench.mjs --casos final-c1,final-c2,final-p2` | igual |
| Envolventes de audio | `python3 scripts/envolventes.py --fps 60 --salida public/datos/envolventes.json --pista voz=... --cues ...` | `python scripts\envolventes.py ...` |
| Verificar sincronía | `python3 scripts/verificar-sync.py out/tramos/PruebaTecnica/youtube.mp4` | igual |

Notas:
- En el Studio sin GPU la previsualización de las escenas 3D es lenta. Con `{"calidad":"borrador"}` se renderiza el 3D a media resolución, sin postproceso.
- El render por tramos va en background: es largo (ver §5).

## 4. Navegador y WebGL

### Lo que hay en el contenedor (medido con `scripts/diagnostico-gl.mjs`)
No hay GPU: el único backend real es **SwiftShader** (Vulkan por CPU) detrás de ANGLE. El renderer siempre informa `ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero)), SwiftShader driver)`, WebGL 2, MSAA hasta 4× y render targets float y half-float.

| `--gl` | Chrome Headless Shell 149 (Remotion) | Chromium 141 (Playwright) |
|---|---|---|
| (sin flag) | funciona (SwiftShader, aviso "automatic fallback deprecated") | funciona |
| `swangle` | **funciona (elegido)** | funciona |
| `angle` | sin WebGL | funciona (cae a SwiftShader) |
| `swiftshader` | sin WebGL | funciona (SwiftShader) |
| `egl` | sin WebGL | funciona (SwiftShader) |
| `vulkan` | sin WebGL | funciona (SwiftShader) |
| `angle-egl` | sin WebGL | funciona (SwiftShader) |

**Elegido para Linux sin GPU: `swangle`** (`--use-gl=angle --use-angle=swiftshader`). Es explícito, funciona en los dos navegadores y no depende del fallback automático que Chrome ya marcó como obsoleto. Rinde igual que el modo por defecto porque usan el mismo backend.

### Windows con GPU
- `scripts/entorno.mjs` elige **`angle`** en Windows y macOS: ANGLE sobre Direct3D 11 (Metal en Mac) usa la placa.
- Remotion baja su Chrome Headless Shell, así que no hace falta `browserExecutable`.
- Otras opciones: `REMOTION_GL=vulkan` (solo si los drivers son buenos) o `REMOTION_GL=default`.
- Concurrencia por defecto en Windows: `50%` de los hilos. Con GPU conviene probar 4–8 pestañas: `node scripts/bench.mjs --casos final-c2` (editar la concurrencia del caso) o `REMOTION_CONCURRENCY=6`.
- Siempre verificar con `diagnostico-gl.mjs` que el renderer nombre la GPU.

## 5. Rendimiento (medido en este contenedor)

Máquina: 4 núcleos, 15 GB, **sin GPU** (SwiftShader). Composición `PruebaTecnica` en calidad final, 1920×1080, capturas JPEG 95 y tramos H.264 CRF 10 veryfast. Medido con `scripts/bench.mjs`.

Ojo: la máquina se comparte con otros agentes. Hubo momentos con un benchmark de whisper (~1,5 núcleos) y un render de música (~1 núcleo) corriendo a la vez, y las cifras de pared varían ±25 % según la carga. Por eso cada número lleva su contexto, y `bench.mjs` también informa los segundos de CPU por cuadro.

### Concurrencia (lo más importante)
| Configuración | fps estable | s por cuadro |
|---|---|---|
| 1 proceso × 1 pestaña (`final-c1`) | 0,23–0,26 | 3,8–4,3 |
| 1 proceso × 2 pestañas (`final-c2`) | 0,23 | 4,3 |
| 2 procesos × 1 pestaña (`final-p2`) | 0,24 | 4,2 |
| Ajustes rápidos, 2 procesos (`rapido-p2`) | 0,28 | 3,6 |
| Calidad borrador, 2 pestañas (`borrador-c2`) | 0,93–1,03 | ~1,0 |

**Más pestañas o procesos NO aceleran el 3D en esta máquina.** SwiftShader ya reparte el rasterizado en ~2,5 núcleos con UNA pestaña (el proceso GPU de Chrome llega a 240 % de CPU), y las pestañas de un mismo navegador comparten ese proceso. Con 2 procesos hay dos procesos GPU que compiten por los mismos 4 núcleos. Por eso, dentro del límite de 2 que se pidió, da lo mismo: `render-tramos.mjs` usa 1 proceso × 2 pestañas por defecto.

### Costo de cada parte (s por cuadro, 1 pestaña)
| Parte | Costo | Cómo se midió |
|---|---|---|
| Fijo: React + captura JPEG + envío + x264 | ~0,12 | composición vacía: 7,8 fps |
| Postproceso completo (composer HalfFloat + MSAA 4× + DOF + tone mapping + capa) | ~1,8 | `final` 3,8 → `sin-post` 2,0 |
| DOF (bokeh a media resolución) | ~0,9 | `sin-dof` 2,9 |
| MSAA 4× | ~0,4 | `sin-msaa` 3,4 |
| Escena 3D sin postproceso (sombras 2048, PBR, niebla, 50k partículas) | ~1,2 | `sin-post` − capas 2D |
| 50k partículas / shadow map 1024 en vez de 2048 | < 0,1 (dentro del ruido) | `sin-particulas`, `sombra1024` |
| Viñeta CSS `radial-gradient` a pantalla completa | 0,23, o 0,04 con `will-change` | capas 2D sueltas, 60 cuadros |
| Trazos SVG a pantalla completa (capa de parallax) | ~0,2 | ídem |
| Texto (titular + frase) | ~0,03 | ídem |
| Grano CSS | 0,13 (fusión normal) a 0,45 (`mix-blend-mode`) | ídem |
| Grano + viñeta en WebGL (`EfectoGrano`) | ~0 | van en el pase del tone mapping |
| Capturas PNG en vez de JPEG | +0,6 | `solo-2d-png` |

### Estimaciones
Un minuto de video a 60 fps son 3.600 cuadros.

| Contenido | fps | 1 minuto | Video de 10 minutos |
|---|---|---|---|
| 3D completo como `PruebaTecnica` final (este contenedor) | ~0,23 | **~4,3 h** | **~43 h** |
| Ídem con ajustes rápidos (MSAA 2×, DOF 0,35, buffers de 8 bits) | ~0,28 | ~3,6 h | ~36 h |
| Borrador (3D a media resolución, sin postproceso) | ~1,0 | ~1 h | ~10 h |
| Escenas solo 2D (texto, SVG, grano) | 2,5–4 | 15–25 min | 2,5–4 h |
| 3D completo en una PC con GPU (Windows, **estimado, sin medir**) | 10–25 | 2,5–6 min | 25–60 min |

La estimación con GPU sale de esto:
- Con GPU, el costo de WebGL de esta escena baja a milisegundos.
- Queda el costo fijo de captura y codificación (~0,1 s por cuadro por pestaña), que sí escala con la concurrencia (4–8 pestañas).
- Hay que confirmarla con `node scripts/bench.mjs --casos final-c2` en esa máquina, subiendo la concurrencia del caso.

**Conclusión:**
- Este contenedor sirve para desarrollar, hacer stills, hojas de contacto, borradores y probar el pipeline.
- El render final de un video largo con 3D pesado tiene que ir en la PC con GPU, o con una estética más liviana (sin DOF ni MSAA y con menos capas a pantalla completa).
- El render por tramos permite repartirlo en varias noches o en varias máquinas: los tramos de distintas máquinas se pueden unir si usan la misma versión del código.

### Para que rinda (sobre todo sin GPU)
- Grano y viñeta en WebGL (`EfectoGrano`), no en CSS.
- Capas DOM estáticas con `will-change: transform`. Nunca en capas que se mueven (ver §10).
- DOF solo donde aporte (es lo más caro). Para previsualizar: `perfil.dofEscala` 0,35 o sin DOF.
- MSAA 2× o 0× con grano: el grano tapa el aliasing.
- `calidad: "borrador"` para revisar timing.

## 6. Render por tramos (reanudable)

`scripts/render-tramos.mjs` parte el video en tramos y renderiza cada uno en un proceso aparte, con su propio navegador. Al final los une sin recomprimir.

```bash
# Tramos de 30 s en calidad de entrega; al final intermedio.mov (unión sin recomprimir) y youtube.mp4
node scripts/render-tramos.mjs VideoEjemplo --tramo 30 --perfil final --youtube
# Con GPU (Windows): más pestañas por proceso
node scripts/render-tramos.mjs VideoEjemplo --tramo 30 --perfil final --concurrencia 6 --youtube
# Cortar en los inicios de escena de la hoja de cues (y subdividir escenas largas)
node scripts/render-tramos.mjs VideoEjemplo --por-escena --tramo 30
# Rehacer solo los tramos 3 y 7 (después de corregir algo en esas escenas)
node scripts/render-tramos.mjs VideoEjemplo --por-escena --solo 3,7 --conservar
```

Cómo funciona:
1. Empaqueta una vez (`build/`) y lee la composición: duración, fps y la hoja de cues si existe.
2. Arma el plan de tramos:
   - Por tamaño: `--tramo` en segundos.
   - Por escena: `--por-escena` corta en cada `inicio` de la hoja y une los restos menores a `--min-tramo`.
   - Cada corte es independiente porque cada cuadro es función pura del número de cuadro (ver §10).
3. Cada tramo se renderiza con `render-rango.mjs`:
   - Video H.264 en MPEG-TS (`h264-ts`, como Remotion Lambda), sin audio.
   - Audio aparte en WAV PCM (`separateAudioTo`, `enforceAudioTrack`).
   - Se escribe como `.part`. Se valida la cantidad EXACTA de cuadros (ffprobe) y de muestras (cuadros × 800 a 48 kHz y 60 fps). Recién entonces se renombra.
4. `manifiesto.json` guarda:
   - El plan.
   - La firma del render: composición, fps, rango, props, perfil.
   - Por tramo: estado, tiempo y hash del código (`src/` + `public/`).
5. Si se corta (error, reinicio, Ctrl+C), **se corre el mismo comando** y rinde solo lo que falta.
   - Si cambió el código, rehace los tramos con hash viejo, salvo `--conservar`.
   - Si cambió la firma (otras props, otro perfil), se niega y pide `--rehacer` u otra `--salida`.
6. Unión (`scripts/unir.mjs`, también se puede correr sola):
   - Video: protocolo `concat:` de ffmpeg sobre los `.ts`, con `-c copy -r 60`.
   - Audio: demuxer concat sobre los WAV, exacto a la muestra.
   - El resultado es `intermedio.mov` (H.264 + PCM). Se valida otra vez cuadros y muestras.

Perfiles (`--perfil`):
| Perfil | Tramos | Para qué |
|---|---|---|
| `intermedio` (por defecto) | H.264 CRF 10, x264 veryfast, yuv420p, BT.709 | Intermedio de alta calidad, rápido de codificar. Después va `codificar-youtube.mjs`. |
| `final` (**recomendado sin GPU**) | H.264 CRF 17, x264 slow, GOP 30 | Sin segunda codificación: `codificar-youtube.mjs --copiar-video` solo pasa el audio a AAC (`--youtube` lo hace solo). |
| `prores` | ProRes 422 HQ (.mov), unión con demuxer concat | Para editar en un NLE. Ocupa ~3 GB por minuto a 1080p60. |

Disco:
- El intermedio CRF 10 con grano midió **~120 Mbps**: ~900 MB por minuto, ~9 GB para 10 minutos.
- Si falta espacio, `--perfil final` (CRF 17) ocupa varias veces menos y evita la segunda codificación.
- Para ajustar el CRF del intermedio: `PERFILES` en `scripts/render-rango.mjs`.

## 7. Salida maestra para YouTube

```bash
node scripts/codificar-youtube.mjs out/tramos/VideoEjemplo/intermedio.mov out/youtube.mp4
```
Equivale a:
```bash
ffmpeg -i intermedio.mov -map 0:v:0 -map 0:a:0 \
  -c:v libx264 -preset slow -crf 17 -profile:v high -level:v 4.2 -pix_fmt yuv420p \
  -g 30 -keyint_min 30 -bf 2 -flags +cgop -sc_threshold 0 \
  -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv \
  -c:a aac -b:a 320k -ar 48000 -ac 2 -movflags +faststart youtube.mp4
```
- H.264 High 4.2, 1080p60, yuv420p y CRF 17 con preset slow.
- GOP cerrado de medio segundo con 2 B-frames: es la recomendación de YouTube.
- BT.709 declarado, para que YouTube no corra los colores.
- AAC-LC 320 kbps a 48 kHz (YouTube recomienda 384k para estéreo: `--audio-kbps 384`).
- `+faststart`: el índice va al principio del archivo.
- El grano fino de 1 px se pierde en la recompresión de YouTube y dispara el bitrate. Conviene escala ≥ 1,5 px y poca intensidad.
- Bitrate medido con el grano de la prueba: ~50 Mbps a CRF 17. YouTube acepta eso sin problema.
- **Velocidad de x264 `slow`:**
  - Midió 1,7 fps en este contenedor con la máquina cargada, o sea horas para 10 minutos. En una máquina libre de 4 núcleos se esperan 8–15 fps.
  - Cuando el render es el cuello de botella (siempre sin GPU), conviene `--perfil final`: x264 `slow` trabaja durante el render, mientras espera cuadros, y al final `codificar-youtube.mjs --copiar-video` solo codifica el audio. `render-tramos.mjs --perfil final --youtube` ya lo hace solo.
  - El perfil `intermedio` + recodificación conviene si se quiere un máster para varias salidas.
- El AAC decodificado dura ~13 ms más que el video: es el relleno del último bloque de 1.024 muestras. No mueve la sincronía; está medido en §8.

## 8. Sincronía de audio y continuidad de cuadros

Cómo se garantiza:
- **Audio sin chunks AAC.** Cada tramo genera su audio en WAV PCM. A 60 fps y 48 kHz son exactamente 800 muestras por cuadro, sin redondeo. La unión de los WAV es exacta a la muestra, y el AAC se codifica UNA sola vez al final, sobre el audio completo. Así no hay huecos ni desfases por el "priming" del AAC en cada unión.
- **Validación dura en cada paso:**
  - Cada tramo tiene que tener exactamente sus cuadros y sus muestras.
  - El intermedio tiene que tener el total.
  - Si algo no cuadra, el script corta con error.
- **Determinismo.** `scripts/determinismo.mjs` renderiza cada cuadro como PNG de 4 maneras y compara hashes:
  - still en un proceso,
  - still en otro proceso,
  - a mitad de una secuencia,
  - primer cuadro de una secuencia, que es como arranca cada tramo.

  Resultado: **idénticos bit a bit** en los cuadros 150, 300 y 451 de `PruebaTecnica` en calidad final. El primer cuadro de un tramo es igual al mismo cuadro en un render continuo: no hay costuras.

Cómo se verifica (`scripts/verificar-sync.py`), con `PruebaTecnica` en modo `depuracion`:
- **Código de cuadro.** Cada cuadro lleva abajo a la izquierda su número en binario (20 bits, celdas de 16 px). El script lo lee del archivo final y comprueba que estén todos, en orden, sin perdidos ni repetidos. Es la prueba de las uniones entre tramos.
- **Marcas de sincronía.** En los cuadros 60, 149, 150, 300, 451, 512 y 599 hay una celda blanca en el video y un clic agudo de 2 ms en el audio. Los cuadros 149, 150, 300 y 451 caen justo en las uniones de los tramos de 150 cuadros, y el 599 es el último cuadro.
- El script mide el desfase de cada clic contra su cuadro. Pasa si todos quedan dentro de medio cuadro (±8,3 ms).

### Resultado (PruebaTecnica, calidad final, 4 tramos de 150 cuadros, 2 procesos)
Corrida: `node scripts/render-tramos.mjs PruebaTecnica --props '{"calidad":"final","depuracion":true,"tono":"agx"}' --tramo 2.5 --min-tramo 1 --procesos 2 --concurrencia 1 --youtube`

| Archivo | Cuadros | Uniones 149/150, 299/300, 449/450 | Audio | Peor desfase de clic |
|---|---|---|---|---|
| `intermedio.mov` (H.264 copiado + PCM) | 600 de 600, en orden | sin perdidos ni repetidos | 480.000 muestras exactas (10,0000 s) | **0,27 ms** |
| `youtube.mp4` (x264 slow CRF 17 + AAC) | 600 de 600, en orden | ídem | 10,0053 s (relleno AAC al final) | **0,27 ms** |

- `youtube.mp4`: H.264 High 4.2, yuv420p, BT.709, 2 B-frames, 60/1, ~51 Mbps; AAC-LC 48 kHz estéreo; `moov` al principio.
- Tiempos con la máquina compartida: render 37,7 min (0,26 fps); unión, segundos; x264 slow, 168 s (3,6 fps). Total 41 min por 10 s de video.

## 9. Utilidades (independientes del estilo)

### 9.1 Transcripción (`src/lib/transcripcion.ts`)
- Acepta `[{word,start,end}]`, `{words:[...]}` (whisper) y `{segments:[{words}]}` (WhisperX).
- Agrupa en frases (puntuación, silencios ≥ 0,6 s, máximo 14 palabras o 6 s).
- La búsqueda ignora tildes y mayúsculas.
```tsx
const voz = useTranscripcion(staticFile('datos/transcripcion.json'));
const palabra = usePalabraActual(voz);            // {palabra, progreso, sonando}
const frase = useFraseActual(voz, {adelanto: 0.1});
const f = cuadroDePalabra(voz, 'cerebro entrópico', fps);       // tira error si no está
const todas = buscarPalabras(voz, 'neuro', {prefijo: true});     // neurona, neuronas...
segundosACuadro(12.34, 60);                                      // 740
```
Los hooks usan el **cuadro absoluto**:
- Envolver la composición maestra en `<ProveedorTiempoAbsoluto>`. `LineaDeTiempo` ya lo hace.
- Dentro de una `<Sequence>`, `useCurrentFrame()` es local; `useCuadroAbsoluto()` no.

### 9.2 Hoja de cues → línea de tiempo (`src/lib/cues.ts`, `LineaDeTiempo.tsx`)
Toda la estructura del video sale de un JSON. Ejemplo: `public/datos/cues-ejemplo.json`.
```json
{"fps": 60, "duracion": 612.4, "fondo": "#0e0c0a",
 "transcripcion": "datos/transcripcion.json", "envolventes": "datos/envolventes.json",
 "audio": [{"id": "voz", "src": "audio/voz.wav"},
           {"id": "pad", "src": "audio/pad.wav", "volumen": 0.6, "fundidoSalida": 2,
            "ducking": {"fuente": "voz", "reduccion": 0.5}}],
 "escenas": [
   {"id": "intro", "tipo": "mundo3d", "inicio": 0, "fin": 14.2, "params": {"orbita": 30}},
   {"id": "idea", "tipo": "titulo", "inicio": 14.2, "fin": 21.0,
    "transicion": {"tipo": "difuso", "duracion": 1.0}, "params": {"texto": "Sueño lúcido"}}]}
```
- Tiempos en segundos absolutos de la voz.
- La transición queda **centrada en el corte**, así las escenas siguen alineadas con la voz aunque `TransitionSeries` solape escenas.
- Los huecos se rellenan con `fondo`. Si una transición no entra, se recorta con aviso.
- Tipos de transición:
  - `corte`, `fundido`, `difuso` (CSS: blur + fundido) y `barrido`/`deslizar` (con `direccion`).
  - `zoomOnirico`, `disolucion` y `desenfoque`: shaders de Remotion (HTML-in-canvas).
- La duración del video sale de la hoja (`calculateMetadata`).
- Cada video registra su composición con su propio registro de escenas (ver `src/escenas/registro.tsx`):
```tsx
export const MiVideo = (p) => <LineaDeTiempo {...p} registro={{mundo3d: Escena3D, titulo: EscenaTitulo}} />;
```
Dentro de una escena, `useEscena()` da `t` (segundos desde el inicio nominal, negativo durante la transición de entrada), `progreso` 0..1 y el segmento.

### 9.3 Audio sin FFT en el render (`scripts/envolventes.py` + `src/lib/audio.ts`)
```bash
python3 scripts/envolventes.py --fps 60 --salida public/datos/envolventes.json \
  --pista voz=public/audio/voz.wav --pista bajo=../musica/stems/bajo.wav \
  --pista pad=../musica/stems/pad.wav --cues ../musica/cues.json --bandas
```
- Por pista y por cuadro calcula:
  - **Nivel**: RMS en dB → 0..1, con techo en el percentil 99,5 y rango de 48 dB.
  - **Bandas** (opcionales): graves, medios y agudos.
  - **Onsets**: flujo espectral con ventana causal, así el ataque cae en el cuadro en que suena.
- Lee `cues.json`:
  - Con `bpm` + `downbeats`, o `bpm` + `primer_downbeat`, o listas explícitas.
  - Saca beats y downbeats en cuadros y pasa `secciones`/`marcas` tal cual.
- Formato compacto: u8 en base64. 10 min con 5 pistas ≈ 1 MB.
```tsx
const env = useEnvolventes(staticFile('datos/envolventes.json'));
<ProveedorAudio envolventes={env}>...</ProveedorAudio>
const nivelVoz = useNivel('voz', {ataque: 0.03, relajacion: 0.35});   // envolvente AR precalculada
const golpe = usePulso('downbeats', {caida: 18, anticipo: 2});          // 1 en cada downbeat y cae
const fase = useFaseCompas();                                           // 0..1 dentro del compás
<Audio src={staticFile('audio/pad.wav')} volume={volumenConDucking(env, {fuente: 'voz', reduccion: 0.5})} />
```
Verificado con la prueba: los onsets de la voz caen en el cuadro de inicio de cada palabra (±1) y los bombos en sus cuadros exactos (30, 70, 110…).

### 9.4 Movimiento y cámara (`src/lib/movimiento.ts`, `src/lib/camara.ts`)
- `CURVAS`:
  - `apple`, `appleOut` y `appleIn`: las de `motion/docs/APPLE-MOTION.md`.
  - `respiro` (seno), `llegada` (expo out) y `lineal`.
- `D`: duraciones `micro`, `rapido`, `base`, `revelado`, `escena`, `sostener` y `escalonadoMax`.
- `SPRINGS`: `vivo`, `aterriza` (rebote 0,15), `suave`, `lento` y `onirico`. Se definen como en SwiftUI: `springSwiftUI({duracion, rebote})`.
- Helpers: `progreso()`, `entradaSalida()`, `resorte()` y `escalonado()`.
- `fbm`, `deriva2` y `deriva3`: deriva suave con ruido sembrado (`@remotion/noise`).
- Rig de cámara puro: `estadoCamara(t, {claves, respiracion, rolido})`.
  - Las claves se interpolan con Catmull-Rom y una curva por tramo.
  - El MISMO estado mueve:
    - la cámara 3D (`<CamaraRig estado={...}/>`);
    - las capas 2D con parallax físico (`<CapaParallax camara referencia profundidad>`);
    - las anotaciones ancladas a puntos 3D (`proyectar(p, camara, ancho, alto)`).

## 10. Reglas para escribir escenas (las rompió alguna prueba)
1. **Todo es función del cuadro.** Nada de `Math.random`, `Date.now`, relojes ni estado acumulado entre cuadros.
   - Azar: `crearAzar('semilla')` o `random()` de Remotion.
   - Así funciona el render por tramos: cada tramo arranca en frío en cualquier cuadro.
2. **Prohibido `useFrame` para animar** (sí para dibujar).
   - Tampoco sirven los componentes de drei que usan el reloj (`Float`, `Sparkles`, `Stars` con speed, `Cloud`, `MeshDistortMaterial`, `MeshWobbleMaterial`).
   - Probados y deterministas: `Environment frames={1}` con `Lightformer`, `RoundedBox`, `ContactShadows` y `Text` vía `<Texto3D>`.
3. **Uniforms y transformaciones en `useLayoutEffect` o en props JSX, nunca en `useEffect`.**
   - `<ThreeCanvas>` dibuja el cuadro en un `useEffect` que corre ANTES que los `useEffect` de los hijos.
   - Con `useEffect` la imagen va un cuadro atrasada.
4. **Postproceso: usar `src/three/Postproceso.tsx`, no el `<EffectComposer>` de @react-three/postprocessing.**
   - El wrapper crea el composer en un efecto y suma los pases 2–3 commits después: el primer cuadro de cada still o tramo salía vacío.
   - Además, `<DepthOfField>` recrea el efecto cada vez que cambia el foco.
   - Por eso se sacó esa dependencia.
5. **Recursos asincrónicos sin Suspense** (troika, workers, imágenes en CSS): retener con `delayRender` hasta que estén listos y volver a dibujar el cuadro (`advance`). Ver `Texto3D.tsx` y `Grano.tsx`.
   - Trampa: si un hijo SUSPENDE antes del commit, React descarta el estado del padre y vuelve a correr su `useState(() => delayRender())`. El primer handle queda huérfano y el render vence por timeout (pasó con `<Text>`).
   - Solución: envolver ese hijo en un `<Suspense>` propio, o crear el handle en `useLayoutEffect`.
6. **Partículas o elementos sin profundidad + DOF**: van en la capa posterior (`PaseCapa`). Si no, el DOF las desenfoca según lo que tienen detrás.
7. **Sin GPU, cada capa DOM grande que cambia se re-rasteriza en cada cuadro.**
   - Grano y viñeta van en WebGL (`EfectoGrano`, gratis).
   - `will-change: transform` SOLO en capas que no cambian nunca (como la viñeta CSS).
     - En una capa que se mueve, Chrome re-muestrea un rasterizado de cuadros anteriores.
     - El resultado depende de la historia: el primer cuadro de un tramo no coincide con el mismo cuadro a mitad del render. Medido: hasta 37 niveles de diferencia en los trazos.
   - Nada de `mix-blend-mode` a pantalla completa.
   - SVG del tamaño justo.
8. **Capturas en JPEG 95, no PNG.** PNG suma ~0,6 s por cuadro.
9. Texto en pantalla mínimo (skill `motion-copy`). Tipografía: League Spartan, DM Sans y DM Mono (`src/lib/fuentes.ts`).

## 10 bis. Flujo propuesto para el video real
1. **Voz:**
   - Copiar la voz editada a `public/audio/voz.wav`.
   - Copiar la transcripción a `public/datos/transcripcion.json`. Sirve cualquier formato de §9.1, incluida la salida de WhisperX de `motion/tools`.
2. **Música:**
   - Copiar los stems a `public/audio/`.
   - El `cues.json` de `motion/musica` tiene que traer `bpm` y `downbeats` (o `primer_downbeat`).
   - Correr `scripts/envolventes.py` con la voz y cada stem (`--bandas` para los stems que van a mover cosas).
3. **Hoja de cues:**
   - Escribir `public/datos/cues.json` con las escenas (inicio y fin tomados de la transcripción) y las pistas de audio.
   - `cuadroDePalabra()` sirve para ubicar momentos exactos dentro de cada escena.
4. **Escenas:**
   - Cuando llegue la referencia de estilo, crear `src/escenas/<tipo>.tsx` y un registro propio.
   - Registrar la composición del video: `(p) => <LineaDeTiempo {...p} registro={...} />` con `calculateMetadata={metadatosLinea}`.
   - Registrar cada escena también como composición suelta (connected compositions) para editarla en el Studio.
5. **Revisión:**
   - Studio + `calidad: "borrador"`.
   - Stills y hojas de contacto con `npx remotion render --sequence --frames=...`.
   - `scripts/determinismo.mjs` sobre la composición nueva antes del render largo.
6. **Render final:**
   - En la PC con GPU: `render-tramos.mjs --por-escena --perfil final --youtube`.
   - Si se corta, se reanuda con el mismo comando.
   - Probar el pipeline con `--rango` sobre un minuto antes de lanzar todo.

## 11. Problemas encontrados (y cómo quedaron resueltos)

| Problema | Causa | Solución |
|---|---|---|
| Con Chrome 149, `--gl=angle/egl/vulkan/swiftshader/angle-egl` dan "Error creating WebGL context" | No hay GPU y Chrome 149 ya no cae solo a SwiftShader en esos modos | `swangle` en Linux (`scripts/entorno.mjs`) |
| Aviso "Automatic fallback to software WebGL has been deprecated" | Chrome avisa en cualquier contexto WebGL por software | Inocuo; con `swangle` el contexto se pide explícitamente |
| El primer cuadro de cada still/tramo salía sin 3D con postproceso | `<EffectComposer>` de @react-three/postprocessing arma los pases 2–3 commits después de montar | Composer propio en `src/three/Postproceso.tsx`; se quitó @react-three/postprocessing |
| DOF roto con la cámara en movimiento | `<DepthOfField>` recrea el efecto cuando cambia el foco | El foco se actualiza por uniforms (`cocMaterial.focusDistance`) |
| Las partículas se veían como una tormenta de nieve | No escriben profundidad y el DOF las desenfocaba según el fondo | Capa posterior al DOF (`PaseCapa`) con bokeh propio y oclusión suave |
| Capas CSS carísimas sin GPU | Viñeta `radial-gradient` a pantalla completa: ~230 ms por cuadro; grano con `mix-blend-mode`: ~160–450 ms | Grano y viñeta en WebGL (`EfectoGrano`); `will-change: transform` en capas estáticas (viñeta a ~40 ms) |
| El primer cuadro de un tramo no coincidía con el mismo cuadro en un render continuo | `will-change: transform` en la capa de parallax: Chrome re-muestrea un rasterizado de cuadros anteriores | `will-change` solo en capas que no cambian; `scripts/determinismo.mjs` da PNG idénticos en los 4 métodos |
| PNG suma ~0,6 s por cuadro | Codificar PNG 1080p en Chrome | JPEG 95 por defecto |
| Texto 3D faltaba en el primer cuadro | troika genera glifos en un worker, sin Suspense | `<Texto3D>` retiene el render hasta `onSync` |
| Google Fonts no carga en el contenedor | TLS interceptado: `net::ERR_CERT_AUTHORITY_INVALID` | Fuentes locales en `public/fuentes`; Google Fonts funciona con `--ignore-certificate-errors` |
| Onsets un cuadro antes de tiempo | Ventana de STFT centrada (ve 21 ms de futuro) | Ventana causal que termina al final del cuadro |
| La capa de parallax salía de cuadro | Referencia = cámara inicial; la cámara recorre metros | Referencia = la misma cámara sin la deriva |
| `@remotion/noise` lento con muchas semillas | Su caché guarda 10 semillas | Una semilla fija y la coordenada desplazada (`fbm`, `deriva3`) |
| `create-video` hace `git init` en la carpeta destino | Comportamiento del scaffolder | El proyecto se armó a mano, con versiones fijas |
| Advertencia de memoria "CGroup … 8796093008327 MB" | El contenedor informa un límite de cgroup absurdo | Inocua: Remotion usa el menor valor |
| Más pestañas o procesos no aceleran el 3D en el contenedor | SwiftShader ya usa ~2,5 núcleos con UNA pestaña; las pestañas comparten el proceso GPU | Concurrencia 1 para 3D sin GPU (ver §5) |
| npm avisa que eslint 9 no tiene soporte | `@remotion/eslint-config-flat@4.0.528` pide eslint ≥ 9 | Sin impacto; `npm run lint` = eslint + `tsc` |
