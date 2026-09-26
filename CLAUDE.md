# ediciones

Motion graphics explicativos para videos que el usuario edita en CapCut. El usuario escribe en español rioplatense; en pantalla va español neutro.

- Todo el trabajo de animación está en `motion/`. Para cualquier pedido de animación usá la skill `motion-graphics`: tiene el proceso, los comandos y el presupuesto de tokens.
- Antes de escribir una escena, leé `motion/docs/RULES.md` (reglas técnicas) y `motion/docs/APPLE-MOTION.md` (curvas, duraciones, tipografía).
- Revisá primero con `node qa.mjs <escena>`, que no gasta imágenes. Mirá imágenes solo para juzgar el diseño, con hojas de 16 cuadros y recortes.
- Los renders finales van en background: son ~2,5 min por versión.
- Para entregar: SendUserFile tiene un límite de 30 MB por archivo. Commiteá los renders en `motion/renders/`, pero no `stills/` ni `node_modules/`.
- Las dependencias se instalan solas al abrir la sesión (hook en `.claude/settings.json` → `motion/setup.sh`).
- **Texto en pantalla: mínimo** (skill `motion-copy`, obligatoria): ≤ 5 palabras por titular, ≤ 18 por escena, sin "FIG.", láminas, citas ni rótulos técnicos. La voz en off explica.
- **Tipografía prioritaria (pedido del usuario): League Spartan** para titulares, con DM Sans para el cuerpo y DM Mono para los rótulos (`motion/lib/fonts-spartan.css`). Usarla por defecto en todo trabajo nuevo, sin preguntar.
- Estética: que no parezca hecha con IA. Evitar degradés arcoíris, glassmorphism y glow en todo. Preferir el estilo editorial o de lámina científica, con 3D real (Three.js, `motion/lib/three-stage.mjs`). El usuario dio permiso para decidir sin pedir confirmación.
