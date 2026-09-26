# Reglas técnicas del motor (leer antes de escribir una escena)

Motor: `lib/stage.js` (API `M.*`), estilos en `lib/theme.css`. Escena de referencia: `scenes/01-balance.html`.
API: `M.textIn/textOut`, `M.popIn/popOut`, `M.zoomIn/zoomOut`, `M.draw/undraw`, `M.counter`, `M.fmt`, `M.onFrame`, `M.D`, `M.spring`. Íconos: `<i data-icon=\"nombre\">` (Phosphor duotone) + `icons:[...]` en `M.scene`.
Todo en `M.tl` (timeline pausado). Prohibido: CSS animations/transitions, setTimeout, rAF, Math.random (usar `M.rng(seed)`).

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
12. Modo `alfa`: mismos efectos que fondo sin el fondo; las tarjetas translúcidas dejan ver el video de abajo, así que conviene subir la opacidad del relleno si el texto pierde legibilidad.

