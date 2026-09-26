# Bitácora del proyecto de motion graphics

Última actualización: 2026-09-26. Rama: `claude/capcut-usage-77m4ya`.

## Cómo retomar en una sesión nueva
1. El hook de SessionStart instala las dependencias solo (`motion/setup.sh`). Si falla: `cd motion && npm install && pip install imageio-ffmpeg numpy pillow`.
2. Antes de hacer nada, leé `CLAUDE.md`, esta bitácora, la skill `motion-graphics` y la skill `motion-copy`.
3. Comandos habituales (siempre desde `motion/`):
   - `node render.mjs <escena> --sheet 16 --modes fondo`: hoja de 16 cuadros.
   - `node render.mjs <escena> --stills 3,8 --scale 0.5 --modes fondo`: cuadros sueltos.
   - `node qa.mjs <escena> --modes fondo`: QA de layout, chroma y verborragia, sin imágenes.
   - `node render.mjs <escena> --modes fondo`: video final con audio si la escena carga `lib/audio.js`.
   - `node render.mjs <escena> --audio-only`: regenera solo el sonido, tarda ~3 s.
   - Versión de entrega < 30 MB (límite de SendUserFile), desde la raíz del repo:
     ```
     ffmpeg -i renders/X_FONDO.mp4 -c:v libx264 -preset slow -crf 21 -tune film -c:a copy renders/X_ENTREGA.mp4
     ```
     El ffmpeg es el que devuelve `python3 -c "import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())"`.

## Preferencias del usuario (obligatorias)
- **Tipografía:** League Spartan para titulares, DM Sans para el cuerpo y DM Mono para rótulos (`lib/fonts-spartan.css`). No preguntar.
- **Texto mínimo** (skill `motion-copy`): ≤ 5 palabras por titular y ≤ 18 por escena. Prohibido en pantalla: "FIG.", láminas, citas, rótulos técnicos, descripciones. "No es un paper."
- **Que no parezca hecho con IA:** nada de degradés arcoíris, glassmorphism holográfico, neón ni glow en todo.
- **Color pensado:** base cálida terrosa y **un solo acento azul** (psilocibina), usado solo en lo importante.
- **3D real** (Three.js) bien modelado. Nada flota ni se atraviesa. Verificar de cerca.
- **Formato:** 16:9 1920×1080 a 60 fps. **Sin chroma verde** (al usuario no le funcionó). Solo versión FONDO.
- **Sonido procedural** sincronizado (`lib/audio.js`, docs en `docs/AUDIO.md`), mezclado bajo para ir debajo de su voz.
- Español neutro en pantalla. El usuario escribe en rioplatense. Modo `/caveman` activo en el chat.
- Tiene permiso para decidir sin preguntar. Pidió **cuidar créditos**.

## Estado
- Workflow serie 3 lanzado el 26/09 (`psicodelicos-sin-texto`, run wf_4c877fcd-bab). Si la sesión se corta, revisar `scenes/p0*.html`: pueden existir en borrador.

### Serie 1: Calorías (estilo azul noche). TERMINADA
`scenes/01..05`. Renders FONDO y VERDE en `renders/`, sin sonido.

### Serie 2: Hongos mágicos (estilo v3: 3D, cálido y azul, texto mínimo)
- Datos: solo de `FICHA-HONGOS.md` (verificada en PubMed). Brief: `BRIEF-HONGOS.md` (v3).
- **h01-hongos: TERMINADA.** Tiene 3D del hongo (`lib/mushroom3d.mjs`), diorama de suelo con micelio y sonido.
  - Renders: `renders/h01-hongos_FONDO.mp4` (55 MB), `_ENTREGA.mp4` (23 MB) y `_AUDIO.wav`. Ya enviada al usuario.
- **h02-quimica, h03-receptor, h04-redes, h05-ciencia: EN CURSO.**
  - Workflow `hongos-escenas-v3`: constructor → crítico → corrección.
  - Al 26/09 ya estaban construidas las cuatro y h02 iba por la etapa de crítica.
  - Falta:
    1. Terminar crítica y corrección.
    2. Agregar sonido: `<script src="../lib/audio.js">` después de `stage.js`, `audio:{key:'D',mode:'lydian',bed:{}}` en `M.scene` y `M.sfx(...)` en los eventos clave. Usar h01 como modelo.
    3. Render FONDO.
    4. Versión ENTREGA.
    5. Enviar y hacer commit.

### Serie 3: Psicodélicos SIN TEXTO. CONSTRUIDA; render en curso (pedido del 26/09)
- Escenas p01–p05 construidas (QA sin errores).
- Render FONDO con audio + ENTREGA: lanzados con `/tmp/claude-0/batch.sh` (se pierde si reinicia el contenedor). Si faltan `renders/p0*_ENTREGA.mp4`, re-renderizar.
- p03: el recorrido de los axones cambió al final y no se revisó en detalle. En la hoja se ve bien.

