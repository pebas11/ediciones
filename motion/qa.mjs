// QA automático de una escena, sin mirar imágenes (barato en tokens).
//
//   node qa.mjs <escena> [--modes fondo,verde]
//
// Revisa:
//  - errores de consola
//  - "beats" en reposo (ventanas sin animación) → borrador de hoja de cues
//  - en cada reposo: textos fuera del margen seguro, solapados, desbordando su tarjeta,
//    demasiado chicos, y máscaras con line-height que corta tildes
//  - modo verde: inicio y fin 100 % verde, píxeles "sucios" (mezcla con verde fuera de bordes),
//    estilos semitransparentes / sombras / glow que quedaron activos en verde
// Sale con código 1 si hay errores (✖). Las advertencias (⚠) no cortan.
import { startServer, launch, openScene, capture, sceneExists } from './lib/harness.mjs';

const args = process.argv.slice(2);
const scene = args[0];
const opt = (k, d) => { const i = args.indexOf('--' + k); return i >= 0 ? args[i + 1] : d; };
const modes = opt('modes', 'fondo,verde').split(',');
if (!scene || !sceneExists(scene)) { console.error('escena inexistente:', scene); process.exit(2); }

const SAFE = { x0: 96, x1: 1824, y0: 60, y1: 1020 };
const server = await startServer();
const browser = await launch();
let nErr = 0, nWarn = 0;
const out = [];
const E = (s) => { nErr++; out.push('  ✖ ' + s); };
const W = (s) => { nWarn++; out.push('  ⚠ ' + s); };
const OK = (s) => out.push('  ✔ ' + s);
const fmtT = (t) => { const m = Math.floor(t / 60); return `${m}:${(t - m * 60).toFixed(1).padStart(4, '0')}`; };

