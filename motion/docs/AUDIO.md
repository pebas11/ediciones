# Sonido de las escenas (`lib/audio.js`)

Diseño sonoro procedural con Web Audio, renderizado offline y determinista (48 kHz, estéreo). La estética es la de un documental científico o una keynote: cama cálida, whooshes de aire, ticks de madera, campanas FM suaves. No usa ondas cuadradas ni diente de sierra, ni arpegios de videojuego.

Todo está mezclado **bajo**, porque va debajo de una voz en off. El render **no normaliza**: cada preset sale a un nivel absoluto calibrado, así todas las escenas quedan parejas entre sí.

## Uso rápido

```html
<script src="../lib/stage.js"></script>
<script src="../lib/audio.js"></script>   <!-- después de stage.js -->
<script>
M.scene({ duration: 13, audio: { key: 'D', mode: 'major', bed: {} } }, (tl, M) => {
  M.textIn(titulo, 0.4);            M.sfx(0.42, 'tick');
  M.popIn(card, 2.0);               M.sfx(2.0, 'whoosh', { dur: 0.9, peak: 0.35 });
  M.counter(num, { to: 80, at: 4 }); M.sfx(4.0, 'swell', { dur: 1 }).sfx(4.0, 'impact');
});
</script>
```

Después, `node render.mjs <escena>` genera el MP4 con el audio muxeado y además `renders/<escena>_AUDIO.wav`.

Una escena que no carga `audio.js` sale muda, como siempre. Sin `audio.js`, `M.sfx` solo anota el cue.

## API

### `M.scene({ …, audio })`

| Opción | Por defecto | Qué hace |
|---|---|---|
| `key` | `'D'` | Tonalidad: `'C'`…`'B'`, con `#` o `b`. También acepta `'F# minor'`. |
| `mode` | `'major'` | `major`, `minor`, `dorian`, `lydian` o `mixolydian`. |
| `bed` | ninguna | Cama ambiental: `{}` usa los valores por defecto. Parámetros en la tabla de presets. |
| `gain` | 0 | dB sobre toda la escena. |
| `reverb` | `{ decay: 2.4, predelay: 0.018, damp: 1, gain: -4 }` | Sala generada. `gain` es el retorno en dB. |
| `pocket` | −3 | dB a 3 kHz (Q 0,9) sobre toda la mezcla: deja lugar a las consonantes de la voz. 0 lo desactiva. |
| `seed` | 1 | Cambia todas las texturas de ruido y la variación. |

**Tonalidad:** usá la misma `key`/`mode` en toda la serie.
- `major` o `lydian`: asombro, descubrimiento.
- `dorian` o `minor`: temas serios.

### `M.sfx(at, type, opts)`

Devuelve `M`, así que se puede encadenar. `at` está en segundos del timeline de la escena.

**Parámetros comunes:**
- `gain`: dB sobre el nivel calibrado.
- `pan`: de −1 a 1.
- `pitch`: semitonos.
- `verb`: envío a la reverb, de 0 a 1.
- `dur`: segundos.
- `vary`: variación humana de tono, nivel y paneo. 1 por defecto; 0 hace todos los golpes idénticos.
- `anchor`: `'start'`, `'end'` o `'peak'`.

**Presets tonales** (`tap`, `impact`): la nota sale de `note` (`'E5'` o Hz) o de `deg` + `oct`, el grado de la escala en la tonalidad de la escena (0 = tónica, 7 = octava). Por ejemplo `deg: 4, oct: 5` es la quinta en la octava 5.

### Dónde cae `at` (anchor)

| Preset | `at` es… |
|---|---|
| `riser`, `swell` | **El clímax**: el sonido termina en `at` y empieza `dur` antes. Poné el mismo `at` que el `impact` o el revelado. |
| `whoosh` | El inicio del movimiento. Con `anchor: 'peak'`, `at` es el momento de máxima velocidad. |
| Los demás | El inicio. |

## Presets

Niveles medidos con cada preset solo y los parámetros por defecto, mediana de 6 semillas. M es el loudness momentáneo máximo (ventana de 400 ms).

