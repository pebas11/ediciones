/* Neón para la serie 7 (Hugging Face). Bloom aditivo barato y determinista sobre el canvas 2D.
   Uso: <script src="../lib/neon.js"></script>; al FINAL de cada M.onFrame: Neon.bloom(ctx, cv, { k: 0.9 }).
   Colores = significado fijo (ver BRIEF-HF.md). */
(function () {
  const PAL = {
    BG: [5, 7, 13],
    INK: [226, 236, 250],        // texto y estructura neutra
    CYAN: [24, 230, 255],        // agentes / enjambre
    RED: [255, 51, 85],          // intrusión, vulnerabilidad, alarma
    GREEN: [120, 255, 90],       // defensa, Hugging Face, detección, correcto
    AMBER: [255, 176, 32],       // datos, credenciales, secretos
    VIOLET: [155, 107, 255],     // infraestructura de OpenAI / entorno de evaluación
    MAG: [255, 46, 147],         // encubrimiento, engaño
  };
  const rgba = (c, a) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${Math.max(0, Math.min(1, a)).toFixed(3)})`;
  const mk = (w, h) => { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; };
  let g1, g2, g3;
  /* Bloom: copia reducida y desenfocada, sumada en modo 'lighter'. Tres radios = halo suave sin degradés baratos. */
  function bloom(ctx, cv, o) {
    o = o || {}; const k = o.k == null ? 0.6 : o.k;
    const W = cv.width, H = cv.height;
    if (!g1) { g1 = mk(W / 4, H / 4); g2 = mk(W / 8, H / 8); g3 = mk(W / 16, H / 16); }
    const a = g1.getContext('2d'), b = g2.getContext('2d'), c = g3.getContext('2d');
    a.clearRect(0, 0, g1.width, g1.height); a.filter = 'contrast(1.9) blur(2px)'; a.drawImage(cv, 0, 0, g1.width, g1.height); a.filter = 'none';
    b.clearRect(0, 0, g2.width, g2.height); b.filter = 'blur(3px)'; b.drawImage(g1, 0, 0, g2.width, g2.height); b.filter = 'none';
    c.clearRect(0, 0, g3.width, g3.height); c.filter = 'blur(3px)'; c.drawImage(g2, 0, 0, g3.width, g3.height); c.filter = 'none';
    ctx.save(); ctx.globalCompositeOperation = 'lighter';
    ctx.globalAlpha = 0.55 * k; ctx.drawImage(g1, 0, 0, W, H);
    ctx.globalAlpha = 0.55 * k; ctx.drawImage(g2, 0, 0, W, H);
    ctx.globalAlpha = 0.45 * k; ctx.drawImage(g3, 0, 0, W, H);
    ctx.restore();
  }
  /* Fondo: negro azulado + malla muy tenue que respira + viñeta propia. */
  function bg(ctx, t, o) {
    o = o || {}; const W = 1920, H = 1080;
    ctx.fillStyle = rgba(PAL.BG, 1); ctx.fillRect(0, 0, W, H);
    const gA = (o.grid == null ? 0.05 : o.grid);
    ctx.strokeStyle = rgba(PAL.CYAN, gA); ctx.lineWidth = 1; ctx.beginPath();
    for (let x = 0; x <= W; x += 80) { ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, H); }
    for (let y = 0; y <= H; y += 80) { ctx.moveTo(0, y + 0.5); ctx.lineTo(W, y + 0.5); }
    ctx.stroke();
  }
  /* Texto con halo (shadowBlur) además del bloom global. */
  function text(ctx, s, x, y, font, col, a, o) {
    if (a <= 0.004) return; o = o || {};
    ctx.save(); ctx.font = font; ctx.textAlign = o.align || 'left'; ctx.textBaseline = o.base || 'alphabetic';
    if (o.spacing) ctx.letterSpacing = o.spacing;
    ctx.shadowColor = rgba(col, 0.9 * a); ctx.shadowBlur = o.glow == null ? 10 : o.glow;
    ctx.fillStyle = rgba(col, a); ctx.fillText(s, x, y); ctx.restore();
  }
  window.Neon = { PAL, rgba, bloom, bg, text };
})();
