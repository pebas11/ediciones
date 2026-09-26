---
name: motion-graphics
description: Crear, revisar y renderizar motion graphics explicativos (HTML + GSAP → MP4 para CapCut) en este repo. Usar cuando el usuario pide animaciones, gráficos animados, títulos, overlays con chroma/alfa o cambios a escenas en motion/scenes/.
---

# Motion graphics — proceso optimizado

Motor propio en `motion/`: escena HTML + GSAP (timeline pausado, determinista) → Chromium headless → ffmpeg.
Salidas por escena: `renders/<escena>_FONDO.mp4` (azul noche completo) y `_VERDE.mp4` (chroma #00FF00).
Modo `alfa` disponible (PNG con transparencia) — solo usarlo si el usuario confirmó qué formato con alfa acepta su CapCut.

## Proceso (en este orden; cada paso es barato salvo el render final)
1. **Brief**: datos, textos y beats. Una idea por vez; 12–15 s por escena; holds ≥ 1,5 s para la narración.
   Si hay afirmaciones científicas, verificarlas (PubMed está conectado) antes de animarlas.
2. **Construir** `motion/scenes/NN-nombre.html` copiando la estructura de `scenes/01-balance.html`.
   Reglas técnicas: `motion/docs/RULES.md` (leer SIEMPRE antes de escribir). Tokens de motion: `motion/docs/APPLE-MOTION.md`.
   Recetas de movimiento (on demand, no leer todo): `motion/reference/hyperframes/hyperframes-animation/rules-index.md`.
3. **QA automático** (sin imágenes, ~20 s): `node qa.mjs <escena>` → errores de layout, chroma, cues. Corregir hasta 0 ✖.
4. **Mirar** solo lo necesario, en este orden de costo:
   - `node render.mjs <escena> --sheet 16 --modes fondo` → 1 imagen 1920×1080 (~2,8k tokens) para ritmo y composición.
   - `--stills t --crop x,y,w,h` para inspeccionar un detalle a resolución completa (recorte = pocos tokens).
   - `--stills t --scale 0.5` para un cuadro entero barato. Evitar cuadros completos a 1920 salvo el control final.
5. **Previa de movimiento** (opcional, para aprobar con el usuario): `node render.mjs <escena> --draft --modes fondo` (960×540, 30 fps, ~1 min).
6. **Render final**: `node render.mjs <escena>` (3 workers en paralelo, ~2,5 min por versión de 13 s). Correr en background.
7. **Entregar**: SendUserFile (límite 30 MB por archivo) + hoja de cues (sale de `qa.mjs`). Commit + push.

## Presupuesto (calidad/costo)
- Una escena: construir y revisar en la sesión principal con esfuerzo **high**. Sin multi-agente.
- Varias escenas en paralelo: un subagente constructor por escena + **un** revisor `motion-reviewer` (sonnet, medium) que use qa.mjs + 1 hoja. Continuar al mismo constructor con SendMessage para las correcciones (no crear uno nuevo: re-leería todo).
- Nunca más de ~6 imágenes completas por iteración; preferir qa.mjs y recortes.

## Comandos
```
cd motion
node qa.mjs 04-deficit                       # QA completo (fondo + verde)
node render.mjs 04-deficit --sheet 16 --modes fondo
node render.mjs 04-deficit --stills 6.2 --crop 400,200,960,540
node render.mjs 04-deficit --draft --modes fondo
node render.mjs 04-deficit                   # final 60 fps, ambas versiones
python3 qa_chroma.py renders/04-deficit_VERDE.mp4   # control del MP4 verde ya codificado
node alpha_test.mjs 01-balance 5 8.5         # clips de prueba con alfa (5 códecs)
```