| Preset | Para qué | Nivel | Parámetros propios (por defecto) | Recomendado |
|---|---|---|---|---|
| `bed` | Cama ambiental: pad cálido que alterna dos acordes y tono de sala. | M −32, corto plazo ≈ −34 a −36 | `cycle` 8 s, `voicings` `[[0,4,8,9],[0,5,8,10]]`, `oct` 3, `sub` 0,18, `air` 1, `bright` 1, `fadeIn` 1,5, `fadeOut` 2 | `cycle` 6–10; `bright` 0,8–1,2; `sub` 0,1–0,25; más `voicings` para camas largas. |
| `whoosh` | Movimientos de cámara y transiciones grandes. Ruido filtrado que cruza el estéreo. | M −24 | `dur` 0,8, `peak` 0,45, `dir` 1 (izq.→der.), `width` 0,55, `bright` 1 | `dur` = duración del movimiento (0,6–1,2). `peak` 0,3–0,35 con `swift`/`appleOut` (arrancan rápido) y 0,45 con curvas simétricas. `dir` según el sentido del movimiento. |
| `tick` | Entrada de un texto principal: tap de madera diminuto. | pico ≈ −21,5 dBFS | `tone: 'glass'` (vidrio en vez de madera) | Uno por rótulo, no por palabra. `at` ≈ inicio de `textIn` + 0,02. `gain` entre −3 y +2. |
| `tap` | Ítems de una lista: nota corta de marimba suave. | M −26 | `bright` 1; nota por `deg`/`oct` (5) | Subí el grado en cada ítem (`deg` 0, 2, 4): así la lista "se completa". `bright` 0,7 para algo más suave. |
| `impact` | La revelación principal: golpe grave suave con cola tonal. | M −20 | `dur` 1,8 (cola), `weight` 1, `bloom` 1 | **Máximo uno por escena.** Con `swell` o `riser` terminando en el mismo `at`. `weight` 0,7–1,2. |
| `shimmer` | Aparece un dato o una cifra: acorde de campanas FM. | M −24 | `degs` `[4,7,9]`, `oct` 5, `spread` 0,05, `dur` 2,4 | `spread` 0,03–0,08; `degs` `[2,4,7]` para variar. |
| `scan` | Escaneos y líneas que barren: ruido estrecho que sube. | M −28 | `dur` 1,2, `from` 500, `to` 3500 Hz, `q` 5, `dir` 1, `width` 0,6, `tone` 0,015 | `dur` = duración del barrido; `dir` según el sentido visual; `q` 3–8. |
| `grow` | Crecimiento orgánico (micelio, raíces, un gráfico que crece): crepitar fino. | M −29,5 | `dur` 1,5, `density` 110 granos/s, `spread` 0,7, `bright` 1, `body` 1 | `dur` = duración del crecimiento; `density` 60–160. |
| `riser` | Tensión antes de un momento: ruido y tonos que suben. | M −22 | `dur` 1,5, `semis` 12, `oct` 3, `bright` 1 | `dur` 1–3; `semis` 7–12. Termina en seco: siempre seguido de algo en `at`. |
| `swell` | Acorde en reversa que desemboca en un revelado. | M −23 | `dur` 1,6, `degs` `[0,4,7,9]`, `oct` 3, `release` 0,06, `bright` 1 | `dur` 0,6–1,5, con un `impact` o un `textIn` en `at`. |

**Menos es más.** Un sonido por idea, no por cada movimiento.
- Hasta un `impact` por escena.
- Un `whoosh` solo en los movimientos de cámara grandes.
- `tick` solo en los textos principales.
- Dejá ~0,5 s de silencio de efectos antes del revelado clave: el `impact` pega más.
- Como guía, no más de un efecto por segundo en promedio.

## Niveles y CapCut

- **Referencia:** el WAV y el AAC salen pensados para ponerlos a **0 dB en CapCut** debajo de una voz a **−16 LUFS**, lo típico en redes.
  - La cama queda ~18 LU por debajo de la voz; los efectos, entre 4 y 13 LU abajo.
  - Si la voz está a −14 LUFS, subí el clip +2 dB. Si está a −20, bajalo −4 dB o renderizá con `--gain -4`.
