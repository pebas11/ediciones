# Brief: serie "Hongos mágicos" (5 motion graphics, estilo MYCO)

El usuario pidió animaciones **más coloridas y con un estilo más tecnológico**, sobre hongos mágicos. Las anteriores tenían otro estilo, azul noche.

- **Formato:** 1920×1080 a 60 fps, **solo versión FONDO**. Al usuario no le convenció el chroma, así que no se renderiza la versión verde.
- **Encuadre:** educativo y científico. Nada de instrucciones de consumo, dosis recreativas ni cultivo.
- **Texto en pantalla:** español neutro, sin voseo. Números en formato español.

## Dirección de arte v2: "lámina científica 3D". Reemplaza el estilo MYCO
El usuario pidió:
- Un hongo más trabajado.
- **Que no parezca hecho con IA.**
- Elementos 3D.
- Mejor estética.
- **League Spartan** como tipografía prioritaria.

**Referencia aprobada:** `scenes/h01-hongos.html`. Copiá su estructura: importmap de three, `createStage3D`, capa `#ann` de anotaciones, grano de película, esquinas de marco y `#plate`.

- **3D real con Three.js:**
  - Usá `lib/three-stage.mjs` (`createStage3D`, `project()`, `fbm`, `noise3`) y, si hace falta, `lib/mushroom3d.mjs`.
  - Cada escena tiene un protagonista 3D modelado por código, iluminado como en un estudio:
    - clave cálida,
    - dos contraluces de color suaves,
    - hemisférica violeta,
    - sombras suaves,
    - niebla (`FogExp2`) y bloom sutil (threshold ≥ 0,85).
  - El 3D se renderiza en `M.onFrame` con `S.render()`, a partir de proxies animados en `M.tl`. Todo tiene que ser determinista.
- **Tipografía (prioridad):** cargar `lib/fonts-spartan.css`.
  - League Spartan 800–900 para titulares, en minúscula de oración ("Hongos mágicos", no MAYÚSCULAS), con tracking de −0,03 a −0,05em.
  - DM Sans para el cuerpo y DM Mono para rótulos técnicos (en mayúsculas, con tracking de 0,14 a 0,22em).
- **Paleta contenida y de autor**, no arcoíris:
  - Fondo tinta violeta: `#0f0a1c` → `#040308`.
  - Hueso `#F3EDE2` para el texto y color secundario `rgba(243,237,226,0.62)`.
  - **Un** acento principal por escena, más un secundario como mucho:
    - h02: cian `#7FD8FF` + caramelo.
    - h03: magenta `#FF6CC4` + hueso.
    - h04: lima `#C6F36B` + violeta `#9D8CFF`.
    - h05: caramelo `#E0A15A` + azul `#6E9BFF`.
  - El color fuerte va en la luz del 3D, no en degradés de texto.
- **Lo que hace que algo parezca hecho con IA (NO hacerlo):**
  - Degradés arcoíris en texto o bordes.
  - Glassmorphism con borde holográfico.
  - Glow en todo.
  - Todo centrado y simétrico.
  - Chips de colores por todas partes.
  - Partículas brillantes sin motivo.
  - Íconos genéricos.
  - Textos en MAYÚSCULAS con glow.
- **Lo que hace que se vea diseñado (HACERLO):**
  - Grilla editorial: texto alineado a la izquierda en x = 140, el 3D a la derecha con la cámara corrida (`setViewOffset`).
  - Anotaciones numeradas (01, 02…) con líneas finas de 1,5 px que siguen al objeto 3D (`S.project`).
  - Marcas de esquina y un rótulo tipo "LÁMINA 0N".
  - Jerarquía clara: titular grande, un solo dato protagonista y un texto de apoyo corto.
  - Grano de película, viñeta y aire.
- **Movimiento:**
  - Tokens de `docs/APPLE-MOTION.md`.
  - Cámara 3D con movimientos lentos y motivados: dolly, grúa u órbita corta.
  - Texto con `M.textIn` / `textOut`, en palabras o letras.
- **Técnica:** reglas de `docs/RULES.md` (salvo las de modo verde), 13–15 s por escena, solo modo `fondo`.
- **Render:**
  - Hoja de contacto: `node render.mjs <escena> --sheet 16 --modes fondo`.
  - Cuadros sueltos: `--stills t --scale 0.5`.
  - QA: `node qa.mjs <escena> --modes fondo`.
  - Final: `node render.mjs <escena> --modes fondo`, en background.
  - Un cuadro 3D tarda ~0,5 s, así que la hoja de contacto demora ~30 s.

