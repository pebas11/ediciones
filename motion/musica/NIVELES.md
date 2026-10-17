# Niveles de los instrumentos muestreados

Medición antes y después de la nivelación nueva del motor (octubre de 2026). Sirve para
rebalancear las canciones: la **tabla 2** dice cuánto cambió cada instrumento a las
velocidades típicas; compensalo con `vol` de la pista (o con la velocidad).

## Qué cambió

* **Medida por muestra** (en `muestras.py`, cacheada en el manifiesto): loudness K-ponderada
  (BS.1770). Sostenidos: potencia media de los primeros 5 s del tramo estable (bloques de 0,5 s
  recortados a +2,5 dB de su mediana, para que un regulador de la toma no decida el nivel).
  Percusivos: promedio, en dB, de una ventana corta después del ataque (0,4 s; pizzicato 0,3 s)
  y de la loudness integrada de los primeros 2 s. Se mide con la cadena con que suena cada banco
  por defecto (paneo y cierre M/S de las cuerdas, `abrir`, `tope_hz`, domado de los vibráfonos).
  Antes se usaba el rms de los primeros 200 ms (en las capas suaves de cuerdas, el arco todavía
  no había entrado: por eso la capa suave de chelos y violas quedaba 7–12 dB *más fuerte*) con
  topes de ±8/±30 dB.
* **Cada muestra va a la referencia de su capa** y las capas quedan separadas por `capas_db`
  (catálogo de `muestras.py`, de suave a fuerte respecto de la más fuerte): cuerdas, trémolos y
  pizzicatos −8 dB, piano −8, arpa −7, vibráfono −10, glock −10/−4. La curva de nivel es
  calibración + `rango_db`·(vel^curva − 1) + el cruce de capas en potencia: siempre monótona.
* **Cruce de capas sin cancelaciones.** Las dos capas de una nota son la misma cuerda o lámina
  grabada dos veces: después de corregir la afinación quedaban en fase fija y el cruce cancelaba
  (La4 del piano a vel 0,6 sonaba −40 LUFS: más bajo que la capa suave sola). Ahora la capa suave
  se alinea con la fuerte (desfase de hasta media onda y polaridad) y la mezcla se compensa en
  potencia K (en el contrabajo solista, con ventanas que siguen el tiempo).
* **Muestras excluidas** (defectuosas; se transponen las vecinas): vibráfono con arco La3 (casi
  vacía, sin fundamental), vibráfono Fa3 (grabada con la lámina apagada), arpa Re2 (cuerda
  apagada), glock Sol5 suave (cae 6 dB en 0,1 s) y viola Sol5 suave (regulador de 8 dB).
* **Calibración** rehecha: una nota a vel 0,6 = −26 LUFS (mediana de las alturas de las muestras).

**Convención de medida** (la del README): nota aislada; sostenidos = nota de 8 s medida entre 3 y 7 s
(vibráfono con arco: 10 s, entre 3 y 8 s); percusivos = LUFS integrado de los primeros 2 s. «Antes» se
midió con el código anterior (HEAD) y la misma convención; el vibráfono con arco no tenía instrumento:
su «antes» es el banco crudo (`Muestreador("vibrafono_arco", rango_db=18)`, como lo usaba «Marea»).

## 1. Resumen por instrumento