Son 5 animaciones útiles como B-roll para narración, **sin ningún texto en pantalla**. Mismo estilo v3 (3D, cálido y azul, grano, viñeta, fundido a `#060504`) y con sonido. Cada una dura 12–15 s y muestra una idea por beat. Escenas en `scenes/p0N-*.html`.

**Storyboards:**
1. **p01-sinapsis:** sinapsis 3D. Llega un impulso por el axón, las vesículas liberan serotonina (esferas cálidas) y se acoplan a receptores. Después una molécula azul (psilocina) ocupa un receptor y la señal se amplifica en ondas azules.
2. **p02-viaje:** recorrido de la molécula por el cuerpo. Una silueta humana translúcida muestra el estómago y el hígado, donde el fosfato se desprende. Después sigue la sangre (partícula azul por un vaso), cruza la barrera hematoencefálica y llega a la corteza. Cámara que sigue a la partícula.
3. **p03-plasticidad:** una dendrita 3D en primer plano. Con el tiempo brotan espinas dendríticas nuevas (crecimiento orgánico) y se forman sinapsis nuevas que se iluminan.
4. **p04-entropia:** actividad cerebral. Primero muchas señales ordenadas y periódicas en canales paralelos (ondas cálidas). Después pasan a un patrón más complejo y diverso (azul), con más conexiones entre regiones de un cerebro 3D de puntos. Idea del "cerebro entrópico".
5. **p05-familias:** cuatro moléculas psicodélicas en 3D de bolas y varillas: psilocina, DMT, LSD y mescalina. El núcleo común de las triptaminas (indol) se resalta en azul en las tres primeras. La mescalina (fenetilamina) muestra un núcleo distinto, en cálido. Las moléculas rotan y se alinean por su núcleo.
   - Tienen que ser químicamente correctas. Verificar las estructuras en PubChem.

**Plan barato (créditos):**
- Un agente constructor por escena, esfuerzo medio, con autocontrol: hoja + `qa.mjs` + 2 cuadros a media resolución.
- Sin crítico aparte.
- El render y el sonido los hace el orquestador.
- Reutilizar `three-stage.mjs`, la iluminación de h01 y el modelador de moléculas de h02 (`scenes/h02-quimica.html`) para p05.

## Infra hecha en esta sesión (para no rehacerla)
- **`render.mjs`:**
  - 3 Chromium en paralelo con captura CDP. FONDO sale en JPEG.
  - Opciones `--draft`, `--sheet`, `--stills` (con `--scale` y `--crop`) y audio con `--audio-only`, `--bed-only` y `--gain`.
- **`qa.mjs`:** QA sin imágenes.
  - Detecta quietud por píxeles, margen seguro, solapamientos, desbordes, tildes cortadas, suciedad del chroma y verborragia.
  - Arma un borrador de hoja de cues.
- **`lib/three-stage.mjs`:** 3D determinista con bloom, `project()` para anotaciones y ruido `fbm`/`noise3`.
- **`lib/mushroom3d.mjs`:**
  - *Psilocybe cubensis* con `age` (0 joven, 1 maduro), pie grueso, motas del velo y azulado.
  - `buildGrass`.
  - Ajustado a partir de fotos de Wikimedia.
- **`lib/audio.js`:** sonido procedural determinista con niveles calibrados.
- **Skills del proyecto** (`.claude/skills/`):
  - Propias: `motion-graphics`, `motion-copy`.
  - Descargadas: caveman, GSAP (5), Three.js (5), `high-end-visual-design`, `impeccable`, `game-audio`.
- **Docs:** `docs/RULES.md`, `docs/APPLE-MOTION.md`, `docs/AUDIO.md` y `docs/OPTIMIZACION.md` (costo/calidad; conviene esfuerzo high sin ultracode para 1–2 escenas).

## Lecciones (errores que no hay que repetir)
- **LatheGeometry:** el perfil de arriba hacia abajo deja las caras hacia adentro. Usar `side: DoubleSide`, o se ve el interior del objeto.
- **Piezas del modelo:** hay que encastrarlas. El pie entra en el sombrero y el sombrero se ubica según su cara inferior, no según su origen.
- **Revisar el texto:** contar palabras siempre. Las anotaciones y los rótulos "científicos" sobrecargan.
- **`pgrep -f` en un bucle de espera:** se encuentra a sí mismo y el bucle no termina nunca. Usar el PID o un archivo.
- **Varios workflows a la vez:** con 4 CPU, el render se vuelve ~5× más lento.
