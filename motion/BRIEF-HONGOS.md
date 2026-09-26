# Brief: serie "Hongos mágicos" (5 motion graphics, estilo MYCO)

El usuario pidió animaciones **más coloridas y con un estilo más tecnológico**, sobre hongos mágicos. Las anteriores tenían otro estilo, azul noche.

- **Formato:** 1920×1080 a 60 fps, **solo versión FONDO**. Al usuario no le convenció el chroma, así que no se renderiza la versión verde.
- **Encuadre:** educativo y científico. Nada de instrucciones de consumo, dosis recreativas ni cultivo.
- **Texto en pantalla:** español neutro, sin voseo. Números en formato español.

## Estilo MYCO (ya implementado)
- **CSS:** `lib/theme.css` + `lib/theme-myco.css`, cargados en ese orden.
- **Referencia aprobada:** `scenes/h01-hongos.html`. Copiá su estructura: `#bg`, `#world`, `#cam` si hay cámara, `M.scene` con `grid:'dots'`, `lights` de colores y `particles`.
- **Paleta:**
  - Fondo violeta profundo: `--night` #07030F y `--deep` #140A2A.
  - Neones: `--magenta` #FF3DCB, `--violet` #8B5CFF, `--cyan` #22E4FF, `--lime` #B6FF3B, `--amber` #FFB23F.
  - Blanco frío `--white` #F7F3FF y lila `--sky` #C9B8FF.
  - Degradé holográfico `--holo` (magenta → violeta → cian → lima) para palabras destacadas (`cls:'hl'`) y bordes de tarjeta.
- **Tipografías:**
  - Unbounded (900/800) para titulares y números (`.display`, `.num`, `.title`).
  - Space Grotesk para el cuerpo.
  - JetBrains Mono para rótulos (`.kicker`, `.tag`).
- **Componentes:**
  - `.card` con borde holográfico (y `.accent`).
  - `.tag.mag|lime|cyan|amber|violet`: chips de color sólido.
  - `.glow`, `.glow-mag`, `.glow-lime` para trazos SVG de neón.
- **Lenguaje visual:**
  - Line-art de neón dibujado progresivamente con DrawSVG y varios colores.
  - Redes y ramificaciones generadas por código con `M.rng(seed)`.
  - Pulsos de luz que viajan por los trazos.
  - Profundidad 2.5D con cámara (`#cam` con x/y/scale), tarjetas con leve rotationY y reflejos discretos.
- **Movimiento:** usá los tokens de `docs/APPLE-MOTION.md` (`apple`, `appleOut`, `appleIn`, `M.spring(0.15)`, `M.D`). Nada de rebotes exagerados.
- **Reglas técnicas:** `docs/RULES.md`. Las reglas del modo verde no aplican; todo lo demás sí.
- **Cada escena:**
  - Dura entre 13 y 15 s y tiene 2 o 3 beats, con una idea por vez.
  - Cada beat queda quieto al menos 1,5 s una vez construido.
  - Empieza y termina vacía: ~0,15 s al inicio y ~0,3 s al final.
  - Usa colores DISTINTOS como protagonistas, para que la serie no sea monótona: h02 cian/lima (química), h03 magenta/violeta (receptor), h04 arcoíris (redes), h05 ámbar/lima (ciencia).

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
