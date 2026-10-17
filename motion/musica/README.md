# Motor musical (`motion/musica/`)

Banda sonora original para los videos: muestras reales CC0 + síntesis propia,
**48 kHz estéreo, float32 interno, WAV de 24 bit, determinista** (misma partitura
→ mismos bits). Las cinco canciones son "la misma banda": comparten instrumentos,
espacio (reverb, sala, eco) y cinta.

> Fase 2: componé tu canción en `canciones/NN_nombre.py` **sin tocar `motor/`**.
> Leé este README y `canciones/01_umbral.py` (la canción modelo).

---

## 1. En 30 segundos

```bash
python3 motion/musica/muestras.py          # una vez: baja y prepara las muestras (~3,3 GB en disco, idempotente)
python3 motion/musica/render.py umbral     # renderiza la canción 1 (≈ 3–4 min en total)
python3 motion/musica/render.py 02 --hasta 17      # prueba rápida: corta en el compás 17
python3 motion/musica/render.py 02 --desde 41 --hasta 49   # una sección del medio (con preroll)
python3 motion/musica/render.py 02 --partitura     # imprime cifrado y melodías (sin audio)
python3 motion/musica/render.py todas              # todas, una tras otra
```

Dependencias: `pip install -r motion/musica/requirements.txt` (numpy, numba, scipy,
soundfile, soxr, pyloudnorm, matplotlib). Python 3.13. Hilos limitados a 2.

Salida de cada canción en `salida/<slug>/` (no se commitea):

| archivo | qué es |
|---|---|
| `master.wav` | 24 bit / 48 kHz, −14 LUFS integrados, pico real ≤ −1 dBTP |
| `stems/{bateria,bajo,armonia,melodia,textura}.wav` | mismo largo; sumados = mezcla previa al bus master (exacto); sin limitar |
| `cues.json` | bpm, compás, tonalidad, secciones (inicio/fin, energía, emoción, bajo voz, loop), downbeats, armonía |
| `qa.json` + `espectrograma.png`, `forma_de_onda.png`, `espectro.png`, `pianola.png` | control de calidad |

Y `motion/renders/musica/<slug>.mp3` (320 kbps) para escuchar en el celular (sí se commitea).

---

## 2. Archivos

```
musica/
  muestras.py          baja VSCO-2 CE y VCSL (git sparse) y arma muestras/proc/manifest.json
                       (catálogo, afinación y nivelación de cada muestra: ver NIVELES.md)
  NIVELES.md           niveles de cada instrumento antes y después de la nivelación nueva
  render.py            CLI de render
  canciones/NN_*.py    una canción por archivo; cada una define cancion() -> Cancion
  motor/
    nucleo.py          SR, conversiones, azar determinista, Tempo, Auto (automatizaciones)
    teoria.py          escalas, cifrado (acorde), conducción de voces (conducir, bajos)
    secuencia.py       Cancion, Seccion, Pista, Nota, mini-notación de melodías
    instrumentos/      muestreados.py, sintes.py, bateria.py, mecanica.py, texturas.py, base.py
    figuras.py         figuras reutilizables: espiral() (ostinato que gira), columna()
    efectos.py         efectos de pista + reverb (IR generada), eco, cinta, limitador
    mezcla.py          pistas → stems → master, cues.json, mp3
    analisis.py        QA: loudness, picos, clicks, balance espectral, imágenes
    pruebas.py         demos por instrumento y pruebas con criterio (python3 -m motor.pruebas tests)
  muestras/            (ignorado por git) repos parciales + proc/*.npy
  salida/              (ignorado por git) renders
```

---

## 3. Cómo se declara una canción

Una canción es un módulo con `cancion()` que construye y devuelve un `Cancion`.
Todo es Python plano: datos (secciones, cifrado, melodías) arriba, arreglo abajo.

### 3.1 Posiciones y duraciones

* **Posición** = compás (1 = comienzo; `9.5` = mitad del compás 9) o texto
  `"compás:tiempo"` contando desde 1 (`"40:4.5"` = el "y" del 4 del compás 40).
* **Duración** = tiempos (negras): `R=4` redonda, `B=2` blanca, `N=1` negra,
  `C=0.5` corchea, `S=0.25` semicorchea (importables de `motor.secuencia`).
* `bpm` siempre en negras por minuto, también en 6/8 (un compás de 6/8 = 3 tiempos).
* `C.c(t)` convierte tiempos absolutos (los que devuelven `C.voicings`) a compás.

### 3.2 La canción

```python
C = Cancion("Deriva", slug="02-deriva", bpm=104, compas=(4, 4),
            tonalidad="La mayor", semilla=2024, cola_s=8.0)
C.ritardando(61, 65, 96)             # opcional: rampa de tempo entre compases
```

`semilla` fija todo el azar (humanización, granos, fases). `cola_s` = segundos de
cola después del último compás (las reverbs se apagan; el final queda en silencio).

### 3.3 Secciones (estructura y cues)

```python
C.seccion("intro", 8, energia=0.2, emocion="curiosidad", voz=False, loop=(5, 9))
C.seccion("a", 16, energia=0.4, emocion="avance", voz=True)      # loop por defecto: últimos 8
```

