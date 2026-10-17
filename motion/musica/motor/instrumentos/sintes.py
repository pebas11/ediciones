"""Instrumentos sintetizados: celesta modal, piano eléctrico FM, pads, dron y bajo sub."""
from __future__ import annotations

import numpy as np
import numba as nb
import soxr
from scipy.signal import sosfilt

from ..nucleo import SR, desde_db, midi_a_hz, rng, rampa, mezclar_en, valor, ruido_suave
from ..efectos import biquad, _svf, Chorus, _seguidor, coef, sosf
from .base import Instrumento, envolvente_nota


# ================================================================ celesta ===
class Celesta(Instrumento):
    """Celesta por síntesis modal (no hay muestras CC0 de celesta).

    Placas de acero con resonador: fundamental dominante con un gemelo
    levemente desafinado (batido lento), modos inarmónicos de placa (2,76 y
    5,40) que se apagan rápido, golpe de martillo de fieltro y un toque de
    mecánica. Suena como se escribe (rango útil C4–C8).
    * brillo 0..1 · golpe 0..1 (martillo) · decaimiento (factor de la cola)
    * Usa pedal; sin pedal la nota se apaga 0,15 s después de soltar."""
    usa_pedal = True
    PARCIALES = [  # (razón, amplitud, factor de caída, sensible al brillo)
        (1.0, 1.00, 1.00, 0.0),
        (1.0016, 0.32, 0.85, 0.0),
        (2.0, 0.07, 0.40, 0.5),
        (2.756, 0.20, 0.17, 1.0),
        (3.01, 0.05, 0.25, 0.6),
        (5.404, 0.07, 0.07, 1.0),
        (8.933, 0.025, 0.035, 1.0),
    ]

    def __init__(self, brillo=0.5, golpe=0.5, decaimiento=1.0, rango_db=24.0, soltar=0.15,
                 dejar_sonar=False, pan=0.0, abrir=0.15):
        self.brillo, self.golpe, self.decaimiento = brillo, golpe, decaimiento
        self.rango_db, self.soltar, self.dejar_sonar = rango_db, soltar, dejar_sonar
        self.pan, self.abrir = pan, abrir
        self.nombre = "celesta"

    def voz(self, nt, ctx, pista):
        midi = nt.midi
        f0 = float(midi_a_hz(midi))
        T = 2.6 * 2 ** (-(midi - 72) / 12 * 0.55) * self.decaimiento
        T = float(np.clip(T, 0.5, 6.0))
        i0 = ctx.muestra(nt.t)
        n_on = max(32, self.fin_nota(nt, ctx, pista) - i0)
        n_nat = int(min(T * 4.0, 9.0) * SR)
        if self.dejar_sonar or nt.x.get("dejar_sonar"):
            n_on = max(n_on, n_nat)
        n_sol = int(self.soltar * SR)
        n = min(n_on, n_nat) + n_sol
        t = np.arange(n) / SR
        g = rng(ctx.semilla, "celesta", round(nt.t * 480), int(midi))
        v = nt.vel
        y = np.zeros(n)
        for (r, a, fd, sb) in self.PARCIALES:
            f = f0 * r * (1 + g.normal(0, 0.0003))
            if f > 18000:
                continue
            amp = a * (1 + sb * (self.brillo - 0.5) * 1.2) * (v ** (1 + 1.2 * sb))
            tau = T * fd / 6.91 * 3.0
            ph = g.uniform(0, 2 * np.pi) if r != 1.0 else 0.0
            y += amp * np.sin(2 * np.pi * f * t + ph) * np.exp(-t / tau)
        # martillo de fieltro: ruido corto filtrado + "toc" grave de la mecánica
        nh = min(n, int(0.012 * SR))
        ruido = g.standard_normal(nh) * np.exp(-np.arange(nh) / (0.0025 * SR))
        ruido = sosfilt(biquad("banda", min(9000, 1800 + f0 * 1.2), 1.1), ruido)
        y[:nh] += self.golpe * 0.5 * v * ruido
        nk = min(n, int(0.03 * SR))
        y[:nk] += self.golpe * 0.06 * v * np.sin(2 * np.pi * 190 * t[:nk]) * np.exp(-t[:nk] / 0.008)
        y[: int(0.0012 * SR)] *= rampa(int(0.0012 * SR))
        env = envolvente_nota(n, min(n_on, n_nat), 0.0, n_sol / SR)
        y *= env
        y *= desde_db(self.rango_db * (max(v, 1e-3) - 1) + 3.5) * 0.5
        pan = nt.x.get("pan", self.pan) + self.abrir * np.clip((midi - 78) / 18, -1, 1)
        a = (np.clip(pan, -1, 1) + 1) * np.pi / 4
        out = np.stack([y * np.cos(a), y * np.sin(a)], axis=1).astype(np.float32)
        return out, i0