- **Ajuste fino, de lo más local a lo más global:**
  1. `gain` del cue.
  2. `audio.gain` de la escena.
  3. `--gain` del render.
- **`--lufs N`** normaliza el integrado de cada escena. Existe, pero **rompe la paridad**. Medido:
  - `_audio-demo` recibiría +9,9 dB.
  - Una escena con cama y 3 ticks recibiría +18,2 dB.
  - La cama saltaría 8 dB entre escenas.
  - Usalo solo para escuchar un clip suelto.
- **Limitador de seguridad:** actúa solo si el true peak supera −1,5 dBTP, con techo en −2. Con los niveles calibrados no se activa: la demo tiene su pico en −10,5 dBTP.

## Render

```
node render.mjs <escena>                     # video + audio (el audio va solo en FONDO; VERDE queda mudo)
node render.mjs <escena> --audio-only        # ~3 s: regenera el audio y remuxea el MP4 existente (video copiado tal cual)
node render.mjs <escena> --no-audio          # video mudo
node render.mjs <escena> --no-bed            # sin la cama de la escena (solo efectos)
node render.mjs <escena> --gain -4           # ganancia fija en dB
node render.mjs <escena> --lufs -16          # normalizar (ver arriba)
node render.mjs <escena> --bed-only --dur 95 # solo la cama → renders/<escena>_BED.wav
node render.mjs <escena> --draft             # la previa también lleva audio (renders/draft/)
```

`--audio-only` es el camino normal para iterar el sonido: tocás los `M.sfx` y en ~3 s tenés el MP4 remuxeado sin volver a renderizar cuadros. El cálculo es:

- La duración se toma de los cuadros del MP4 existente.
- Se re-sintetiza el audio.
- Se escribe el WAV.
- Se remuxea con `-c:v copy`.

Si la escena ya no tiene sonido, `--audio-only` quita la pista AAC del MP4 y borra el `_AUDIO.wav` viejo.

**Qué sale:**

- **`renders/<escena>_FONDO.mp4`:** AAC de 256k cortado exactamente al largo del video, con un fundido de 0,2 s al final para que no haya clic en el corte.
- **`renders/<escena>_AUDIO.wav`:** 16 bits, 48 kHz, con dither.
  - Arranca en el mismo instante que el video.
  - Trae además la **cola** que sigue sonando después del final (reverb, impactos): hasta 3 s, recortada donde cae 72 dB bajo el pico.
  - Para que una cola se derrame sobre la escena siguiente, usá el WAV en su propia pista de CapCut en vez del audio del MP4.
- **Aviso:** si en los 300 ms después del final queda energía por encima de −45 dBFS RMS, el render avisa `el MP4 corta una cola`. Solución: usar el WAV o adelantar el cue.
  - Medido, energía después del corte según cuánto antes del final suena el cue:

    | Cue | 0,5 s antes | 1 s antes | 1,5 s antes | 2 s antes |
    |---|---|---|---|---|
    | `impact` | −31 dBFS | −44 dBFS | −55 dBFS | −64 dBFS |
    | `shimmer` | −33 dBFS | −41 dBFS | −52 dBFS | −58 dBFS |
    | `whoosh` | −37 dBFS | −62 dBFS | −75 dBFS | −88 dBFS |
    | `tap` | −52 dBFS | −64 dBFS | −74 dBFS | −91 dBFS |

  - Para un corte limpio en el MP4, dejá **≥ 1,5 s** entre el último `impact`/`shimmer` y el final.

### Serie de escenas: una sola cama

La cama de cada escena entra con fundido de 1,5 s, sale con 2 s y reinicia sus acordes. Si unís escenas que tienen cada una su cama, la cama cae a silencio en cada corte. Para una serie:

1. En las escenas, `audio: { key, mode }` **sin `bed`**: solo efectos.
2. Una sola cama del largo total del video, con la misma tonalidad y semilla. Sale de cualquier escena que cargue `audio.js` y tenga esa `key`/`mode`, con o sin `bed` (sin `bed` usa los valores por defecto):
   `node render.mjs <escena> --bed-only --dur 95`