Se encadenan en orden. `voz=True` marca "sección bajo voz": el motor aplica un
hueco suave (−3 dB, campana ancha en 2,4 kHz) a armonía, melodía y textura, y el
compositor debe dejar la melodía escasa. `loop=(ini, fin_exclusivo)` en compases va
a `cues.json`. `energia` (0–1) es la intención: el QA compara con el loudness real.

### 3.4 Armonía

```python
C.progresion(1, "Dmaj9 | E/D | Bm11 | Gmaj13#11")   # un acorde por compás
C.progresion(17, "Bm11 | E/G# | Asus4 A | Gm6")     # "Asus4 A" = dos acordes en un compás
```

Cifrado soportado: mayor, `m`, `maj7/maj9/maj13`, `7/9/11/13`, `m7/m9/m11`, `6`, `m6`,
`6/9`, `sus2`, `sus4`, `add9`, `dim`, `dim7`, `ø`/`m7b5`, `aug`, alteraciones
`b5 #5 b9 #9 #11 b13`, `no3 no5`, bajo con barra `E/G#`. `acorde("Gmaj13#11")`
devuelve las clases de altura y el rol de cada nota (tercera, séptima, color,
alterada, raíz, quinta). `escala("D", "lidio")` y `MODOS` para escalas.

### 3.5 Voicings con conducción de voces

```python
vs = C.voicings(9, 17, voces=4, rango=("E3", "B4"))     # [(t0, t1, cifrado, [midi…]), …]
bs = C.bajos(9, 17, rango=("A1", "G#2"))                # [(t0, t1, cifrado, midi_bajo), …]
pad.acordes_ligados(C.voicings(9, 17, voces=5, rango=("E3", "F5")), vel=0.6)
```

`conducir()` elige, para cada acorde, el voicing que menos se mueve respecto del
anterior, con estas reglas: grave limpio (debajo de Mi3 solo 5ª justa o más entre
voces vecinas; entre Mi3 y La3 al menos 3ª menor; segundas solo desde Do4), sin
novenas menores entre voces, sin duplicar 3ª/7ª/tensiones, omite primero la 5ª y
después la raíz (el bajo la toca). Opciones: `tope=` nota máxima preferida para
la voz superior (una o lista por acorde), `con_raiz=True`, `inicio=` voicing
previo. Si el rango es muy estrecho, relaja de a poco en vez de fallar.

La regla del grave vale también **entre instrumentos** (bajo del piano contra el pad,
dron contra el arpa…): el QA y `render.py --partitura` corren `revisar_grave(C)`, que
recorre toda la partitura (con pedales y con las notas que se dejan sonar) y lista cada
choque. «Umbral» marca 1 (el Sol2 del gesto de Gm6 del arpa sigue sonando sobre el Re2 del
compás 57: el arpista lo apagaría). Trucos:
bajo del piano en A1–G#2, voicings desde E3, el arpa apaga su bajo al cambiar de acorde,
y los pedales de Re (dron) se retiran cuando la armonía se mueve.

### 3.6 Pistas

```python
piano = C.pista("piano", Piano(fieltro=0.65), "armonia", vol=3.0, pan=0.0,
                envios={"reverb": 0.22, "eco": 0.03},
                efectos=[EQ(("pa", 40), ("campana", 320, -2.0, 0.8))])
```

* `stem`: uno de `bateria`, `bajo`, `armonia`, `melodia`, `textura`.
* `vol` en dB (post-fader). `pan` −1..1. `envios` lineales post-fader a los buses
  compartidos `reverb` (sala grande 3,6–3,8 s), `sala` (0,9 s) y `eco` (delay).
* `efectos`: cadena de inserción (sección 5).

### 3.7 Notas

```python
p.nota(9, "D2", 4, vel=0.45)                          # pos, altura, dur (tiempos), vel 0..1
p.acorde("9:3", ["D3", "A3", "E4"], 2, vel=0.4, rasgueo=0.02)   # rasgueo = s entre notas
p.melodia(3, "A5/0.5 E6 D6 G#5/1.5 A5/1 | F#5/3 r/1", vel=0.5)  # mini-notación
p.arpegio(17, 25, C.voicing_en(vs), patron="0 1 2 3 4 3 2 1", paso=0.5, vel=0.5,
          acentos=[1.15, 0.8, 0.95, 0.8])
p.acordes_ligados(vs, vel=0.6)                        # notas comunes sin reatacar (pads, cuerdas)
p.pedal_por_compas(9, 17)                             # pedal de resonancia (piano, vibráfono, celesta, Rhodes)
p.pedal(63, 65.9)
p.silenciar(29, 31)                                   # mutea notas que empiezan en ese tramo
```

Extras por nota (`**x`): `legato=True` (cuerdas: sin golpe de arco, ataque lento),
`vel_fin=0.9` (cuerdas: crescendo/diminuendo dentro de la nota), `ataque=`,
`soltar=`, `pan=`, `apagar=True` (arpa/glock: cortar en vez de dejar sonar),
`dejar_sonar=True` (celesta), `exacto=True` (sin humanización de tiempo).

