# Mezclador de música y voz (`motion/musica/mezcla_voz.py`)

Arma la banda sonora del video con las canciones del motor (`salida/<slug>/stems` + `cues.json`)
según un **plan musical** escrito sobre la línea de tiempo de la voz, la baja por stems cuando
habla la voz y entrega la mezcla final a −14 LUFS. Todo es determinista: el mismo plan y la
misma voz dan los mismos bits.

> **Pedido del autor (vigente):** la música va **bajito y nunca a tope**. Por defecto:
> −24 LU por debajo de la voz mientras habla, en las pausas sube pero sin pasar de voz − 10 LU,
> y sin voz (intro y final) no supera −20 LUFS de corto plazo. Ver §6.

---

## 1. En 30 segundos

```bash
python3 motion/musica/mezcla_voz.py --plan plan.json --validar --voz voz_final.wav    # revisa el plan y muestra el armado (2–5 s)
python3 motion/musica/mezcla_voz.py --voz voz_final.wav --plan plan.json --out salida/mezcla
python3 motion/musica/mezcla_voz.py ... --param niveles.musica_bajo_voz_lu=-26 --param ducking.ataque_ms=60
python3 motion/musica/mezcla/pruebas/verificar.py [--largo]                            # pruebas con criterios medibles
```

Necesita las dependencias del motor (`requirements.txt`). Usa 2 hilos. Las canciones se buscan en
`motion/musica/salida/` (o `--canciones DIR`); el análisis de cada canción queda en caché en
`<carpeta de canciones>/_mezcla_cache/` y se recalcula solo si cambian los stems.

## 2. Qué hace

1. **Valida el plan** y resuelve cada canción (slug, número o nombre).
2. **Armado musical** (`mezcla/armado.py`): elige los compases de cada tramo (loops, acortes,
   anclas) y construye una EDL de segmentos con sus fundidos, colas de reverb y empalmes.
3. **Voz** (`mezcla/voz.py`): mide su sonoridad y detecta frases y pausas.
4. **Niveles** (`mezcla/niveles.py`): estima la ganancia de cada bloque (sección dentro de un
   tramo) proyectando la sonoridad de la fuente con el ducking real, sin renderizar.
5. **Render** (`mezcla/render.py`): arma cada stem, aplica ducking y EQ dinámica, y suma la cama.
   Si algún bloque quedó a más de 0,5 LU de su objetivo, corrige y vuelve a renderizar.
6. **Techos** (guardia): baja suavemente la cama donde pase su techo (bajo la voz, en pausas o sin voz).
7. **Master** (`mezcla/master.py`): ganancia hasta −14 LUFS integrados y limitador de pico real
   con anticipo (≤ −1 dBTP). Dither TPDF a 24 bit.
8. **Informe, envolventes y gráfico** (`mezcla/informe.py`, `envolventes.py`, `grafico.py`).

## 3. Salidas (`--out`)

| archivo | qué es |
|---|---|
| `mezcla_final.wav` | voz + música, 48 kHz, 24 bit, −14 LUFS integrados, pico real ≤ −1 dBTP |
| `musica_cama.wav` | la música armada y duckeada, sola, **en la escala de la mezcla final** (sin limitador). Para rearmar la mezcla en CapCut: voz × `ganancia_master_db` (del informe) + cama |
| `informe.json` | niveles (voz, música bajo la voz, pausas, intro, final, máximo), master y limitador, tramos y transiciones con sus tiempos reales, empalmes, clicks, ducking, parámetros efectivos, avisos y tiempos de proceso |
| `mezcla.png` | voz, ganancia de cada stem, sonoridad de corto plazo con sus techos, limitador y arreglo (tramos, secciones, loops, transiciones, anclas, downbeats) |
| `envolventes.json` | por cuadro (60 fps): RMS de la voz y de la cama, onsets, bandas de la cama, downbeats y pulsos efectivos, secciones, tramos y transiciones. Formato de `motion/remotion/src/lib/audio.ts` (§10) |