| instrumento | capas | excluidas | vel 0,6 (LUFS) | peor caída al subir la vel. | residuo máx. entre vecinas | rango vel 0,3→0,85 |
|---|---|---|---|---|---|---|
| `Piano()` | −8 / 0 dB | — | −29.0 → **−26.1** | −4.4 → **0** dB | 12.8 → **1.7** dB (nivelación: 1.2) | 14.7 → **22.5** dB |
| `Arpa()` | −7 / 0 dB | Re2 | −26.3 → **−26.0** | −0.6 → **0** dB | 9.1 → **2.7** dB (nivelación: 1.3) | 11.1 → **18.4** dB |
| `Glock()` | −10 / −4 / 0 dB | Sol5 (suave) | −24.8 → **−26.0** | −1.5 → **0** dB | 5.6 → **1.1** dB (nivelación: 0.3) | 8.1 → **20.7** dB |
| `Vibrafono()` | −10 / 0 dB | Fa3 | −31.6 → **−26.0** | −6.0 → **0** dB | 13.7 → **1.4** dB (nivelación: 0.2) | 12.1 → **22.1** dB |
| `VibrafonoArco()` (nuevo) | 1 capa | La3 | −16.1 → **−26.0** | 0 → **0** dB | 11.1 → **0.6** dB | 9.9 → **11.0** dB |
| `Violines()` | −8 / 0 dB | — | −25.1 → **−25.9** | −0.4 → **0** dB | 4.5 → **1.2** dB | 12.0 → **19.1** dB |
| `Violas()` | −8 / 0 dB | Sol5 (suave) | −25.4 → **−26.0** | −4.5 → **0** dB | 8.0 → **1.4** dB | 5.1 → **20.1** dB |
| `Chelos()` | −8 / 0 dB | — | −29.2 → **−26.0** | −9.4 → **0** dB | 8.6 → **1.1** dB | 0.7 → **19.8** dB |
| `Contrabajo()` | −8 / 0 dB | — | −26.4 → **−26.0** | −0.7 → **0** dB | 10.3 → **1.5** dB | 14.1 → **18.9** dB |
| `CuerdasTrem("violines")` | −8 / 0 dB | — | −29.2 → **−26.1** | −6.9 → **0** dB | 6.8 → **0.9** dB | 0.9 → **19.4** dB |
| `CuerdasTrem("violas")` | −8 / 0 dB | — | −24.0 → **−26.0** | −1.2 → **0** dB | 7.3 → **0.9** dB | 9.9 → **19.6** dB |
| `CuerdasTrem("chelos")` | −8 / 0 dB | — | −26.7 → **−26.0** | −0.1 → **0** dB | 4.2 → **0.6** dB | 11.1 → **19.5** dB |
| `Pizzicato("violines")` | −8 / 0 dB | — | −23.4 → **−26.0** | 0 → **0** dB | 6.7 → **1.9** dB (nivelación: 1.3) | 11.3 → **18.8** dB |
| `Pizzicato("chelos")` | −8 / 0 dB | — | −25.3 → **−26.0** | −0.3 → **0** dB | 5.8 → **2.5** dB (nivelación: 0.9) | 10.9 → **18.5** dB |
| `Pizzicato("contrabajo")` | −8 / 0 dB | — | −29.4 → **−26.0** | −5.4 → **0** dB | 8.1 → **2.6** dB (nivelación: 0.9) | 9.3 → **17.7** dB |

* *Peor caída*: lo máximo que baja el nivel al subir la velocidad (en las alturas de las
  muestras; los percusivos, con la energía K de los 2 s, sin la compuerta de BS.1770, que baja
  la medida cuando una capa trae más cola). Antes los crescendos podían bajar hasta 9 dB.
* *Residuo entre vecinas*: cuánto se aparta el nivel de cada muestra de la recta entre sus dos
  vecinas, en la convención del README. En los percusivos, entre paréntesis, el mismo residuo
  en la métrica de la nivelación (ataque + 2 s): ≤ 1,5 dB en todos. En los 2 s solos quedan
  diferencias de forma, no de nivel: el pizzicato de Re2 del contrabajo es cuerda al aire y suena
  más largo; el arpa a vel 0,6 en La4 mezcla dos capas con colas distintas.
