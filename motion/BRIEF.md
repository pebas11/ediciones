# Brief: motion graphics "Calorías vs. comida chatarra"

Son 5 animaciones explicativas para un video de YouTube en 16:9 (1920×1080, 60 fps) que se editan en CapCut.
Cada una se entrega en dos versiones:
- `*_FONDO.mp4`: fondo azul noche completo, con glow, reflejos y tarjetas de vidrio.
- `*_VERDE.mp4`: chroma key sobre #00FF00, con todo opaco.

Tesis del guion: **para bajar de peso lo que importa son las calorías (el balance energético), no si la comida es "chatarra" o "saludable"**.
Como ejemplo se usa el caso del profesor Mark Haub (2010).

## Estilo (lo pidió el usuario)
- Estética tecnológica y científica, 2D con profundidad 2.5D: leve perspectiva, capas, sombras suaves y reflejos inferiores discretos.
- Fondo azul noche con variaciones de luz muy suaves. Ya lo resuelve `lib/stage.js` (luces, grilla en perspectiva, partículas, ruido).
- Siluetas e íconos en azul eléctrico y cian. Íconos: Phosphor duotone, en `node_modules/@phosphor-icons/core/assets/duotone/`.
- Tipografía sans serif limpia (Inter) con contrastes fuertes de tamaño y peso. JetBrains Mono para rótulos y unidades.
- Palabras destacadas grandes que aparecen siguiendo la narración.
- Tarjetas translúcidas con esquinas redondeadas y bordes finos (`.card`, `.pill`).
- Contadores, conexiones y gráficos que se construyen de a poco.
- Entradas y salidas fluidas, con aceleración y frenado controlados (eases `swift`, `smooth`, `exit`, `settle`).
- Espacio libre suficiente para entender **una idea por vez**. Cada escena tiene 2 o 3 "beats" que se reemplazan entre sí.

Paleta (tokens en `lib/theme.css`):
- Noche `#020C1B`
- Profundo `#061B3A`
- Eléctrico `#087EFF`
- Cian `#20C4EF`
- Blanco frío `#F5F8FF`
- Celeste `#73BDF2`

## Motor (NO modificar `lib/theme.css`, `lib/stage.js` ni `render.mjs`: los comparten todas las escenas)
- Referencia terminada y aprobada: `scenes/01-balance.html`. Hay que copiar su estructura (`#bg`, `#world`, scripts, `M.scene(...)`).
- Todo se anima en `M.tl`, un timeline GSAP pausado. Cada frame se dibuja con `M.seek(t)`. No usar CSS animations, transitions, `setTimeout` ni `requestAnimationFrame`.
- La geometría procedural que depende del tiempo va en `M.onFrame(t => ...)`, leyendo proxies que se tweenean en `M.tl` (ver la balanza en la escena 01).
- Helpers disponibles:
  - Texto: `M.textIn(el, at, {type:'chars'|'words', dur, stagger, cls:'hl'})` y `M.textOut(split, at, {type})`.
  - Tarjetas: `M.popIn(el, at, {dur, rotX, y, scale})` y `M.popOut(el, at)`.
  - Escalas: `M.zoomIn` y `M.zoomOut`.
  - Trazos SVG: `M.draw(svgEl, at, {dur})` y `M.undraw(svgEl, at, {to})`.
  - Números: `M.counter(el, {from, to, decimals, at, dur, prefix, suffix, sign})`, con formato español (1.800 / 28,8).
  - Formato suelto: `M.fmt(v, dec)`.
- Íconos: `<i data-icon="nombre"></i>` y `icons:[...]` en `M.scene`.
  - OJO: `apple-logo` es una marca, no usarlo.
  - Frutas y verduras disponibles: carrot, orange, avocado, leaf, egg, fish, bowl-food.
  - Chatarra: hamburger, pizza, cookie, popcorn, ice-cream, cake.
  - Otros: fire, scales, person, person-simple-run, clock, calendar, graduation-cap, drop, heartbeat, trend-down, trend-up, chart-line-down, pill, barbell, arrow-down, arrow-up.