**Mini-notación** (`p.melodia`, `melodia()`, `nube()`): tokens separados por espacio.
`A5/0.5` nota/duración (sin duración repite la anterior) · `r/2` o `-/2` silencio ·
`[D4 F#4 A4]/2` acorde (las notas a la vez; lleva los mismos sufijos: `[D4 F#4]/2!`,
`[A3 E4]_`) · `!` acento ×1,25 · `?` suave ×0,7 · `@0.8` velocidad ·
`_` ligada a la siguiente (legato) · `4+2` suma duraciones · `|` barra que verifica
que el compás cierre (si no cierra, error: atrapa errores de escritura).
`p.melodia(..., transponer=-12)` transpone.

**Batería** (`Bateria()`): patrones de semicorcheas que se ciclan entre dos compases:

```python
bat.patron("bombo",  "x... ..x. x.x. ....", 25, 33, vel=0.8)
bat.patron("aro",    ".... x... .... x...", 29, 33, vel=0.6)
bat.patron("aro",    "...o .... ..o. ...o", 29, 33, vel=0.6)   # fantasmas
bat.patron("shaker", "3264 3264 3264 3274", 33, 41)            # dígitos = vel/9
bat.golpe("40:4.5", "hat_abierto", 0.5)
bat.golpe(40, "barrido", 0.55, dur=4)                           # barrido de escobilla
```

`x` normal · `X` acento ×1,3 · `o`/`g` fantasma ×0,35 · `1`–`9` velocidad/9 · `.` silencio;
espacios y `|` se ignoran; 16 pasos = un compás de 4/4 (12 en 6/8). `prob=0.9`
omite golpes al azar (determinista). Ojo: un patrón de 4 pasos se repite cada tiempo.
`vel` es la velocidad de `x`/`X`/`o`; los dígitos son velocidades absolutas y `vel` no los toca
(así suenan las canciones). `escala=0.8` multiplica **todas** las velocidades del patrón,
dígitos incluidos: para subir o bajar un groove entero.

**Mecánica del piano** (`Mecanica()`, stem `bateria`): los apagadores y el pedal reales del
vertical como percusión, con la misma interfaz que la batería:

```python
mec = C.pista("mecanica", Mecanica(pb_hz=3000), "bateria", vol=-8, envios={"sala": 0.2})
mec.patron("apagador", "x.....x.....x...", 1, 9, vel=0.5, altura=73)   # la altura elige la tecla
mec.golpe(1, "pedal", 0.6)                                             # también "pedal_baja"
```

**Ostinato que gira** (`espiral()`, de «Espiral»): una célula de índices recorre "columnas" de
alturas por compás y corre continua a través de las barras (7 corcheas sobre compases de 8:
cada compás empieza en otro punto del giro), con acento en cada vuelta y crescendo:

```python
cols = {9: columna(("F#", "G#", "A", "C#")), 25: columna(("B", "C#", "D", "F#"))}   # desde La3
notas = espiral(piano, 9, 33, cols, patron="0 2 1 3 2 4 3", desplaz=1, vel=0.35)
```

`columnas` también puede ser una lista fija o una función compás → alturas; `filtro(k, compás)`
elige qué pasos suenan; devuelve las notas agregadas `(t, compás, k, midi, vel)`.

### 3.8 Humanización (determinista)

```python
p.humanizar(tiempo_ms=8, vel=0.07, swing=0.55, swing_div=0.25, desfase_ms=0)
```

σ de microtiempo en ms, variación relativa de velocidad, swing estilo DAW (0,5 recto;
0,54–0,58 leve) sobre la subdivisión `swing_div` (0,5 corcheas, 0,25 semicorcheas),
y desfase fijo (positivo = atrás del tiempo). Cada nota usa una semilla propia
derivada de (canción, pista, posición, altura): cambiar una nota no altera las demás.

### 3.9 Automatización

```python
pad.auto("corte", [(5, 380), (9, 600, "exp"), (41, 4200, "exp"), (65, 450, "exp")])
dron.auto("vol", [(1, -30), (3, -2, "suave"), (13, -2), (21, -40, "suave")])
violines.auto("expresion", [(41, 0.86), (44.9, 1.0, "suave"), (45, 0.9)])
```

Puntos `(posición, valor[, curva])`; la curva describe el tramo que llega al
punto: `"lin"` (por defecto), `"exp"` (frecuencias, valores > 0), `"suave"` (S),
`"paso"`. Antes del primero y después del último se mantiene el valor.
Parámetros: `vol` (dB relativos, toda pista), `pan` (toda pista), `corte` (Pad,
Dron), `expresion` (0..1, Cuerdas). Los efectos aceptan `Auto(...)` en sus
parámetros marcados (p. ej. `Filtro(corte=Auto([...]))`, `Tremolo(prof=Auto(...))`).

### 3.10 Texturas (clips de audio)

```python
tex = C.pista("textura", Textura(), "textura", envios={"reverb": 0.12})
tex.clip(swell(Piano(fieltro=0.5), ["D2", "A2", "F#3", "C#4"], largo_tiempos=8), fin=9, ganancia_db=-9)
tex.clip(nube(Celesta(), MOTIVO + " " + RESPUESTA, dur_s=26, estirar=5, tonos=(0, 12, -12, 7),
              pesos=(5, 2, 1, 1)), pos=59, ganancia_db=-3)
tex.clip(nube_de_banco("vibrafono_arco", "A4", dur_s=24, estirar=14), pos=1, ganancia_db=-17)
```