# ===================================================== piano eléctrico FM ===
class Rhodes(Instrumento):
    """Piano eléctrico tipo Rhodes por FM (dos pares de operadores).

    * Par cuerpo (1:1) con índice que cae: calidez y "ladrido" a velocidad alta.
    * Par púa (1:14) con caída rapidísima: el "tine" metálico del ataque.
    * trem_hz / trem_prof: trémolo estéreo tipo Suitcase · brillo · campana
    """
    usa_pedal = True

    def __init__(self, brillo=0.45, campana=0.35, trem_hz=4.3, trem_prof=0.28, detune=4.0,
                 drive=0.35, soltar=0.22, tope_hz=6500.0, rango_db=22.0, pan=0.0):
        self.brillo, self.campana = brillo, campana
        self.trem_hz, self.trem_prof, self.detune, self.drive = trem_hz, trem_prof, detune, drive
        self.soltar, self.tope_hz, self.rango_db, self.pan = soltar, tope_hz, rango_db, pan
        self.nombre = "rhodes"

    def voz(self, nt, ctx, pista):
        midi = nt.midi
        f = float(midi_a_hz(midi))
        i0 = ctx.muestra(nt.t)
        tau = float(np.interp(midi, [36, 60, 84, 100], [3.2, 2.0, 1.0, 0.6]))
        n_on = max(32, self.fin_nota(nt, ctx, pista) - i0)
        n_on = min(n_on, int(tau * 5 * SR))
        n_sol = int(self.soltar * SR)
        n = n_on + n_sol
        t = np.arange(n) / SR
        v = nt.vel
        g = rng(ctx.semilla, "rhodes", round(nt.t * 480), int(midi))
        ph = g.uniform(0, 2 * np.pi, 3)
        I1 = (0.5 + 2.2 * self.brillo * v ** 1.6) * np.exp(-t / 0.5) + 0.25
        cuerpo = np.sin(2 * np.pi * f * t + I1 * np.sin(2 * np.pi * f * t + ph[0]))
        k_tine = 14.0 if f * 14 < 9000 else max(3.0, 9000 / f)
        I2 = self.campana * 3.2 * v * np.exp(-t / 0.028) * (1.0 if f < 1300 else 0.3)
        fd = f * 2 ** (self.detune / 1200)
        tine = np.sin(2 * np.pi * fd * t + ph[1] + I2 * np.sin(2 * np.pi * fd * k_tine * t + ph[2]))
        env2 = np.exp(-t / (tau * 0.5))
        y = 0.75 * cuerpo + 0.45 * tine * env2
        env = np.exp(-t / tau) * envolvente_nota(n, n_on, 0.0015, n_sol / SR)
        y *= env
        d = 1 + 3 * self.drive * v
        y = np.tanh(d * (y + 0.12 * y * y)) / d
        y *= desde_db(self.rango_db * (max(v, 1e-3) - 1) + 3.1) * 0.45
        a = (np.clip(nt.x.get("pan", self.pan), -1, 1) + 1) * np.pi / 4
        return np.stack([y * np.cos(a), y * np.sin(a)], axis=1).astype(np.float32), i0

    def render(self, notas, ctx, pista):
        out = super().render(notas, ctx, pista)
        # quitar DC de la asimetría, oscurecer y trémolo estéreo (fase global)
        out = sosf(np.vstack([biquad("pa", 40.0), biquad("pb", self.tope_hz, 0.6)]), out)
        if self.trem_prof > 0:
            tt = np.arange(ctx.n) / SR
            lfo = np.sin(2 * np.pi * self.trem_hz * tt)
            gl = 1 - self.trem_prof * (0.5 + 0.5 * lfo)
            gr = 1 - self.trem_prof * (0.5 - 0.5 * lfo)
            out *= np.stack([gl, gr], axis=1).astype(np.float32)
        return out