- Render:
  - Hoja de contacto: `node render.mjs <escena> --sheet 16 --modes fondo` (o `verde`) → `stills/<escena>_<modo>_SHEET.png`.
  - Cuadros sueltos: `node render.mjs <escena> --stills 2.5,6.1 --modes fondo,verde` → `stills/<escena>_<modo>_<t>.png`.
  - Video final: `node render.mjs <escena>` → `renders/<escena>_FONDO.mp4` y `renders/<escena>_VERDE.mp4`.
  - QA del chroma: `python3 qa_chroma.py renders/<escena>_VERDE.mp4` → métricas y `stills/<escena>_VERDE_KEYTEST.png`.
- Mirá los PNG con la herramienta Read, porque se ven como imágenes. Siempre revisá los cuadros **a resolución completa** además de la hoja de contacto.

## Reglas técnicas (errores que ya aparecieron o que rompen el chroma)
1. **Modo verde = nada semitransparente sobre el verde.**
   - Todo color con alpha necesita su override opaco bajo `html.verde`. Usá las variables `--line-soft`, `--line-faint`, `--text-dim` y `--card-bg`, que ya lo tienen.
   - Glows, reflejos, sombras, blur y degradés con transparencia van solo en modo fondo: clase `.fondo-only`, chequeo `if (!M.chroma)` o variables que ya valen `none` en verde.
   - Las entradas y salidas en verde tienen que funcionar sin `opacity`. Usá máscara (`textIn`), clip (`popIn`), escala (`zoomIn`) o trazo (`draw`). Las fundidas con `opacity` o `filter` van solo `if (!M.chroma)`.
2. Degradés SVG en líneas horizontales o verticales: `gradientUnits="userSpaceOnUse"` con coordenadas absolutas. Con `objectBoundingBox`, una línea de alto 0 no se dibuja.
3. Escalar o rotar elementos SVG: `gsap.set(el, {svgOrigin: 'x y'})` **antes** de crear los tweens.
4. No repetir `id`s entre `<defs>` y elementos.
5. Texto dividido con SplitText (máscaras): el `line-height` tiene que ser ≥ 1.2 para que no se corten las tildes (Í, É, Á) ni los descensores. `.display` ya trae 1.25.
6. Márgenes seguros: nada importante a menos de 96 px de los bordes.
7. Legibilidad a 1080p:
   - Texto de cuerpo ≥ 34 px.
   - Rótulos mono ≥ 22 px.
   - Números protagonistas ≥ 96 px.
   - Palabra destacada 180–250 px.
8. Los primeros ~0,15 s y los últimos ~0,3 s quedan vacíos (solo fondo), así el corte en CapCut es limpio. Todo lo que entra tiene que salir.
9. Duración de 12 a 15 s por escena. Cada beat queda quieto al menos 1,5 s después de construirse, para que la narración entre.
10. El texto en pantalla va en español neutro, sin voseo. Números en formato español: 1.800, 28,8 y 33,4 %. El signo menos es "−".
11. Nada de fotos ni logos de marcas. Mark Haub se representa con una silueta genérica.
12. Sin acceso a internet: trabajá solo con lo que hay en el repo.

## Datos verificados del caso Mark Haub
Fuente: cobertura de CNN, noviembre de 2010.
- Mark Haub, profesor de nutrición humana de la Universidad Estatal de Kansas (EE. UU.). Año 2010.
- Duración: **10 semanas**. Comía un snack dulce (pastelitos tipo Twinkie) **cada 3 horas** en lugar de comidas.
  - También comió papas fritas de paquete (Doritos), cereales azucarados y galletitas (Oreos). La prensa lo llamó «la dieta Twinkie».
- Se limitó a **menos de 1.800 kcal por día**. Un hombre de su tamaño consume normalmente **unas 2.600 kcal por día**. Eso da un déficit de unas **800 kcal/día**.
- **Dos tercios** de lo que comía era comida chatarra. El resto era un batido de proteínas diario, un multivitamínico y verduras (una lata de chauchas o unos tallos de apio).
- Peso: **91 kg → 79 kg** (201 → 174 libras), o sea **−12 kg** (−27 libras).
- IMC: **28,8 (sobrepeso) → 24,9 (normal)**.
- Grasa corporal: **33,4 % → 24,9 %**.
- Colesterol LDL («malo»): **−20 %**.
- Colesterol HDL («bueno»): **+20 %**.
- Triglicéridos: **−39 %**.
- Él mismo aclaró que no lo recomienda como dieta. Es un experimento personal.