La voz mono se ubica al centro como mono doble a ganancia unidad (L = R), igual que la pone un
editor. Por eso, en estéreo, una voz mono de −16 LUFS mide −13 LUFS, y el master la deja en ≈ −14.

---

## 4. El plan (`plan.json`)

Lo escribe el orquestador según el guion: una lista de **tramos** sobre la línea de tiempo de la voz.

### 4.1 Esquema

Nivel superior:

| clave | tipo | |
|---|---|---|
| `version` | 1 | opcional |
| `tramos` | lista | obligatoria, en orden de `inicio` |
| `parametros` | objeto | opcional: cambia cualquier valor de §8 (mismas claves) |
| `canciones_dir` | texto | opcional: otra carpeta de canciones |
| `notas` | texto | libre |

Cada tramo:

| clave | tipo | qué hace |
|---|---|---|
| `cancion` | texto/número | `"01-umbral"`, `"01"`, `1`, `"umbral"` o el título |
| `secciones` / `seccion` / `compases` | lista / texto / `[a, b]` | el material, en el orden dado (se puede saltar o repetir secciones). `compases` es inclusivo |
| `inicio`, `fin` | segundos | sobre la línea de tiempo de la voz. `fin` de un tramo = `inicio` del siguiente, salvo con `"pausa"` |
| `id` | texto | nombre para mensajes, informe y gráfico |
| `nivel_db` | número (±12) | corre el objetivo de la música en este tramo (+2 = más presente, −3 = más discreta) |
| `transicion` | texto u objeto | cómo pasa al tramo siguiente (§4.2). Por defecto `fundido` de 4 tiempos; en el último, `cola` |
| `entrada` | `"golpe"` o `{"tipo": "fundido", "tiempos": N}` | cómo entra este tramo (por defecto lo decide la transición anterior; el primero entra a golpe) |
| `ancla` | objeto | `{"seccion": "cumbre", "en": 131.2}` o `{"compas": 41, "tiempo": 1, "en": 131.2, "repeticion": 1}`: ese downbeat cae exacto en ese segundo |
| `repetir` | texto | sección a loopear si falta material (por defecto la última del material que tenga loop, nunca la que cierra la canción si hay otra) |
| `acortar` | `"final"` / `"inicio"` | si sobra material: corta el final (por defecto) o conserva el final y entra más adelante |
| `stems` | objeto | ganancias fijas por stem en este tramo: `{"melodia": -4, "bateria": "silencio"}` |
| `ducking` | `false` u objeto | `false` = sin ducking en este tramo; `{"profundidad_db": {"melodia": -12}, "eq_db": -6}` |

### 4.2 Transiciones

| tipo | claves | qué pasa |
|---|---|---|
| `fundido` | `tiempos` (4), `alineacion` (`auto`/`antes`/`despues`) | fundido cruzado de N tiempos alineado al downbeat del que entra. `antes`: el que entra arranca con su propio material previo y llega pleno al downbeat (el que sale se apaga en esa ventana). `despues`: entra a golpe y el anterior se apaga en N tiempos. `auto` usa `antes` si el que entra tiene material previo |
| `cola` | `segundos` (3; recomendado 2–4) | el anterior para en su límite de compás y queda su cola de reverb, que se apaga en N segundos; el nuevo entra a golpe en su downbeat |
| `pausa` | `silencio_s` (2, si `fin` = `inicio` siguiente) | el anterior para en su compás, su cola decae sola y hay silencio hasta que entra el siguiente |
| `corte` | — | empalme corto (½ tiempo) en el downbeat del que entra |
| `final` | — | solo en el último tramo: deja terminar la canción con su cola real (el material se alinea por el final) |

Entre canciones distintas, **batería y bajo nunca se superponen**: los del tramo que sale
terminan antes del downbeat del que entra (dos grooves a tempos distintos suenan a choque).

### 4.3 Ejemplo

