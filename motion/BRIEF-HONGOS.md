# Brief: serie "Hongos mágicos" (5 motion graphics, estilo MYCO)

El usuario pidió animaciones **más coloridas y con un estilo más tecnológico**, sobre hongos mágicos. Las anteriores tenían otro estilo, azul noche.

- **Formato:** 1920×1080 a 60 fps, **solo versión FONDO**. Al usuario no le convenció el chroma, así que no se renderiza la versión verde.
- **Encuadre:** educativo y científico. Nada de instrucciones de consumo, dosis recreativas ni cultivo.
- **Texto en pantalla:** español neutro, sin voseo. Números en formato español.

## Dirección de arte v3 (vigente): la que el usuario aprobó en h01 después de sus correcciones
Referencia: `scenes/h01-hongos.html` (versión actual). El usuario marcó tres cosas:
- Había texto de sobra: "fig 14? No es un paper".
- Tamaños, contrastes y colores sin pensar.
- Problemas de modelado: el sombrero quedaba flotando.

**Estas reglas son obligatorias:**

1. **Texto: skill `motion-copy` (`.claude/skills/motion-copy/SKILL.md`), leerla antes de escribir.**
   - Titular de ≤ 5 palabras, como mucho 2 bloques de texto visibles a la vez y ≤ 18 palabras en TODA la escena.
   - PROHIBIDO en pantalla:
     - "FIG.", "LÁMINA", marcas de esquina, kickers o eyebrows.
     - Rótulos técnicos, citas o fuentes (van en la descripción del video).
     - Anotaciones con descripción, nombres científicos junto al título, fórmulas largas.
   - La voz en off explica y la pantalla ancla una palabra o un número.
2. **Guion de color (pensado, no decorativo):**
   - **Base cálida terrosa, oscura:** fondo `#130f0c` → `#050403`, niebla `#090706`.
   - **Un solo acento frío: azul psilocibina** (`#8FB0FF` en texto, `#7fa2ff` en luz). Solo para lo que importa: la palabra o número clave, el contraluz y lo "activo" (moléculas activas, señal, red).
   - **Cálido:** caramelo `#E3A560`, para lo "orgánico / hongo".
   - Texto en hueso `#F3EDE2`.
   - NADA de violeta, rosa o magenta, arcoíris, neón ni degradés en el texto.
3. **Contraste de valores:**
   - El protagonista 3D va en valor medio-alto sobre fondo casi negro.
   - Un contraluz frío separa la silueta.
   - Todo lo secundario (suelo, fondo) queda en valores bajos y poco saturados.
4. **Tamaños:**
   - El protagonista ocupa entre el 45 y el 70 % del alto del cuadro.
   - Titular de 110 a 200 px. El número protagonista, de 250 a 330 px.
   - Texto de apoyo ≥ 44 px.
   - El texto va en el espacio negativo, a la izquierda (x = 140). El 3D va a la derecha, con `setViewOffset`.
   - Nada se toca ni se superpone: `qa.mjs` avisa.
5. **Tipografía:**
   - League Spartan, con contraste de peso: 800 contra 300 en el mismo titular, como "Hongos / mágicos".
   - DM Sans para el apoyo.
   - DM Mono casi nunca.
6. **3D:**
   - `lib/three-stage.mjs` + iluminación de h01: clave cálida lateral, contraluz frío, hemisférica tenue, sombras, bloom muy sutil (threshold ≥ 0,92).
   - **Modelado correcto:** las piezas tienen que estar unidas. Revisá de cerca que nada flote ni se atraviese: sacá un cuadro con `--scale 0.5` desde el ángulo más cercano.
   - Materiales creíbles. Cuidado con `side`: si ves el interior de un objeto, usá `THREE.DoubleSide`.
7. **Coherencia de serie:** misma luz, misma paleta, mismo grano y viñeta, mismas eases (`apple`, `appleOut`, `appleIn`). La escena se abre con el protagonista y se cierra con un fundido a `#060504`.
8. **Datos:** SOLO de `FICHA-HONGOS.md`.

## Storyboards v3
Cada escena: 13–15 s, 3 beats, **texto mínimo**. Las palabras exactas en pantalla están entre comillas; no agregar más. El dato sale de `FICHA-HONGOS.md`.

### h02-quimica
- **Beat 1:** molécula 3D de psilocibina, de bolas y varillas. Átomos C gris cálido, N azul claro, O caramelo y P ámbar; enlaces finos; rota lento. Pantalla: "Psilocibina".
- **Beat 2:** el grupo fosfato (cálido) se separa y se aleja. La molécula que queda, la psilocina, se ilumina con el acento azul (es la forma activa). Pantalla: "Psilocina" (azul), reemplazando al texto anterior.
- **Beat 3:** la psilocina junto a la serotonina, con el núcleo indol común resaltado en las dos (contorno azul que se dibuja). Pantalla: "Prima de la serotonina".
- **Las estructuras tienen que ser correctas:**
  - **Indol:** benceno fusionado con pirrol.
  - **Psilocina:** OH en C4 y cadena CH2-CH2-N(CH3)2 en C3.
  - **Psilocibina:** en C4 va O-PO3H2 en lugar del OH.
  - **Serotonina:** OH en C5 y CH2-CH2-NH2 en C3.
  - Usá coordenadas 2D estándar con leve profundidad Z y los hidrógenos implícitos. Los H visibles son opcionales, chicos y tenues.

### h03-receptor
- **Beat 1:** neurona piramidal 3D (soma, dendritas y axón como tubos finos) con luz cálida. La cámara se acerca a una zona de membrana con receptores 5-HT2A: proteínas de 7 hélices como grupos de cilindros. Pantalla: "Receptor 5-HT2A".
- **Beat 2:** la psilocina (versión compacta del modelo de h02) entra en el bolsillo del receptor. El receptor se activa: pulso azul y ondas en la membrana. Pantalla: "Encaja como una llave".
- **Beat 3:** con el dato de la ficha (72 % de ocupación, Madsen 2019), número grande "72 %" + "de los receptores ocupados".

### h04-redes
- **Beat 1:** dos redes cerebrales 3D lado a lado, como nubes de nodos esféricos agrupados por módulos con tonos cálidos distintos (caramelo, hueso, tierra). A la izquierda, "Placebo": conexiones dentro de cada módulo.
- **Beat 2:** a la derecha, "Psilocibina": se dibujan muchas conexiones entre módulos con el acento azul.
- **Beat 3:** número "374" contra "165" (Petri 2014): "conexiones fuertes". Las dos cifras grandes y un rótulo corto.

### h05-ciencia
- **Beat 1:** línea de tiempo en 3D, recorrida con un dolly de cámara. Tres hitos como planos finos con el año grande: "1958" (Hofmann aísla la psilocibina), "2018" (FDA terapia innovadora), "2023" (Australia). Solo los años y una palabra por hito: "Aislada", "Terapia innovadora", "Australia".
- **Beat 2:** un dato clínico grande de la ficha: "71 %" + "de respuesta en depresión" (Davis 2021). El 3D de fondo: el hongo de h01 (`lib/mushroom3d.mjs`) desenfocado o una molécula.
- **Beat 3:** cierre responsable, 2 líneas cortas: "Investigación clínica controlada." / "No es una recomendación." El fundido cierra la serie.

## Ficha de datos verificados
Ver `FICHA-HONGOS.md`. Es la única fuente válida.
