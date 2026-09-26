# Optimización del pipeline de motion graphics (septiembre de 2026)

## Punto de partida (v1, medido en esta sesión)
- **Escena 01**, hecha por el agente principal solo: unos 45 minutos y alrededor de 100 mil tokens de contexto. Calidad aprobada.
- **Escenas 02 a 05**, con un workflow multi-agente ("ultracode") de 5 agentes por escena (construir, 2 revisores, corregir, renderizar): cada una llevó entre 75 y 80 minutos y **entre 1,0 y 1,1 millones de tokens**, o sea unas 10 veces más. Los revisores sí encontraron problemas reales: salidas que se cortaban, trazos finos que desaparecían con el chroma, marcas sueltas.
- **Render de la versión FONDO**: ~1,4 s por cuadro, unos 15–18 minutos por escena. La versión VERDE: ~0,15 s por cuadro.
- **Mayor gasto de tokens**: las imágenes. Un cuadro de 1920×1080 cuesta ~2,8 mil tokens y en una sola etapa se miraban hasta 80.

## Las 5 revisiones de la cadena

### Revisión 1 · Velocidad de render
- Comparé varios métodos de captura:

  | Método | ms por cuadro |
  |---|---|
  | PNG de Playwright | 1437 |
  | JPEG q95 | 571 |
  | 3 páginas en un mismo Chromium | 525 |
  | 3 Chromium separados | 303 |
  | 3 Chromium con `--disable-gpu` | 247 |

- Las páginas de un mismo navegador comparten el compositor, por eso no escalan.
- **Cambios aplicados:**
  - Un navegador por worker.
  - Captura por CDP.
  - JPEG q95 en FONDO (el H.264 final ya tiene pérdida) y PNG en VERDE, para que los bordes queden limpios.
  - Un solo ffmpeg con buffer ordenado.
- **Resultado:** FONDO completo en **149 s (191 ms por cuadro) contra ~15 minutos**, 6–7 veces más rápido y con la misma calidad.
- Nuevo `--draft` (960×540 a 30 fps) para aprobar el movimiento en ~1 minuto.
- **Pendiente con más ganancia:** `HeadlessExperimental.beginFrame`, que midió 1,6× más en la investigación. Es una API experimental: dejarla para cuando el render sea el cuello de botella.

### Revisión 2 · Tokens
- **`qa.mjs`** revisa una escena en ~20 s sin mirar imágenes:
  - Detecta los tramos quietos comparando píxeles.
  - En esos tramos, busca textos fuera del margen seguro, solapados, desbordados, demasiado chicos, y máscaras que cortan tildes.
  - En VERDE revisa además: inicio y fin vacíos, suciedad del chroma y estilos semitransparentes.
  - Genera la hoja de cues en borrador.
  - Reemplaza casi todo el trabajo del revisor de "exactitud".
- **Hojas de contacto** con celdas de 480×270: una imagen de 1920×1080 para 16 cuadros.
- **`--crop x,y,w,h`** para mirar un detalle a resolución completa, que cuesta pocos tokens. **`--scale 0.5`** para cuadros enteros baratos.
- **Subagente `motion-reviewer`** (sonnet, esfuerzo medium) con un proceso fijo y barato. Las correcciones se piden al mismo constructor con SendMessage, sin crear agentes nuevos que vuelvan a leer todo.
- **CLAUDE.md corto y la skill `motion-graphics`**: el proceso está escrito una vez y se carga solo cuando hace falta.

### Revisión 3 · Calidad de diseño (estilo Apple)
- **Tokens de motion en `stage.js`:**
  - Curvas medidas en el CSS de apple.com: `apple` (0.4,0,0.6,1), `appleOut` (0,0,0.2,1) y `appleIn`.
  - `M.spring(bounce)` al estilo SwiftUI.
  - Duraciones `M.D` (0,24 / 0,4 / 0,5 / 0,8 / 1,0 s), tope de stagger de 0,5 s y hold de 1,5 s.
- **`docs/APPLE-MOTION.md`**: curvas, duraciones, escala tipográfica con tracking según el tamaño, y principios.
- **Skills oficiales de GSAP** instaladas en el proyecto: core, timeline, plugins, performance y utils.
- **Recetas de HyperFrames** (Apache-2.0, 100+ reglas de motion compatibles con nuestro timeline pausado) guardadas como referencia en `reference/hyperframes/`. Se leen solo cuando hacen falta.
- **Plugins sugeridos** (los activa el usuario): `frontend-design` y `design` (crítica de diseño), ambos de Anthropic.

### Revisión 4 · Entrega y CapCut
- **Modo `alfa`**: los mismos efectos que FONDO (vidrio, glow, reflejos) pero sin fondo, en PNG con transparencia real.
- **5 clips de prueba** (ProRes 4444, WebM VP9, WebM VP8, QuickTime RLE, PNG MOV) para ver cuál acepta el CapCut del usuario.
  - Si alguno funciona, se reemplaza la versión verde: la mitad del render y sin las restricciones del chroma.
- **Límite de envío**: 30 MB por archivo, contemplado.
- **Opción futura**: `capcut-cli` (MIT) arma proyectos de CapCut con los clips, el chroma y keyframes ya aplicados. Es un formato no oficial y se puede romper con actualizaciones.

### Revisión 5 · Validación de punta a punta
- El QA encontró falsos positivos en las escenas 02 y 04: clip-path en px, movimiento ambiente constante y el interlineado contado como solapamiento. Los corregí: umbral de quietud adaptativo, recorte por overflow y cajas "de tinta".
- Resultado: las escenas 01, 02 y 04 dan 0 errores y 0 advertencias.
- Las escenas 02 y 04 se terminaron con el pipeline nuevo (render final más QA del chroma).
- **Persistencia**: un hook SessionStart (`motion/setup.sh`) instala las dependencias en cada sesión nueva en la nube. El contenedor es efímero y antes había que reinstalar a mano.

## Nivel de exigencia recomendado (calidad/costo)
| Tarea | Configuración | Por qué |
|---|---|---|
| Escena nueva, 1 o 2 por pedido | Sesión principal con **high** + `qa.mjs` + 1 `motion-reviewer` | Calidad de la escena 01 a ~1/5 del costo del multi-agente |
| Cambios de texto, tiempos o colores | **medium** o **low**, solo `qa.mjs` | No hace falta mirar imágenes |
| Cambios del motor (`stage.js`, `render`) | **xhigh** | Afecta todas las escenas |
| Lote de 4 o más escenas con apuro | Ultracode/workflow: 1 constructor por escena (high), 1 revisor sonnet/medium, sin etapa de "fix" aparte | Paraleliza el tiempo. Con las herramientas nuevas debería costar ~3 veces menos que en la v1 |
| Render y entrega | Cualquier nivel, en background | Es trabajo de máquina, no de modelo |

- **Ultracode no conviene por defecto**: en la v1 multiplicó el costo por ~10 para una mejora de calidad chica.
- **Modo `/fast`**: sirve para iterar rápido con el usuario al lado. No mejora la calidad y cuesta más por token.
