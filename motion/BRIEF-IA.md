# Brief: serie 4 "IA" (3 animaciones, 2D, sin 3D)

Pedido del usuario (26/09):
- Olvidar la estética 3D por ahora.
- 3 animaciones: AGI, inteligencia recursiva y una larga de 30 s que muestre visualmente todos los tipos de IA y redes neuronales.
- **Texto mínimo o nada.**
- Libertad para probar enfoques distintos.

## Reglas comunes
- **Formato:** 1920×1080 a 60 fps, solo modo `fondo`. Con sonido: `lib/audio.js`, ver `docs/AUDIO.md`.
- **2D:** SVG, Canvas 2D o CSS. Nada de Three.js en esta serie. Todo determinista con `M.tl` / `M.onFrame` y `M.rng(seed)`, sin `Math.random`.
- **Que no parezca hecho con IA:** nada de "cerebro azul brillante con circuitos", robots, neón, arcoíris, glow en todo ni partículas sin sentido. Cada forma y cada movimiento explica algo.
- **Texto:**
  - a01 y a02: sin texto.
  - a03: como máximo un rótulo de 1 o 2 palabras por tipo de red, chico, en DM Mono. Nombres estándar: "Perceptrón", "Red densa", "CNN", "RNN", "Autoencoder", "GAN", "Transformer", "Difusión", "Refuerzo".
  - Tipografía: League Spartan, DM Sans y DM Mono (`lib/fonts-spartan.css`).
- **Cada escena con un enfoque visual DISTINTO**, para probar lenguajes:
  - **a01-agi, "Bauhaus / suizo":**
    - Fondo papel cálido `#F2EDE4`, formas planas geométricas y colores primarios apagados: rojo `#D2452B`, azul `#2E4A9E`, amarillo `#E8B63B`, negro `#1B1A18`.
    - Grilla suiza visible muy sutil.
    - Idea: muchos sistemas estrechos, cada uno una forma que hace una sola tarea (una gira, otra ordena, otra traduce un patrón), aislados en su celda de la grilla. Se conectan, rompen las celdas y se funden en una sola forma general que puede tomar la forma de cualquiera de ellos y de otras nuevas.
    - Duración 14 s.
  - **a02-recursiva, "tinta sobre papel + zoom infinito":**
    - Fondo hueso `#EFEDE8`, línea negra fina tipo plumín, un único acento rojo `#C8372D`.
    - Idea: un sistema que se mejora a sí mismo. Un diagrama o máquina dibuja una versión mejorada de sí misma dentro de sí (efecto Droste). La cámara hace zoom a la copia, que dibuja otra aún mejor, cada ciclo más rápido.
    - Aceleración exponencial visible: ciclos de 3 s → 1,8 → 1 → 0,5 → …
    - Cierra en una curva exponencial dibujada por los propios ciclos.
    - Duración 14 s.
  - **a03-tipos-ia, "diagramas vivos", 30 s:**
    - Fondo grafito `#15171A`, líneas y nodos en hueso `#E9E6DF`. Un color funcional por familia de red, apagado y no neón: ámbar, verde salvia, terracota, azul pizarra, lila gris.
    - Un recorrido continuo que transforma una arquitectura en la siguiente (morph) mientras la señal fluye:
      1. perceptrón
      2. red densa (MLP)
      3. CNN (kernel deslizándose sobre una grilla de píxeles → mapas de características)
      4. RNN (bucle en el tiempo que se despliega)
      5. autoencoder (reloj de arena)
      6. GAN (dos redes: generador vs. discriminador)
      7. Transformer (tokens con líneas de atención de grosor variable)
      8. difusión (ruido que se va limpiando hasta formar una figura)
      9. aprendizaje por refuerzo (agente ↔ entorno con recompensa)
    - Cada tipo dura ~3 s. Las transiciones son fluidas: los nodos de uno se reorganizan en el siguiente.
- **Sonido:** `audio:{key:'D',mode:'lydian',bed:{...}}` y pocos `M.sfx` con motivo.
  - En a03, cada arquitectura tiene un sonido propio y breve, siempre en la misma tonalidad.
  - En a02, la aceleración también se oye: ticks o taps cada vez más juntos.