# =================================================================== pads ===
@nb.njit(cache=True, fastmath=True)
def _supersaw(n, f0, cents, deriva, deriva_hz, fases, gl, gr, sr):
    """Suma de sierras PolyBLEP desafinadas con deriva lenta; salida estéreo.
    La deriva se actualiza cada 32 muestras (inaudible y ~10× más rápido)."""
    out = np.zeros((n, 2))
    V = cents.shape[0]
    BL = 32
    for v in range(V):
        ph = fases[v]
        for b0 in range(0, n, BL):
            c = cents[v] + deriva[v] * np.sin(2 * np.pi * deriva_hz[v] * b0 / sr + fases[v] * 6.28)
            dt = f0 * 2.0 ** (c / 1200.0) / sr
            b1 = min(n, b0 + BL)
            glv = gl[v]
            grv = gr[v]
            for i in range(b0, b1):
                ph += dt
                if ph >= 1.0:
                    ph -= 1.0
                s = 2.0 * ph - 1.0
                if ph < dt:
                    x = ph / dt
                    s -= x + x - x * x - 1.0
                elif ph > 1.0 - dt:
                    x = (ph - 1.0) / dt
                    s -= x * x + x + x + 1.0
                out[i, 0] += s * glv
                out[i, 1] += s * grv
    return out


class Pad(Instrumento):
    """Pad cálido: supersaw PolyBLEP + sub, filtro de 4 polos que "respira", chorus.

    Automatizable desde la pista: 'corte' (Hz). Parámetros:
    * voces, desafinar (cents), sub (nivel de la sub-octava senoidal)
    * ataque, soltar (s) · corte, q, respira (octavas), respira_hz
    * chorus (mezcla), ancho (0..1), pa (pasaaltos Hz), saturar (dB)
    """

    def __init__(self, voces=6, desafinar=14.0, sub=0.25, ataque=1.6, soltar=3.0,
                 corte=1100.0, q=0.85, respira=0.35, respira_hz=0.06, chorus=0.35,
                 ancho=0.9, pa=110.0, saturar=3.0, deriva=3.0, ganancia_db=0.0):
        self.voces, self.desafinar, self.sub = voces, desafinar, sub
        self.ataque, self.soltar, self.corte, self.q = ataque, soltar, corte, q
        self.respira, self.respira_hz, self.chorus = respira, respira_hz, chorus
        self.ancho, self.pa, self.saturar, self.deriva = ancho, pa, saturar, deriva
        self.ganancia_db = ganancia_db
        self.nombre = "pad"

    def render(self, notas, ctx, pista):
        out = np.zeros((ctx.n, 2), dtype=np.float64)
        V = self.voces
        for nt in notas:
            i0 = ctx.muestra(nt.t)
            n_on = max(32, ctx.muestra(nt.t + nt.dur) - i0)
            ataque = nt.x.get("ataque", self.ataque)
            soltar = nt.x.get("soltar", self.soltar)
            n = n_on + int(soltar * SR)
            if i0 >= ctx.n:
                continue
            n = min(n, ctx.n - i0)
            g = rng(ctx.semilla, pista.nombre if pista else "pad", round(nt.t * 480), int(nt.midi))
            cents = np.linspace(-1, 1, V) * self.desafinar + g.normal(0, 1.5, V)
            der = g.uniform(0.5, 1.0, V) * self.deriva
            der_hz = g.uniform(0.05, 0.25, V)
            fases = g.uniform(0, 1, V)
            pans = np.linspace(-self.ancho, self.ancho, V)
            g.shuffle(pans)
            a = (pans + 1) * np.pi / 4
            amp = 1.0 / np.sqrt(V)
            s = _supersaw(n, float(midi_a_hz(nt.midi)), cents, der, der_hz, fases,
                          np.cos(a) * amp, np.sin(a) * amp, float(SR))
            if self.sub > 0:
                tt = np.arange(n) / SR
                sub = self.sub * np.sin(2 * np.pi * midi_a_hz(nt.midi) / 2 * tt) * 0.7
                s += sub[:, None]
            env = envolvente_nota(n, n_on, ataque, soltar)
            s *= env[:, None] * nt.vel
            mezclar_en(out, s, i0)
        # filtro de pista (automatizable + respiración)
        corte = pista.autos.get("corte", self.corte) if pista else self.corte
        fc = valor(corte, ctx.n, ctx.tempo)
        if self.respira:
            tt = np.arange(ctx.n) / SR
            fase = rng(ctx.semilla, "pad-respira", pista.nombre if pista else "").uniform(0, 6.28)
            lfo = np.sin(2 * np.pi * self.respira_hz * tt + fase) + \
                0.4 * np.sin(2 * np.pi * self.respira_hz * 2.31 * tt + 2 * fase)
            fc = fc * 2 ** (self.respira * lfo / 1.4)
        fc = np.clip(fc, 30, 16000)
        gg = np.tan(np.pi * fc / SR)
        y = np.empty_like(out)
        for c in range(2):
            z = np.tanh(out[:, c] * desde_db(self.saturar) * 0.5) / (desde_db(self.saturar) * 0.5)
            z = _svf(z, gg, 1.0 / self.q, 0)
            z = _svf(z, gg, 1.0 / 0.6, 0)
            y[:, c] = z
        y = sosf(biquad("pa", self.pa, 0.6), y)
        y = y.astype(np.float32)
        if self.chorus:
            y = Chorus(mezcla=self.chorus, base_ms=16.0, prof_ms=3.5, hz=0.27).procesar(y, ctx, pista)
        return y * np.float32(desde_db(self.ganancia_db - 13.0))


