# Proyecto 1016: video completo con animación onírica

Pedido del 17/10/2026. Este proyecto **no sigue las series anteriores de la bitácora**: el usuario pidió olvidar ese contexto. Las reglas generales siguen valiendo: poco texto en pantalla y que no parezca hecho con IA.

## Pedido
- **Estilo:** replicar el de `C:\Users\pebas\Downloads\1001.mp4` y, a partir de él, crear uno propio, más onírico.
- **Voz:** el audio de `E:\videos yt\1016.mp4`. Hay que extraerlo, arreglarlo, normalizarlo y optimizarlo, y recortar silencios, repeticiones y bloopers.
- **Animación para todo el video:**
  - fluida, que siempre pasen cosas;
  - con objetos bien dimensionados para verse en YouTube;
  - muy pulida y legible, nada feo;
  - cuanto menos texto, mejor.
- **Música original:** varias canciones dinámicas y fluidas que acompañen la emoción y vayan variando, con un volumen que no tape la voz. Nada de efectos de sonido de videojuego.
- Se pueden usar fotos, capturas o videos reales descargados, si suman.
- **Herramientas:** Remotion primero, y después cualquier otra disponible. Nada genérico: la mejor calidad posible.
- **Entrega:** el video completo, en buena calidad, en el Escritorio del usuario (`C:\Users\pebas\Desktop`).

## Preferencias del usuario sobre la música (17/10)
- Las canciones quedan a criterio: tienen que encajar con lo que dice, con el momento y con el ritmo de la narración.
- **Bajito: "no me pongas la música a tope".** Mientras habla, la música va ~24 dB por debajo de la voz. En las pausas sube poco: ~10 dB por debajo de la voz. En intro y outro, como máximo ≈ −20 LUFS de corto plazo.
- Uso previsto de las canciones:
  - «Umbral»: apertura y gancho.
  - «Deriva»: explicaciones, la cama principal.
  - «Espiral»: problemas, preguntas y tensión.
  - «Marea»: momentos emotivos o reflexivos.
  - «Aurora»: clímax y cierre.

## Dónde se puede hacer cada parte
- `C:\`, `E:\` y el Escritorio existen solo en la PC del usuario. Una sesión en la nube no los ve.
- **Este repo es público.** No subir el audio crudo, `1001.mp4` (es de terceros) ni ningún archivo de entrada. Para eso está `motion/input/`, que está en `.gitignore`.

## Piezas (rama `ccr-1c1089b6-6o0jmz`)
Hacé `git pull` antes de cada etapa. Cada carpeta tiene su README con los comandos.

| Carpeta | Qué hace | Estado |
|---|---|---|
| `motion/musica/` | Motor musical y 5 canciones con stems y cues: Umbral (apertura), Deriva (explicación), Marea (reflexión), Espiral (tensión), Aurora (clímax/cierre). MP3 en `motion/renders/musica/`. Los WAV se regeneran con `python3 motion/musica/render.py todas`, después de `python3 motion/musica/muestras.py`. | Hechas y rebalanceadas con el motor corregido (nivelación por capas, `NIVELES.md`). QA: −14 LUFS, 0 clicks, 0 clusters en el grave. |
| `motion/musica/mezcla_voz.py` | Mezclador: arma la cama musical desde un plan JSON, aplica ducking por stems y masteriza a −14 LUFS. Guía en `MEZCLA.md`. | Hecho: 57/57 controles. |
| `motion/tools/voz/` | Extrae, limpia, normaliza a −16 LUFS y transcribe con Whisper palabra por palabra. Propone los cortes (silencios, repeticiones, bloopers) y aplica la EDL. | Hecho: 24 pruebas. |
| `motion/remotion/` | Base de Remotion: Three.js, sincronía con la transcripción, hoja de cues en JSON, audio reactivo, render por tramos y codificación para YouTube. | Hecho. El estilo visual todavía no está definido. |

## Seguir en la PC del usuario (teleport)
Esta sesión en la nube se puede traer a la PC con todo el historial:
1. Instalar Git y Claude Code: en PowerShell, `irm https://claude.ai/install.ps1 | iex`.
2. Bajar el repo: `git clone https://github.com/pebas11/ediciones`, después `cd ediciones`.
3. Traer la sesión: `claude --teleport session_01VXJ4Q86RsggQ8gd5wmPzDW`.
4. Para seguir desde el celular: `/remote-control`.

## Plan de producción
1. **Voz.** Pasar el audio por `motion/tools/voz`. Revisar cada corte en `cortes.md` con criterio editorial, no a ciegas. Resultado: `voz_final.wav` + `palabras_final.json`.
2. **Estilo.** Extraer cuadros de `1001.mp4` (1 cada 1–2 s, más hojas de contacto) y analizar paleta, tipografía, composición, movimiento de cámara, ritmo de cortes, transiciones y texturas. Definir el estilo propio onírico en `motion/ESTILO-1016.md`.
3. **Guion visual.**
   - Dividir la transcripción en beats de 4–10 s, con una idea visual por beat.
   - Encadenar las escenas con transformaciones, no con cortes secos.
   - Que haya movimiento constante.
4. **Música.** Asignar canción y sección a cada tramo según la emoción del guion. `motion/musica/mezcla_voz.py` arma la cama musical con ducking.
5. **Render.**
   - Remotion por tramos, con revisión de cuadros.
   - Mezcla final: voz a −16 LUFS, mezcla total a −14 LUFS y ≤ −1 dBTP.
   - Codificación H.264 1080p60 de alta calidad.
6. **Entrega.** Copiar el MP4 final a `C:\Users\pebas\Desktop\`.

## Dónde conviene renderizar
- **Contenedor en la nube, sin GPU:** Remotion en calidad final va a ~0,25 fps, con WebGL por CPU (`swangle`). Un video de 10 min a 60 fps son ~43 h. Sirve solo para borradores (~1 fps) y cuadros sueltos.
- **PC del usuario, con GPU:** estimado en 25–60 min para 10 min de video, sin medir. Hay que correr `npm run bench` en `motion/remotion` para confirmarlo.
- Detalles en `motion/remotion/README.md`: `--gl=angle` en Windows y render por tramos reanudable.

## Para una sesión de Claude Code en la PC del usuario
1. Bajar el repo: `git clone https://github.com/pebas11/ediciones`, o `git pull` si ya está. Después, `git checkout ccr-1c1089b6-6o0jmz`.
2. Instalar lo que falte: Node 20+, Python 3.11+ y ffmpeg (`winget install Gyan.FFmpeg`).
3. Leer los archivos de entrada desde sus rutas, o copiarlos a `motion/input/`. Nunca commitearlos.
4. Seguir el plan de arriba con los README de cada carpeta.
5. Dejar el video final en el Escritorio.