## Storyboards
Son guía, no ley. Mejoralos si algo se ve mejor, pero respetá los datos y "una idea por vez".

### 02 · `02-chatarra-vs-saludable` (≈14 s)
- **Beat 1:** kicker "MISMA CANTIDAD DE CALORÍAS".
  - Entran dos tarjetas de vidrio grandes, inclinadas en 2.5D hacia el centro.
  - Izquierda: "COMIDA SALUDABLE", con 3 íconos en badges (carrot, fish, avocado u orange).
  - Derecha: "COMIDA CHATARRA", con hamburger, pizza y cookie o ice-cream.
  - Cada una tiene un contador que llega a **1.800 kcal**.
- **Beat 2:** un signo **=** grande entre las dos tarjetas se dibuja con glow. Desde la base de cada tarjeta salen conexiones que convergen en un nodo abajo.
- **Beat 3:** tarjeta resultado abajo: "MISMO DÉFICIT → MISMA PÉRDIDA DE PESO". Adentro, un mini gráfico donde dos curvas descendentes (una por dieta) se dibujan superpuestas.
- **Beat 4 (remate):** todo sale y queda una frase grande. Kicker "PARA LA BALANZA" y palabra destacada **"1 kcal = 1 kcal"**, o similar con "una caloría es una caloría".

### 03 · `03-mark-haub` (≈13 s)
- **Beat 1:** kicker "CASO REAL · 2010".
  - A la izquierda, una silueta genérica de persona dentro de un marco circular "tech": anillos concéntricos con marcas, un anillo que gira lento y una elipse de piso en perspectiva.
  - A la derecha, **MARK HAUB** grande y debajo "Profesor de Nutrición Humana" y "Universidad Estatal de Kansas · EE. UU.", con el ícono graduation-cap.
- **Beat 2:** kicker "EL EXPERIMENTO" (puede decir «LA DIETA TWINKIE»). Aparecen en secuencia 3 tarjetas unidas por una línea con nodos que se dibuja:
  - [calendar] **10 semanas**
  - [clock] **Un snack dulce cada 3 horas**
  - [cookie/cake/popcorn] **Pastelitos, papas fritas, galletitas y cereales azucarados**
  - El 10 y el 3 pueden ser números grandes con contador.

### 04 · `04-deficit` (≈14 s)
- **Beat 1:** kicker "LA CLAVE: LA CANTIDAD". Panel de vidrio grande con gráfico de barras horizontal y eje de 0 a 3.000 kcal con marcas.
  - Barra "LO QUE NECESITABA": **2.600 kcal/día**, en eléctrico.
  - Barra "LO QUE COMIÓ": **menos de 1.800 kcal/día**, en cian.
  - Las barras crecen con contadores. Después se marca la diferencia con un corchete y la etiqueta **"DÉFICIT ≈ −800 kcal/día"**. Ojo: "≈" no está en la fuente latin de Inter, así que usá "~" o solo "−800".
- **Beat 2:** sale el panel y entra una dona que se dibuja de a poco. Kicker "¿DE DÓNDE SALÍAN LAS CALORÍAS?".
  - Segmento de 2/3 en cian: "COMIDA CHATARRA".
  - Segmento de 1/3 en eléctrico: "BATIDO DE PROTEÍNAS, MULTIVITAMÍNICO Y VERDURAS".
  - Número grande en el centro: **2/3**.

### 05 · `05-resultados` (≈15 s)
- **Beat 1:** kicker "RESULTADOS EN 10 SEMANAS".
  - Contador grande de peso **91 kg → 79 kg**.
  - Al lado, un gráfico de línea (semana 0 a 10) que se dibuja descendiendo, con un punto que recorre la curva.
  - Aparece el chip **"−12 kg"**.
- **Beat 2:** tarjetas de métricas con contadores:
  - IMC **28,8 → 24,9** (etiquetas "SOBREPESO" → "NORMAL").
  - Grasa corporal **33,4 % → 24,9 %**.
- **Beat 3:** tres tarjetas de análisis de sangre:
  - LDL («malo») **−20 %**, con flecha abajo.
  - HDL («bueno») **+20 %**, con flecha arriba.
  - Triglicéridos **−39 %**.
  - Nota al pie chica en mono: "Experimento personal de Mark Haub (2010). No es una recomendación médica."
