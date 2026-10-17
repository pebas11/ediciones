# Pipeline de voz

Del MP4 casero del youtuber a una voz limpia y editada, con la transcripción palabra por
palabra re-mapeada a la nueva línea de tiempo (para sincronizar la animación).

```
video.mp4 ──► procesar.py ──► voz_limpia.wav + transcripcion.json + edl_propuesta.json + cortes.md
                                   │
                    (el orquestador revisa cortes.md y escribe edl_final.json)
                                   │
              aplicar.py ◄─────────┘ ──► voz_final.wav + palabras_final.json + cortar_video.*
```

Todo corre en CPU, con 2 hilos por defecto, y es reproducible (mismas entradas → mismas
salidas). Funciona en Linux, macOS y Windows: rutas con `pathlib`, ffmpeg del sistema y, si no
hay, el de `imageio-ffmpeg`.

## Instalación

Python 3.13. Desde `motion/tools/voz/`.

**Linux / macOS**

```bash
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# DeepFilterNet3 desde Python (recomendado: es la reducción de ruido más rápida y natural)
pip install -r requirements-dfn.txt          # torch CPU + deepfilterlib (en 3.13 compila con Rust)
pip install --no-deps deepfilternet==0.5.6   # sin dependencias: fija numpy<2 y no hace falta
```

**Windows (PowerShell)**

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
# Opcional, solo si tenés Rust (https://rustup.rs) para compilar deepfilterlib:
pip install -r requirements-dfn.txt
pip install --no-deps deepfilternet==0.5.6
```

Si DeepFilterNet no se puede instalar, no pasa nada: con `--ruido auto` (el defecto) el pipeline
baja solo el ejecutable oficial `deep-filter` (el mismo modelo DFN3, 36 MB, también para
Windows) y, si tampoco puede, usa RNNoise (`arnndn` de ffmpeg) o `noisereduce`.

Los modelos se bajan solos la primera vez a `modelos/` (ignorado por git):

| modelo | tamaño | para qué |
|---|---|---|
| `large-v3-turbo` (faster-whisper, int8) | 1,6 GB | transcripción (defecto) |
| `large-v3` | 3,1 GB | transcripción de máxima calidad (opcional) |
| `medium` | 1,5 GB | respaldo si no hay turbo |
| DeepFilterNet3 | 8 MB | reducción de ruido |
| `deep-filter` (ejecutable) | 36 MB | reducción de ruido sin torch |
| RNNoise `std.rnnn` | 0,3 MB | respaldo |

Variables útiles: `VOZ_FFMPEG` (forzar un ffmpeg), `VOZ_MODELOS` (otra carpeta de modelos),
`VOZ_DEEP_FILTER` (ruta al ejecutable `deep-filter`).

## Uso

```bash
# 1. Extraer, analizar, limpiar, transcribir y proponer cortes
python procesar.py ruta/al/video.mp4 --out salida/mi_video

# 2. Revisar salida/mi_video/cortes.md y escribir la EDL final
cp salida/mi_video/edl_propuesta.json salida/mi_video/edl_final.json   # y editar