```json
{
  "version": 1,
  "tramos": [
    {"id": "intro", "cancion": "01-umbral", "secciones": ["umbral"], "inicio": 0.0, "fin": 15.0,
     "transicion": {"tipo": "fundido", "tiempos": 2}},
    {"id": "exposicion", "cancion": "umbral", "secciones": ["despertar"], "repetir": "despertar",
     "inicio": 15.0, "fin": 66.5, "stems": {"melodia": -3}, "transicion": {"tipo": "cola", "segundos": 3}},
    {"id": "revelacion", "cancion": "umbral", "secciones": ["pulso", "apertura"],
     "ancla": {"seccion": "apertura", "en": 72.2}, "inicio": 66.5, "fin": 103.6,
     "transicion": {"tipo": "fundido", "tiempos": 2}},
    {"id": "cumbre", "cancion": "umbral", "secciones": ["cumbre"], "inicio": 103.6, "fin": 125.8,
     "nivel_db": 1, "ducking": {"profundidad_db": {"melodia": -12}}, "transicion": {"tipo": "pausa"}},
    {"id": "cierre", "cancion": "umbral", "secciones": ["cierre"], "inicio": 127.4, "fin": 150.0,
     "transicion": {"tipo": "final"}}
  ]
}
```

Más ejemplos en `mezcla/pruebas/plan_*.json` (uno con las cinco canciones y voz real de 8:44).

### 4.4 Validación

`--validar` revisa todo sin generar audio e imprime el armado real (compases, loops, anclas con su
error, transiciones). Los errores salen todos juntos y con sugerencia:

```
error: plan inválido:
  - parametros.ducking.atake_ms: clave desconocida (¿quisiste decir 'ataque_ms'?). Válidas: …
  - tramo 2 («b»): la sección 'cumbre3' no existe en 01-umbral (¿quisiste decir 'cumbre'?). Secciones: …
  - tramo 2 («b»): transicion.tipo 'fade' no válido; usá uno de: fundido, cola, pausa, corte, final
  - entre tramo 1 (fin 30.0) y tramo 2 (inicio 33.0) hay un hueco de 3.00 s: usá "transicion": {"tipo": "pausa"} …
```

Además valida rangos (p. ej. `ancla.en` dentro del tramo y del material, stems válidos, tramos de
al menos 2 s, `final` solo al final) y avisa (sin frenar) lo que se resolvió de otra forma.

---

## 5. Cómo arma la música

* **Todo corte cae en un límite de compás** (downbeats de `cues.json`). Los fundidos de empalme
  terminan `guarda_ms` (30 ms) antes del downbeat: los ataques humanizados que se adelantan quedan
  enteros del lado que entra y no se cuelan del lado que sale.
* **Fundidos de igual potencia adaptativos**: con la correlación r de cada stem entre los dos lados,
  g_sale² + g_entra² + 2·r·g_sale·g_entra = 1 (r = 0 → igual potencia; r = 1 → igual ganancia).
  En empalmes de una misma canción se busca un desfase de hasta ±5 ms que maximice la correlación
  en graves: el bajo y el pad no se cancelan en el fundido.
* **Extender**: se repite el loop recomendado de la sección (`cues.json`) las veces justas; cada
  vuelta es un fundido de 1 tiempo que termina antes del downbeat (la vuelta entra con su ataque
  entero). Si el final y el comienzo del loop no suenan parejos (crescendo, decrescendo) y el salto
  pasa de max(3 dB, p90 + 1,5 dB) —p90: cuánto cambia el nivel de un compás al siguiente en la
  propia sección—, el lado más fuerte se compensa con una rampa de 2 compases y el salto queda en
  el p90.
* **Acortar**: termina en un límite de compás; la transición decide si es con fundido o con cola.
  `acortar: "inicio"` (y `final`) alinean el material por el final: la cadencia cae en el punto final.
* **Anclas**: el tramo se desplaza para que el downbeat pedido caiga exacto; la entrada queda en el
  límite de compás más cercano a `inicio` (hasta medio compás antes o después). Si falta material
  antes del ancla se repite el loop previo o se arranca antes en la canción.
