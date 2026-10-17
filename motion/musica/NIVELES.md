# Niveles de los instrumentos muestreados

Medición antes y después de la nivelación nueva del motor (octubre de 2026). Sirve para
rebalancear las canciones: la **tabla 2** dice cuánto cambió cada instrumento a las
velocidades típicas (mediana de todo el rango) y la **2b** cuánto en cada registro, con las
notas que más cambiaron (en las cuerdas, también para notas cortas: **2c**); compensalo con
`vol` de la pista (o con la velocidad).

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

**La mediana subestima los registros extremos y algunas notas sueltas** (p. ej. el contrabajo
en La1–Sol#2 o los violines en Re5–Re6 bajaron bastante más que la mediana). Para compensar
una parte concreta usá la **tabla 2b** (por registro, con la nota que más bajó y la que más
subió), la **2c** si las notas de cuerdas son cortas, o la **tabla 3** (nivel por altura).

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

## 2b. Cambio por registro (después − antes, dB)

Cada instrumento partido en tres registros (tercios de su rango, contando cada semitono: también
las notas transpuestas, que heredan el nivel de su muestra). Mediana del registro y, entre
corchetes, la nota que más bajó y la que más subió. Misma convención de medida que la tabla 2:
sostenidos en el tramo estable de una nota de 8 s; percusivos, sus primeros 2 s.

| instrumento | registro | vel 0,3 | vel 0,6 | vel 0,85 |
|---|---|---|---|---|
| `Piano()` | grave (La0–Do#3) | **−5.3** [La0 −7.5 … Do3 −2.8] | **−0.3** [Sol#1 −4.6 … Do2 +6.3] | **+3.1** [Sol#1 +0.4 … Do2 +5.6] |
|  | medio (Re3–Fa#5) | **−1.5** [La3 −3.1 … Fa5 +1.5] | **+4.5** [Sol4 −0.9 … La4 +15.1] | **+5.9** [Sol4 +3.7 … Mi5 +9.6] |
|  | agudo (Sol5–Do8) | **−0.9** [Do6 −2.6 … Fa6 +1.0] | **+4.2** [Sol#6 −0.8 … La5 +10.3] | **+6.5** [La6 +2.5 … Mi7 +10.6] |
| `Arpa()` | grave (Mi1–Re#3) | **−2.7** [Fa#2 −3.6 … Mi1 +10.0] | **+2.2** [Re3 −0.7 … Sol1 +7.3] | **+5.0** [Do#3 +3.2 … Re#2 +7.6] |
|  | medio (Mi3–Mi5) | **−5.1** [Mi4 −8.4 … Fa3 −3.2] | **−2.4** [Mi5 −4.8 … Sol4 +1.2] | **+3.7** [Mi5 +1.0 … La#4 +6.4] |
|  | agudo (Fa5–Fa7) | **−3.5** [Fa5 −7.3 … Do#7 +8.5] | **−0.1** [Fa#5 −4.9 … Do#7 +5.4] | **+2.2** [Fa#5 +0.1 … Do#6 +4.8] |
| `Glock()` | grave (Sol5–Mi6) | **−7.9** [Do#6 −7.9 … Sol#5 −2.4] | **−1.2** [La5 −1.3 … Mi6 −0.3] | **+5.4** [Sol#5 +4.9 … Re6 +5.7] |
|  | medio (Fa6–Re7) | **−7.5** [La#6 −7.5 … La6 −7.5] | **+0.1** [Fa#6 −0.3 … Do7 +0.5] | **+5.1** [La#6 +3.6 … La6 +5.6] |
|  | agudo (Re#7–Do8) | **−10.7** [Fa7 −10.8 … Re#7 −7.5] | **−2.0** [La7 −2.0 … Re#7 +0.5] | **−0.1** [Sol#7 −0.7 … La#7 +5.0] |
| `Vibrafono()` | grave (La3–Fa#4) | **−6.1** [Si3 −6.7 … La#3 −4.2] | **+0.6** [Si3 −0.0 … La#3 +5.8] | **+6.0** [Fa#4 +4.5 … La#3 +13.2] |
|  | medio (Sol4–Fa5) | **−6.0** [Sol4 −6.4 … Mi5 −5.2] | **+1.5** [La4 +1.2 … Re#5 +17.1] | **+4.0** [La4 +3.9 … Sol4 +4.5] |
|  | agudo (Fa#5–Mi6) | **−7.0** [Re6 −8.5 … Fa#5 −5.2] | **+11.0** [Si5 −2.7 … Mi6 +11.4] | **+1.9** [Mi6 +0.5 … Fa#5 +4.4] |
| `VibrafonoArco()` (nuevo) | grave (Mi4–Si4) | **−7.3** [Si4 −14.4 … Fa#4 −7.1] | **−6.7** [Si4 −13.9 … Fa#4 −6.4] | **−6.2** [Si4 −13.4 … Fa#4 −6.0] |
|  | medio (Do5–Sol5) | **−14.2** [Do5 −14.4 … Fa#5 −12.5] | **−13.6** [Do5 −13.8 … Fa#5 −11.9] | **−13.1** [Do5 −13.3 … Fa#5 −11.4] |
|  | agudo (Sol#5–Mi6) | **−12.5** [Do#6 −16.4 … Do6 −11.8] | **−11.9** [Do#6 −15.9 … Do6 −11.2] | **−11.4** [Do#6 −15.4 … Do6 −10.7] |
| `Violines()` | grave (Sol3–Mi4) | **−7.1** [Sol#3 −8.8 … Sol3 −5.4] | **−0.7** [Mi4 −2.3 … Sol3 +0.1] | **+0.3** [Mi4 −1.4 … Sol#3 +0.6] |
|  | medio (Fa4–Re#5) | **−10.2** [Si4 −12.1 … Re5 −7.6] | **−1.4** [Fa4 −2.3 … Sol#4 +0.2] | **+2.5** [Fa4 −1.4 … Sol#4 +3.8] |
|  | agudo (Mi5–Re6) | **−8.0** [Do#6 −11.2 … Mi5 −7.6] | **−3.2** [Re6 −6.8 … Mi5 −1.0] | **−2.9** [Do#6 −6.4 … Mi5 +0.5] |
| `Violas()` | grave (Do3–Do4) | **−11.5** [Re3 −11.9 … Do3 −9.1] | **−0.1** [Do3 −2.7 … Fa3 +0.3] | **+5.4** [Do3 −1.7 … Fa#3 +6.9] |
|  | medio (Do#4–Do#5) | **−11.8** [Do5 −13.7 … Do#4 −10.1] | **−0.5** [Si4 −0.9 … Fa#4 +1.9] | **+5.0** [Do#4 +1.1 … Si4 +5.8] |
|  | agudo (Re5–Re6) | **−10.9** [Fa#5 −15.7 … Do6 −9.2] | **−0.7** [Re6 −6.2 … Si5 +0.4] | **+3.0** [Do#6 −5.3 … Fa#5 +6.3] |
| `Chelos()` | grave (Do2–Do#3) | **−12.1** [Do2 −14.3 … Re2 −6.0] | **−0.2** [Do2 −3.4 … Re2 +4.9] | **+11.6** [Do2 +5.3 … Do#3 +13.7] |
|  | medio (Re3–Re#4) | **−8.4** [Re3 −12.1 … Re4 −3.8] | **+3.4** [Re3 −0.5 … Re#4 +6.9] | **+10.6** [Mi3 +9.1 … Do4 +14.3] |
|  | agudo (Mi4–Fa5) | **−6.2** [Fa5 −8.6 … Fa4 −3.6] | **+5.3** [Mi5 +3.1 … Mi4 +7.1] | **+10.5** [La4 +9.0 … Sol4 +12.5] |
| `Contrabajo()` | grave (Mi1–Do#2) | **−1.1** [La1 −7.2 … Sol1 +3.3] | **+2.1** [La#1 −3.1 … Sol#1 +6.4] | **+2.4** [La1 −2.4 … Sol1 +7.1] |
|  | medio (Re2–Do3) | **−4.9** [Sol2 −14.0 … Re2 +2.6] | **−1.6** [Sol#2 −5.2 … Mi2 +3.5] | **−0.4** [Sol#2 −2.8 … Re#2 +4.9] |
|  | agudo (Do#3–Si3) | **−7.3** [Fa#3 −10.9 … Do#3 −5.0] | **+0.2** [La#3 −8.1 … Fa3 +3.5] | **+2.2** [Si3 −8.2 … Re#3 +2.7] |
| `CuerdasTrem("violines")` | grave (Sol3–Mi4) | **−4.7** [La#3 −7.0 … Sol#3 −2.2] | **+6.6** [La#3 +3.3 … Sol#3 +7.7] | **+11.3** [La#3 +7.8 … Sol3 +13.8] |
|  | medio (Fa4–Re#5) | **−5.5** [La4 −11.4 … Do5 −4.9] | **+4.4** [Sol#4 +0.0 … Fa4 +5.9] | **+8.2** [Si4 +7.7 … Fa4 +11.7] |
|  | agudo (Mi5–Re6) | **−12.8** [Re6 −14.7 … Mi5 −9.9] | **−0.9** [Re6 −2.9 … Fa5 +1.4] | **+9.9** [Do#6 +6.4 … Sol5 +10.3] |
| `CuerdasTrem("violas")` | grave (Do3–Do4) | **−9.0** [La#3 −10.4 … Fa#3 −8.9] | **−2.5** [Do4 −3.0 … Do3 +0.8] | **−1.5** [Re3 −1.5 … Do#3 +3.4] |
|  | medio (Do#4–Do#5) | **−7.9** [Sol#4 −13.4 … Fa#4 −4.4] | **−0.6** [La#4 −7.4 … Mi4 +1.2] | **+0.5** [Sol4 −6.5 … Re4 +1.9] |
|  | agudo (Re5–Re6) | **−15.6** [La#5 −17.8 … Do#6 −11.5] | **−6.5** [Do6 −7.1 … Re6 −1.2] | **−3.5** [Re5 −5.6 … Do#6 +4.2] |
| `CuerdasTrem("chelos")` | grave (Do2–Do#3) | **−8.1** [La2 −11.0 … Do2 −4.1] | **+0.2** [La2 −2.3 … Do#2 +3.2] | **+2.9** [Fa#2 −0.8 … Do2 +4.1] |
|  | medio (Re3–Re#4) | **−6.7** [Re#3 −10.1 … Fa#3 −3.6] | **+1.3** [Re3 +0.3 … Mi3 +1.9] | **+3.1** [Sol3 +2.5 … Re3 +4.1] |
|  | agudo (Mi4–Fa5) | **−7.5** [Sol4 −8.8 … Re#5 −4.8] | **−0.2** [Fa#4 −2.2 … Mi4 +0.9] | **+1.0** [Sol4 −1.4 … Fa4 +3.1] |
| `Pizzicato("violines")` | grave (Sol3–Mi4) | **−5.7** [Si3 −6.7 … Sol3 −3.3] | **−0.2** [Si3 −3.0 … Do4 +2.4] | **+1.7** [Si3 +0.8 … Sol3 +2.6] |
|  | medio (Fa4–Re#5) | **−7.1** [Do5 −13.5 … Sol4 −5.0] | **−2.0** [Do#5 −6.4 … Fa#4 +0.8] | **+0.7** [Do#5 −1.7 … Fa4 +1.9] |
|  | agudo (Mi5–Re6) | **−8.1** [Fa5 −11.6 … La5 −7.1] | **−2.7** [Do#6 −3.7 … Sol#5 −0.4] | **−0.5** [Fa5 −1.3 … Re6 −0.1] |
| `Pizzicato("chelos")` | grave (Do2–Do#3) | **−6.3** [Si2 −8.9 … Re#2 −4.8] | **−0.9** [La2 −5.3 … Do3 +3.0] | **+3.4** [Si2 −0.5 … Re#2 +4.4] |
|  | medio (Re3–Re#4) | **−6.7** [Re#4 −8.5 … Re3 −4.2] | **−0.5** [Sol#3 −4.5 … Sol3 +3.3] | **+1.8** [Do4 +0.1 … Re#3 +3.6] |
|  | agudo (Mi4–Fa5) | **−7.4** [Sol4 −9.2 … Re5 −5.1] | **−1.0** [Fa5 −5.9 … Sol#4 +1.4] | **+0.7** [Re#5 −1.9 … Fa4 +2.6] |
| `Pizzicato("contrabajo")` | grave (Mi1–Do#2) | **−0.1** [Do#2 −4.0 … Sol#1 +1.0] | **+4.6** [Do#2 −0.1 … Fa#1 +10.1] | **+7.6** [La#1 +5.0 … Do#2 +9.7] |
|  | medio (Re2–Do3) | **−1.2** [Sol#2 −5.3 … Mi2 +1.0] | **+3.1** [Re2 −0.7 … Mi2 +5.2] | **+7.1** [La#2 +6.4 … Fa2 +7.6] |
|  | agudo (Do#3–Si3) | **−2.9** [Si3 −4.9 … Do#3 −1.0] | **+0.9** [La#3 −1.1 … Do#3 +5.4] | **+6.9** [Mi3 +6.1 … Re#3 +8.1] |

* Los +10 a +17 dB del piano y del vibráfono a vel 0,6 son notas que antes casi desaparecían: el
  cruce de capas cancelaba justo en la mitad del cruce. A vel 0,45 y 0,75 el cambio es mucho
  menor (tabla 2: vibráfono −1,0 y +3,8; piano −0,4 y +4,6).
* Donde el «antes» saltaba de nota en nota (sobre todo en el contrabajo), la mediana del registro
  dice poco: mirá las puntas (contrabajo: La1 −7 dB y Sol2 −14 dB a vel 0,3).

### 2c. Cuerdas y vibráfono con arco: notas cortas (1,5 s)

En una melodía o un bajo de notas de 1–2 s pesa el comienzo de la nota, no el tramo estable.
Con una sola capa (vel ≤ 0,3 o ≥ 0,85) el cambio es el mismo que en las notas largas; donde se
mezclan las dos capas (≈ 0,45–0,75) puede diferir hasta 6 dB en algunas notas. Nota aislada de
1,5 s, LUFS integrado de la nota más 0,5 s de soltar; el resto, como la 2b.

| instrumento | registro | vel 0,3 | vel 0,45 | vel 0,6 | vel 0,85 |
|---|---|---|---|---|---|
| `VibrafonoArco()` (nuevo) | grave (Mi4–Si4) | **−5.7** [Si4 −11.5 … Fa#4 −4.1] | **−5.4** [Si4 −11.2 … Fa#4 −3.8] | **−5.1** [Si4 −10.9 … Fa#4 −3.5] | **−4.6** [Si4 −10.4 … Fa#4 −3.0] |
|  | medio (Do5–Sol5) | **−13.3** [Mi5 −13.9 … Fa#5 −11.2] | **−13.0** [Mi5 −13.6 … Fa#5 −10.9] | **−12.7** [Mi5 −13.3 … Fa#5 −10.6] | **−12.2** [Mi5 −12.8 … Fa#5 −10.1] |
|  | agudo (Sol#5–Mi6) | **−12.6** [Re#6 −18.9 … Sol#5 −11.8] | **−12.3** [Re#6 −18.6 … Sol#5 −11.5] | **−12.0** [Re#6 −18.3 … Sol#5 −11.2] | **−11.5** [Re#6 −17.8 … Sol#5 −10.8] |
| `Violines()` | grave (Sol3–Mi4) | **−7.1** [Sol#3 −8.8 … Sol3 −5.4] | **−2.6** [Mi4 −5.1 … La#3 −1.8] | **+0.1** [Mi4 −1.8 … Sol3 +0.2] | **+0.3** [Mi4 −1.4 … La3 +0.6] |
|  | medio (Fa4–Re#5) | **−10.2** [Do#5 −12.1 … Re#5 −7.6] | **−5.2** [Do#5 −7.8 … Re5 −3.5] | **+0.1** [Sol4 −2.0 … Sol#4 +2.7] | **+2.5** [Fa#4 −1.4 … Sol#4 +3.8] |
|  | agudo (Mi5–Re6) | **−8.0** [Do#6 −11.2 … Mi5 −7.6] | **−4.8** [Re6 −8.3 … Mi5 −3.6] | **−2.9** [Re6 −6.4 … Mi5 −0.0] | **−2.9** [Re6 −6.4 … Fa5 +0.5] |
| `Violas()` | grave (Do3–Do4) | **−11.6** [Fa#3 −13.1 … Do3 −9.1] | **−6.1** [Re3 −7.7 … Fa#3 −5.3] | **+2.3** [Do3 −0.5 … Fa#3 +4.1] | **+5.4** [Do3 −1.7 … Sol3 +6.9] |
|  | medio (Do#4–Do#5) | **−11.8** [Si4 −13.7 … Re4 −10.1] | **−9.2** [Do#5 −9.8 … Do#4 −3.7] | **+0.5** [Sol#4 −0.7 … Mi4 +1.5] | **+5.0** [Do#4 +1.1 … Do5 +5.8] |
|  | agudo (Re5–Re6) | **−10.7** [Sol#5 −19.4 … La5 −9.5] | **−7.3** [Sol#5 −13.5 … La5 −4.0] | **+0.5** [Re6 −6.1 … La5 +2.2] | **+3.0** [Do#6 −5.3 … Sol5 +6.3] |
| `Chelos()` | grave (Do2–Do#3) | **−12.5** [Do2 −14.3 … Re2 −6.0] | **−9.9** [Sol#2 −10.9 … Re2 −3.0] | **−0.1** [Sol2 −1.2 … Re#2 +6.1] | **+11.6** [Do#2 +5.3 … Do#3 +13.7] |
|  | medio (Re3–Re#4) | **−8.4** [Re3 −12.1 … Re4 −3.8] | **−7.1** [Re#3 −7.5 … Re4 −1.5] | **+3.1** [La#3 +0.7 … Si3 +7.3] | **+10.7** [Fa3 +9.1 … Do#4 +14.3] |
|  | agudo (Mi4–Fa5) | **−6.3** [Mi5 −9.0 … Mi4 −3.8] | **−2.7** [Fa5 −5.1 … Fa#4 −1.2] | **+5.6** [Fa5 +4.8 … Fa#4 +8.1] | **+10.4** [La4 +9.0 … Fa#4 +12.5] |
| `Contrabajo()` | grave (Mi1–Do#2) | **−1.1** [La1 −7.2 … Sol#1 +3.3] | **+2.2** [La1 −7.8 … Sol1 +5.4] | **+3.4** [La1 −4.5 … Sol1 +7.7] | **+2.4** [La1 −2.4 … Sol1 +7.1] |
|  | medio (Re2–Do3) | **−4.6** [La2 −14.7 … Re2 +2.6] | **−2.9** [Sol2 −12.5 … Re2 +3.8] | **+0.2** [Sol2 −6.7 … Mi2 +3.2] | **−0.4** [Sol#2 −2.9 … Re#2 +4.9] |
|  | agudo (Do#3–Si3) | **−7.3** [Fa#3 −10.9 … Do#3 −4.6] | **−6.8** [Sol3 −7.2 … Do#3 −2.6] | **+0.1** [La#3 −7.3 … Do#3 +1.9] | **+2.2** [Si3 −7.8 … Re#3 +2.7] |
| `CuerdasTrem("violines")` | grave (Sol3–Mi4) | **−4.7** [La#3 −7.0 … La3 −2.2] | **+0.5** [La#3 −4.0 … Sol3 +3.8] | **+9.0** [La#3 +4.2 … Sol3 +12.0] | **+11.3** [Do4 +7.8 … Sol3 +13.8] |
|  | medio (Fa4–Re#5) | **−5.5** [La#4 −11.4 … Si4 −4.9] | **−2.9** [La#4 −6.5 … Fa4 −1.4] | **+4.3** [La#4 +3.6 … Fa4 +7.7] | **+8.2** [Si4 +7.7 … Fa4 +11.5] |
|  | agudo (Mi5–Re6) | **−12.8** [Do#6 −14.7 … Mi5 −9.9] | **−6.3** [Re6 −10.3 … Mi5 −4.0] | **+4.5** [Re6 +0.0 … Mi5 +5.4] | **+9.8** [Do#6 +6.4 … Fa#5 +10.3] |
| `CuerdasTrem("violas")` | grave (Do3–Do4) | **−9.0** [La#3 −10.4 … Sol#3 −8.9] | **−5.5** [Fa3 −6.4 … La3 −4.5] | **−1.8** [Fa3 −2.2 … Do3 +1.6] | **−1.5** [Re#3 −1.5 … Do3 +3.4] |
|  | medio (Do#4–Do#5) | **−7.9** [Sol4 −13.4 … Fa4 −4.4] | **−2.7** [La#4 −8.4 … Mi4 +1.3] | **+0.3** [La#4 −6.7 … Mi4 +1.8] | **+0.5** [La#4 −6.5 … Do#4 +1.9] |
|  | agudo (Re5–Re6) | **−15.6** [Si5 −17.6 … Re6 −11.5] | **−9.8** [Do6 −12.4 … Do#6 −0.4] | **−4.4** [Fa5 −6.1 … Do#6 +4.1] | **−3.7** [Re5 −5.6 … Do#6 +4.4] |
| `CuerdasTrem("chelos")` | grave (Do2–Do#3) | **−8.8** [La#2 −11.0 … Do2 −4.1] | **−4.9** [La#2 −7.6 … Do2 +0.9] | **+2.5** [La#2 −1.9 … Do#2 +3.9] | **+2.7** [Fa#2 −0.8 … Do2 +4.1] |
|  | medio (Re3–Re#4) | **−6.9** [Re3 −10.7 … Mi3 −3.9] | **−4.5** [Re#3 −6.5 … Fa#3 −2.5] | **+1.4** [Do#4 +1.0 … Re3 +2.0] | **+2.9** [Sol3 +2.5 … Re3 +3.8] |
|  | agudo (Mi4–Fa5) | **−7.5** [Fa#4 −8.5 … Do#5 −5.1] | **−5.1** [Fa4 −5.4 … Re#5 −3.2] | **−0.1** [Sol4 −1.7 … Mi4 +1.2] | **+1.2** [Sol4 −1.6 … Mi4 +3.4] |

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

