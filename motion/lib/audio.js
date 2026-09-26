/* ==========================================================================
   audio.js — diseño sonoro procedural para las escenas (Web Audio, offline).
   Script clásico → window.MAudio. Lo usa stage.js (M.sfx / window.__renderAudio).

   Estética: motion graphics premium (documental científico / keynote), NO
   videojuego: nada de ondas cuadradas ni arpegios chiptune. Todo nace de ruido
   filtrado, resonadores, FM de índice bajo y una reverb de sala generada.
   Mezcla pensada para ir DEBAJO de una voz en off: la cama deja un "hueco" en
   2–4 kHz y los efectos tienen niveles calibrados (ver LEVEL).

   Determinista: 48 kHz estéreo, OfflineAudioContext, ruido con PRNG sembrado.
   Mismo cues + misma semilla → mismas muestras, bit a bit.

   Uso (desde una escena, con lib/audio.js cargado después de stage.js):
     M.scene({ duration: 8, audio: { key: 'D', mode: 'major', bed: { gain: 0 }, gain: 0 } }, (tl, M) => {
       M.sfx(0.3, 'whoosh', { dur: 0.9 });
       M.sfx(2.0, 'impact');
     });
   `gain` siempre en dB (recorte relativo al nivel calibrado del preset).
   ========================================================================== */