* `swell(instr, alturas, largo_tiempos, vel, reverb, seco, curva)`: toca el acorde,
  lo pasa por la reverb de la canción, lo invierte y lo ubica para que **termine
  exactamente en `fin`** (el downbeat), con un fundido de 12 ms que evita el click.
* `nube(instr, melodía, dur_s, …)`: toca la melodía y la convierte en nube granular
  estirada (acepta acordes: `"[D3 A3 E4]/2 [D4 F#4 A4]/2"`). `nube_acordes(instr,
  [(t, dur, alturas[, vel]), …], dur_s, …)`: igual, con acordes o notas armados en Python
  (p. ej. la salida de `espiral`). `nube_de_banco(banco, altura, dur_s, …)`: igual, con una
  muestra real cruda (sin nivelar; nunca una muestra excluida del catálogo).
  Parámetros: `estirar`, `densidad` (granos/s), `grano=(mín, máx)` s, `dispersion`,
  `tonos` + `pesos` (transposiciones), `pan`, `ataque`, `caida`, `desde/hasta` (tramo
  de la fuente 0..1), `brillo_hz`.
* `p.clip(generador, pos=… | fin=…)` acepta cualquier función `ctx → array (n, 2)`.

---

## 4. Instrumentos

Todos están **calibrados**: una nota a `vel=0.6` ronda **−26 LUFS** (sostenidos: medido en
el tramo estable; percusivos: en sus primeros ~2 s) (batería:
patrón de negras a 0,6 → bombo −24, caja −26, escobilla −28, aro −30, shaker/hat
abierto/tic −36, hat −38; mecánica del piano: apagador −24 con altura 73, pedal −35).
Mezclar con `vol` de la pista y `vel`. Tabla de niveles por altura y velocidad, y el cambio
respecto de la versión anterior del motor, en `NIVELES.md`.

**Curva de velocidad de los muestreados** (monótona): calibración + `rango_db`·(vel^curva − 1)
+ el cruce de capas en potencia. La capa suave está `capas_db` por debajo de la fuerte (catálogo
de `muestras.py`: cuerdas, trémolos, pizzicatos y piano −8 dB, arpa −7, vibráfono −10, glock
−10/−4), así que de vel 0,3 a 0,85 hay unos 18–22 dB (vibráfono con arco: 11 dB, una capa).

| Instrumento | Fuente | Rango útil | Parámetros principales |
|---|---|---|---|
| `Piano()` | piano vertical real (VCSL Knight, 2 capas + ruidos de apagadores y pedal) | A0–C8 | `fieltro` 0–1 (oscurece y ablanda el ataque), `brillo`, `mecanica` 0–1 (ruidos reales), `rango_db` 26. Usa pedal. |
| `Arpa()` | arpa de concierto real (VCSL, 2 capas) | E1–F7 | deja sonar (nota `apagar=True` para cortar), `largo_max` 6 s, `abrir` (paneo por altura), `tope_hz` |
| `Glock()` | glockenspiel real (VCSL, 3 capas) | G5–C8 | deja sonar, `largo_max` 4,5 s, `tope_hz` 10 k |
| `Vibrafono(motor_hz=5, motor_prof=0.35)` | vibráfono real, baquetas blandas (VCSL) + motor simulado | F3–F6 | motor = AM en la banda de la fundamental con fase global; usa pedal; `soltar`; `domar` (ver abajo) |
| `VibrafonoArco()` | vibráfono frotado con arco (VCSL), sin motor | C4–F6 | notas largas sin ataque (`ataque` 0,3, `soltar` 2,5; bucles si la nota es más larga que la muestra); `domar` |
| `Celesta()` | síntesis modal (no hay celesta CC0) | C4–C8 | `brillo`, `golpe` (martillo), `decaimiento`, `dejar_sonar`. Usa pedal. |
| `Violines()`, `Violas()`, `Chelos()`, `Contrabajo()` | secciones reales VSCO-2 CE (2 capas, vibrato) | violín G3–D6, viola C3–D6, chelo C2–F5, contrabajo E1–B3 | `doble=True` (sección más grande), `legato` por nota, `vel_fin`, automatización `expresion`; la dinámica cruza capas p→f, sube volumen y brillo. Notas largas: bucles con fundido alineado por correlación y nivel aplanado. |
| `CuerdasTrem("violines"\|"violas"\|"chelos")` | trémolo real | ídem | tensión, misterio |
| `Pizzicato("violines"\|"chelos"\|"contrabajo")` | pizzicato real | ídem | deja sonar ~2,5 s |
| `Rhodes()` | FM de dos pares (cuerpo 1:1 + púa 1:14) | E2–C7 | `brillo`, `campana`, `trem_hz`/`trem_prof` (trémolo estéreo), `drive`, `detune`. Usa pedal. |
| `Pad()` | supersaw PolyBLEP + filtro 4 polos que respira + chorus | — | `voces`, `desafinar`, `sub`, `ataque`, `soltar`, `corte` (automatizable), `q`, `respira`, `respira_hz`, `chorus`, `ancho`, `pa`, `saturar` |
| `Dron()` | parciales con deriva lenta + aire resonante | graves | `ataque`, `soltar`, `corte` (automatizable), `aire`, `brillo`, `respira` |
| `Sub()` | senoidal + 8va, saturación suave | A1–A2 | `drive_db`, `octava`, `glide_ms` (solo entre notas ligadas), `ataque`, `soltar`, `pb`, `pa`; la velocidad se aplica después de saturar (conserva la dinámica; a vel 0,7, igual que antes) |
| `Bateria()` | síntesis (sección 3.7) | — | `niveles={golpe: dB}`, `tono`, `color` |
| `Mecanica()` | apagadores y pedal reales del piano (sección 3.7) | — | `ganancia_db`, `pb_hz`, `largo_s`, `pan`, `vecinas`; golpes `apagador`, `pedal`, `pedal_baja` |
| `Textura()` | pista de clips (sección 3.10) | — | — |

