# Brief: serie 6 "Cómo funciona un LLM" (6 escenas ≈ 90 s, SIN VOZ)

Pedido (09/10): video de ultracalidad y atención al detalle que explique cómo funcionan los LLM, **sin voz en off**.
Como no hay narración, la imagen tiene que explicar sola: el orden de los beats lo cuenta todo y se permite un poco más de texto que en las series sin texto (pocas palabras reales, nunca frases largas).

## Estilo (plantilla: `scenes/b03-lenguaje.html`, la favorita del usuario)
- Grafito `#15171A`, grano 5 %, viñeta, trazo hueso `#E9E6DF`. Canvas 2D en `M.onFrame`, determinista (`M.rng`).
- Colores con significado FIJO en toda la serie (apagados, sin glow ni neón):
  - hueso = tokens / texto / estructura
  - ámbar `[201,154,75]` = predicción / lo recién generado
  - lila `[162,148,190]` = atención
  - pizarra `[122,146,178]` = espacio de significado (embeddings) y capas del modelo
  - salvia `[143,169,138]` = acierto / correcto
  - terracota `[196,110,82]` = error / pérdida
- Tipografía: League Spartan (tokens y palabras clave), DM Mono (rótulos pequeños) vía `../lib/fonts-spartan.css`. En canvas: `font = '600 44px "League Spartan"'`. Si la fuente no está lista al renderizar, verificá con un cuadro.
- Formato 1920×1080, 60 fps, 14–16 s por escena. Primeros 0,15 s y últimos 0,3 s vacíos (fundido desde/hacia grafito, como b03). Holds ≥ 1,5 s por idea.
- Sonido: `audio:{key:'D',mode:'lydian',bed:{...}}`, pocos `M.sfx`, cada uno con motivo (ticks al nacer tokens, scan en barridos, tap ámbar al generar, un `impact` máximo por escena). Sin voz, así que el sonido puede ir un poco más presente que en series anteriores: `gain` de escena +3.
- Cada movimiento explica algo. Nada decorativo.
- **Texto en pantalla:** palabras reales solo donde hacen falta (tokens, palabras candidatas, 1 rótulo corto por beat clave ≤ 3 palabras, DM Mono mayúsculas ≥ 24 px, español neutro). ≤ 24 palabras por escena en total. Sin "FIG.", sin citas, sin paréntesis.
- Frase de ejemplo común a toda la serie: **"El gato se sentó en la"** → siguiente palabra **"alfombra"**. Tokens de ejemplo: `El`, ` gato`, ` se`, ` sent`, `ó`, ` en`, ` la`. (La separación `sent`+`ó` muestra que un token no es una palabra.)

## Escenas
1. **c01-tokens (14 s). Texto → tokens → números.** Aparece la frase tipeada con cursor. Se parte en bloques (tokens) con cortes visibles; `sent|ó` se parte en dos. Cada bloque recibe un número ID debajo (DM Mono). Rótulo: "TOKENS". Cierra con la fila de IDs sola, el modelo no ve letras, ve números.
2. **c02-embeddings (15 s). Números → significado.** Cada ID se convierte en vector (barras con signo) y vuela a un espacio 2D/3D proyectado (pizarra) donde palabras parecidas quedan cerca: cúmulo animales (gato, perro, león), cúmulo muebles/lugares (alfombra, sofá, mesa) y verbos. Mostrar que "gato" y "perro" están cerca y "alfombra" lejos; una flecha-diferencia (gato→gatos ≈ perro→perros) como prueba de que las direcciones tienen sentido. Rótulo: "SIGNIFICADO".
3. **c03-atencion (16 s). Cada palabra mira a las demás.** Fila de tokens. El último token ("la") lanza arcos lila de grosor variable (atención) hacia "gato" y "sentó"/"en". Luego se despliega la matriz de atención 6×6 (celdas lila, triangular inferior: nadie mira al futuro) y se la ve construirse fila por fila. Muestra Q (pregunta) / K (clave) / V (valor) como tres mini-barras por token: el producto Q·K define el grosor, V se mezcla. Rótulos: "ATENCIÓN", y "Q · K · V" (mono).
4. **c04-capas (16 s). Apilar bloques.** Un token-vector sube por una pila de ~12 bloques (atención + red densa, dibujados como placas pizarra en perspectiva simple 2D). En cada capa el vector se modifica (barras cambian) y un hilo "residual" lo acompaña a la izquierda sumando. Zoom out: la pila se multiplica a 96 capas y sale una distribución. Rótulos: "× 96 CAPAS". Idea: profundidad = refinar significado.
5. **c05-prediccion (16 s). Elegir la próxima palabra.** Vector final → ~12 candidatos con barras de probabilidad (alfombra 41 %, silla, cama, mesa…; números formateados es-ES, ej. `41 %`). Softmax visible: barras crecen/normalizan. Después **temperatura**: bajo (una barra domina), alto (se aplanan); un dado/muestreo elige una → ámbar → entra al texto. El texto se extiende y el bucle arranca de nuevo, cada vez más rápido (autoregresivo), la frase se escribe sola. Rótulos: "PROBABILIDADES", "TEMPERATURA".
6. **c06-entrenamiento (16 s). Cómo aprendió.** Millones de fragmentos de texto cayendo como lluvia fina de bloques. Se toma uno, se oculta la última palabra, el modelo predice (barras), la verdad se compara (terracota = error) y el error retropropaga por la pila como en b02 ajustando pesos (grosores de conexiones). Repite acelerado: la barra correcta sube hasta volverse salvia. Zoom out final: la red completa, miles de millones de conexiones (nube de puntos fina) y un contador que sube (`175.000.000.000`, formato es-ES) hasta quedar quieto. Rótulos: "PREDECIR · COMPARAR · AJUSTAR" (si cabe, sino dividir en 3 beats con una palabra cada uno).

## Entrega
Cada escena la construye su agente (qa 0 errores + 1 hoja de 16 + ≤3 recortes). Render final y unión (`concat` con ffmpeg) los hace el orquestador. El video completo va a `renders/llm_COMPLETO_ENTREGA.mp4` (< 30 MB).