* **Tramos seguidos de la misma canción** con material contiguo (p. ej. para cambiar el nivel o los
  stems): si el siguiente entra a menos de medio compás del final natural, la música sigue sin
  empalme y solo cambia el nivel (rampa de 2 tiempos).
* **Colas de reverb**: vienen dentro de los stems, pero mezcladas con lo que sigue. Al cortar en un
  compás (cola, pausa, final sin la canción entera) el sonido directo se apaga en ½ tiempo y una
  **cola sintética** (la misma reverb de la banda, `generar_ir` del motor, alimentada con los
  últimos 2 tiempos) decae sola. Si el tramo llega al final real de la canción, suena su cola real.

## 6. Niveles

Valores por defecto (pedido del autor: "bajito, no me pongas la música a tope"):

| momento | criterio | parámetro |
|---|---|---|
| mientras habla la voz | música −24 LU respecto de la voz en sonoridad de corto plazo (ventana 22–26 dB) | `niveles.musica_bajo_voz_lu`, `ventana_lu`, `nivel_db` del tramo |
| pausas de la voz | sube (sin bombeo), pero nunca más que voz − 10 LU (≈ −26 LUFS-S si la voz está a −16) | `ducking.*`, `niveles.realce_pausas_db`, `techo_pausas_lu` |
| intro y final sin voz | más presente, pero como máximo −20 LUFS de corto plazo en la mezcla final | `niveles.realce_intro_db`, `techo_sin_voz_lufs` |
| mezcla final | −14 LUFS integrados, ≤ −1 dBTP; el limitador no debe tocar la voz más de ~1 dB | `master.*` |

**Cómo se logra:**
* *Música bajo la voz* se mide con compuerta de habla: ventanas de 3 s que cuentan solo los
  sub-bloques de 100 ms con voz, así la subida de las pausas no ensucia la medida.
* Cada **bloque** (una sección dentro de un tramo) recibe una ganancia propia, estimada proyectando
  la sonoridad K de la fuente (con las potencias cruzadas entre stems: el dron y el pad comparten
  fundamentales) con la curva de ducking y la EQ reales. Se respeta la mitad de la diferencia
  natural entre secciones (`conservar_dinamica`), dentro de ±`ventana_lu`, para que la música
  "vaya variando" con la emoción. Si al medir la cama renderizada un bloque quedó a más de 0,5 LU,
  se corrige y se vuelve a renderizar.
* **Techos** (guardia): donde la cama supera su techo (bajo la voz: objetivo + `nivel_db` +
  ventana; en pausas: voz − 10 LU; sin voz: −20 LUFS-S final) se baja toda la cama con rampas de
  ~0,5 s. Es lo que haría un mezclador con el fader.
* El **master** casi no tiene que limitar: la suma ya entra cerca de −14 (en las pruebas baja todo
  0,7–1 dB) y los picos de una voz a −16 LUFS / −1,5 dBTP quedan 1,3–1,6 dB bajo el techo. En las
  tres pruebas el limitador no actuó (0,0 dB); queda como seguro, con aviso si toca la voz > 1 dB.

## 7. Ducking por stems

* **Envolvente de la voz** (offline, con el futuro conocido): la bajada empieza `lookahead_ms` (50)
  antes de la primera sílaba y dura `ataque_ms` (80, rampa coseno); se mantiene mientras dura la
  frase y `mantener_ms` (200) después; la subida dura `relajacion_ms` (600, rampa coseno).
* **Anti-bombeo**: en pausas de menos de `pausa_minima_s` (0,6 s) la música no sube; desde
  `pausa_completa_s` (2 s) sube del todo; en el medio sube en proporción. En pausas largas
  (≥ `pausa_larga_s`, 2,5 s) suma `realce_pausas_db`, siempre bajo el techo.
* **Profundidad por stem** (dB a fondo): melodía −10, armonía −6, textura −6, batería −3, bajo −3.
* **EQ dinámica**: con voz, campana ancha en la franja de presencia (1,5–4 kHz, centro 2,45 kHz):
  −4 dB en el centro y ≈ −2 dB en los bordes, en armonía, melodía y textura. Se suma al hueco fijo
  de −3 dB que el motor ya deja en las secciones `voz=True`.