* Saltos entre semitonos vecinos (donde se cambia de muestra): ≤ 1,5 dB, salvo el vibráfono con
  arco (2,1 dB entre Fa5 y Fa#5: tiene 5 muestras útiles, cada una transpuesta hasta ±3,5 st).

## 2. Cambio neto esperado (después − antes, dB)

Mediana en las alturas de las muestras; entre corchetes, del 10 % al 90 % de las alturas (el
«antes» era desparejo entre notas, así que el cambio depende de la nota). Positivo = suena más
fuerte que antes. Para que la mezcla vuelva a sonar como antes, restá este valor al `vol`.

| instrumento | vel ≤ 0,3 | vel 0,45 | vel 0,6 | vel 0,75 | vel 0,85 |
|---|---|---|---|---|---|
| `Piano()` | **−1.8** [−6.0 … +0.1] | **−0.4** [−4.6 … +2.4] | **+2.7** [−0.9 … +7.9] | **+4.6** [+1.3 … +8.7] | **+5.6** [+2.6 … +7.2] |
| `Arpa()` | **−3.5** [−6.4 … +8.0] | **−3.7** [−6.4 … +8.0] | **+0.3** [−4.4 … +3.6] | **+2.9** [−1.1 … +6.0] | **+3.7** [+1.0 … +5.8] |
| `Glock()` | **−7.6** [−10.8 … −5.5] | **−2.9** [−8.0 … −1.0] | **−1.2** [−2.0 … +0.0] | **+3.2** [−2.5 … +4.9] | **+5.1** [−0.6 … +5.4] |
| `Vibrafono()` | **−6.0** [−7.2 … −5.1] | **−1.0** [−4.2 … +4.1] | **+3.6** [−0.3 … +12.0] | **+3.8** [+2.8 … +7.3] | **+4.2** [+1.7 … +7.5] |
| `VibrafonoArco()` (nuevo) | **−12.4** [−14.9 … −7.7] | **−12.1** [−14.6 … −7.4] | **−11.8** [−14.3 … −7.1] | **−11.5** [−14.0 … −6.8] | **−11.3** [−13.8 … −6.6] |
| `Violines()` | **−8.3** [−11.2 … −6.9] | **−6.4** [−9.6 … −5.3] | **−1.2** [−5.7 … +0.1] | **+0.3** [−5.1 … +2.5] | **+0.3** [−5.1 … +2.5] |
| `Violas()` | **−11.5** [−13.4 … −9.4] | **−9.0** [−10.5 … −7.0] | **−0.5** [−2.6 … +0.4] | **+3.9** [−1.2 … +6.0] | **+3.9** [−1.1 … +6.2] |
| `Chelos()` | **−8.4** [−12.4 … −5.4] | **−5.9** [−10.7 … −2.8] | **+3.2** [−1.0 … +5.8] | **+10.5** [+8.9 … +13.3] | **+10.6** [+9.0 … +13.4] |
| `Contrabajo()` | **−4.4** [−12.9 … +2.0] | **−3.2** [−11.1 … +2.5] | **+0.4** [−4.9 … +3.6] | **+1.8** [−2.7 … +4.6] | **+1.8** [−2.7 … +4.7] |
| `CuerdasTrem("violines")` | **−7.0** [−13.8 … −4.1] | **−4.4** [−11.0 … −1.6] | **+3.3** [−1.2 … +6.8] | **+8.5** [+7.7 … +11.5] | **+8.7** [+7.8 … +11.5] |
| `CuerdasTrem("violas")` | **−9.7** [−15.4 … −7.8] | **−7.7** [−13.1 … −5.4] | **−1.8** [−7.1 … +0.7] | **−0.5** [−5.4 … +3.3] | **−0.5** [−5.4 … +3.3] |
| `CuerdasTrem("chelos")` | **−7.7** [−9.7 … −4.1] | **−5.5** [−7.0 … −2.2] | **+0.7** [−1.4 … +2.0] | **+2.8** [−0.6 … +3.9] | **+2.8** [−0.6 … +4.0] |
| `Pizzicato("violines")` | **−6.7** [−9.1 … −5.3] | **−5.5** [−6.8 … −2.2] | **−2.3** [−3.3 … +0.6] | **−0.0** [−1.0 … +2.4] | **+0.8** [−0.6 … +2.3] |
| `Pizzicato("chelos")` | **−6.6** [−8.9 … −5.3] | **−5.2** [−8.4 … −3.7] | **−1.2** [−4.3 … +0.3] | **+0.6** [−1.3 … +2.4] | **+1.1** [−0.4 … +2.6] |
| `Pizzicato("contrabajo")` | **−1.5** [−4.6 … +0.5] | **−0.7** [−3.7 … +4.1] | **+2.8** [−0.3 … +8.1] | **+6.0** [+4.2 … +8.8] | **+7.0** [+6.2 … +8.2] |

* Debajo de 0,3 el cambio es el mismo que a 0,3 (las dos versiones usan solo la capa suave).
* `VibrafonoArco()`: su «antes» es el banco crudo, sin calibrar (−16 LUFS a vel 0,6). «Marea» lo usaba
  con `ganancia_db=-11` y su tabla `CORR` (−27,2 a −30,9 LUFS a vel 0,6): contra eso, el nuevo suena
  +1 a +2 dB en casi todas las notas y +5 dB en Mi6.
  «Espiral» usaba su `ArcoVibrafono` (nivel propio): el instrumento nuevo suena a −26 LUFS a vel 0,6.

Además (no muestreados):

* `Sub()`: la velocidad ya no se aplasta en la saturación. A vel 0,7 suena idéntico; vel 0,3 −3,5 dB,
  0,5 −1,8 dB, 0,78 +0,7 dB, 0,9 +1,7 dB respecto de antes (de 0,5 a 0,78 ahora hay 4,4 dB; antes, 1,8).
  Con `glide_ms`, las notas no ligadas ya no deslizan.
* `Piano()`: cuando el pedal sube y apaga k notas a la vez, el ruido de cada apagador baja √k y se
  reparte en 25 ms (antes sumaban: con `pedal_por_compas`, un golpe en cada cambio de compás). Con
  acordes de 5 notas, el ruido en cada cambio de pedal baja 7 dB (de −5,9 a −12,4 dB respecto del
  piano). Un apagador solo (nota soltada con la tecla) suena igual que antes.
* Vibráfonos: domado del parcial 4·f0 (−8 dB después del ataque; con arco, −12 dB) y del 3er modo
  de las láminas graves (a −30 dB de la fundamental). Con `domar=0` vuelve el timbre crudo (la
  nivelación se midió domada: crudos, Sol#3–Do#4 suenan 1–2 dB más en el ataque).

## 3. Tablas por instrumento (LUFS, nota aislada)

Alturas de muestras reales repartidas en el rango (en «después», tocadas sin transponer).

### `Piano()`

| altura | antes 0,3 | antes 0,6 | antes 0,85 | después 0,3 | después 0,6 | después 0,85 |
|---|---|---|---|---|---|---|
| La0 | −30.4 | −21.9 | −16.5 | −37.9 | −24.8 | −15.5 |
| La1 | −30.3 | −19.9 | −15.6 | −37.5 | −24.4 | −15.1 |
| La2 | −33.3 | −26.0 | −20.1 | −38.2 | −25.3 | −16.1 |
| La3 | −36.0 | −29.1 | −21.8 | −39.1 | −26.3 | −17.1 |
| La4 | −36.9 | −40.1 | −22.8 | −38.3 | −25.0 | −16.3 |
| La5 | −39.9 | −36.5 | −24.4 | −40.1 | −26.2 | −17.7 |
| La6 | −39.0 | −26.4 | −20.0 | −40.4 | −26.8 | −17.5 |
| La7 | −40.4 | −32.3 | −26.2 | −41.1 | −27.0 | −18.9 |
| Do8 | −39.4 | −33.5 | −24.7 | −41.0 | −27.1 | −17.9 |

### `Arpa()`

| altura | antes 0,3 | antes 0,6 | antes 0,85 | después 0,3 | después 0,6 | después 0,85 |
|---|---|---|---|---|---|---|
| Mi1 | −44.2 | −32.0 | −21.1 | −34.2 | −25.0 | −15.4 |
| Fa2 | −30.6 | −25.9 | −20.1 | −34.2 | −25.2 | −15.7 |
| Mi3 | −32.6 | −26.3 | −21.4 | −35.8 | −26.9 | −17.3 |
| Re4 | −30.5 | −25.8 | −23.1 | −35.6 | −27.1 | −17.8 |
| Do5 | −29.4 | −25.2 | −22.8 | −35.8 | −25.0 | −17.2 |
| Si5 | −33.1 | −25.8 | −21.2 | −35.8 | −26.7 | −17.4 |
| La6 | −31.2 | −24.5 | −19.5 | −34.5 | −25.7 | −17.3 |
| Fa7 | −38.4 | −27.1 | −17.0 | −35.5 | −24.9 | −15.5 |

### `Glock()`

| altura | antes 0,3 | antes 0,6 | antes 0,85 | después 0,3 | después 0,6 | después 0,85 |
|---|---|---|---|---|---|---|
| Sol5 | −33.3 | −25.8 | −23.6 | −35.9 | −27.0 | −18.4 |
| Do6 | −28.8 | −24.8 | −22.9 | −36.6 | −26.0 | −17.2 |
| Sol6 | −30.0 | −26.0 | −22.8 | −37.5 | −26.3 | −17.7 |
| Do7 | −30.1 | −27.4 | −22.1 | −37.6 | −26.9 | −17.0 |
| Sol7 | −26.3 | −23.3 | −15.2 | −37.0 | −25.4 | −15.9 |
| Sol#7 | −26.6 | −23.3 | −15.6 | −37.3 | −25.4 | −16.2 |
| Do8 | −29.2 | −24.8 | −21.1 | −36.9 | −25.3 | −16.1 |

### `Vibrafono()`

| altura | antes 0,3 | antes 0,6 | antes 0,85 | después 0,3 | después 0,6 | después 0,85 |
|---|---|---|---|---|---|---|
| La3 | −36.9 | −31.6 | −31.4 | −41.2 | −25.9 | −18.2 |
| Do4 | −33.0 | −25.2 | −24.5 | −39.7 | −25.2 | −17.6 |
| Mi4 | −34.2 | −26.3 | −23.1 | −40.2 | −25.7 | −18.1 |
| Sol4 | −33.6 | −27.0 | −22.4 | −40.0 | −25.5 | −17.9 |
| Si4 | −34.4 | −27.2 | −22.3 | −40.4 | −25.9 | −18.4 |
| Re5 | −34.6 | −43.2 | −22.6 | −40.5 | −26.1 | −18.6 |
| Fa5 | −35.9 | −33.1 | −23.2 | −41.1 | −26.5 | −18.9 |
| La5 | −35.0 | −37.4 | −20.9 | −41.0 | −26.4 | −18.8 |
| Do6 | −34.7 | −24.5 | −21.5 | −41.7 | −27.2 | −19.6 |
| Mi6 | −32.9 | −38.2 | −19.9 | −41.4 | −26.8 | −19.4 |

### `VibrafonoArco()` (nuevo)

| altura | antes 0,3 | antes 0,6 | antes 0,85 | después 0,3 | después 0,6 | después 0,85 |
|---|---|---|---|---|---|---|
| Mi4 | −23.5 | −18.1 | −13.6 | −32.1 | −26.1 | −21.1 |
| Sol4 | −24.9 | −19.5 | −15.0 | −32.0 | −26.0 | −21.0 |
| Re5 | −18.3 | −12.9 | −8.4 | −32.5 | −26.5 | −21.5 |
| La5 | −19.5 | −14.1 | −9.6 | −31.9 | −25.9 | −20.9 |
| Mi6 | −16.5 | −11.1 | −6.6 | −31.9 | −25.9 | −20.9 |

### `Violines()`

| altura | antes 0,3 | antes 0,6 | antes 0,85 | después 0,3 | después 0,6 | después 0,85 |
|---|---|---|---|---|---|---|
| Sol3 | −34.1 | −26.0 | −20.0 | −39.5 | −26.0 | −19.5 |
| Si3 | −32.1 | −25.4 | −20.1 | −39.0 | −26.1 | −19.8 |
| Fa#4 | −31.4 | −23.6 | −18.1 | −39.7 | −25.9 | −19.6 |
| Do5 | −26.8 | −24.4 | −22.2 | −38.9 | −25.9 | −19.7 |
| Sol5 | −28.4 | −20.2 | −14.6 | −38.6 | −25.9 | −19.7 |
| Re6 | −27.1 | −18.8 | −13.1 | −38.4 | −25.6 | −19.5 |

### `Violas()`

| altura | antes 0,3 | antes 0,6 | antes 0,85 | después 0,3 | después 0,6 | después 0,85 |
|---|---|---|---|---|---|---|
| Do3 | −31.2 | −23.0 | −17.6 | −40.4 | −25.6 | −19.3 |
| Mi3 | −28.4 | −26.0 | −23.4 | −40.0 | −26.0 | −19.5 |
| Si3 | −28.6 | −26.1 | −25.3 | −39.1 | −26.2 | −19.9 |
| Fa4 | −30.2 | −27.3 | −25.0 | −41.0 | −25.8 | −19.5 |
| Do5 | −27.3 | −25.4 | −25.4 | −41.0 | −26.0 | −19.6 |
| Sol5 | −24.6 | −23.0 | −25.7 | −39.4 | −25.5 | −19.3 |
| Re6 | −27.6 | −20.0 | −14.5 | −39.6 | −26.1 | −19.8 |

### `Chelos()`

| altura | antes 0,3 | antes 0,6 | antes 0,85 | después 0,3 | después 0,6 | después 0,85 |
|---|---|---|---|---|---|---|
| Do2 | −24.6 | −22.7 | −25.1 | −39.0 | −26.1 | −19.8 |
| Sol2 | −26.6 | −25.2 | −32.4 | −38.7 | −26.3 | −20.1 |
| Re3 | −26.5 | −25.8 | −33.3 | −38.6 | −26.3 | −19.6 |
| La3 | −31.1 | −29.2 | −30.4 | −39.5 | −26.1 | −19.8 |
| Mi4 | −35.9 | −32.2 | −29.5 | −39.7 | −25.2 | −19.3 |
| Si4 | −33.9 | −30.9 | −28.4 | −39.1 | −25.7 | −19.4 |
| Fa5 | −30.7 | −29.1 | −30.5 | −39.3 | −25.9 | −19.5 |

### `Contrabajo()`

| altura | antes 0,3 | antes 0,6 | antes 0,85 | después 0,3 | después 0,6 | después 0,85 |
|---|---|---|---|---|---|---|
| Mi1 | −40.1 | −28.7 | −22.3 | −39.4 | −25.0 | −19.2 |
| Sol1 | −42.3 | −31.6 | −26.6 | −39.0 | −25.3 | −19.6 |
| Do2 | −36.1 | −25.5 | −19.7 | −39.0 | −25.8 | −20.0 |
| Mi2 | −39.0 | −29.7 | −25.3 | −38.8 | −26.2 | −20.4 |
| Sol#2 | −25.1 | −20.8 | −17.3 | −39.0 | −26.0 | −20.2 |
| Do#3 | −34.0 | −27.3 | −21.8 | −38.9 | −25.8 | −19.9 |
| Sol#3 | −27.8 | −26.3 | −22.4 | −38.7 | −26.1 | −20.2 |
| Si3 | −32.0 | −18.3 | −12.1 | −39.3 | −26.2 | −20.4 |

### `CuerdasTrem("violines")`

| altura | antes 0,3 | antes 0,6 | antes 0,85 | después 0,3 | después 0,6 | después 0,85 |
|---|---|---|---|---|---|---|
| Sol3 | −34.5 | −32.6 | −33.6 | −39.7 | −26.1 | −19.8 |
| Si3 | −32.2 | −29.2 | −27.6 | −39.2 | −25.9 | −19.8 |
| Fa#4 | −33.5 | −30.5 | −28.1 | −39.0 | −26.1 | −19.9 |
| Do5 | −34.8 | −31.1 | −27.6 | −39.7 | −26.1 | −19.6 |
| Sol5 | −25.8 | −24.6 | −29.9 | −39.6 | −25.8 | −19.6 |
| Re6 | −24.5 | −23.2 | −26.2 | −39.2 | −26.1 | −19.8 |

### `CuerdasTrem("violas")`

| altura | antes 0,3 | antes 0,6 | antes 0,85 | después 0,3 | después 0,6 | después 0,85 |
|---|---|---|---|---|---|---|
| Do3 | −30.4 | −26.6 | −23.1 | −39.4 | −25.8 | −19.7 |
| Sol3 | −30.4 | −25.7 | −21.1 | −39.3 | −26.0 | −19.6 |
| Re4 | −31.4 | −26.3 | −22.1 | −39.3 | −26.4 | −20.2 |
| La4 | −26.3 | −19.0 | −13.5 | −39.7 | −26.4 | −20.1 |
| Mi5 | −26.8 | −19.8 | −14.4 | −40.0 | −26.4 | −20.0 |
| Si5 | −21.5 | −18.8 | −17.5 | −39.2 | −25.9 | −19.9 |
| Re6 | −27.2 | −24.6 | −23.9 | −38.7 | −25.9 | −19.8 |

### `CuerdasTrem("chelos")`

| altura | antes 0,3 | antes 0,6 | antes 0,85 | después 0,3 | después 0,6 | después 0,85 |
|---|---|---|---|---|---|---|
| Do2 | −35.0 | −29.0 | −23.7 | −39.0 | −26.1 | −19.6 |
| Sol2 | −30.9 | −24.4 | −18.9 | −39.1 | −26.1 | −19.7 |
| Re3 | −29.2 | −26.0 | −23.6 | −39.3 | −25.7 | −19.6 |
| La3 | −33.8 | −27.9 | −22.8 | −39.2 | −26.5 | −20.2 |
| Do4 | −31.6 | −27.1 | −22.8 | −39.5 | −26.1 | −19.6 |
| Sol4 | −30.4 | −23.6 | −18.1 | −39.2 | −25.8 | −19.5 |
| Re5 | −34.3 | −25.4 | −19.4 | −39.1 | −26.0 | −19.6 |
| Fa5 | −31.5 | −26.6 | −21.9 | −39.1 | −26.0 | −19.6 |

### `Pizzicato("violines")`

| altura | antes 0,3 | antes 0,6 | antes 0,85 | después 0,3 | después 0,6 | después 0,85 |
|---|---|---|---|---|---|---|
| Sol3 | −35.5 | −27.2 | −22.0 | −38.8 | −27.0 | −19.4 |
| Si3 | −30.5 | −23.0 | −19.0 | −37.2 | −26.0 | −18.1 |
| Fa#4 | −31.1 | −26.8 | −20.6 | −37.8 | −26.1 | −19.3 |
| Do5 | −23.4 | −20.9 | −18.3 | −36.9 | −25.8 | −18.1 |
| Sol5 | −29.2 | −23.3 | −17.1 | −38.3 | −25.6 | −17.7 |
| Re6 | −29.0 | −22.7 | −18.1 | −37.2 | −26.0 | −18.3 |

### `Pizzicato("chelos")`

| altura | antes 0,3 | antes 0,6 | antes 0,85 | después 0,3 | después 0,6 | después 0,85 |
|---|---|---|---|---|---|---|
| Do2 | −31.0 | −25.4 | −19.8 | −37.2 | −27.2 | −18.7 |
| Sol2 | −30.9 | −25.8 | −21.4 | −36.9 | −27.0 | −18.6 |
| Re3 | −33.9 | −25.6 | −21.3 | −38.1 | −27.1 | −19.3 |
| La3 | −30.7 | −29.0 | −19.8 | −37.4 | −26.0 | −18.1 |
| Mi4 | −30.9 | −25.4 | −19.7 | −37.4 | −25.5 | −18.7 |
| Si4 | −28.2 | −24.0 | −18.3 | −36.1 | −25.1 | −17.5 |
| Fa5 | −27.2 | −19.0 | −15.4 | −36.0 | −24.9 | −17.0 |

### `Pizzicato("contrabajo")`

| altura | antes 0,3 | antes 0,6 | antes 0,85 | después 0,3 | después 0,6 | después 0,85 |
|---|---|---|---|---|---|---|
| Mi1 | −35.5 | −29.3 | −23.8 | −35.8 | −24.3 | −17.0 |
| Sol1 | −36.1 | −32.5 | −25.4 | −36.2 | −26.3 | −17.7 |
| Do2 | −36.1 | −34.0 | −26.6 | −35.7 | −25.1 | −17.5 |
| Mi2 | −37.6 | −30.2 | −24.0 | −36.6 | −25.1 | −17.5 |
| Sol#2 | −30.6 | −26.1 | −24.6 | −35.9 | −25.8 | −18.1 |
| Do#3 | −36.3 | −31.5 | −26.3 | −37.3 | −26.2 | −19.0 |
| Sol#3 | −33.2 | −28.9 | −26.1 | −36.1 | −27.0 | −19.8 |
| Si3 | −30.3 | −26.5 | −26.9 | −35.2 | −27.1 | −19.4 |