# 3. Aplicar
python aplicar.py salida/mi_video --edl edl_final.json
python aplicar.py salida/mi_video --edl edl_final.json --video ruta/al/video.mp4   # corta también el video
```

Opciones de `procesar.py`:

| opción | defecto | |
|---|---|---|
| `--modelo` | `large-v3-turbo` | `large-v3` (más lento, algo más literal), `medium` |
| `--compute` | `int8` | `int8_float32`, `float32` |
| `--beam` | 5 | 1 = búsqueda voraz, ~20 % más rápida |
| `--lote` | 0 | > 0: transcripción por lotes (`BatchedInferencePipeline`) |
| `--hilos` | 2 | hilos de CPU para todo |
| `--ruido` | `auto` | `dfn`, `dfn-bin`, `rnnoise`, `noisereduce`, `ninguno` |
| `--atenuacion` | 12/15/18 dB según SNR | límite de reducción de ruido |
| `--lufs`, `--tp` | −16, −1,5 | objetivo de loudness y techo de pico verdadero |
| `--confianza` | 0,75 | confianza mínima para que un corte de contenido salga con `aplicar: true` |
| `--sin-prompt` | | no pedirle a Whisper que transcriba muletillas literalmente |
| `--reusar` | | reusar lo ya calculado (p. ej. rehacer solo la EDL con otra `--confianza`) |
| `--sin-espectrogramas` | | |

Opciones de `aplicar.py`: `--edl` (defecto `edl_final.json`, si no existe usa la propuesta),
`--fundido-ms` (10–30, defecto 20), `--video original.mp4`, `--fps` (si la fuente era solo
audio; p. ej. `29.97`), `--lufs`, `--tp`, `--hilos`.

**Si sobra tiempo, el modelo más grande**: `python procesar.py video.mp4 --out salida/mi_video
--reusar --modelo large-v3` reusa la extracción y la limpieza, vuelve a transcribir con
`large-v3` (~2,5× más lento que turbo) y rehace la propuesta. Conviene hacerlo antes de revisar
la EDL (los índices de palabras cambian).

## Qué hace `procesar.py`

1. **Extracción** a WAV 48 kHz mono float (`audio_original.wav`). Si el estéreo tiene un canal
   mudo usa el otro; si los canales están en contrafase, L − R.
2. **Análisis** (`analisis.json`, del original y del resultado): piso de ruido, SNR, LUFS
   integrado (BS.1770-4), pico verdadero, picos principales, clipping, DC, zumbido de 50/60 Hz
   con armónicos y frecuencia exacta de la red, espectro de voz y de ruido por tercios de
   octava, ancho de banda útil y RT60 aparente (reverb).
3. **Limpieza natural** (`voz_limpia.wav`, sin cortes, 24 bits). Todos los parámetros salen del
   análisis:
   0. DC y **de-clip** por interpolación AR (LSAR), solo si hay clipping.
   1. **Pasa-altos** 75 Hz (Butterworth 4.º orden).
   2. **Zumbido**: se resta. Cada armónico (hasta 1 kHz) se estima como un fasor —amplitud y
      fase— en la frecuencia exacta de la red, en bloques sin voz y con mediana en ±4 s; se
      sintetiza y se resta. No se usan notches (ver *Decisiones*).
   3. **Ruido**: de-click previo y DeepFilterNet3 con límite de atenuación de 12/15/18 dB según
      la SNR (para que no suene robótico). El de-click solo toca impulsos aislados de ≤ 2 ms en
      las pausas (o muy brillantes, ≥ 4,5 kHz, dentro de la voz): en voz real casi todo lo que
      parece un clic es la explosión de una "p", "t" o "k" y eso no se toca.
   4. **Clics residuales y plosivas**: los golpes de aire < 150 Hz se atenúan solo en esa banda
      y solo mientras dura el golpe.
   5. **De-esser** dinámico 5–9 kHz: comprime solo las sibilantes más fuertes (más o menos
      cantidad según cuán sibilante sea la voz respecto de la referencia), máx. 6 dB.
   6. **EQ correctiva suave**: −1 a −3 dB en 300 Hz si sobra barro respecto del espectro de voz
      de referencia (LTASS); +1 dB de presencia en 3,8 kHz y +1,5 dB de aire (estante en 10 kHz)
      si la voz no es ya brillante y hay contenido real arriba de 12,5 kHz.
   7. **Compresión moderada**: nivelador lento (±6 dB, empareja frases que quedaron más bajas)
      y compresor 2,5:1 con rodilla suave, ataque 5 ms, liberación 90 ms.
   8. **Normalización en dos pasadas** a −16 LUFS integrados y −1,5 dBTP (limitador de pico
      verdadero con sobremuestreo ×4 y anticipación de 2 ms).
4. **Transcripción** con faster-whisper (`large-v3-turbo`, int8, CPU), idioma `es`,
   `word_timestamps=True`, VAD de Silero, y un prompt inicial escrito con muletillas para que
   Whisper no "limpie" el texto. Salida: `transcripcion.json` y `transcripcion.txt`.
   **Ajuste de bordes**: se mide el corrimiento sistemático de Whisper (en el fixture adelanta
   las palabras ~0,1 s; en LibriVox, 0,04 s) contra el final real de las palabras que terminan
   antes de una pausa y se corrige; después cada borde que cae en silencio se lleva a la voz,
   cada borde que corta la voz se lleva al ataque/caída real, los finales se miden sin la cola
   de la sala, se corrigen las palabras que Whisper estira sobre una pausa y se reubica la que
   pega en la cola de la frase anterior.
5. **Propuesta de edición** (`edl_propuesta.json` y `cortes.md`), ver abajo.
6. **Espectrogramas** antes/después (`espectrogramas/`) y **tiempos** (`tiempos.json`).

## La EDL: formato y cómo revisarla

Los tiempos son segundos sobre `voz_limpia.wav` (misma línea de tiempo que el video original).
Cada corte:

```json
{
  "id": "c008",
  "tipo": "blooper",
  "inicio": 18.68, "fin": 23.33, "duracion": 4.65,
  "aplicar": true,
  "confianza": 0.98,
  "motivo": "Blooper: marcador «ay», «perdon», «de nuevo» y después se retoma la toma «Puede crecer kilómetros bajo él.» (similitud 100 %). Se saca la toma fallida completa y se queda la última.",
  "texto": "Puede crecer kilómetros bajo él. Ay, perdón, de nuevo.",
  "contexto": "…que no vemos, y es enorme. ⟦Puede crecer kilómetros bajo él. Ay, perdón, de nuevo.⟧ Puede crecer kilómetros bajo el suelo…",
  "palabras": [43, 52],
  "similitud": 100.0
}
```

Tipos:

| tipo | qué detecta | cuándo sale `aplicar: true` |
|---|---|---|
| `silencio` | pausas > 0,45 s: quedan en 0,28 s (0,32 s tras coma, 0,45 s tras punto); silencio inicial y final | siempre |
| `muletilla` | "eh", "ehm", "mmm", "este…" (solo si es muletilla: pausa o puntos suspensivos después, no "este video") | confianza ≥ 0,75 |
| `arranque_falso` | el comienzo de una frase se repite enseguida y la segunda toma sigue más lejos | idem |
| `repeticion` | frase completa repetida, o palabra pegada repetida ("la la idea") | idem |
| `blooper` | marcadores ("perdón", "de nuevo", "otra vez", "corto", "me equivoqué", "no, no, no", risas, tos…) + la toma fallida entera, si después se retoma | idem |
| `sonido_sin_texto` | voz que Whisper no transcribió (¿muletilla? ¿palabra?) | nunca (revisar) |
| `ruido` | sonido sin voz con ataque brusco y corto (¿tos? ¿golpe?) | nunca (revisar) |
| `manual` | cortes que agrega el orquestador | — |

Las respiraciones no se proponen como cortes: una inspiración corta pegada a la frase que sigue
se conserva entera (se deja 0,05 s antes de ella en lugar de 0,15 s), y las demás cuentan como
silencio.

Repeticiones y arranques en falso: para cada inicio de cláusula se busca, dentro de 30 s hacia
atrás, el inicio más temprano tal que **todo** el texto entre ese inicio y el actual (sin
muletillas ni marcadores) coincide con el comienzo de lo que sigue (rapidfuzz, ≥ 85 %; ≥ 75 %
si hay un marcador de blooper). Así se queda siempre la última toma completa y no se confunde
con frases que solo empiezan parecido ("No es una planta. No es un animal.").

**Cómo se combinan los cortes.** Alrededor de cada palabra que queda se respetan los mismos
márgenes (0,15 s antes; después, lo que falte para la pausa objetivo según la puntuación).
Por eso la unión de cualquier conjunto de cortes da pausas naturales: un silencio que cae
adentro de un blooper, o una muletilla pegada a un arranque en falso, se suman sin dejar
huecos raros. Los cortes pueden pisarse.

**Para el orquestador:**

1. Leer `cortes.md`: arriba están los cortes de contenido con texto, motivo y contexto; los
   silencios van al final (los marcados "dentro de cXXX" quedan absorbidos por otro corte).
2. Copiar `edl_propuesta.json` a `edl_final.json` y editar solo lo necesario:
   - `"aplicar": false` para conservar algo (una pausa dramática, un "eh" que suena natural).
   - `"aplicar": true` en un corte dudoso (`confianza` < 0,75) que sí hay que sacar.
   - Mover `inicio`/`fin`, o agregar `{"id": "m001", "tipo": "manual", "inicio": 61.20, "fin": 62.05, "aplicar": true}`.
   - No hace falta mantener ordenados ni únicos los intervalos.
3. `python aplicar.py <carpeta> --edl edl_final.json` y mirar el resumen y `estadisticas.json`
   (avisos incluidos).

Garantías de `aplicar.py`: **nunca corta dentro de una palabra que queda** (si un corte la pisa,
lo recorta al borde de la palabra y lo avisa); cada borde se lleva al punto de menor energía
cercano (±15 ms, sin entrar en palabras) y al cruce por cero más próximo; en cada unión hay un
fundido de igual potencia (sin² + cos² = 1) de 20 ms centrado en el corte, que se acorta si del
otro lado hay una palabra cortada.

## Qué genera `aplicar.py`

- `voz_final.wav`: 48 kHz, 24 bits, −16 LUFS, ≤ −1,5 dBTP (se re-mide tras los cortes).
- `palabras_final.json`: `{"palabras": [{"i", "texto", "norm", "inicio", "fin", "prob",
  "i_original", "inicio_original", "fin_original"}], "frases": [{"inicio", "fin", "texto",
  "palabras": [i0, i1]}]}`. Tiempos sobre `voz_final.wav`, listos para animar palabra por palabra.
- `subtitulos_final.srt`: las mismas frases, por si sirven en CapCut.
- `cortar_video.ffscript` + `cortar_video.sh` / `cortar_video.bat`: el mismo corte para el video
  original (con la voz final como audio). Los cuadros de cada tramo se eligen para que el video
  acumulado nunca se separe más de medio cuadro de la voz, aunque haya cientos de cortes; se
  convierte a cuadros constantes antes (los celulares graban con cuadros variables).
- `estadisticas.json`: duración antes/después, cortes por tipo (propuestos, aplicados,
  segundos), pausas antes/después, loudness final, avisos.

## Tiempos medidos

Máquina de 4 núcleos, **2 hilos**, con otros procesos corriendo a la vez (carga media 6–7:
renders de Remotion y de música de otros agentes), así que son tiempos pesimistas. Segundos de
proceso por **minuto de audio**:

| etapa | voz densa real (LibriVox, 8:20) | fixture (53 s, con silencios) |
|---|---|---|
| extracción | 0,8 | 0,5 |
| análisis (original + resultado) | 2,9 | 1,9 |
| limpieza sin la red (pasos 0, 1 y 4–8) | 5,4 | 4,2 |
| resta de zumbido (solo si hay zumbido) | — (no tenía) | 3,7 |
| reducción de ruido DeepFilterNet3 | 14,1 (5,5 con la máquina libre) | 8,3 |
| espectrogramas | 1,7 | 4,1 |
| transcripción `large-v3-turbo` int8 | 55,0 | 85,6 |
| ajuste de bordes + propuesta de EDL | 0,3 | 0,3 |
| **total `procesar.py`** | **80** | **105** |
| `aplicar.py` (sin video) | 2,2 | — |

La transcripción es el 70 % del tiempo. Un video de 25 minutos tarda ~35 minutos con el modelo
por defecto (con la máquina libre, bastante menos). Para la voz densa la tasa por minuto es
estable; el fixture tiene más carga fija (cargar el modelo, ~10 s) repartida en menos audio.

Modelos, 3 minutos de voz densa real (`pruebas/benchmark_modelos.py`; WER contra `large-v3`):

| configuración | s por min de audio | diferencias con `large-v3` | comentario |
|---|---|---|---|
| `large-v3-turbo`, beam 5 (**defecto**) | 60 | 5,7 % | buen equilibrio; erra en palabras raras ("escurso", "batracomio maquilla") |
| `large-v3-turbo`, beam 1 (`--beam 1`) | 49 | 5,3 % | ~20 % más rápido, casi igual |
| `large-v3-turbo`, lotes de 8 (`--lote 8`) | 56 | 3,2 % | poca ganancia en CPU |
| `medium` | 71 | 7,4 % | más lento **y** peor que turbo: solo sirve de respaldo |
| `large-v3` | 281 (*) | — | el más fiel en palabras raras ("batracomiomaquía") |

(*) medido con la máquina muy cargada (carga 10–12). En el fixture, con carga ~3, `large-v3`
tardó 79 s/min contra 35 de turbo: ~2,3× más lento. Con 25 minutos de video: turbo ≈ 25 min
de transcripción; `large-v3` ≈ 1 hora o más.

## Pruebas

```bash
python -m pytest pruebas/test_unidades.py -q  # 15 pruebas rápidas sin Whisper (EDL, cortes, DSP)
python pruebas/generar_fixture.py             # fixture sintético (TTS es-AR + problemas conocidos)
python -m pytest pruebas/test_pipeline.py -q  # procesa, aplica y compara EDL esperada vs obtenida
python pruebas/test_pipeline.py               # lo mismo, imprimiendo el reporte completo
python pruebas/bajar_librivox.py              # grabaciones reales de dominio público (LibriVox)
python pruebas/limpieza_voz_real.py pruebas/librivox/escuerzo.mp3   # voz real + degradación conocida
python pruebas/benchmark_modelos.py salida/X/voz_limpia.wav --dur 180  # comparar modelos
```

El fixture (`pruebas/fixtures/`, ignorado por git; `generar_fixture.py` lo rehace con el mismo
guion y semillas; edge-tts necesita internet y su caché queda en `fixtures/tts_cache/`)
tiene: silencios de 1,5–2,8 s; un arranque en falso repetido; un blooper ("Ay, perdón,
de nuevo.") seguido de la toma buena; muletillas ("Eh…", "este…", "mmm"); trampas que no hay que
cortar ("Bienvenidos *de nuevo* al canal", "*Este* intercambio"); ruido rosa a −56 dBFS;
zumbido de 50 Hz con 9 armónicos; reverb de habitación (RT60 0,5 s); 3 clics de boca; 3 golpes
de plosiva y un grito que clipea 3,7 dB. Se codifica a MP4 (AAC estéreo + video de prueba a
30 fps). `esperado.json` guarda la verdad: tiempos de cada palabra (calibrados contra el
audio), rol (mantener/quitar) y cortes esperados.

**Resultado (fixture, `large-v3-turbo`; 24 pruebas en verde: 9 de punta a punta + 15 unitarias):**

| esperado | t (s) | obtenido | detalle |
|---|---|---|---|
| silencio 2,23 s | 4,9 | `silencio` | queda 0,44 s |
| arranque en falso «Los hongos no son…» | 9,1 | `arranque_falso` 0,97 | cubre 100 % de las palabras, no pisa vecinas |
| muletilla «Eh…» | 15,2 | `muletilla` 0,96 | 100 % |
| blooper «Puede crecer kilómetros bajo el… Ay, perdón, de nuevo.» | 19,0 | `blooper` 0,98 | 100 %, se queda la toma buena |
| silencio 2,83 s | 26,2 | `silencio` | queda 0,47 s |
| muletillas «este… mmm» | 30,4 | 2 × `muletilla` 0,80 / 0,96 | 100 % |
| silencio 1,93 s | 35,4 | `silencio` | queda 0,53 s |
| silencio 1,54 s | 44,8 | `silencio` | queda 0,48 s |

Sin cortes de contenido extra: "Bienvenidos de nuevo al canal" y "Este intercambio" quedan.
Texto final contra el guion sin tomas fallidas: WER 2 % (solo "micelio" → "miserio", ×2).
Pausa máxima final 0,48 s. Duración 53,5 s → 33,3 s. El video cortado dura lo mismo que la voz
(1000 cuadros a 30 fps = 33,33 s).

Limpieza medida en el fixture: SNR en las pausas 28,5 → 44,3 dB (+15,8 dB, límite de 15 dB
más el zumbido quitado); zumbido: f0 estimada 49,9998 Hz (real 50), en los silencios queda a
0–3 dB del ruido de fondo (antes, 19–24 dB por encima); clipping detectado en el AAC y ausente
en el resultado (de-clip aislado: 20,3 → 24,9 dB de SNR); clics 9,6 / 16,4 / 16,9 dB sobre el
fondo → −1,4 / 2,6 / 5,3 dB; graves de las plosivas −2,2 / −6,3 / −7,5 dB → −12,7 / −13,6 /
−10,0 dB (la referencia seca tiene −16 / −13 / −15); −16,0 LUFS y −1,65 dBTP; RT60 aparente
0,46 → 0,31 s (DeepFilterNet baja algo la reverb, no la saca).

Bordes de palabra contra la verdad del TTS (varía un poco entre corridas): inicio, mediana
40–51 ms (Whisper solo: ~100 ms), p90 ~105 ms; final antes de pausa, mediana ~20 ms, p90 45–67 ms.

**Voz real con degradación conocida** (`limpieza_voz_real.py`: 2 min de LibriVox con el mismo
ruido rosa, zumbido, recorte y AAC del fixture; se compara contra el original limpio):

| | voz sobre pausas | distancia espectral (LSD) en voz |
|---|---|---|
| original limpio | 54,7 dB | — |
| degradada (sin reverb) | 23,5 dB | 5,89 dB |
| **limpiada** | **40,8 dB** (+17 dB) | **3,77 dB** |
| degradada con reverb de sala | 23,7 dB | 7,33 dB |
| limpiada | 29,2 dB (+5,5 dB) | 7,25 dB |

El ruido y el zumbido se van; la reverb de una sala bastante viva (RT60 0,5 s, DRR +4 dB) no:
en las pausas cortas de la lectura continua queda la cola de la sala.

**Grabación real (LibriVox, "El escuerzo", 8:20):** la grabación ya venía limpia (−27 LUFS,
piso −70 dBFS, seca, sin zumbido ni recorte). Resultado −16,0 LUFS / −1,65 dBTP sin artefactos
visibles en los espectrogramas (ni ruido musical ni pre-eco); EQ −1,7 dB en 300 Hz, +1 dB de
presencia, +1,5 dB de aire; de-esser actuando el 5 % del tiempo; 16 clics de boca reparados
(de 455 candidatos: los otros 439 eran explosiones de "p/t/k" y no se tocaron).
Transcripción: 1453 palabras, probabilidad media 0,975; los errores están en palabras raras
o pegadas ("atraviliario" por "atrabiliario", "despansurrado" por "despanzurrado", "la afinada
Antonia" por "la finada Antonia") y en algún tramo sin puntuación. Propuesta: 23 silencios
(pausas p95 0,67 → 0,48 s), 2 sonidos sin transcribir y un "Aumentó, aumentó de una manera…"
(recurso del texto) que queda con confianza 0,65 y sin aplicar. Las respiraciones fuertes
entre frases no se proponen como cortes.

## Decisiones y hallazgos

- **Zumbido por resta, no por notches.** Un notch de 1,5 Hz "suena" ~0,5 s. Con `filtfilt`
  aparecía un pre-eco de −37 dBFS 70 ms antes de cada palabra; causal, el sonido quedaba
  después de cada frase cuando un armónico de la voz pasa por un múltiplo de 50 Hz (en voz
  masculina real, la pausa siguiente subía a −10 dB respecto de la voz) y en los silencios del
  fixture quedaban armónicos 7–14 dB sobre el ruido. Con la resta de fasores quedan 0–3 dB
  (inaudible) y la voz no se toca: no está en fase con la red.
- **Frecuencia exacta de la red.** Un error de 0,03 Hz deja pasar el zumbido 20–30 dB más
  fuerte; se refina con la suma coherente de los armónicos (error < 0,001 Hz en el fixture).
- **De-click antes de la red neuronal.** DeepFilterNet conserva los clics pero los desparrama
  ~20 ms; medido en el fixture: con de-click después quedaban ~10 dB sobre el fondo, antes < 3 dB.
- **De-clip LSAR** (interpolación autorregresiva con la restricción de que lo reconstruido no
  baje del techo). Un spline empeoraba la señal; `adeclip` de ffmpeg no detecta el recorte
  después del AAC. El detector usa el histograma de amplitudes (la voz sana no tiene "joroba"
  junto al pico).
- **Whisper adelanta las palabras** ~0,1 s en el fixture; el corrimiento se mide en cada
  archivo y se corrige (ver *Ajuste de bordes*).
- **medium no es más rápido que large-v3-turbo en CPU**: turbo tiene 4 capas de decodificador.

## Limitaciones

- **Bordes de palabra**: Whisper + energía da ~50 ms de mediana y ~105 ms en el percentil 90
  para el inicio. Dentro del habla continua la energía no separa palabras: ahí solo se corrige
  el corrimiento global. Para precisión de cuadro, el paso siguiente sería un alineador
  forzado CTC (p. ej. `torchaudio.pipelines.MMS_FA`, 1,2 GB, también en CPU) sobre el texto ya
  corregido. No está incluido.
- **Whisper puede "limpiar" el texto**: si no transcribe una muletilla o una repetición, la EDL
  no la ve como palabra. Queda marcada como `sonido_sin_texto` (sin aplicar) si suena con voz y
  no se pega a una palabra; si queda pegada, pasa de largo.
- **Repeticiones con intención** ("Aumentó. Aumentó de una manera…", "¡Increíble! ¡Increíble!"):
  de una sola palabra o completas y cortas quedan bajo el umbral; de varias palabras se
  cortarían. Revisar los `repeticion`/`arranque_falso` en `cortes.md`.
- **Bloopers sin marcador ni retoma** (una frase abandonada y después otra distinta) no se
  detectan; con marcador pero sin retoma clara se proponen con confianza baja.
- **De-clip después del AAC**: mejora la forma de onda (+0,7 a +3,6 dB de SNR medido) pero no
  hace milagros con un recorte fuerte; lo que sí se garantiza es que la salida no recorte.
- **Reverb**: DeepFilterNet la baja un poco (RT60 aparente 0,46 → 0,31 s en el fixture); no hay
  de-reverberación dedicada. Con voz real en una sala viva, las pausas cortas siguen llenas de
  cola (+5,5 dB de mejora contra +17 dB sin reverb).
- **Zumbido con mucha deriva** (generadores, inversores): la resta usa una frecuencia de red
  por archivo y fasores con mediana en ±4 s; si la red se corre más de ~0,05 Hz, los armónicos
  altos se restan peor (DeepFilterNet se lleva parte del resto).
- **Tiempo**: la transcripción manda (~1 min de proceso por minuto de audio con la máquina
  cargada). `--beam 1` ahorra ~20 %; `large-v3` es mucho más lento.
- **DeepFilterNet en Python 3.13**: `deepfilterlib` no publica ruedas para 3.13 (hay que
  compilarla con Rust) y `deepfilternet` 0.5.6 fija `numpy<2` y usa una API vieja de
  torchaudio (el pipeline la parchea al importar). En Windows sin Rust se usa el ejecutable
  `deep-filter` (mismo modelo y mismo resultado, 3–6× más lento) o RNNoise.
- **ffmpeg ≥ 7.1** marca `-filter_complex_script` como obsoleto: `aplicar.py --video` elige la
  sintaxis según la versión; los `.sh`/`.bat` usan la clásica (hay un comentario con la nueva).
- Si se cambia de modelo después de editar `edl_final.json`, los índices de `palabras` de la EDL
  apuntan a la transcripción vieja (los tiempos siguen valiendo). Conviene elegir el modelo
  antes de revisar.
- El fixture es TTS: la voz real tiene más variedad (respiraciones, muletillas pegadas,
  solapamientos). Por eso se probó también con LibriVox, que sin embargo ya venía limpia.