Golpes de batería: `bombo` (corto, ~50 Hz), `aro` (cross-stick de madera),
`escobilla`, `barrido`, `caja` (suave, para clímax), `shaker` (granular), `hat`,
`hat_abierto`, `tic`/`tac` (tic-tac de madera para tensión). Cada golpe varía un
poco de afinación, color y largo: no suena a ametralladora.

Todos los muestreadores eligen la muestra más cercana, la transponen con soxr (HQ)
y corrigen su afinación medida (cents en el manifiesto).

* **Nivelación** (`muestras.py`, cacheada en el manifiesto; se actualiza sola si cambia la
  versión): cada muestra va a la referencia de su capa según su loudness K-ponderada
  (BS.1770), medida con la cadena con que suena por defecto (paneo y cierre de las cuerdas,
  `abrir`, `tope_hz`). Sostenidos: primeros 5 s del tramo estable (el mismo nivel al que los
  bucles aplanan las notas largas). Percusivos: promedio de una ventana corta después del
  ataque (0,4 s; pizzicato 0,3 s) y de los primeros 2 s. Residuo entre muestras vecinas ≤ 1,5 dB.
* **Muestras excluidas** (defectuosas; se transponen las vecinas): vibráfono con arco La3,
  vibráfono Fa3, arpa Re2, glock Sol5 suave, viola Sol5 suave (`excluir` en el catálogo).
* **Cruce de capas sin cancelaciones**: las capas de una nota son la misma cuerda o lámina
  grabada dos veces y quedan en fase fija; la suave se alinea con la fuerte (desfase de hasta
  media onda y polaridad) y la mezcla se compensa en potencia K (en el contrabajo solista,
  siguiendo el tiempo). `Cuerdas(doble=True)`: la copia pasa por `leer()` como la principal.
