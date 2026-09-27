# Brief: serie 5 "diagramas vivos" (3 animaciones)

Pedido del usuario (27/09): "me gusta más la última (a03), haz 3 animaciones más con ese estilo y una sobre la consciencia que incluya un ojo despertándose".

## Estilo (idéntico a `scenes/a03-tipos-ia.html`, que es la plantilla)
- **Fondo:** grafito `#15171A`, con grano 5 % y viñeta suave.
- **Trazo:** líneas y nodos en hueso `#E9E6DF`.
- **Colores funcionales, apagados y nunca neón:**
  - ámbar `[201,154,75]`
  - salvia `[143,169,138]`
  - terracota `[196,110,82]`
  - pizarra `[122,146,178]`
  - lila gris `[162,148,190]`

  Cada color significa algo y se usa siempre para lo mismo.
- **Técnica:** Canvas 2D dibujado en `M.onFrame`, determinista, con `M.rng(seed)` y sin `Math.random`. Reutilizar las utilidades de a03: `line`, `dot`, `ring`, `head`, `seg`, `pop` y los eases `apple`, `appleOut` y `spring`.
- **Texto:** NINGUNO. La voz en off explica.
- **Formato:** 1920×1080 a 60 fps. Fundido de entrada desde el grafito y fundido de salida al grafito.
- **Sonido:** `audio:{key:'D',mode:'lydian',bed:{...}}`, con pocos `M.sfx` y cada uno por un motivo.
- **Ritmo:** holds de 1,5 s o más para la narración. Una idea por beat.
- **Estética:**
  - Nada de glow ni de "cerebro brillante".
  - La luz se sugiere con opacidad y grosor, no con bloom.
  - Cada movimiento explica algo.

## b01-consciencia (16 s): un ojo que se despierta
1. **0–3 s, oscuridad:** estímulos sueltos y desordenados parpadean en todo el cuadro (puntos hueso tenues, sin estructura). En el centro, un párpado cerrado: una curva hueso con pestañas cortas.
2. **3–6 s, despertar:** el párpado tiembla, se entreabre y se vuelve a cerrar (un parpadeo fallido). Después se abre de verdad, lento, con curvas bezier que se separan con un ease `apple`.
   - Aparece el iris: líneas radiales finas en ámbar y salvia, como un dibujo técnico de iris.
   - La pupila se contrae cuando "entra la luz".
3. **6–10 s, percibir:** los estímulos sueltos dejan de parpadear al azar y viajan hacia la pupila en trayectorias curvas. Al entrar se ordenan en un patrón: anillos concéntricos o una malla que se organiza. El caos pasa a tener estructura porque hay alguien mirando.
4. **10–14 s, darse cuenta de sí:**
   - Dentro de la pupila aparece un segundo ojo más chico, que se abre igual.
   - Adentro de ese, uno más chico todavía, como en un Droste breve.
   - Una línea lila une el ojo grande con el chico, en un bucle: el sistema se observa a sí mismo.
5. **14–16 s:** un parpadeo tranquilo, el ojo queda abierto y estable, y fundido al grafito.

**Sonido:**
- drone grave;
- `swell` al abrir el ojo;
- ticks suaves cuando los estímulos entran a la pupila;
- `shimmer` cuando aparece el ojo interior.

## b02-aprendizaje (14 s): cómo aprende una red
Mitad izquierda: una red densa de 4-5-5-2 nodos. Mitad derecha: un valle de pérdida dibujado con curvas de nivel (isolíneas hueso finas) y una bola que desciende.
1. **0–2,5 s:** la red se arma. Las conexiones tienen grosores aleatorios, que son los pesos. El valle aparece y la bola está arriba.
2. **2,5–5 s, pasada hacia adelante:**
   - La señal ámbar cruza la red.
   - La salida da un valor equivocado. La comparación con el objetivo se muestra con dos barras: la de la salida y la del objetivo, que está marcado con una línea punteada.
   - La diferencia se ve en terracota: es el error.
3. **5–8 s, retropropagación:**
   - El error terracota viaja hacia atrás, capa por capa.
   - Al pasar, cada conexión cambia de grosor, porque los pesos se ajustan.
   - En el valle, la bola da un paso grande cuesta abajo.
4. **8–12 s:** se repite más rápido: tres ciclos de 1,2 s, 0,8 s y 0,5 s.
   - Cada ciclo el error es más chico y la bola da pasos más cortos hacia el fondo.
   - Las barras de salida y objetivo convergen.
5. **12–14 s:** la salida coincide con el objetivo y se pone salvia. La bola queda quieta en el fondo del valle. Hold y fundido.

**Sonido:**
- tap en cada pasada hacia adelante;
- whoosh grave invertido en cada retropropagación;
- tick más agudo en cada paso de la bola;
- al final, un acorde resuelto (shimmer).

## b03-lenguaje (16 s): cómo escribe un modelo de lenguaje
Sin palabras. Los tokens son bloques redondeados hueso de anchos distintos, como una frase sin letras.
1. **0–3 s:** una fila de 5 tokens aparece a la izquierda, a media altura.
2. **3–6 s, embeddings:** cada token se convierte en una columna de 8 barritas de alturas distintas, su vector. Los vectores se proyectan como puntos en un plano de fondo (pizarra tenue), donde los de significado parecido quedan cerca. Mostrarlo con dos cúmulos de colores distintos.
3. **6–9 s, atención:**
   - Se vuelve a la fila.
   - El último token mira a todos los anteriores con arcos lila de grosor variable.
   - Uno de los arcos es claramente el más grueso.
4. **9–12 s, predicción:**
   - Sobre el hueco a la derecha de la fila crece un histograma de probabilidades de ~12 barras (candidatos). Una barra ámbar es la más alta.
   - Esa barra se "despega", se convierte en un token nuevo y se suma a la fila.
5. **12–15 s, autorregresión acelerada:**
   - El ciclo atención → histograma → token nuevo se repite cada vez más rápido: 1 s, 0,6 s, 0,4 s, 0,3 s.
   - La fila crece y hace wrap a una segunda línea, como un párrafo que se escribe solo.
6. **15–16 s:** hold y fundido.

**Sonido:**
- tap por cada token nuevo, con los taps cada vez más juntos;
- `scan` suave en la atención;
- `tick` en el histograma.