/* ---------- análisis dentro de la página ---------- */
const PAGE_FN = {
  // ventanas de reposo a partir de los hijos directos del timeline
  rests: () => {
    const kids = M.tl.getChildren(false, true, true);
    const iv = kids.map((k) => [k.startTime(), k.startTime() + k.totalDuration()]).filter(([a, b]) => b - a > 0.001).sort((a, b) => a[0] - b[0]);
    const merged = [];
    for (const [a, b] of iv) { if (merged.length && a <= merged[merged.length - 1][1] + 1e-3) merged[merged.length - 1][1] = Math.max(merged[merged.length - 1][1], b); else merged.push([a, b]); }
    const gaps = [];
    let prev = 0;
    for (const [a, b] of merged) { if (a - prev >= 0.6) gaps.push([prev, a]); prev = Math.max(prev, b); }
    if (M.duration - prev >= 0.6) gaps.push([prev, M.duration]);
    return gaps;
  },

  // bloques de texto visibles con su caja real (Range) + chequeos de estilo
  inspect: (SAFE) => {
    const world = document.getElementById('world');
    const visibleChain = (el) => {
      let op = 1;
      for (let e = el; e && e !== document.body; e = e.parentElement) {
        const cs = getComputedStyle(e);
        if (cs.display === 'none' || cs.visibility === 'hidden') return 0;
        op *= parseFloat(cs.opacity);
        const cp = cs.clipPath;
        if (cp && cp.startsWith('inset(')) {
          const w = e.offsetWidth || e.getBBox?.().width || 0, h = e.offsetHeight || e.getBBox?.().height || 0;
          const px = (x, ref) => x.endsWith('%') ? parseFloat(x) / 100 * ref : parseFloat(x);
          const raw = cp.slice(6).split('round')[0].replace(')', '').trim().split(/\s+/);
          const [t, r = t, b = t, l = r] = raw;
          if (px(t, h) + px(b, h) >= h - 1 || px(l, w) + px(r, w) >= w - 1) return 0;
        }
        const tr = cs.transform;
        if (tr && tr !== 'none') {
          const m = tr.match(/matrix(3d)?\(([^)]+)\)/);
          if (m) { const n = m[2].split(',').map(Number); const sx = m[1] ? Math.hypot(n[0], n[1], n[2]) : Math.hypot(n[0], n[1]); const sy = m[1] ? Math.hypot(n[4], n[5], n[6]) : Math.hypot(n[2], n[3]); if (sx < 0.02 || sy < 0.02) return 0; }
        }
      }
      return op;
    };
    // recorta la caja por todos los ancestros con overflow; null si queda (casi) oculta
    const clipRect = (el, r) => {
      let x0 = r.left, y0 = r.top, x1 = r.right, y1 = r.bottom;
      for (let e = el.parentElement; e && e !== document.body; e = e.parentElement) {
        const cs = getComputedStyle(e);
        if (cs.overflow !== 'visible' || cs.overflowX === 'clip' || cs.overflowY === 'clip') {
          const c = e.getBoundingClientRect();
          x0 = Math.max(x0, c.left); y0 = Math.max(y0, c.top); x1 = Math.min(x1, c.right); y1 = Math.min(y1, c.bottom);
        }
      }
      if (x1 - x0 <= 1 || y1 - y0 <= 1) return null;
      if ((x1 - x0) * (y1 - y0) < 0.5 * r.width * r.height) return null;   // a medio enmascarar → transición
      return { left: x0, top: y0, right: x1, bottom: y1 };
    };
    const blockOf = (el) => {
      for (let e = el; e && e !== world; e = e.parentElement) {
        const d = getComputedStyle(e).display;
        if (!d.startsWith('inline') && d !== 'contents') return e;
      }
      return el;
    };
    const desc = (e) => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + (typeof e.className === 'string' && e.className ? '.' + e.className.trim().split(/\s+/).slice(0, 2).join('.') : '');

    // 1) textos
    const blocks = new Map();
    const tw = document.createTreeWalker(world, NodeFilter.SHOW_TEXT);
    for (let n = tw.nextNode(); n; n = tw.nextNode()) {
      if (!n.textContent.trim()) continue;
      const el = n.parentElement;
      if (el.closest('svg') && el.closest('defs')) continue;
      const op = visibleChain(el);
      if (op < 0.05) continue;
      const rg = document.createRange(); rg.selectNodeContents(n);
      const r0 = rg.getBoundingClientRect();
      if (r0.width < 1 || r0.height < 1) continue;
      const r = clipRect(el, r0);
      if (!r) continue;
      const b = blockOf(el);
      const fs = parseFloat(getComputedStyle(el).fontSize);
      const cur = blocks.get(b) || { text: '', x0: 1e9, y0: 1e9, x1: -1e9, y1: -1e9, minFs: 1e9, el: b };
      cur.text += (cur.text && (r.top > cur.lastBottom - 2 || r.left - cur.lastRight > 3) ? ' ' : '') + n.textContent; cur.lastBottom = Math.max(cur.lastBottom || 0, r.bottom); cur.lastRight = r.right; cur.x0 = Math.min(cur.x0, r.left); cur.y0 = Math.min(cur.y0, r.top); cur.x1 = Math.max(cur.x1, r.right); cur.y1 = Math.max(cur.y1, r.bottom); cur.minFs = Math.min(cur.minFs, fs);
      blocks.set(b, cur);
    }
    const list = [...blocks.values()].map((b) => {
      const box = b.el.closest('.card, .pill');
      let over = null;
      if (box) { const c = box.getBoundingClientRect(); const o = Math.max(c.left - b.x0, b.x1 - c.right, c.top - b.y0, b.y1 - c.bottom); if (o > 2) over = Math.round(o); }
      // máscaras de SplitText (overflow clip) con line-height justo → tildes cortadas
      let tight = false;
      b.el.querySelectorAll('*').forEach((m) => { const cs = getComputedStyle(m); if ((cs.overflow === 'clip' || cs.overflow === 'hidden') && m.children.length) { const lh = parseFloat(cs.lineHeight), f = parseFloat(cs.fontSize); if (lh && f && lh / f < 1.18) tight = true; } });
      return { text: b.text.replace(/\s+/g, ' ').trim().slice(0, 48), x0: b.x0, y0: b.y0, x1: b.x1, y1: b.y1, minFs: b.minFs, over, tight, sel: desc(b.el) };
    });

    // 2) estilos no aptos para chroma (se evalúan en ambos modos; el llamador decide)
    const bad = new Map();
    const alpha = (c) => { const m = c && c.match(/rgba?\(([^)]+)\)/); if (!m) return 1; const p = m[1].split(/[ ,/]+/).filter(Boolean); return p.length >= 4 ? parseFloat(p[3]) : 1; };
    world.querySelectorAll('*').forEach((el) => {
      if (el.closest('defs')) return;
      const r = el.getBoundingClientRect();
      if (r.width < 1 || r.height < 1) return;
      const op = visibleChain(el);
      if (op < 0.05) return;
      const cs = getComputedStyle(el);
      const why = [];
      if (op < 0.98) why.push('opacity ' + op.toFixed(2));
      if (cs.boxShadow !== 'none') why.push('box-shadow');
      if (cs.filter !== 'none') why.push('filter');
      if (cs.backdropFilter && cs.backdropFilter !== 'none') why.push('backdrop-filter');
      if (cs.webkitBoxReflect && cs.webkitBoxReflect !== 'none') why.push('reflejo');
      if (cs.mixBlendMode !== 'normal') why.push('blend ' + cs.mixBlendMode);
      if (el.childNodes.length && [...el.childNodes].some((c) => c.nodeType === 3 && c.textContent.trim()) && alpha(cs.color) < 0.98 && cs.webkitTextFillColor !== 'rgba(0, 0, 0, 0)') why.push('color alpha ' + alpha(cs.color));
      if (alpha(cs.backgroundColor) > 0.01 && alpha(cs.backgroundColor) < 0.98) why.push('fondo alpha');
      if (/rgba\([^)]*,\s*0?\.\d+\)/.test(cs.backgroundImage)) why.push('degradé con transparencia');
      if (el instanceof SVGElement) {
        if (cs.fill !== 'none' && alpha(cs.fill) < 0.98) why.push('fill alpha');
        if (cs.stroke !== 'none' && alpha(cs.stroke) < 0.98) why.push('stroke alpha');
        if (parseFloat(cs.fillOpacity) < 0.98 && cs.fill !== 'none') why.push('fill-opacity');
        if (parseFloat(cs.strokeOpacity) < 0.98 && cs.stroke !== 'none') why.push('stroke-opacity');
      }
      if (why.length) { const k = desc(el); bad.set(k, [...new Set([...(bad.get(k) || []), ...why])]); }
    });
    return { list, bad: [...bad.entries()] };
  },
};