3. En CapCut, `_BED.wav` va en su propia pista a 0 dB, debajo de todo.

## Cadena de mezcla

- **Cada cue:** nivel, paneo de potencia constante y envío a la reverb.
- **Bus de efectos:** pasa-altos de 4.º orden a 40 Hz.
- **Bus de cama:** pasa-altos a 45 Hz.
- **Reverb:** convolución con una IR de sala generada (reflexiones tempranas y cola que se oscurece), con pasa-altos a 220 Hz y shelf −5 dB a 6,5 kHz.
- **Suma:** `audio.gain`, luego el hueco para la voz (−3 dB a 3 kHz).
- **Master:** pasa-altos a 28 Hz y compresor suave (2:1 desde −24 dB).
  - Chromium le suma **+5,3 dB fijos de compensación**.
  - En la práctica comprime como mucho 0,8 dB, en impact + swell.
- **Fundidos de seguridad:** 5 ms al inicio y 30 ms al final de la cola.

## Si tocás `audio.js`

- **Nunca conectes más de 2 nodos a la misma entrada:** usá `sum()`. Chromium suma las conexiones en un orden que varía de render a render, y con 3 o más el resultado deja de ser idéntico bit a bit.
- **No uses `StereoPannerNode`:** usá `pan2()`. Con un filtro después, cambia entre corridas.
- **Q de `BQ()`:** siempre es **lineal** (0,707 = Butterworth). Web Audio interpreta en dB el Q de `lowpass`/`highpass`, y `BQ()` lo convierte. No crees biquads a mano.
- **Semilla:** cada cue se siembra por `tipo | at en ms | n.º de aparición`. Agregar o quitar un cue no cambia el sonido de los demás. Verificado: el impact sale idéntico con y sin el whoosh anterior.
- **Si cambiás un preset o el compresor, re-medí y ajustá `LEVEL`.** Método:
  1. Cada preset solo, 6 semillas.
  2. BS.1770 momentáneo máximo, mediana.
  3. Las metas son las de la tabla de arriba.
- **Nada de `Math.random`:** todo el ruido sale de `mulberry32`.

## Mediciones de referencia (`_audio-demo`, nivel fijo, `--gain 0`)

**WAV:**
- 8,00 s de escena + 1,66 s de cola.
- Integrado −25,8 LUFS (la escena sola, −25,7). True peak −10,5 dBTP. Ninguna muestra recortada.
- DC −125 dB. Correlación L/R 0,92. Pérdida al sumar a mono −0,18 dB.

**AAC en el MP4:**
- 384 000 muestras = 8,000 s, igual que los 480 cuadros a 60 fps.
- −25,7 LUFS, −10,5 dBTP, LRA 4,3 LU.
- Desfase: 0 muestras entre el render en float y el WAV, y 0 entre el WAV y el AAC.

**Niveles en la mezcla:**
- Cama: corto plazo −33,7 LUFS.
- Pico momentáneo de la mezcla: −19,3 LUFS a los 2,7 s (impact + swell).
- Máximo de corto plazo: −23,6 LUFS.

**Espectro (energía relativa al total):**

| Banda | Antes | Ahora |
|---|---|---|
| < 30 Hz | −26 dB | −63,6 dB |
| 30–60 Hz | −18 dB | −34,9 dB |
| 2–5 kHz, bus de efectos | −12,8 dB | −16,0 dB |
| 2–5 kHz, grow | −2,3 dB | −8 dB |

**Onsets** (primera muestra no nula de cada cue aislado):
- ticks 1,1000 / 1,2500 / 1,4000
- taps 3,1000 / 3,3000 / 3,5000
- impact 2,4000
- shimmer 3,9000
- whoosh 0,2002
- scan 4,7001
- grow 5,7001
- swell y riser terminan en su `at` (2,40 y 7,30).

**Determinismo:** mismo md5 del WAV en tres `--audio-only` y en un render completo. El MP4 también sale idéntico en `--audio-only` y en el render completo.

**Clics:** ninguno detectado.