### Protagonista 3D de cada escena
- **h02:** moléculas 3D de bolas y varillas: psilocibina → psilocina (el grupo fosfato se separa) y la comparación con la serotonina. Átomos con materiales físicos, enlaces como cilindros y anotaciones con los nombres de los grupos.
- **h03:** un parche 3D de membrana (bicapa lipídica con cabezas en instancias). El receptor 5-HT2A es un haz de 7 hélices (cilindros o tubos). La psilocina entra en el bolsillo y la membrana se ilumina.
- **h04:** dos conectomas 3D: nodos sobre una esfera o un anillo, con arcos entre nodos que se dibujan de a poco. Uno modular y ordenado, el otro integrado (con psilocibina). Rotan lento.
- **h05:** una línea de tiempo en el espacio 3D, recorrida por un dolly de cámara, con hitos como planos o paneles finos. Después, datos clínicos en paneles editoriales y el cierre responsable.

## Storyboards
Son una guía. Los datos tienen que salir de la ficha verificada que está más abajo; si un dato no aparece ahí, no va en pantalla.

### h02-quimica · "De psilocibina a psilocina"
- **Beat 1:** kicker "QUÍMICA". Molécula de psilocibina en estructura esquelética, con los enlaces dibujados de a poco: indol (hexágono + pentágono fusionados), cadena etilamina con N(CH3)2 y grupo fosfato en posición 4. Los átomos N, O y P van como nodos de color con su letra. Nombre grande "PSILOCIBINA" y la fórmula.
- **Beat 2:** "En el cuerpo pierde el fosfato". El grupo fosfato se desprende y sale flotando con la etiqueta "fosfato". La molécula se convierte en psilocina (OH en posición 4). El nombre cambia a "PSILOCINA", con su fórmula y el chip "LA FORMA ACTIVA".
- **Beat 3:** psilocina junto a serotonina (5-HT), con el núcleo indol común brillando en las dos. Texto: "Casi la misma forma que la serotonina".
- **Nota:** las estructuras tienen que ser químicamente correctas. Usá coordenadas de hexágono y pentágono regulares con ángulos de 120° y 108°.

### h03-receptor · "La llave y la cerradura"
- **Beat 1:** una neurona piramidal de neón (soma triangular, dendritas ramificadas, axón). La cámara se acerca a una membrana con receptores 5-HT2A.
- **Beat 2:** la psilocina, como icono molecular simplificado, encaja en el receptor. El receptor se enciende y salen ondas de señal. Texto: "Activa el receptor de serotonina 5-HT2A".
- **Beat 3:** con el dato de la ficha (bloqueo con ketanserina), un bloqueador ocupa el receptor y no pasa señal. Texto corto con la cita.

### h04-redes · "El cerebro se reconecta"
- **Beat 1:** silueta del cerebro de perfil con los hubs de la red neuronal por defecto (según la ficha). Rótulo "RED NEURONAL POR DEFECTO".
- **Beat 2:** dos grafos circulares, uno "NORMAL" (módulos por color con pocas conexiones entre sí) y otro "CON PSILOCIBINA" (muchas conexiones entre módulos, de todos los colores). Los enlaces se dibujan de a poco. Cita: Petri et al., 2014.
- **Beat 3:** un dato de la ficha, por ejemplo Siegel 2024 o la plasticidad neuronal, con un contador.

### h05-ciencia · "Lo que dice la investigación"
- **Beat 1:** línea de tiempo con nodos que se dibuja de izquierda a derecha. Solo hitos de la ficha: por ejemplo 1958 (Hofmann aísla la psilocibina), 2006 (Johns Hopkins), 2018–2019 (FDA "terapia innovadora") y 2023 (Australia).
- **Beat 2:** 2 o 3 tarjetas con los números de los ensayos clínicos de la ficha. Cada una con contador, tamaño de muestra y cita.
- **Beat 3:** encuadre responsable con tres chips o líneas, sacado de la ficha. Por ejemplo: "Ilegal en la mayoría de los países" · "Se investiga en entornos clínicos controlados" · "No es una recomendación".

## Ficha de datos verificados
(Se completa abajo con el resultado de la verificación en PubMed.)