(function () {
  'use strict';
  const SR = 48000;
  const PAD = 0.1;           // colchón inicial (s): deja anticipar riser/swell y compensar latencia del compresor

  /* ------------------------------ utilidades ------------------------------ */
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  function hashStr(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619); return h >>> 0; }
  const dB = (x) => Math.pow(10, x / 20);
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  const smooth = (a, b, x) => { const u = clamp((x - a) / (b - a), 0, 1); return u * u * (3 - 2 * u); };
  const cents = (c) => Math.pow(2, c / 1200);
  const semis = (s) => Math.pow(2, s / 12);

  /* ------------------------------ tonalidad ------------------------------ */
  const PC = { C: 0, 'C#': 1, Db: 1, D: 2, 'D#': 3, Eb: 3, E: 4, F: 5, 'F#': 6, Gb: 6, G: 7, 'G#': 8, Ab: 8, A: 9, 'A#': 10, Bb: 10, B: 11 };
  const MODES = {
    major: [0, 2, 4, 5, 7, 9, 11], minor: [0, 2, 3, 5, 7, 8, 10], dorian: [0, 2, 3, 5, 7, 9, 10],
    lydian: [0, 2, 4, 6, 7, 9, 11], mixolydian: [0, 2, 4, 5, 7, 9, 10],
  };
  const mtof = (m) => 440 * Math.pow(2, (m - 69) / 12);
  function makeKey(key = 'D', mode = 'major') {
    let [k, m] = String(key).trim().split(/\s+/);
    m = m || mode;
    const root = PC[k.charAt(0).toUpperCase() + k.slice(1)];
    if (root === undefined) throw new Error('MAudio: tonalidad inválida ' + key);
    if (!MODES[m]) throw new Error('MAudio: modo inválido ' + m);
    return { root, scale: MODES[m], name: k + ' ' + m };
  }
  /** grado de la escala (0 = tónica, 7 = octava; admite negativos) en la octava `oct` → MIDI */
  function degMidi(K, deg, oct) {
    const o = Math.floor(deg / 7), d = ((deg % 7) + 7) % 7;
    return 12 * (oct + 1) + K.root + K.scale[d] + 12 * o;
  }
  /** 'A4' → Hz. */
  function noteHz(n) {
    const m = /^([A-Ga-g][#b]?)(-?\d)$/.exec(String(n));
    if (!m) throw new Error('MAudio: nota inválida ' + n);
    return mtof(12 * (+m[2] + 1) + PC[m[1].charAt(0).toUpperCase() + m[1].slice(1)]);
  }
  /** frecuencia de un preset tonal: note ('E5' o Hz) | deg + oct (en la tonalidad) · + pitch (semitonos) */
  function tone(p, K, deg, oct) {
    let f;
    if (p.note !== undefined) f = typeof p.note === 'number' ? p.note : noteHz(p.note);
    else f = mtof(degMidi(K, p.deg ?? deg, p.oct ?? oct));
    return f * semis(p.pitch || 0);
  }
  /** tónica llevada al rango [lo, hi) (para el sub del impacto) */
  function rootIn(K, lo, hi) { let f = mtof(12 + K.root); while (f < lo) f *= 2; while (f >= hi) f /= 2; return f; }

  /* ------------------------------ nodos ------------------------------ */
  const G = (ctx, v = 1) => { const g = ctx.createGain(); g.gain.value = v; return g; };
  function BQ(ctx, type, f, Q = 0.707, gain = 0) {
    const b = ctx.createBiquadFilter(); b.type = type; b.frequency.value = f; b.Q.value = Q; b.gain.value = gain; return b;
  }
  function osc(ctx, type, f) { const o = ctx.createOscillator(); if (typeof type === 'string') o.type = type; else o.setPeriodicWave(type); o.frequency.value = f; return o; }
  function src(ctx, buf) { const s = ctx.createBufferSource(); s.buffer = buf; return s; }
  /** curva 0..1 muestreada para setValueCurveAtTime */
  function curve(fn, n = 512, scale = 1) { const a = new Float32Array(n); for (let i = 0; i < n; i++) a[i] = fn(i / (n - 1)) * scale; return a; }
  /** ruido sembrado: 'white' | 'pink' (Kellet) | 'brown' */
  function noiseBuf(ctx, dur, R, color = 'pink', ch = 1) {
    const n = Math.max(2, Math.ceil(dur * SR));
    const b = ctx.createBuffer(ch, n, SR);
    for (let c = 0; c < ch; c++) {
      const d = b.getChannelData(c);
      let b0 = 0, b1 = 0, b2 = 0, b3 = 0, b4 = 0, b5 = 0, b6 = 0, br = 0;
      for (let i = 0; i < n; i++) {
        const w = R() * 2 - 1;
        if (color === 'white') d[i] = w;
        else if (color === 'brown') { br = (br + 0.02 * w) / 1.02; d[i] = br * 3.5; }
        else {
          b0 = 0.99886 * b0 + w * 0.0555179; b1 = 0.99332 * b1 + w * 0.0750759; b2 = 0.969 * b2 + w * 0.153852;
          b3 = 0.8665 * b3 + w * 0.3104856; b4 = 0.55 * b4 + w * 0.5329522; b5 = -0.7616 * b5 - w * 0.016898;
          d[i] = (b0 + b1 + b2 + b3 + b4 + b5 + b6 + w * 0.5362) * 0.11; b6 = w * 0.115926;
        }
      }
    }
    return b;
  }
  /** voz FM (portadora + moduladora senoidales). index = desviación / frec. moduladora */
  function fm(ctx, t0, t1, f, { ratio = 1, index = 1, indexEnd = 0.05, tau = 0.1, detune = 0 } = {}) {
    const fc = f * cents(detune);
    const car = osc(ctx, 'sine', fc), mod = osc(ctx, 'sine', fc * ratio), dev = G(ctx, 0);
    dev.gain.setValueAtTime(index * fc * ratio, t0);
    dev.gain.setTargetAtTime(indexEnd * fc * ratio, t0, tau);
    mod.connect(dev); dev.connect(car.frequency);
    car.start(t0); mod.start(t0); car.stop(t1); mod.stop(t1);
    return car;
  }
  /** salida de un preset: nivel → paneo → bus (+ envío a reverb) */
  function out(ctx, g, node, { pan = 0, verb = 0, bus = 'sfx', level = 1 } = {}) {
    const v = G(ctx, level); node.connect(v);
    const p = ctx.createStereoPanner(); p.pan.value = clamp(pan, -1, 1); v.connect(p);
    p.connect(g[bus]);
    if (verb > 0) { const s = G(ctx, verb); p.connect(s); s.connect(g.send); }
    return p;
  }
  function tanhCurve(k) { const n = 2048, c = new Float32Array(n), nk = Math.tanh(k); for (let i = 0; i < n; i++) { const x = (i / (n - 1)) * 2 - 1; c[i] = Math.tanh(k * x) / nk; } return c; }

  /* ------------------------------ reverb: IR generada ------------------------------
     Sala mediana cálida: pre-delay, reflexiones tempranas discretas y cola difusa de ruido
     decorrelado L/R con decaimiento exponencial y paso-bajo que se cierra con el tiempo
     (los agudos mueren antes, como en una sala real). Energía normalizada a 1. */
  function makeIR(ctx, { decay = 2.4, predelay = 0.018, damp = 1 } = {}, seed = 1) {
    const len = Math.ceil((decay * 1.15 + predelay) * SR);
    const buf = ctx.createBuffer(2, len, SR);
    const pre = Math.round(predelay * SR);
    for (let c = 0; c < 2; c++) {
      const R = mulberry32(seed * 7919 + c * 104729 + 17);
      const d = buf.getChannelData(c);
      let lp = 0;
      for (let i = pre; i < len; i++) {
        const t = (i - pre) / SR;
        const env = Math.exp(-6.9078 * t / decay) * smooth(0, 0.012, t);
        const fc = 1400 + 9000 * Math.exp(-t / (0.35 * decay)) / damp;       // Hz, se oscurece con el tiempo
        const a = 1 - Math.exp(-2 * Math.PI * fc / SR);
        lp += a * ((R() * 2 - 1) - lp);
        d[i] = lp * env;
      }
      // reflexiones tempranas (distintas por canal → imagen ancha)
      for (let k = 0; k < 9; k++) {
        const at = pre + Math.round((0.004 + R() * 0.06) * SR);
        const amp = (0.55 - k * 0.04) * (R() < 0.5 ? -1 : 1);
        for (let j = 0; j < 24 && at + j < len; j++) d[at + j] += amp * Math.exp(-j / 5) * 0.35;
      }
    }
    let e = 0; for (let c = 0; c < 2; c++) { const d = buf.getChannelData(c); for (let i = 0; i < len; i++) e += d[i] * d[i]; }
    const k = 1 / Math.sqrt(e / 2);
    for (let c = 0; c < 2; c++) { const d = buf.getChannelData(c); for (let i = 0; i < len; i++) d[i] *= k; }
    return buf;
  }

  /* ------------------------------ grafo global ------------------------------ */
  const COMP = { threshold: -24, knee: 12, ratio: 2, attack: 0.02, release: 0.3 };
  function master(ctx, dest) {
    const hp = BQ(ctx, 'highpass', 28, 0.707);
    const comp = ctx.createDynamicsCompressor();
    for (const k in COMP) comp[k].value = COMP[k];
    hp.connect(comp); comp.connect(dest);
    return hp;
  }
  function graph(ctx, A, seed) {
    const mix = G(ctx, dB(A.gain || 0));
    mix.connect(master(ctx, ctx.destination));
    // reverb
    const send = G(ctx, 1);
    const conv = ctx.createConvolver(); conv.normalize = false; conv.buffer = makeIR(ctx, A.reverb || {}, seed);
    const rhp = BQ(ctx, 'highpass', 220, 0.6), rhs = BQ(ctx, 'highshelf', 6500, 0.707, -5);
    const ret = G(ctx, dB(A.reverb?.gain ?? -4));
    send.connect(conv); conv.connect(rhp); rhp.connect(rhs); rhs.connect(ret); ret.connect(mix);
    // efectos
    const sfx = G(ctx, 1), sfxHp = BQ(ctx, 'highpass', 32, 0.707);
    sfx.connect(sfxHp); sfxHp.connect(mix);
    // cama: hueco para la voz (2,8 kHz) y sin retumbe
    const bed = G(ctx, 1), bedHp = BQ(ctx, 'highpass', 45, 0.707), pocket = BQ(ctx, 'peaking', 2800, 0.8, A.pocket ?? -4);
    bed.connect(bedHp); bedHp.connect(pocket); pocket.connect(mix);
    return { mix, send, sfx, bed };
  }

  /* ------------------------------ presets ------------------------------
     LEVEL = nivel calibrado de cada preset (dB). Medido aislado (sin cama), queda en
     loudness momentáneo aprox.: cama −30 LUFS · tick −31 · tap −27 · scan/grow −28 ·
     whoosh/shimmer −25 · swell/riser −23 · impact −21. `gain` de cada cue suma a esto. */
  const LEVEL = { bed: -21, tick: -14, tap: -17, impact: -9, whoosh: -12, shimmer: -17, scan: -12, grow: -3, riser: -14, swell: -17 };

  // Cómo se interpreta `at` en cada preset (anchor por defecto): 'start' | 'end' | 'peak' (solo whoosh)
  const ANCHOR = { riser: 'end', swell: 'end' };
  // Duración por defecto (s). En tap/shimmer/impact es el largo de la cola.
  const DUR = { tick: 0.05, tap: 0.9, impact: 1.8, whoosh: 0.8, shimmer: 2.4, scan: 1.2, grow: 1.5, riser: 1.5, swell: 1.6 };

  const P = {};

  /** Tick: tecla/papel muy discreto para textos. Resonador de madera excitado por un pulso de ruido. */
  P.tick = (ctx, g, t, p, R, K, J) => {
    const tr = semis((p.pitch || 0) + J(0.7));
    const glass = p.tone === 'glass';
    const n = Math.round(0.014 * SR), buf = ctx.createBuffer(1, n, SR), d = buf.getChannelData(0);
    for (let i = 0; i < n; i++) d[i] = (R() * 2 - 1) * Math.exp(-i / (0.0009 * SR));
    const s = src(ctx, buf);
    const click = BQ(ctx, 'bandpass', 3600 * tr, 0.9), body = BQ(ctx, 'bandpass', (glass ? 2700 : 1350) * tr, glass ? 40 : 18);
    const cg = G(ctx, 0.35), bg = G(ctx, glass ? 5 : 3.2), mix = G(ctx, dB(LEVEL.tick + (p.gain || 0) + J(1.2)));
    s.connect(click); click.connect(cg); cg.connect(mix);
    s.connect(body); body.connect(bg); bg.connect(mix);
    const lp = BQ(ctx, 'lowpass', 7000, 0.707); mix.connect(lp);
    out(ctx, g, lp, { pan: (p.pan || 0) + J(0.12), verb: p.verb ?? 0.07 });
    s.start(t);
  };

  /** Tap: nota corta de marimba suave (FM relación 1 con índice que cae + parcial 4:1 + mazo). */
  P.tap = (ctx, g, t, p, R, K, J, span) => {
    const f = tone(p, K, 0, 5) * cents(J(3));
    const dur = span.d, bright = p.bright ?? 1, t1 = t + dur * 1.9;
    const mix = G(ctx, dB(LEVEL.tap + (p.gain || 0) + J(0.8)));
    const amp = G(ctx, 0);
    amp.gain.setValueAtTime(0, t); amp.gain.linearRampToValueAtTime(1, t + 0.004); amp.gain.setTargetAtTime(0, t + 0.004, dur / 5);
    fm(ctx, t, t1, f, { ratio: 1, index: 1.1 * bright, indexEnd: 0.06, tau: 0.06 }).connect(amp); amp.connect(mix);
    const o4 = osc(ctx, 'sine', f * 3.99), a4 = G(ctx, 0);
    a4.gain.setValueAtTime(0, t); a4.gain.linearRampToValueAtTime(0.2 * bright, t + 0.003); a4.gain.setTargetAtTime(0, t + 0.003, 0.035);
    o4.connect(a4); a4.connect(mix); o4.start(t); o4.stop(t + 0.4);
    const ns = src(ctx, noiseBuf(ctx, 0.03, R, 'white')), nbp = BQ(ctx, 'bandpass', Math.min(9000, f * 2), 1.5), na = G(ctx, 0);
    na.gain.setValueAtTime(0.12, t); na.gain.setTargetAtTime(0, t, 0.005);
    ns.connect(nbp); nbp.connect(na); na.connect(mix); ns.start(t);
    const lp = BQ(ctx, 'lowpass', 5200, 0.707); mix.connect(lp);
    out(ctx, g, lp, { pan: (p.pan || 0) + J(0.1), verb: p.verb ?? 0.22 });
  };

  /** Impact: golpe grave suave (sub con caída de tono + saturación leve para parlantes chicos),
      "thump" de aire, transitorio medio y una floración tonal que alimenta la reverb. */
  P.impact = (ctx, g, t, p, R, K, J, span) => {
    const f0 = (p.note !== undefined ? tone(p, K, 0, 1) : rootIn(K, 40, 80) * semis(p.pitch || 0));
    const tail = span.d, w = p.weight ?? 1, t1 = t + tail + 0.5;
    const lvl = dB(LEVEL.impact + (p.gain || 0));
    // sub
    const o = osc(ctx, 'sine', f0 * 1.9);
    o.frequency.setValueAtTime(f0 * 1.9, t); o.frequency.exponentialRampToValueAtTime(f0, t + 0.14);
    const a = G(ctx, 0);
    a.gain.setValueAtTime(0, t); a.gain.linearRampToValueAtTime(1, t + 0.008); a.gain.setTargetAtTime(0, t + 0.03, 0.3 * tail / 1.8);
    const sh = ctx.createWaveShaper(); sh.curve = tanhCurve(1.6); sh.oversample = '4x';
    const subG = G(ctx, 0.85 * w * lvl);
    o.connect(a); a.connect(sh); sh.connect(subG); o.start(t); o.stop(t1);
    out(ctx, g, subG, { pan: 0, verb: 0 });
    // thump de aire
    const th = src(ctx, noiseBuf(ctx, 0.5, R, 'brown')), thLp = BQ(ctx, 'lowpass', 190, 0.8), thA = G(ctx, 0);
    thA.gain.setValueAtTime(0, t); thA.gain.linearRampToValueAtTime(0.9 * lvl, t + 0.004); thA.gain.setTargetAtTime(0, t + 0.004, 0.07);
    th.connect(thLp); thLp.connect(thA); th.start(t);
    out(ctx, g, thA, { pan: 0, verb: 0.08 });
    // transitorio medio (definición) + floración tonal
    const md = src(ctx, noiseBuf(ctx, 0.15, R, 'pink')), mdBp = BQ(ctx, 'bandpass', 650, 0.8), mdA = G(ctx, 0);
    mdA.gain.setValueAtTime(0, t); mdA.gain.linearRampToValueAtTime(0.35 * lvl, t + 0.002); mdA.gain.setTargetAtTime(0, t + 0.002, 0.02);
    md.connect(mdBp); mdBp.connect(mdA); md.start(t);
    const fb = rootIn(K, 110, 220) * semis(p.pitch || 0);
    const bl = G(ctx, 0);
    bl.gain.setValueAtTime(0, t); bl.gain.linearRampToValueAtTime(0.16 * lvl * (p.bloom ?? 1), t + 0.012); bl.gain.setTargetAtTime(0, t + 0.012, tail / 3.2);
    fm(ctx, t, t1, fb, { ratio: 1, index: 0.5, indexEnd: 0.02, tau: 0.15 }).connect(bl);
    fm(ctx, t, t1, fb * 1.5, { ratio: 1, index: 0.3, indexEnd: 0.02, tau: 0.15, detune: 3 }).connect(bl);
    const bLp = BQ(ctx, 'lowpass', 1800, 0.707); mdA.connect(bLp); bl.connect(bLp);
    out(ctx, g, bLp, { pan: p.pan || 0, verb: p.verb ?? 0.45 });
  };

  /** Whoosh: ruido rosa por un pasa-banda que abre y cierra + cuerpo grave; cruza el estéreo.
      `at` = inicio del movimiento; `peak` = fracción de dur donde el movimiento es más rápido. */
  P.whoosh = (ctx, g, t, p, R, K, J, span) => {
    const d = span.d, pk = clamp(p.peak ?? 0.45, 0.1, 0.9), br = (p.bright ?? 1) * semis(p.pitch || 0);
    const dir = p.dir ?? 1, wd = p.width ?? 0.55;
    const shape = (u) => u < pk ? Math.pow(Math.sin(0.5 * Math.PI * u / pk), 2)
      : Math.pow(Math.cos(0.5 * Math.PI * (u - pk) / (1 - pk)), 2) * Math.exp(-1.2 * (u - pk) / (1 - pk));
    const lvl = dB(LEVEL.whoosh + (p.gain || 0) + J(0.8));
    const layer = (fLo, fHi, q, level, panOff) => {
      const s = src(ctx, noiseBuf(ctx, d + 0.05, R, 'pink'));
      const bp = BQ(ctx, 'bandpass', fLo * br, q);
      bp.frequency.setValueAtTime(fLo * br, t);
      bp.frequency.exponentialRampToValueAtTime(fHi * br, t + d * pk);
      bp.frequency.exponentialRampToValueAtTime(fLo * 1.8 * br, t + d);
      const env = G(ctx, 0); env.gain.setValueCurveAtTime(curve(shape, 512, level * lvl), t, d);
      s.connect(bp); bp.connect(env); s.start(t); s.stop(t + d + 0.02);
      const pn = out(ctx, g, env, { pan: 0, verb: p.verb ?? 0.14 });
      pn.pan.setValueAtTime(clamp((p.pan || 0) - dir * wd + panOff, -1, 1), t);
      pn.pan.linearRampToValueAtTime(clamp((p.pan || 0) + dir * wd + panOff, -1, 1), t + d);
      return s;
    };
    layer(240, 2300, 1.1, 1, -0.08);
    layer(330, 3100, 1.6, 0.55, 0.08);
    // cuerpo (desplazamiento de aire)
    const s = src(ctx, noiseBuf(ctx, d + 0.05, R, 'pink')), lp = BQ(ctx, 'lowpass', 380, 0.7), env = G(ctx, 0);
    env.gain.setValueCurveAtTime(curve(shape, 512, 0.5 * lvl), t, d);
    s.connect(lp); lp.connect(env); s.start(t); s.stop(t + d + 0.02);
    out(ctx, g, env, { pan: p.pan || 0, verb: 0.05 });
  };

  /** Shimmer: brillo tonal para datos. Campanitas FM suaves (relación 3,5, índice bajo) en acorde
      de la tonalidad, arpegiadas apenas, con gemelo desafinado + chispa de aire en la reverb. */
  P.shimmer = (ctx, g, t, p, R, K, J, span) => {
    const degs = p.degs ?? [4, 7, 9], oct = p.oct ?? 5, d = span.d, spread = p.spread ?? 0.05;
    const lvl = dB(LEVEL.shimmer + (p.gain || 0));
    const bus = G(ctx, lvl), lp = BQ(ctx, 'lowpass', 9000, 0.707); bus.connect(lp);
    out(ctx, g, lp, { pan: p.pan || 0, verb: p.verb ?? 0.42 });
    degs.forEach((dg, i) => {
      const f = mtof(degMidi(K, dg, oct)) * semis(p.pitch || 0) * cents(J(4));
      const t0 = t + i * spread + Math.abs(J(0.006)), t1 = t0 + d * 1.6;
      const side = (i % 2 ? 1 : -1) * (0.15 + 0.2 * (i / Math.max(1, degs.length - 1)));
      [[0, 1, side], [6, 0.45, -side]].forEach(([det, lv, pan]) => {
        const a = G(ctx, 0);
        a.gain.setValueAtTime(0, t0); a.gain.linearRampToValueAtTime(lv / Math.pow(i + 1, 0.35), t0 + 0.003); a.gain.setTargetAtTime(0, t0 + 0.003, d / 4.5);
        fm(ctx, t0, t1, f, { ratio: 3.5, index: 0.65, indexEnd: 0.04, tau: 0.25, detune: det }).connect(a);
        const pn = ctx.createStereoPanner(); pn.pan.value = pan; a.connect(pn); pn.connect(bus);
      });
    });
    const sp = src(ctx, noiseBuf(ctx, 0.6, R, 'white')), hp = BQ(ctx, 'highpass', 7500, 0.707), sa = G(ctx, 0);
    sa.gain.setValueAtTime(0, t); sa.gain.linearRampToValueAtTime(0.05, t + 0.02); sa.gain.setTargetAtTime(0, t + 0.02, 0.12);
    sp.connect(hp); hp.connect(sa); sa.connect(bus); sp.start(t);
  };

  /** Scan: barrido delicado. Ruido por pasa-banda estrecho que sube (from→to) mientras cruza
      el estéreo como la línea de escaneo, con una sombra tonal casi inaudible. */
  P.scan = (ctx, g, t, p, R, K, J, span) => {
    const d = span.d, tr = semis(p.pitch || 0), from = (p.from ?? 500) * tr, to = (p.to ?? 5000) * tr;
    const dir = p.dir ?? 1, wd = p.width ?? 0.6;
    const lvl = dB(LEVEL.scan + (p.gain || 0));
    const shape = (u) => smooth(0, 0.14, u) * (1 - 0.2 * u) * (1 - smooth(0.8, 1, u));
    const env = G(ctx, 0); env.gain.setValueCurveAtTime(curve(shape, 512, lvl), t, d);
    const s = src(ctx, noiseBuf(ctx, d + 0.05, R, 'pink')), bp = BQ(ctx, 'bandpass', from, p.q ?? 5);
    bp.frequency.setValueAtTime(from, t); bp.frequency.exponentialRampToValueAtTime(to, t + d);
    s.connect(bp); bp.connect(env); s.start(t); s.stop(t + d + 0.02);
    const o = osc(ctx, 'sine', from / 2), og = G(ctx, p.tone ?? 0.05);
    o.frequency.setValueAtTime(from / 2, t); o.frequency.exponentialRampToValueAtTime(to / 2, t + d);
    o.connect(og); og.connect(env); o.start(t); o.stop(t + d + 0.02);
    const pn = out(ctx, g, env, { pan: 0, verb: p.verb ?? 0.2 });
    pn.pan.setValueAtTime(clamp((p.pan || 0) - dir * wd, -1, 1), t);
    pn.pan.linearRampToValueAtTime(clamp((p.pan || 0) + dir * wd, -1, 1), t + d);
  };

  /** Grow: crepitar orgánico fino (granular). Proceso de Poisson de micro-resonancias amortiguadas
      (1,5–6 kHz, 0,5–2,5 ms), a veces en racimos, repartidas en estéreo, + un roce de fondo. */
  P.grow = (ctx, g, t, p, R, K, J, span) => {
    const d = span.d, dens = p.density ?? 110, sp = p.spread ?? 0.7, br = (p.bright ?? 1) * semis(p.pitch || 0);
    const env = (u) => smooth(0, 0.18, u) * (1 - smooth(0.72, 1, u)) * (0.7 + 0.3 * u);
    const n = Math.ceil((d + 0.05) * SR), buf = ctx.createBuffer(2, n, SR), L = buf.getChannelData(0), Rt = buf.getChannelData(1);
    const grain = (tt, e) => {
      const f = Math.exp(Math.log(1500) + R() * (Math.log(6000) - Math.log(1500))) * br;
      const tau = (0.0005 + R() * 0.002) * Math.sqrt(2500 / f);
      const a = 0.25 * Math.pow(10, -R() * 1.3) * (0.6 + 0.4 * e) * (R() < 0.5 ? -1 : 1);
      const pan = clamp((p.pan || 0) + (R() * 2 - 1) * sp, -1, 1), gl = Math.cos((pan + 1) * Math.PI / 4), gr = Math.sin((pan + 1) * Math.PI / 4);
      const i0 = Math.round(tt * SR), len = Math.min(Math.ceil(tau * 7 * SR), n - i0), w = 2 * Math.PI * f / SR, k = 1 / (tau * SR);
      for (let i = 0; i < len; i++) { const v = a * Math.exp(-i * k) * Math.sin(w * i) * (i < 6 ? i / 6 : 1); L[i0 + i] += v * gl; Rt[i0 + i] += v * gr; }
    };
    let tt = 0;
    for (;;) {
      tt += -Math.log(1 - R() * 0.9999) / dens;              // Poisson con adelgazamiento (thinning)
      if (tt >= d) break;
      const e = env(tt / d);
      if (R() > e) continue;
      grain(tt, e);
      if (R() < 0.18) { const m = 1 + Math.floor(R() * 3); for (let j = 0; j < m; j++) { const t2 = tt + 0.002 + R() * 0.007; if (t2 < d) grain(t2, e); } }
    }
    const s = src(ctx, buf), hp = BQ(ctx, 'highpass', 350, 0.707), lp = BQ(ctx, 'lowpass', 9500 * Math.min(1.2, br), 0.707);
    const lvl = dB(LEVEL.grow + (p.gain || 0)), mix = G(ctx, lvl);
    s.connect(hp); hp.connect(lp); lp.connect(mix); s.start(t);
    // roce de fondo (fibras): ruido rosa por banda ancha, casi inaudible
    const rs = src(ctx, noiseBuf(ctx, d + 0.05, R, 'pink')), rbp = BQ(ctx, 'bandpass', 2200 * br, 0.7), ra = G(ctx, 0);
    ra.gain.setValueCurveAtTime(curve(env, 256, 0.05 * (p.body ?? 1)), t, d);
    rs.connect(rbp); rbp.connect(ra); ra.connect(mix); rs.start(t); rs.stop(t + d + 0.02);
    out(ctx, g, mix, { pan: 0, verb: p.verb ?? 0.12 });
  };

  /** Riser: tensión hacia un momento. Ruido que abre + par de senos desafinados que suben `semis`.
      `at` = el clímax (termina ahí; empieza dur antes). Corte rápido al final para que pegue con el golpe. */
  P.riser = (ctx, g, t, p, R, K, J, span) => {
    const { t0, t1, d } = span;
    const up = semis(p.semis ?? 12), br = (p.bright ?? 1) * semis(p.pitch || 0);
    const lvl = dB(LEVEL.riser + (p.gain || 0));
    const bus = G(ctx, 0);
    bus.gain.setValueCurveAtTime(curve((u) => Math.pow(u, 2.4), 512, lvl), t0, d);
    bus.gain.setTargetAtTime(0, t1, 0.03);
    [-0.45, 0.45].forEach((pan) => {
      const s = src(ctx, noiseBuf(ctx, d + 0.3, R, 'pink')), lp = BQ(ctx, 'lowpass', 250 * br, 1.4);
      lp.frequency.setValueAtTime(250 * br, t0); lp.frequency.exponentialRampToValueAtTime(6500 * br, t1);
      const pn = ctx.createStereoPanner(); pn.pan.value = pan;
      s.connect(lp); lp.connect(pn); pn.connect(bus); s.start(t0); s.stop(t1 + 0.3);
    });
    const tg = G(ctx, 0); tg.gain.setValueCurveAtTime(curve((u) => Math.pow(u, 1.6), 256, 0.22), t0, d);
    const tlp = BQ(ctx, 'lowpass', 1800, 0.707); tg.connect(tlp); tlp.connect(bus);
    [0, 4].forEach((dg) => [-7, 7].forEach((det) => {
      const f = mtof(degMidi(K, dg, p.oct ?? 3)) * semis(p.pitch || 0) * cents(det);
      const o = osc(ctx, 'sine', f); o.frequency.setValueAtTime(f, t0); o.frequency.exponentialRampToValueAtTime(f * up, t1);
      o.connect(tg); o.start(t0); o.stop(t1 + 0.3);
    }));
    out(ctx, g, bus, { pan: p.pan || 0, verb: p.verb ?? 0.3 });
  };

  /** Swell: crescendo tonal "en reversa" (acorde de la tonalidad) que desemboca en `at`. */
  P.swell = (ctx, g, t, p, R, K, J, span) => {
    const { t0, t1, d } = span;
    const degs = p.degs ?? [0, 4, 7, 9], oct = p.oct ?? 3, k = 3.5;
    const lvl = dB(LEVEL.swell + (p.gain || 0));
    const bus = G(ctx, 0);
    bus.gain.setValueCurveAtTime(curve((u) => (Math.exp(k * u) - 1) / (Math.exp(k) - 1), 512, lvl), t0, d);
    bus.gain.setTargetAtTime(0, t1, p.release ?? 0.06);
    const lp = BQ(ctx, 'lowpass', 350, 0.6);
    lp.frequency.setValueAtTime(350, t0); lp.frequency.exponentialRampToValueAtTime(2800 * (p.bright ?? 1), t1);
    lp.connect(bus);
    const pans = [-0.4, 0.4, -0.2, 0.2, 0];
    degs.forEach((dg, i) => {
      const f = mtof(degMidi(K, dg, oct)) * semis(p.pitch || 0);
      [[0, 1], [5, 0.6]].forEach(([det, lv]) => {
        const c = fm(ctx, t0, t1 + 0.4, f, { ratio: 1, index: 0.25, indexEnd: 0.9, tau: d / 2, detune: det });
        const a = G(ctx, lv / degs.length), pn = ctx.createStereoPanner(); pn.pan.value = pans[i % pans.length] * (det ? -1 : 1);
        c.connect(a); a.connect(pn); pn.connect(lp);
      });
    });
    out(ctx, g, bus, { pan: p.pan || 0, verb: p.verb ?? 0.5 });
  };

  /** Bed: cama ambiental cálida y evolutiva. Pedal de tónica + voces que alternan entre dos
      voicings con conducción por grado conjunto (notas comunes sostenidas, sin cancelaciones),
      onda de pad suave (armónicos 1/n^1.6), pares desafinados ±4 cents, respiración lenta por voz,
      filtro que deriva, sub opcional y "aire" estéreo (tono de sala). Va al bus con hueco para la voz. */
  let padWave = null;
  P.bed = (ctx, g, t, p, R, K, J, span) => {
    const d = span.d, fin = p.fadeIn ?? 1.5, fout = p.fadeOut ?? 2.0;
    const cycle = p.cycle ?? 8, oct = p.oct ?? 3, xf = Math.min(2.5, cycle * 0.45);
    const V = p.voicings ?? [[0, 4, 8, 9], [0, 5, 8, 10]];
    if (!padWave) {
      const N = 12, re = new Float32Array(N), im = new Float32Array(N);
      for (let h = 1; h < N; h++) im[h] = 1 / Math.pow(h, 1.6) * (h % 2 ? 1 : 0.7);
      padWave = ctx.createPeriodicWave(re, im);
    }
    const lvl = dB(LEVEL.bed + (p.gain || 0));
    // envolvente general con fundidos sin²
    const env = G(ctx, 0);
    const fi = Math.min(fin, d * 0.45), fo = Math.min(fout, d * 0.45);
    env.gain.setValueCurveAtTime(curve((u) => Math.pow(Math.sin(0.5 * Math.PI * u), 2), 256, lvl), t, fi);
    env.gain.setValueCurveAtTime(curve((u) => Math.pow(Math.cos(0.5 * Math.PI * u), 2), 256, lvl), t + d - fo, fo);
    out(ctx, g, env, { pan: 0, verb: p.verb ?? 0.32, bus: 'bed' });
    // filtro que deriva
    const lp = BQ(ctx, 'lowpass', 1100 * (p.bright ?? 1), 0.6);
    const flfo = osc(ctx, 'sine', 0.055), flg = G(ctx, 320 * (p.bright ?? 1));
    flfo.connect(flg); flg.connect(lp.frequency); flfo.start(t); flfo.stop(t + d);
    lp.connect(env);
    // corridas por nota (una nota común entre voicings sigue sonando: no se cruza consigo misma)
    const runs = [], active = new Map();
    const nSeg = Math.max(1, Math.ceil((d - xf) / cycle));           // no arrancar un acorde en los últimos segundos
    for (let k = 0; k < nSeg; k++) {
      const s0 = k * cycle, notes = V[k % V.length].map((dg) => degMidi(K, dg, oct));
      for (const [m, r] of active) if (!notes.includes(m)) { r.b = s0; runs.push(r); active.delete(m); }
      notes.forEach((m, i) => { if (!active.has(m)) active.set(m, { m, a: s0, i }); });
    }
    for (const [, r] of active) { r.b = d; runs.push(r); }
    runs.forEach((r, n) => {
      const f = mtof(r.m) * semis(p.pitch || 0);
      const a0 = t + (r.a === 0 ? 0 : r.a - xf / 2), b0 = t + (r.b >= d ? d : r.b + xf / 2);
      const up = r.a === 0 ? 0.01 : xf, down = r.b >= d ? 0.01 : xf;
      const vg = G(ctx, 0), lvV = 0.5 / Math.pow(1 + r.i, 0.25);
      vg.gain.setValueAtTime(0, a0); vg.gain.linearRampToValueAtTime(lvV, a0 + up);
      vg.gain.setValueAtTime(lvV, b0 - down); vg.gain.linearRampToValueAtTime(0, b0);
      const br = G(ctx, 1), lfo = osc(ctx, 'sine', 0.045 + 0.05 * R()), lg = G(ctx, 0.28);
      lfo.connect(lg); lg.connect(br.gain); lfo.start(t); lfo.stop(b0 + 0.05);
      const pn = ctx.createStereoPanner(); pn.pan.value = [-0.35, 0.3, -0.15, 0.4, 0][r.i % 5];
      [-4, 4].forEach((c) => { const o = osc(ctx, padWave, f * cents(c + J(1))); o.connect(vg); o.start(a0); o.stop(b0 + 0.02); });
      vg.connect(br); br.connect(pn); pn.connect(lp);
    });
    // pedal sub
    if ((p.sub ?? 0.35) > 0) {
      const o = osc(ctx, 'sine', mtof(degMidi(K, 0, oct - 1)) * semis(p.pitch || 0)), sg = G(ctx, p.sub ?? 0.35);
      o.connect(sg); sg.connect(env); o.start(t); o.stop(t + d);
    }
    // aire: dos ruidos rosa decorrelados, banda alta ancha, respiración lenta
    if ((p.air ?? 1) > 0) {
      [-0.7, 0.7].forEach((pan, i) => {
        const s = src(ctx, noiseBuf(ctx, d, R, 'pink')), bp = BQ(ctx, 'bandpass', 4200, 0.45), ag = G(ctx, 0.05 * (p.air ?? 1));
        const lfo = osc(ctx, 'sine', 0.07 + 0.03 * i), lg = G(ctx, 0.015 * (p.air ?? 1));
        lfo.connect(lg); lg.connect(ag.gain); lfo.start(t); lfo.stop(t + d);
        const pn = ctx.createStereoPanner(); pn.pan.value = pan;
        s.connect(bp); bp.connect(ag); ag.connect(pn); pn.connect(env); s.start(t); s.stop(t + d);
      });
    }
  };

  /* ------------------------------ render ------------------------------ */
  let latency = null;
  /** Latencia del compresor (pre-delay de lookahead) medida con un impulso, para compensarla. */
  async function measureLatency() {
    if (latency !== null) return latency;
    const n = 4800, ctx = new OfflineAudioContext(1, n, SR);
    const b = ctx.createBuffer(1, n, SR); b.getChannelData(0)[100] = 0.01;
    const s = src(ctx, b); s.connect(master(ctx, ctx.destination)); s.start(0);
    const r = (await ctx.startRendering()).getChannelData(0);
    let best = 0, bi = 100; for (let i = 0; i < n; i++) if (Math.abs(r[i]) > best) { best = Math.abs(r[i]); bi = i; }
    latency = Math.max(0, bi - 100);
    return latency;
  }

  /**
   * Renderiza el clip completo.
   * cues: [{ at, type, ...params }] · duration (s) · audio: { key, mode, gain, bed, reverb, pocket, seed }
   * opts: { only: [índices de cue], bed: false, normalize: true }
   * → { sampleRate, channels, frames, latency, gainDb, peakDb, left, right } (Float32Array)
   */
  async function render(cues, duration, audio = {}, opts = {}) {
    const lat = await measureLatency();
    const frames = Math.round(duration * SR);
    const total = frames + Math.round(PAD * SR) + lat + 64;
    const ctx = new OfflineAudioContext(2, total, SR);
    padWave = null;
    const seed = audio.seed ?? 1;
    const K = makeKey(audio.key || 'D', audio.mode || 'major');
    const g = graph(ctx, audio, seed);
    const list = cues.map((c, i) => ({ ...c, _i: i })).filter((c) => !opts.only || opts.only.includes(c._i));
    if (audio.bed && opts.bed !== false) list.unshift({ at: 0, type: 'bed', ...audio.bed, _i: -1 });
    for (const c of list) {
      const fn = P[c.type];
      if (!fn) throw new Error('MAudio: preset desconocido ' + c.type);
      const R = mulberry32(hashStr(c.type) ^ Math.imul(seed, 2654435761) ^ Math.imul(c._i + 7, 40503) ^ Math.round(c.at * 1000));
      const J = (amt) => (R() * 2 - 1) * amt * (c.vary ?? 1);          // variación humana (tono, nivel, paneo)
      const anchor = c.anchor || ANCHOR[c.type] || 'start';
      let d = c.dur ?? (c.type === 'bed' ? duration - c.at : DUR[c.type]);
      let t0 = anchor === 'end' ? c.at - d : anchor === 'peak' && c.type === 'whoosh' ? c.at - d * clamp(c.peak ?? 0.45, 0.1, 0.9) : c.at;
      if (t0 < -PAD + 0.002) { d -= (-PAD + 0.002) - t0; t0 = -PAD + 0.002; }
      const s0 = t0 + PAD, span = { t0: s0, t1: s0 + d, d };
      fn(ctx, g, span.t0, c, R, K, J, span);
    }
    const buf = await ctx.startRendering();
    const off = Math.round(PAD * SR) + lat;
    const left = buf.getChannelData(0).slice(off, off + frames), right = buf.getChannelData(1).slice(off, off + frames);
    // fundidos de seguridad (5 ms al inicio, 30 ms al final) para que no haya clics en los bordes
    const fa = Math.round(0.005 * SR), fb = Math.round(0.03 * SR);
    for (let i = 0; i < fa && i < frames; i++) { const k = i / fa; left[i] *= k; right[i] *= k; }
    for (let i = 0; i < fb && i < frames; i++) { const k = i / fb, j = frames - 1 - i; left[j] *= k; right[j] *= k; }
    let peak = 0; for (let i = 0; i < frames; i++) peak = Math.max(peak, Math.abs(left[i]), Math.abs(right[i]));
    let gainDb = 0;
    if (opts.normalize !== false && peak > 0) {
      gainDb = -1 - 20 * Math.log10(peak);                            // pico a −1 dBFS (resolución máxima en 16 bits)
      const k = dB(gainDb); for (let i = 0; i < frames; i++) { left[i] *= k; right[i] *= k; }
    }
    return { sampleRate: SR, channels: 2, frames, latency: lat, gainDb, peakDb: peak > 0 ? 20 * Math.log10(peak) : -Infinity, left, right };
  }

  /** Int16 intercalado con dither TPDF sembrado → base64 (vía Blob/FileReader: rápido para clips largos) */
  async function encode(r, seed = 1) {
    const R = mulberry32(seed * 31 + 5), n = r.frames, pcm = new Int16Array(n * 2);
    for (let i = 0; i < n; i++) {
      for (let c = 0; c < 2; c++) {
        const x = (c ? r.right : r.left)[i] * 32767 + (R() - R());
        pcm[2 * i + c] = x > 32767 ? 32767 : x < -32768 ? -32768 : Math.round(x);
      }
    }
    const b64 = await new Promise((res, rej) => {
      const fr = new FileReader();
      fr.onload = () => res(String(fr.result).split(',')[1] || '');
      fr.onerror = rej;
      fr.readAsDataURL(new Blob([pcm.buffer], { type: 'application/octet-stream' }));
    });
    return { sampleRate: r.sampleRate, channels: 2, frames: n, format: 's16le', latency: r.latency, gainDb: r.gainDb, peakDb: r.peakDb, b64 };
  }

  window.MAudio = { SR, PRESETS: Object.keys(P), LEVEL, ANCHOR, DUR, MODES, render, encode, makeKey, degMidi, mtof };
})();