## 8. Parámetros

Todos se cambian en `"parametros"` del plan o con `--param ruta=valor`. Claves desconocidas = error.

| ruta | defecto | |
|---|---|---|
| `voz.lufs_esperado` | −16 | aviso si la voz se aparta > 1 LU |
| `voz.umbral_db`, `voz.histeresis_db` | −32, 6 | actividad: dB bajo el nivel activo del habla (p95) |
| `voz.min_habla_ms`, `voz.hueco_palabras_ms` | 60, 300 | ráfagas que no cuentan; huecos que quedan dentro de la frase |
| `ducking.activo` | true | |
| `ducking.lookahead_ms`, `ataque_ms`, `relajacion_ms`, `mantener_ms` | 50, 80, 600, 200 | §7 |
| `ducking.pausa_minima_s`, `pausa_completa_s` | 0,6, 2 | anti-bombeo |
| `ducking.profundidad_db.{stem}` | mel −10, arm −6, tex −6, bat −3, bajo −3 | |
| `ducking.eq.activo`, `desde_hz`, `hasta_hz`, `ganancia_db`, `stems` | true, 1500, 4000, −4, [armonia, melodia, textura] | |
| `niveles.musica_bajo_voz_lu`, `ventana_lu` | −24, 2 | §6 |
| `niveles.techo_pausas_lu`, `techo_sin_voz_lufs` | −10, −20 | techos |
| `niveles.conservar_dinamica` | 0,5 | 0 = todas las secciones al mismo nivel; 1 = toda la dinámica original (acotada a ± ventana) |
| `niveles.realce_pausas_db`, `pausa_larga_s`, `realce_intro_db`, `rampa_realce_s` | 4, 2,5, 8, 1,2 | subidas sin voz (bajo los techos) |
| `niveles.rampa_bloque_tiempos` | 2 | cambio de nivel entre secciones (termina en el downbeat) |
| `niveles.corregir`, `tolerancia_lu` | true, 0,5 | segunda pasada de nivel |
| `niveles.guardia_voz`, `guardia_max_db` | true, 12 | techos |
| `empalmes.loop_tiempos`, `empalme_tiempos` | 1, 0,5 | largo de los fundidos internos |
| `empalmes.guarda_ms`, `entrada_ms` | 30, 10 | |
| `empalmes.alinear_fase_ms` | 5 | 0 = sin búsqueda de desfase |
| `empalmes.stems_ritmicos` | [bateria, bajo] | nunca se superponen entre canciones |
| `transiciones.fundido_tiempos`, `cola_s`, `pausa_silencio_s`, `final_fundido_tiempos` | 4, 3, 2, 8 | valores por defecto de cada tipo |
| `transiciones.corte_cola_tiempos`, `ritmicos_salida_tiempos` | 0,5, 0,5 | fundido del directo antes de la cola; de batería y bajo al cambiar de canción |
| `transiciones.reverb.nivel_db`, `dur`, `predelay_ms`, `brillo`, `ancho`, `ventana_tiempos`, `stems` | −12, 3,6, 28, 0,45, 1, 2, [armonia, melodia, textura] | cola sintética |
| `master.lufs`, `techo_dbtp`, `lookahead_ms`, `relajacion_ms`, `margen_db` | −14, −1, 5, 80, 0,1 | |
| `master.max_reduccion_voz_db` | 1 | aviso si el limitador trabaja más sobre la voz |
| `salidas.fps`, `rango_db`, `png`, `qa` | 60, 48, true, true | |

## 9. Criterios recomendados (para escribir el plan)

* **Bajo la voz, secciones con `bajo_voz: true`** en `cues.json`: tienen la melodía escasa y el
  hueco en 2,4 kHz. Las cumbres (`bajo_voz: false`) van mejor en pausas largas, intros y finales;
  si una cumbre va bajo la voz, el nivel la acomoda, pero conviene `ducking.profundidad_db.melodia: -12`.