// Estadística de píxeles de un PNG, calculada dentro de Chromium
async function greenStats(page, png) {
  return page.evaluate(async (b64) => {
    const bmp = await createImageBitmap(await (await fetch('data:image/png;base64,' + b64)).blob());
    const W = bmp.width, H = bmp.height;
    const cv = new OffscreenCanvas(W, H); const ctx = cv.getContext('2d'); ctx.drawImage(bmp, 0, 0);
    const d = ctx.getImageData(0, 0, W, H).data;
    const pure = new Uint8Array(W * H), mix = new Uint8Array(W * H);
    let nPure = 0;
    for (let i = 0, p = 0; p < W * H; i += 4, p++) {
      const r = d[i], g = d[i + 1], b = d[i + 2];
      if (g > 200 && r < 60 && b < 60) { pure[p] = 1; nPure++; }
      else if (g > r + 50 && g > b + 50) mix[p] = 1;
    }
    // mezcla "sucia" = verdosa y a más de 2 px de cualquier píxel de contenido
    let dirty = 0;
    for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) {
      const p = y * W + x; if (!mix[p]) continue;
      let near = false;
      for (let dy = -2; dy <= 2 && !near; dy++) for (let dx = -2; dx <= 2; dx++) {
        const yy = y + dy, xx = x + dx; if (yy < 0 || yy >= H || xx < 0 || xx >= W) continue;
        const q = yy * W + xx; if (!pure[q] && !mix[q]) { near = true; break; }
      }
      if (!near) dirty++;
    }
    return { pure: nPure / (W * H), dirty: dirty / (W * H) };
  }, png.toString('base64'));
}