# =================================================================== dron ===
class Dron(Instrumento):
    """Dron orgánico: parciales con amplitudes que derivan, batidos lentos y un
    soplo de ruido resonante en los armónicos. Automatizable: 'corte' (Hz)."""

    def __init__(self, ataque=4.0, soltar=5.0, corte=900.0, aire=0.15, brillo=0.5,
                 respira=0.3, ganancia_db=0.0):
        self.ataque, self.soltar, self.corte, self.aire = ataque, soltar, corte, aire
        self.brillo, self.respira, self.ganancia_db = brillo, respira, ganancia_db
        self.nombre = "dron"

    SR_INT = 12000  # el dron vive por debajo de ~3 kHz: se sintetiza a 12 kHz y se sobremuestrea

    def render(self, notas, ctx, pista):
        k = SR // self.SR_INT
        n_int = ctx.n // k + 2
        out = np.zeros((n_int, 2), dtype=np.float64)
        sr = self.SR_INT
        for nt in notas:
            i0 = ctx.muestra(nt.t) // k
            if i0 >= n_int:
                continue
            n_on = max(8, ctx.muestra(nt.t + nt.dur) // k - i0)
            n = min(n_on + int(self.soltar * sr), n_int - i0)
            g = rng(ctx.semilla, "dron", pista.nombre if pista else "", round(nt.t * 480), int(nt.midi))
            f0 = float(midi_a_hz(nt.midi))
            t = np.arange(n) / sr
            s = np.zeros((n, 2))
            # parciales en fase en ambos canales (compatible en mono); cada lado con su
            # propia deriva lenta de amplitud: el sonido se mueve sin cancelarse
            for kk, a in enumerate([1.0, 0.45, 0.22 * (0.5 + self.brillo), 0.14 * (0.5 + self.brillo),
                                    0.08 * self.brillo, 0.05 * self.brillo]):
                h = kk + 1
                if f0 * h > 0.4 * sr:
                    break
                fase = g.uniform(0, 6.28)
                df = g.uniform(0.06, 0.16) * h          # batido lento dentro de cada canal
                tono = np.sin(2 * np.pi * f0 * h * t + fase) + \
                    0.5 * np.sin(2 * np.pi * (f0 * h + df) * t + fase + 1.0)
                for lado in range(2):
                    mod = 0.7 + 0.3 * ruido_suave(n, int(g.uniform(2.5, 6.0) * sr), g)
                    s[:, lado] += a * mod * tono / 1.5
            if self.aire > 0:
                for h in (2, 4):
                    fc = f0 * h
                    if fc > 0.4 * sr:
                        continue
                    r = g.standard_normal((n, 2))
                    gg = np.full(n, np.tan(np.pi * fc / sr))
                    for lado in range(2):
                        s[:, lado] += self.aire * 0.6 * _svf(r[:, lado], gg, 1 / 25.0, 2)
            na = min(n, int(self.ataque * sr))
            env = np.ones(n)
            if na:
                env[:na] = rampa(na)
            nr = n - min(n_on, n)
            if nr > 0:
                tt = np.arange(nr) / (self.soltar * sr)
                env[min(n_on, n):] *= np.exp(-6.91 * tt) * rampa(nr)[::-1] ** 0.5
            s *= (env * nt.vel * 0.35)[:, None]
            mezclar_en(out, s, i0)
        corte = pista.autos.get("corte", self.corte) if pista else self.corte
        fc = valor(corte, n_int * k, ctx.tempo)[::k][:n_int]
        if self.respira:
            tt = np.arange(n_int) / sr
            fc = fc * 2 ** (self.respira * np.sin(2 * np.pi * 0.045 * tt + 1.0))
        gg = np.tan(np.pi * np.clip(fc, 30, 0.45 * sr) / sr)
        y = np.empty_like(out)
        for c in range(2):
            y[:, c] = _svf(out[:, c], gg, 1 / 0.7, 0)
        y = soxr.resample(y, sr, SR, quality="HQ")[: ctx.n]
        if len(y) < ctx.n:
            y = np.concatenate([y, np.zeros((ctx.n - len(y), 2))])
        return (y * desde_db(self.ganancia_db - 8.3)).astype(np.float32)


# ================================================================ bajo sub ==
class Sub(Instrumento):
    """Bajo sub monofónico: senoidal + octava opcional, saturación suave para que
    se escuche en parlantes chicos, deslizamiento opcional entre notas ligadas.
    * drive_db, octava (nivel de la 8ª), glide_ms, ataque, soltar, pb (Hz)"""

    def __init__(self, drive_db=7.0, octava=0.12, glide_ms=0.0, ataque=0.012, soltar=0.12,
                 pb=240.0, pa=28.0, ganancia_db=0.0):
        self.drive_db, self.octava, self.glide_ms = drive_db, octava, glide_ms
        self.ataque, self.soltar, self.pb, self.pa = ataque, soltar, pb, pa
        self.ganancia_db = ganancia_db
        self.nombre = "sub"

    def render(self, notas, ctx, pista):
        n = ctx.n
        if not notas:
            return np.zeros((n, 2), np.float32)
        notas = sorted(notas, key=lambda z: z.t)
        logf = np.full(n, np.log(midi_a_hz(notas[0].midi)))
        gate = np.zeros(n)
        prev_fin = -1
        for k, nt in enumerate(notas):
            i0 = max(0, ctx.muestra(nt.t))
            i1 = min(n, ctx.muestra(nt.t + nt.dur))
            if i0 >= n:
                continue
            logf[i0:] = np.log(midi_a_hz(nt.midi))
            legato = nt.x.get("legato") or (prev_fin >= i0 - int(0.002 * SR) and self.glide_ms > 0)
            gate[i0:i1] = nt.vel
            if not legato and prev_fin >= i0 - int(0.004 * SR):
                gap = int(0.009 * SR)
                gate[max(0, i0 - gap):i0] = 0.0  # rearticular notas repetidas
            prev_fin = i1
        tau = (self.glide_ms if self.glide_ms > 0 else 4.0) / 1000.0
        logf = _seguidor(logf, coef(tau), coef(tau))
        env = _seguidor(gate, coef(self.ataque), coef(self.soltar))
        fase = np.cumsum(np.exp(logf) * 2 * np.pi / SR)
        y = np.sin(fase) + self.octava * np.sin(2 * fase + 0.3)
        y *= env
        d = float(desde_db(self.drive_db))
        y = np.tanh(d * y) / np.tanh(d)
        y = sosf(np.vstack([biquad("pb", self.pb, 0.7), biquad("pa", self.pa, 0.7)]), y)
        y *= desde_db(self.ganancia_db - 16.9) * 0.5
        return np.stack([y, y], axis=1).astype(np.float32)