* **Qué stems bajar**: la melodía es lo que más compite con la palabra (−10 dB, hasta −12/−14 si la
  melodía es activa); armonía y textura ocupan la franja de la voz (−6 dB + EQ dinámica); batería
  y bajo sostienen el pulso y casi no enmascaran (−3 dB). Si el texto es denso, mejor
  `"stems": {"melodia": -4}` en el tramo que subir el ducking global.
* **Transiciones**: entre canciones con batería, `cola` o `fundido` corto (2–4 tiempos); fundidos
  largos solo si uno de los dos lados es ambiental. `pausa` para cambios de tema fuertes. `corte`
  dentro de una misma canción.
* **Anclas** para las revelaciones: poné `en` en el segundo exacto de la palabra (de
  `palabras_final.json`) y elegí la sección cuyo downbeat abre la idea (una que llega tras una
  subida: el compás anterior suele traer su redoble o su swell).
* **`nivel_db`** para el arco emocional: ±1–3 dB alcanzan; el sistema ya respeta la dinámica de cada sección.
* Un tramo de al menos 8 compases deja que la música respire; tramos de menos de 4 compases suenan a corte.

## 10. `envolventes.json`

```json
{"version": 1, "fps": 60, "cuadros": 9541, "duracion": 159.0, "sampleRate": 48000,
 "pistas": {"voz": {"nivel": "<u8 base64>", "rangoDb": [-56.8, -8.8], "onsets": [...], "fuerzaOnsets": [...], "bandas": {}},
            "musica": {"nivel": "...", "rangoDb": [...], "onsets": [...], "fuerzaOnsets": [...],
                       "bandas": {"graves": "...", "medios": "...", "agudos": "..."}}},
 "rmsDb": {"voz": [-120.0, ...], "musica": [...]},
 "vozActiva": [[480, 702], ...],
 "musica": {"bpm": 88, "compas": 4, "beats": [...], "downbeats": [0, 164, ...], "downbeats_s": [...],
            "secciones": [{"nombre": "umbral", "cancion": "01-umbral", "tramo": 1, "inicio": 0.0, "fin": 21.818,
                           "cuadro": 0, "cuadro_fin": 1309, "energia": 0.15, "emocion": "..."}],
            "tramos": [...], "transiciones": [...]}}
```

* `nivel`: RMS en dB mapeado a 0..1 (techo en el percentil 99,5, rango de 48 dB), como lo lee
  `crearEnvolventes`. `rmsDb`: el RMS real en dBFS por cuadro (escala de la mezcla final).
* `downbeats` / `beats`: los **efectivos** (los que suenan después de loops, empalmes, anclas y
  transiciones), en cuadros; `downbeats_s` en segundos. Pulsos: 4/4 → 4, 6/8 → 2.
* Se copia tal cual a `motion/remotion/public/datos/envolventes.json`:
  `useNivel('musica')`, `usePulso('downbeats')`, `useFaseCompas()`.

## 11. Pruebas

```bash
python3 motion/musica/mezcla/pruebas/voz_prueba.py              # voz TTS (edge-tts) con pausas de 0,25 a 6 s, 2:25
python3 motion/musica/mezcla/pruebas/voz_prueba.py --librivox   # voz real: «El escuerzo» (LibriVox), 8:44
python3 motion/musica/mezcla/pruebas/verificar.py --largo       # corre los tres planes y chequea los criterios
```

Planes: `plan_umbral.json` (varias secciones, loop largo, acorte, ancla, cola, fundido, pausa y
final natural), `plan_canciones.json` (Umbral → Deriva → Marea en 6/8 → Aurora → Umbral, dos
anclas) y `plan_largo.json` (voz real, las cinco canciones, siete tramos). Criterios que se
verifican: −14 LUFS ± 0,1; ≤ −1 dBTP; limitador sobre la voz ≤ 1 dB; música bajo la voz con
mediana en el objetivo ± 1 y ≥ 85 % en la ventana del tramo; pausas, intro, final y máximo bajo
sus techos; 0 clicks nuevos (detector del motor, comparado con la fuente); empalmes sin saltos de
nivel (≤ max(3 dB, p90 de la sección + 1,5 dB), medido en la cama armada); grilla ≤ 10 ms; anclas ≤ 1 ms; ducking presente
y sin subidas en pausas cortas; batería y bajo sin superponerse entre canciones.