// Tramos quietos = cuadros consecutivos (cada 0,1 s, en verde a 1/4 de resolución) que casi no cambian.
// Es independiente de cómo esté armado el timeline (contadores, íconos que respiran, etc.).
async function stillWindows() {
  const { page, duration, cdp } = await openScene(browser, server, scene, 'verde', { dsf: 0.25 });
  const moving = [];
  for (let t = 0; t <= duration + 1e-6; t += 0.1) {
    await page.evaluate((t) => window.__seek(t), t);
    const b64 = (await capture(cdp, 'png')).toString('base64');
    // la comparación con el cuadro anterior se hace dentro de la página (sin mover píxeles a Node)
    const f = await page.evaluate(async (b64) => {
      const bmp = await createImageBitmap(await (await fetch('data:image/png;base64,' + b64)).blob());
      const cv = new OffscreenCanvas(bmp.width, bmp.height); const ctx = cv.getContext('2d'); ctx.drawImage(bmp, 0, 0);
      const d = ctx.getImageData(0, 0, bmp.width, bmp.height).data;
      const p = window.__qaPrev; window.__qaPrev = d;
      if (!p) return null;
      let ch = 0;
      for (let i = 0; i < d.length; i += 4) if (Math.abs(d[i] - p[i]) + Math.abs(d[i + 1] - p[i + 1]) + Math.abs(d[i + 2] - p[i + 2]) > 24) ch++;
      return ch / (d.length / 4);
    }, b64);
    if (f !== null) moving.push([t, f]);
    if (process.env.QA_DEBUG && f !== null) console.log('mov', t.toFixed(1), (f * 100).toFixed(2));
  }
  await page.close();
  // umbral adaptativo: escenas con movimiento ambiente constante (derivas, brillos) tienen un "piso" propio
  const nz = moving.map(([, f]) => f).filter((f) => f > 0).sort((a, b) => a - b);
  const floor = nz.length ? nz[Math.floor(nz.length * 0.25)] : 0;
  const thr = Math.max(0.004, floor * 1.6);
  const win = []; let a = null;
  for (const [t, f] of moving) {
    const still = f < thr;
    if (still && a === null) a = t - 0.1;
    if (!still && a !== null) { if (t - 0.1 - a >= 0.5) win.push([a, t - 0.1]); a = null; }
  }
  if (a !== null && duration - a >= 0.5) win.push([a, duration]);
  return win;
}
const STILL = await stillWindows();

