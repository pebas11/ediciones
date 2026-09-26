/* ==========================================================================
   stage.js — motor común de las animaciones.
   Todo es determinista: cada frame se dibuja con M.seek(t) (segundos), así el
   render cuadro a cuadro sale idéntico siempre (sin depender del reloj).

   Uso en una escena:
     <script src="../node_modules/gsap/dist/gsap.min.js"></script>
     <script src="../node_modules/gsap/dist/SplitText.min.js"></script>
     <script src="../node_modules/gsap/dist/DrawSVGPlugin.min.js"></script>
     <script src="../node_modules/gsap/dist/CustomEase.min.js"></script>
     <script src="../lib/stage.js"></script>
     <script>
       M.scene({ duration: 13, icons: ['scales', ...] }, (tl, M) => { ...timeline... });
     </script>
   ========================================================================== */
(function () {
  const params = new URLSearchParams(location.search);
  // fondo = azul noche completo · verde = chroma #00FF00 opaco · alfa = efectos de fondo sin el fondo (PNG con transparencia)
  const MODE = ['verde', 'alfa'].includes(params.get('mode')) ? params.get('mode') : 'fondo';
  document.documentElement.classList.add(MODE);

  gsap.registerPlugin(SplitText, DrawSVGPlugin, CustomEase);
  gsap.ticker.lagSmoothing(0);
  gsap.config({ force3D: true });

  // Curvas de aceleración/frenado controladas (estilo motion graphics)
  CustomEase.create('smooth', 'M0,0 C0.45,0 0.15,1 1,1');        // entrada suave, frenado largo
  CustomEase.create('swift', 'M0,0 C0.7,0 0.2,1 1,1');           // arranque firme, frenado largo
  CustomEase.create('exit', 'M0,0 C0.55,0 0.85,0.35 1,1');        // salida que acelera
  CustomEase.create('settle', 'M0,0 C0.3,0 0.22,1.1 0.55,1.03 C0.72,0.99 0.86,1 1,1'); // leve rebote

  // Tokens de motion estilo Apple (medidos en el CSS de apple.com + springs de SwiftUI). Preferir estos en escenas nuevas.
  CustomEase.create('apple', 'M0,0 C0.4,0 0.6,1 1,1');           // curva de la casa (0.4,0,0.6,1): cambios de estado, movimientos
  CustomEase.create('appleOut', 'M0,0 C0,0 0.2,1 1,1');          // (0,0,0.2,1): entradas / revelados
  CustomEase.create('appleIn', 'M0,0 C0.4,0 1,1 1,1');           // (0.4,0,1,1): salidas
  // Spring tipo SwiftUI normalizado a la duración del tween. bounce 0 = sin rebote (default de Apple), 0.15 = apenas
  const springEase = (bounce = 0) => {
    const z = 1 - bounce, w = 2 * Math.PI * 1.0, wd = w * Math.sqrt(Math.max(1e-6, 1 - z * z));
    const x = (t) => z >= 0.999 ? 1 - Math.exp(-w * t) * (1 + w * t)
      : 1 - Math.exp(-z * w * t) * (Math.cos(wd * t) + (z * w / wd) * Math.sin(wd * t));
    const end = x(1);
    return (t) => x(t) + (1 - end) * t;
  };

  // PRNG determinista
  function rng(seed) { let s = seed >>> 0; return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; }; }

  const frameHooks = [];
  const counters = [];
  const iconCache = {};

  const M = {
    /** Duraciones (s) y ritmo estilo Apple */
    D: { micro: 0.24, fast: 0.4, base: 0.5, reveal: 0.8, scene: 1.0, staggerMax: 0.5, hold: 1.5 },
    spring: springEase,
    W: 1920, H: 1080, mode: MODE, chroma: MODE === 'verde', duration: 10,
    tl: gsap.timeline({ paused: true, defaults: { ease: 'smooth' } }),
    rng,

    onFrame(fn) { frameHooks.push(fn); },

    /** Sonido: cues que se sintetizan al renderizar (lib/audio.js). Sin audio.js solo se registran.
        M.sfx(2.0, 'impact', { gain: -3 }) · presets: bed whoosh tick tap impact shimmer scan grow riser swell */
    audio: { cues: [], opts: null },
    sfx(at, type, opts = {}) { M.audio.cues.push({ ...opts, at, type }); return M; },

    /** Formato numérico en español: 1.800 / 28,8 */
    fmt(v, decimals = 0) {
      const s = Math.abs(v).toFixed(decimals);
      let [i, d] = s.split('.');
      i = i.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
      return (v < 0 ? '−' : '') + (d ? i + ',' + d : i);
    },

    /** Contador animado: tl.to(proxy) + escritura del texto en cada frame */
    counter(el, { from = 0, to, decimals = 0, prefix = '', suffix = '', at, dur = 1.6, ease = 'power2.out', sign = false }) {
      const proxy = { v: from };
      const write = () => {
        const v = proxy.v;
        const s = (sign && v > 0 ? '+' : '') + M.fmt(v, decimals);
        el.textContent = prefix + s + suffix;
      };
      counters.push(write);
      write();
      M.tl.to(proxy, { v: to, duration: dur, ease }, at);
      return proxy;
    },

    /** Inserta un ícono Phosphor (duotone por defecto) */
    icon(name, weight = 'duotone') {
      const key = name + '-' + weight;
      const span = document.createElement('span');
      span.className = 'ico';
      span.innerHTML = iconCache[key] || '';
      return span;
    },

    async loadIcons(names, weight = 'duotone') {
      await Promise.all(names.map(async (n) => {
        const key = n + '-' + weight;
        const file = weight === 'regular' ? `${n}.svg` : `${n}-${weight}.svg`;
        const res = await fetch(`../node_modules/@phosphor-icons/core/assets/${weight}/${file}`);
        if (!res.ok) throw new Error('icono no encontrado: ' + n);
        let svg = await res.text();
        svg = svg.replace(/opacity="0\.2"/g, 'class="duo"');
        iconCache[key] = svg;
      }));
    },

    /** Reemplaza <i data-icon="name"> por el SVG */
    hydrateIcons(root = document) {
      root.querySelectorAll('[data-icon]').forEach((el) => {
        const w = el.dataset.weight || 'duotone';
        el.innerHTML = iconCache[el.dataset.icon + '-' + w] || '';
        el.classList.add('ico');
      });
    },

    /** Texto que sube desde una máscara (por palabras o letras). Sin opacidad → limpio en chroma */
    split(el, type = 'chars', cls) {
      const o = { type: type === 'chars' ? 'chars,words' : 'words', mask: type === 'chars' ? 'chars' : 'words' };
      if (cls) o[type === 'chars' ? 'charsClass' : 'wordsClass'] = cls;
      return SplitText.create(el, o);
    },

    textIn(target, at, { type = 'chars', stagger, dur = 1.0, ease = 'swift', cls } = {}) {
      const sp = M.split(target, type, cls);
      const items = type === 'chars' ? sp.chars : sp.words;
      M.tl.from(items, { yPercent: 105, duration: dur, ease, stagger: stagger ?? (type === 'chars' ? 0.035 : 0.07) }, at);
      if (!M.chroma) M.tl.from(items, { filter: 'blur(8px)', duration: dur * 0.7, ease: 'power2.out', stagger: stagger ?? (type === 'chars' ? 0.035 : 0.07) }, at);
      return sp;
    },

    textOut(sp, at, { type = 'chars', stagger, dur = 0.55 } = {}) {
      const items = type === 'chars' ? sp.chars : sp.words;
      M.tl.to(items, { yPercent: -105, duration: dur, ease: 'exit', stagger: stagger ?? 0.02 }, at);
    },

    /** Entrada de tarjeta/elemento: sube + escala + se "abre" (clip) — 2.5D con leve giro */
    popIn(el, at, { dur = 0.9, y = 40, scale = 0.9, rotX = 18, clip = true, ease = 'swift' } = {}) {
      const vars = { y, scale, rotationX: rotX, duration: dur, ease, transformPerspective: 1400 };
      M.tl.from(el, vars, at);
      if (clip) M.tl.fromTo(el, { clipPath: 'inset(50% 0% 50% 0% round 28px)' }, { clipPath: 'inset(-150% -150% -150% -150% round 28px)', duration: dur * 0.75, ease: 'smooth' }, at);
      if (!M.chroma) M.tl.from(el, { opacity: 0, duration: dur * 0.5, ease: 'power1.out' }, at);
    },

    popOut(el, at, { dur = 0.55, y = -30, scale = 0.94 } = {}) {
      M.tl.to(el, { y: '+=' + y, scale, duration: dur, ease: 'exit' }, at);
      M.tl.to(el, { clipPath: 'inset(50% 0% 50% 0% round 28px)', duration: dur, ease: 'exit' }, at);
    },

    /** Escala desde cero (íconos, puntos) */
    zoomIn(el, at, { dur = 0.7, ease = 'back.out(1.8)' } = {}) { M.tl.from(el, { scale: 0, duration: dur, ease }, at); },
    zoomOut(el, at, { dur = 0.45 } = {}) { M.tl.to(el, { scale: 0, duration: dur, ease: 'back.in(1.6)' }, at); },

    /** Dibuja un trazo SVG progresivamente */
    draw(el, at, { dur = 1.0, from = '0% 0%', ease = 'smooth' } = {}) { M.tl.fromTo(el, { drawSVG: from }, { drawSVG: '0% 100%', duration: dur, ease }, at); },
    undraw(el, at, { dur = 0.5, to = '100% 100%' } = {}) { M.tl.to(el, { drawSVG: to, duration: dur, ease: 'exit' }, at); },

    /** Crea la escena */
    async scene(opts, build) {
      M.duration = opts.duration;
      if (opts.audio) M.audio.opts = opts.audio;
      buildBackground(opts);
      await document.fonts.ready;
      if (opts.icons) await M.loadIcons(opts.icons);
      if (opts.iconsRegular) await M.loadIcons(opts.iconsRegular, 'regular');
      M.hydrateIcons();
      await build(M.tl, M);
      // Cámara: empuje lento hacia adelante (profundidad)
      const world = document.getElementById('world');
      M.onFrame((t) => {
        const k = t / M.duration;
        const s = 1 + (opts.push ?? 0.03) * (0.5 - 0.5 * Math.cos(Math.PI * k));
        world.style.transform = `scale(${s.toFixed(5)})`;
      });
      M.seek(0);
      window.__ready = true;
    },

    seek(t) {
      M.tl.seek(t, true);
      counters.forEach((w) => w());
      frameHooks.forEach((fn) => fn(t));
    },
  };

  /* ---------------------- Fondo azul noche ---------------------- */
  function buildBackground(opts) {
    const bg = document.getElementById('bg');
    if (!bg) return;
    // Temas: opts.lights (luces que derivan) y opts.particles ({ rgb, n }) permiten otros estilos de fondo
    const lights = opts.lights || [
      { x: 0.22, y: 0.28, r: 900, c: 'rgba(8,126,255,0.16)', ax: 60, ay: 40, sp: 0.11 },
      { x: 0.80, y: 0.62, r: 1000, c: 'rgba(32,196,239,0.10)', ax: 70, ay: 50, sp: 0.08 },
      { x: 0.55, y: 0.10, r: 800, c: 'rgba(115,189,242,0.08)', ax: 90, ay: 30, sp: 0.06 },
    ];
    const pcfg = opts.particles || {};
    const prgb = pcfg.rgb || ['140,210,255'];
    const els = lights.map((L) => {
      const d = document.createElement('div');
      d.className = 'light';
      d.style.width = d.style.height = L.r + 'px';
      d.style.background = `radial-gradient(circle, ${L.c} 0%, transparent 70%)`;
      bg.appendChild(d);
      return d;
    });
    if (opts.grid !== false) {
      const g = document.createElement('div'); g.className = 'grid' + (opts.grid === 'dots' ? ' dots' : ''); bg.appendChild(g);
      const h = document.createElement('div'); h.className = 'horizon'; bg.appendChild(h);
    }
    // partículas (polvo luminoso con profundidad)
    const cv = document.createElement('canvas'); cv.width = 1920; cv.height = 1080; bg.appendChild(cv);
    const ctx = cv.getContext('2d');
    const r = rng(7);
    const P = Array.from({ length: pcfg.n ?? 90 }, (_, i) => {
      const z = r();
      return { x: r() * 1920, y: r() * 1080, z, s: 0.8 + z * 2.4, v: 6 + z * 22, a: 0.10 + z * 0.35, ph: r() * 6.28, c: prgb[i % prgb.length] };
    });
    const vg = document.createElement('div'); vg.className = 'vignette'; bg.appendChild(vg);
    // ruido fino (evita el "banding" del degradé al comprimir)
    const nz = document.createElement('canvas'); nz.width = nz.height = 256;
    const nctx = nz.getContext('2d'); const img = nctx.createImageData(256, 256); const rn = rng(99);
    for (let i = 0; i < img.data.length; i += 4) { const v = 128 + (rn() - 0.5) * 255; img.data[i] = img.data[i + 1] = img.data[i + 2] = v; img.data[i + 3] = 255; }
    nctx.putImageData(img, 0, 0);
    const noise = document.createElement('div'); noise.className = 'noise';
    noise.style.backgroundImage = `url(${nz.toDataURL()})`; bg.appendChild(noise);

    M.onFrame((t) => {
      lights.forEach((L, i) => {
        const x = L.x * 1920 - L.r / 2 + Math.sin(t * L.sp * 6.28 + i) * L.ax;
        const y = L.y * 1080 - L.r / 2 + Math.cos(t * L.sp * 6.28 * 0.8 + i * 2) * L.ay;
        els[i].style.transform = `translate(${x.toFixed(2)}px, ${y.toFixed(2)}px)`;
      });
      ctx.clearRect(0, 0, 1920, 1080);
      for (const p of P) {
        const y = ((p.y - t * p.v) % 1080 + 1080) % 1080;
        const x = p.x + Math.sin(t * 0.4 + p.ph) * 12 * p.z;
        const tw = 0.75 + 0.25 * Math.sin(t * 1.3 + p.ph * 3);
        ctx.beginPath(); ctx.arc(x, y, p.s, 0, 6.2832);
        ctx.fillStyle = `rgba(${p.c},${(p.a * tw).toFixed(3)})`; ctx.fill();
      }
    });
  }

  window.M = M;
  window.__seek = (t) => M.seek(t);
  /** Audio de todo el clip → { sampleRate, channels, frames, format:'s16le', b64 (Int16 intercalado), ... } o null.
      o: { duration (s, por defecto M.duration), only: [índices de cue], bed: false, normalize: false } */
  window.__renderAudio = async (o = {}) => {
    const A = M.audio.opts || {};
    if (!window.MAudio || (!M.audio.cues.length && !A.bed)) return null;
    const r = await window.MAudio.render(M.audio.cues, o.duration ?? M.duration, A, o);
    return window.MAudio.encode(r, A.seed ?? 1);
  };
})();