Resultados (17/10/2026, ver `salida/_mezcla_pruebas/verificacion.json`): 57/57 criterios OK.

| prueba | duración | música bajo la voz: mediana · % en la ventana del tramo | pausas: máx vs voz | intro / final: máx | mezcla · pico | limitador sobre la voz | clicks nuevos | empalmes · anclas |
|---|---|---|---|---|---|---|---|---|
| `umbral` (TTS, 1 canción, 5 tramos) | 2:39 | −23,6 LU · 96 % | −13,9 LU | −21,9 / −24,2 LUFS-S | −14,0 LUFS · −1,69 dBTP | 0,0 dB | 0 | 3 loops OK · 0,0 ms |
| `canciones_mix` (TTS, 4 canciones) | 2:39 | −23,8 LU · 92 % | −13,0 LU | −21,5 / −24,2 LUFS-S | −14,0 LUFS · −1,66 dBTP | 0,0 dB | 0 | 2 loops OK · 0,0 / 0,0 ms |
| `largo` (voz real, 5 canciones, 7 tramos) | 8:52 | −24,0 LU · 90 % | −11,6 LU | −28,4 / −24,0 LUFS-S | −14,0 LUFS · −1,95 dBTP | 0,0 dB | 0 | 14 empalmes OK (5 loops igualados) · 0,0 / 0,0 ms |

En las tres, el ducking de la melodía es −10 dB mientras se habla, la música sube en las pausas
largas y no sube en ninguna pausa de menos de 0,6 s; batería y bajo no se superponen en ninguna
de las 10 transiciones entre canciones. Las ventanas fuera de la franja caen en los fundidos entre
tramos (la música baja un poco: la voz queda más clara).

## 12. Tiempos

Medido en esta máquina compartida (4 núcleos, 2 hilos por proceso), con el análisis de las
canciones ya en caché:

| | duración de la mezcla | total | detalle |
|---|---|---|---|
| `--validar` | cualquiera | 2–5 s | sin audio |
| `umbral` | 2:39 | 37 s | render 17 s, master 7 s, envolventes 4 s |
| `canciones_mix` | 2:39 | 51 s | dos renders de 17 s (un bloque se corrigió) |
| `largo` | 8:52 | 128 s | render 60 s, master 21 s, envolventes 20 s, techos 9 s, armado 7 s |

Regla práctica: **≈ 15 s por minuto de video** (≈ 2,5 min para 10 min; si hace falta la segunda
pasada de nivel se suma otro render, ≈ 7 s por minuto), más ~10 s por canción la primera vez que
se usa (después queda en caché). Memoria pico: 1,7 GB para 8:52 (≈ 2 GB para 10 min). Para videos largos conviene
correrlo en segundo plano.

## 13. Limitaciones

* No hay estiramiento de tiempo: dos anclas en un mismo tramo no pueden caer exactas a la vez
  (una por tramo; para otra, dividí el tramo). La entrada de un tramo anclado se corre hasta medio compás.
* Las colas de reverb de los cortes son sintéticas (misma reverb de la banda, sin el eco ni la
  sala corta de la batería); al final real de una canción suena la cola real.
* Los niveles se estiman y se miden con BS.1770 (ponderación K): miden sonoridad, no
  inteligibilidad. La EQ dinámica es una campana fija, no un análisis espectral de la voz.
* La actividad de la voz es por energía (la voz ya viene limpia): respiraciones fuertes cuentan
  como habla (la música baja un poco antes, lo que es inofensivo).
* `musica_cama.wav` va en la escala de la mezcla final; la voz de `voz_final.wav` va sin la ganancia del master.