for (const mode of modes) {
  const { page, duration, errors, cdp } = await openScene(browser, server, scene, mode);
  out.push(`\n[${scene} · ${mode}] duración ${duration}s`);
  if (errors.length) errors.forEach((e) => E('consola: ' + e)); else OK('sin errores de consola');

  const holds = STILL.filter(([a, b]) => a > 0.05 && b < duration - 0.05);
  if (!holds.length) W('no hay ningún tramo quieto ≥ 0,6 s (¿hay pausas para la narración?)');

  const seen = { safe: new Set(), overlap: new Set(), over: new Set(), small: new Set(), tight: new Set(), bad: new Map() };
  const cues = [];
  for (const [a, b] of holds) {
    const t = (a + b) / 2;
    await page.evaluate((t) => window.__seek(t), t);
    const { list, bad } = await page.evaluate(PAGE_FN.inspect, SAFE);
    cues.push(`${fmtT(a)}–${fmtT(b)} quieto: ${list.map((x) => x.text).filter(Boolean).slice(0, 8).join(' · ')}`);
    for (const x of list) {
      if (x.x0 < SAFE.x0 - 1 || x.x1 > SAFE.x1 + 1 || x.y0 < SAFE.y0 - 1 || x.y1 > SAFE.y1 + 1) seen.safe.add(`"${x.text}" [${Math.round(x.x0)},${Math.round(x.y0)}→${Math.round(x.x1)},${Math.round(x.y1)}] @${fmtT(t)}`);
      if (x.over) seen.over.add(`"${x.text}" sobresale ${x.over}px de su tarjeta @${fmtT(t)}`);
      if (x.minFs < 20) seen.small.add(`"${x.text}" ${x.minFs}px`);
      if (x.tight) seen.tight.add(`"${x.text}" (${x.sel})`);
    }
    for (let i = 0; i < list.length; i++) for (let j = i + 1; j < list.length; j++) {
      const ink = (b) => ({ x0: b.x0, x1: b.x1, y0: b.y0 + 0.2 * b.minFs, y1: b.y1 - 0.2 * b.minFs });
      const p = ink(list[i]), q = ink(list[j]);
      p.text = list[i].text; q.text = list[j].text;
      const ix = Math.min(p.x1, q.x1) - Math.max(p.x0, q.x0), iy = Math.min(p.y1, q.y1) - Math.max(p.y0, q.y0);
      if (ix > 2 && iy > 2) {
        const small = Math.min((p.x1 - p.x0) * (p.y1 - p.y0), (q.x1 - q.x0) * (q.y1 - q.y0));
        if (ix * iy > 0.04 * small) seen.overlap.add(`"${p.text}" ↔ "${q.text}" @${fmtT(t)}`);
      }
    }
    if (mode === 'verde') for (const [k, v] of bad) seen.bad.set(k, [...new Set([...(seen.bad.get(k) || []), ...v])]);
  }
  seen.over.forEach((s) => E('texto desborda: ' + s));
  seen.overlap.forEach((s) => W('textos solapados: ' + s));
  seen.safe.forEach((s) => W('fuera del margen seguro: ' + s));
  seen.small.forEach((s) => W('texto chico (<20px): ' + s));
  seen.tight.forEach((s) => W('máscara con line-height < 1.18 (puede cortar tildes): ' + s));
  if (!seen.over.size && !seen.overlap.size && !seen.safe.size) OK(`layout limpio en ${holds.length} tramos quietos`);

  if (mode === 'verde') {
    // inicio y final vacíos
    for (const t of [0.02, duration - 0.04]) {
      await page.evaluate((t) => window.__seek(t), t);
      const s = await greenStats(page, await capture(cdp));
      if (s.pure < 0.9995) E(`el cuadro ${fmtT(t)} no está vacío (verde puro ${(s.pure * 100).toFixed(2)} %)`);
    }
    // suciedad de chroma muestreada
    let worst = 0, worstT = 0;
    for (let t = 0.25; t < duration; t += 0.5) {
      await page.evaluate((t) => window.__seek(t), t);
      const s = await greenStats(page, await capture(cdp));
      if (s.dirty > worst) { worst = s.dirty; worstT = t; }
    }
    (worst > 0.0005 ? E : OK)(`chroma: suciedad máx ${(worst * 100).toFixed(4)} % @${fmtT(worstT)} (límite 0,05 %)`);
    if (seen.bad.size) for (const [k, v] of seen.bad) W(`estilo no opaco en verde: ${k} → ${v.join(', ')}`);
    else OK('sin estilos semitransparentes en reposo');
  } else {
    out.push('  cues (borrador):');
    cues.forEach((c) => out.push('    ' + c));
  }
  await page.close();
}

await browser.close();
server.close();
console.log(out.join('\n'));
console.log(`\nResultado: ${nErr} error(es), ${nWarn} advertencia(s)`);
process.exit(nErr ? 1 : 0);