* **Domado de los vibráfonos** (`domar=1`; 0 = timbre crudo, 2 = el doble): las láminas tienen
  afinado el parcial de dos octavas (4·f0), que en el sostenido queda como un silbido fijo en
  la banda de la voz (2,2–2,4 kHz en Do#5–Re5), y las graves tienen el 3er modo (10,4–10,9·f0)
  muy fuerte en el ataque (2,2–2,9 kHz en Sol#3–Do#4). Cada muestra trae medidos esos dos
  parciales y la nota los recorta con filtros que siguen la transposición: el 4·f0, −8 dB
  después del ataque (con arco, −12 dB siempre); el 3er modo, hasta −30 dB de la fundamental.
* **Pedal del piano**: al subir, caen juntos los apagadores de todas las notas que sostenía; el
  ruido de cada uno baja √k (k = notas apagadas a la vez) y se reparte en 25 ms, así no hay
  golpe. Igual se apagan todas: para que el último acorde se extinga solo, subí el pedal
  después del final (`piano.pedal(83, 96)`, aunque la canción termine antes).
* **Notas que se dejan sonar** (`Arpa`, `Glock`, `Pizzicato`; `apagar=True` las corta):
  `fin_sonoro()` estima hasta dónde suenan (la muestra cae 30 dB, tope `largo_max`); lo usa
  `revisar_grave`.

---

## 5. Efectos de pista (`efectos=[...]`)

| Efecto | Uso |
|---|---|
| `EQ(("pa", 90), ("graves", 200, -2), ("campana", 2500, -3, 1.0), ("agudos", 9000, 2), ("pb", 12000))` | EQ estática RBJ |
| `Filtro("pasabajos"\|"pasaaltos"\|"pasabanda", corte=Auto(...), q, polos=2\|4, respira, respira_hz, mezcla)` | filtro resonante que se puede automatizar y hacer "respirar" |
| `Saturacion(drive_db, tipo="suave"\|"tubo", mezcla, pb)` | calidez |
| `Chorus(mezcla, base_ms, prof_ms, hz, voces)` | ensanche suave |
| `Tremolo(hz \| division=0.5, prof, estereo)` | trémolo / autopan (fase global o sincronizado) |
| `Ducking(fuente="bateria", golpe="bombo", prof_db, ataque_ms, relaj_ms)` | bombeo suave desde las notas del bombo (sin detector) |
| `Compresor(umbral_db, ratio, ataque_ms, relaj_ms, rodilla_db, compensar_db, mezcla)` | compresión (paralela con `mezcla`) |
| `Ancho(ancho, mono_hz)` | M/S; `mono_hz` deja los graves en mono |
| `Paneo(Auto(...))` | paneo automatizado |

---

## 6. Espacio común, cinta y master

`C.fx` trae los valores de la banda (cambiarlos poco, para que las canciones se
encadenen):

```python
C.fx["reverb"]    = {"dur": 3.6, "predelay_ms": 28, "brillo": 0.45, "ancho": 1.0, "tipo": "sala_grande"}
C.fx["sala"]      = {"dur": 0.9, "predelay_ms": 6, "brillo": 0.6, "ancho": 0.8, "tipo": "sala"}
C.fx["eco"]       = {"division": 0.75, "realim": 0.38, "corte": 3200, "graves": 250, "pingpong": True, "a_reverb": 0.35}
C.fx["cinta"]     = {"wow": 0.0012, "flutter": 0.0004, "saturacion": 0.25, "hiss_db": -72, "brillo": 15000}
C.fx["hueco_voz"] = {"frecuencia": 2400, "q": 0.8, "profundidad_db": 3.0, "stems": ("armonia", "melodia", "textura")}
C.fx["master"]    = {"lufs": -14.0, "techo_dbtp": -1.0, "glue": 0.5}
```

* **Reverb**: convolución con IR generada (ruido con T60 dependiente de la frecuencia:
  graves más largos, agudos más cortos), densidad que crece, reflexiones tempranas,
  predelay, estéreo verdadero decorrelacionado (4 respuestas independientes).
* **Eco**: delay sincronizado (`division` en tiempos: 0,75 = corchea con puntillo),
  realimentación filtrada (cada repetición más oscura), ping-pong, parte a la reverb.
* **Cinta** (por stem): wow & flutter (retardo modulado común a todos los stems),
  saturación suave, head bump y pérdida de agudos; hiss muy bajo en el stem textura.
* **Master**: compresión de pegamento suave → normalización a −14 LUFS → limitador
  true-peak con anticipo (iterativo hasta cumplir LUFS y −1 dBTP) → dither TPDF a 24 bit.
* Stems: cada stem pasa por los mismos buses por separado (reverb y eco son lineales):
  **suma de stems = premaster** (error típico −140 dB). Stems y premaster comparten
  una ganancia común con margen (pico de stems ≤ −1 dBFS).

---

## 7. `cues.json`

```json
{ "titulo": "Umbral", "bpm": 88.0, "compas": "4/4", "tonalidad": "Re lidio",
  "duracion_s": 184.1, "lufs_integrado": -14.0, "pico_dbtp": -1.15,
  "secciones": [ { "nombre": "despertar", "compas_inicio": 9, "compas_fin": 16,
                   "inicio_s": 21.818, "fin_s": 43.636, "energia": 0.3,
                   "emocion": "asombro contenido", "bajo_voz": true, "lufs": -21.4,
                   "loop": {"compas_inicio": 9, "compas_fin": 16, "inicio_s": 21.818, "fin_s": 43.636} } ],
  "downbeats_s": [0.0, 2.7273, ...], "armonia": [{"inicio_s": 0.0, "fin_s": 2.727, "acorde": "D5"}],
  "cola": {"inicio_s": 175.1, "fin_s": 184.1} }
```

`compas_fin` es el último compás de la sección (inclusive). Loops de downbeat a downbeat.

---

## 8. Render y tiempos

* `render.py <nombre|número|archivo|todas>`; opciones `--hasta N` (prueba rápida
  hasta el compás N), `--desde N` (empieza en el compás N: para probar secciones del medio),
  `--preroll S`, `--solo pista1,pista2`, `--sin-qa`, `--sin-mp3`,
  `--sin-imagenes`, `--partitura`, `--pianola`, `--salida DIR`. Las pruebas van a
  `salida/_pruebas/` y no generan MP3.
* `--hasta N`: el render dura hasta el compás N más la cola (`cola_s`), pero en la cola no
  empieza nada: las notas, clips, pedales y golpes de ducking escritos desde el compás N se
  descartan (se decide por la posición escrita, no por la humanizada). Lo que ya sonaba sigue:
  notas largas, el pedal que estaba bajado (sube cuando estaba escrito), la reverb y el eco.
  Así el QA de la sección siguiente solo mide colas.
* `--desde N`: se calcula sobre la línea de tiempo completa (automatizaciones, LFO, cinta y
  pedales iguales), pero solo las notas y clips que siguen sonando `--preroll` segundos (12 por
  defecto) antes del compás N: la reverb, el eco y el pedal llegan "cargados". El tramo sale
  idéntico al render entero (error < −98 dB en «Deriva» 41–49) en ~60 % del tiempo, salvo la
  ganancia de margen común de stems y premaster, que sale del pico de lo renderizado (puede
  diferir unas décimas de dB; queda en `ganancia_db` del resultado, y el master y los LUFS del
  QA son los del tramo). El `Sub` (oscilador continuo) calcula siempre todas sus notas. En
  `cues.json` los tiempos se cuentan desde el corte (`recorte.desde_s`).
* Tiempo de «Umbral» (3:04, 14 pistas, ~2 400 notas): 2–2,5 min de render + ~1 min de
  QA e imágenes (≈ 3–3,5 min en total, 2 hilos, según la carga de la máquina). La
  primera ejecución compila numba (~20 s, queda en caché). `--hasta 17` tarda ~1 min.
* `python3 -m motor.pruebas [nombres]` (desde `musica/`): demo de pocos segundos por
  instrumento + `salida/_pruebas/instrumentos/hoja.png`.
* `python3 -m motor.pruebas tests [--rapido] [nombres]`: pruebas con criterio (nivelación,
  parser de acordes, detector de clicks, glide y dinámica del Sub, domado de los vibráfonos,
  `--desde`, `--hasta` y la tabla de LUFS por pista). ~4 min; `--rapido` mide la nivelación
  en 5 bancos (~1 min en total).
* Correr los renders en segundo plano y no más de uno a la vez (la máquina es compartida).

---

## 9. QA (no podemos escuchar: medimos)

El render imprime y guarda en `qa.json`:

* **Integridad**: pico real (dBTP, ×4), DC, clicks (2ª diferencia vs. su entorno de 20 ms;
  en la batería se ignoran sus propios golpes; en los otros stems, dentro de la ventana de
  ataque de cada nota o clip (−4…+40 ms) solo cuenta un pico impulsivo, concentrado en 1–2
  muestras como un empalme roto, un escalón o un corte seco: los ataques de celesta, vibráfono
  o piano reparten su 2ª diferencia y ya no dan falsos positivos), ráfagas >9 kHz fuera de
  ataques de notas, correlación estéreo (global y por segundo: `correlacion_1s_min` cuenta solo
  hasta el fin de la música y los segundos de más de −50 dBFS, sin la cola de hiss), mono −
  estéreo (LU), suma de stems vs. premaster, largos iguales, silencio al inicio y al final.
* **Balance**: LUFS por sección vs. energía pedida (y su correlación), LRA, bandas
  (sub, graves, barro 200–400, medios, presencia 2–5 k, brillo, aire) del master y de
  cada stem, "barro vs vecinas" y "presencia vs vecinas" (dB por octava), resonancias
  angostas >12 dB (las notas de la melodía aparecen ahí: es esperable).
* **Clusters en el grave**: `revisar_grave` (sección 3.5). Cuenta lo que sigue sonando: el
  pedal y las notas que se dejan sonar (arpa, glock, pizzicato: hasta que la muestra cae 30 dB,
  con tope `largo_max`; `apagar=True` las corta). Por eso puede encontrar choques que antes no
  veía (p. ej. un Sol2 de arpa sonando sobre el Re2 del compás siguiente).
* **Tabla de LUFS por pista y sección** (al final del render, escala del premaster): la
  herramienta para mezclar sin oídos. Referencia de «Umbral»:

  | sección | protagonistas (LUFS) | resto |
  |---|---|---|
  | umbral (e 0,15) | celesta −32 | dron −34, textura −32, pad −43 |
  | despertar, bajo voz (0,30) | piano −28 | ecos de celesta −35, pad −35 |
  | arpa, bajo voz (0,42) | arpa −28 | piano −31, pad −33, chelos −36 |
  | pulso, bajo voz (0,55) | batería −27, Rhodes −30 | sub −29, arpa −31, pad −32 |
  | apertura, bajo voz (0,68) | batería −26, piano −29 | arpa −28, cuerdas −30…−33 |
  | cumbre (0,88) | violines −24 | celesta −28, piano −28, arpa −28, chelos −30, batería −26 |
  | cumbre 2 (0,95) | violines −20 | violas −29, piano −28, arpa −27, chelos −30, batería −26 |

  Master por sección: −22, −20, −17, −17, −14, −11, −10 y el cierre −19 LUFS.
* Imágenes: espectrograma (frecuencia logarítmica, secciones marcadas), forma de onda +
  LUFS de corto plazo contra la energía pedida, espectro promedio por stem, pianola.

Objetivos: pico real ≤ −1 dBTP, −14 LUFS, clicks 0, correlación > 0,3, mono − estéreo
entre −1 y −3 LU, barro y presencia vs vecinas < +2 dB, correlación energía-LUFS > 0,9.

---

## 10. Plantilla mínima

```python
"""«Nombre» — canción N: emoción. Tonalidad, bpm, compás, forma."""
from motor import (Cancion, Piano, Pad, Sub, Bateria, Celesta, Textura, swell, EQ, Ducking)

def cancion() -> Cancion:
    C = Cancion("Nombre", slug="0N-nombre", bpm=96, compas=(4, 4), tonalidad="Fa# menor",
                semilla=1234, cola_s=8.0)
    C.seccion("intro", 8, energia=0.2, emocion="intriga", voz=False, loop=(5, 9))
    C.seccion("a", 8, energia=0.5, emocion="avance", voz=True)
    C.progresion(1, "F#m9 | Dmaj7#11 | Bm9 | C#7sus4 | F#m9 | Dmaj7#11 | Bm9 | C#7sus4")
    C.progresion(9, "F#m9 | Dmaj7#11 | Bm9 | C#7sus4 | F#m9 | Dmaj7#11 | Bm9 | C#7sus4")

    piano = C.pista("piano", Piano(), "armonia", vol=2.0, envios={"reverb": 0.22})
    pad = C.pista("pad", Pad(), "armonia", vol=-5.0, envios={"reverb": 0.15},
                  efectos=[Ducking(prof_db=2.5)])
    sub = C.pista("sub", Sub(), "bajo", efectos=[Ducking(prof_db=3.0)])
    bat = C.pista("bateria", Bateria(), "bateria", envios={"sala": 0.18})
    cel = C.pista("celesta", Celesta(), "melodia", envios={"reverb": 0.38, "eco": 0.2})
    tex = C.pista("textura", Textura(), "textura")

    for t0, t1, s, v in C.voicings(1, 17, voces=4, rango=("E3", "B4")):
        piano.acorde(C.c(t0), v, t1 - t0, vel=0.38, rasgueo=0.02)
    piano.pedal_por_compas(1, 17)
    pad.acordes_ligados(C.voicings(1, 17, voces=5, rango=("E3", "F5")), vel=0.6)
    pad.auto("corte", [(1, 400), (9, 2500, "exp")])
    for t0, t1, s, b in C.bajos(9, 17, rango=("A1", "G#2")):
        sub.nota(C.c(t0), b, t1 - t0 - 0.2, vel=0.75)
    bat.patron("bombo", "x... .... x.x. ....", 9, 17, vel=0.8)
    bat.patron("shaker", "4.6. 4.6. 4.6. 4.7.", 9, 17)
    bat.humanizar(tiempo_ms=7, vel=0.1, swing=0.54, swing_div=0.25)
    cel.melodia(3, "C#6/0.5 E6 F#6 G#6/1.5 A6/1 | F#6/3 r/1", vel=0.5)
    tex.clip(swell(Piano(), ["F#2", "C#3", "A3", "E4"], largo_tiempos=6), fin=9, ganancia_db=-10)
    return C
```

---

## 11. Reglas de la banda (de la dirección del proyecto)

* Mundo sonoro: piano de fieltro, destellos (celesta, glock, arpa, vibráfono),
  cuerdas reales con crescendos lentos, pads cálidos que respiran, Rhodes con trémolo,
  sub saturado, batería suave (nada de EDM ni trap), texturas granulares de las propias
  fuentes, cinta. Referencias: Tycho, Boards of Canada, Jon Hopkins (tranquilo),
  Ólafur Arnalds, Nils Frahm, Hammock, M83 soñado.
* **Prohibido**: chiptune, ondas cuadradas de videojuego, blips, "level up", láser,
  risers/impactos/whooshes de librería. Los "swells" son siempre de las propias fuentes.
* Variación real cada 8–16 compases (capas que entran y salen, filtros, armonía,
  contramelodías). Nada de loops estáticos.
* Lugar para la voz: lo melódico ocupado va en intros, transiciones y finales; en
  secciones `voz=True` la melodía es escasa, en la octava 5 o más grave, con
  velocidades bajas (transitorios suaves en 1–4 kHz).
* Tonalidades vecinas del lado de los sostenidos (D, A, Bm, F#m, E…) para encadenar.

---

## 12. Limitaciones conocidas y consejos

* La celesta es sintética (modal): no existe celesta CC0. Suena dulce y "de caja de
  música"; no intentes solos rápidos y fuertes en el agudo extremo.
* Las secciones de cuerdas no tienen muestras de legato real: el legato se simula
  (entrada sin golpe de arco + fundido). Funciona en frases cantables a tempo medio;
  evitá pasajes rápidos (> 4 notas por tiempo) en cuerdas.
* Los samples de contrabajo solista tienen algún cambio de arco natural en notas largas.
* El piano es un vertical (Knight) muestreado cada tono entero (transposición ±1 st).
* Batería y pads: si se agregan muchas notas muy largas, el render tarda más (el pad
  sintetiza ~6 sierras por nota).
* Nivelación (ver `NIVELES.md`): las muestras quedan parejas en su métrica (≤ 1,5 dB entre
  vecinas), pero algunas tienen otra forma: en los percusivos, ataque y cola pesan distinto
  (el pizzicato de Re2 del contrabajo es cuerda al aire y suena más largo; medido solo en 2 s
  difiere hasta 2,7 dB); en las cuerdas suaves hay reguladores naturales dentro de la toma.
  Transponer hacia arriba baja ~0,3 dB por semitono (la cola se acorta): donde las muestras
  están lejos hay saltos de hasta 2,1 dB al cambiar de muestra (vibráfono con arco, que tiene
  5 muestras útiles; el grave, desde Mi4 transpuesto).
* La dinámica de los muestreados es más amplia que antes (las capas suaves ya no están
  subidas al nivel de las fuertes): de vel 0,3 a 0,85 hay 18–22 dB. Las velocidades bajas
  (≤ 0,3) suenan bastante menos que con el motor anterior (tabla 2 de `NIVELES.md`).
* El domado de los vibráfonos está medido para `domar=1`: con `domar=0`, las láminas graves
  (Sol#3–Do#4) suenan 1–2 dB más en el ataque que sus vecinas.
* `nube_de_banco` usa la muestra cruda (sin nivelar): ajustá el nivel con `ganancia_db`.
* Pedal del piano: al subir apaga todas las notas que sostenía (los apagadores ya no suman un
  golpe). Si querés que un acorde se extinga solo, subí el pedal después del final.
* `Bateria.patron` cicla el texto: un patrón de 4 pasos se repite en cada tiempo.
* Si cambiás `muestras.py` (catálogo), corré `python3 motion/musica/muestras.py` de nuevo.
