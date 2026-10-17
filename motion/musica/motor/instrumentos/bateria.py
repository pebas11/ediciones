"""Batería sintetizada suave y cálida (nada de EDM ni trap).

Golpes (nota.x["golpe"], ver Pista.patron / Pista.golpe):
    bombo      bombo corto ~50 Hz, redondo
    aro        aro / cross-stick de madera
    escobilla  caja con escobilla (golpe)
    barrido    barrido de escobilla (dura lo que la nota)
    caja       caja suave con baqueta (para clímax)
    shaker     shaker de semillas (granular)
    hat        hi-hat cerrado suave · hat_abierto
    tic / tac  tic-tac orgánico de madera (para tensión)
Cada golpe varía levemente en afinación, color y largo (determinista), así
no suena a ametralladora aunque se repita.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import sosfilt

from ..nucleo import SR, desde_db, rng, rampa
from ..efectos import biquad
from .base import Instrumento


def _exp(t, tau):
    return np.exp(-t / tau)


def _ruido(g, n):
    return g.standard_normal(n)


def _modal(t, fs, taus, amps, g):
    y = np.zeros_like(t)
    for f, tau, a in zip(fs, taus, amps):
        y += a * np.sin(2 * np.pi * f * t + g.uniform(0, 6.28)) * np.exp(-t / tau)
    return y


class Bateria(Instrumento):
    """Kit sintetizado. niveles: dict golpe → dB para ajustar el balance interno.
    tono: multiplica las afinaciones (1 = normal). color: 0 oscuro … 1 brillante."""

    PAN = {"bombo": 0.0, "aro": -0.12, "escobilla": 0.05, "barrido": 0.1, "caja": 0.0,
           "shaker": -0.35, "hat": 0.28, "hat_abierto": 0.28, "tic": 0.3, "tac": -0.3}
    # calibrados para que un patrón de negras a vel 0.6 ronde: bombo −24, caja −26,
    # escobilla −28, aro −30, shaker/hat_abierto/tic −36, hat −38 LUFS
    NIVEL = {"bombo": -0.6, "aro": -5.6, "escobilla": -7.3, "barrido": -20.0, "caja": -5.3,
             "shaker": -10.2, "hat": -10.8, "hat_abierto": -15.8, "tic": -8.3, "tac": -8.4}

    def __init__(self, niveles=None, tono=1.0, color=0.5, ganancia_db=0.0):
        self.niveles = dict(self.NIVEL)
        if niveles:
            self.niveles.update(niveles)
        self.tono, self.color, self.ganancia_db = tono, color, ganancia_db
        self.nombre = "bateria"

    def voz(self, nt, ctx, pista):
        golpe = nt.x.get("golpe", "bombo")
        g = rng(ctx.semilla, "bat", pista.nombre if pista else "", golpe, round(nt.t * 960))
        v = float(nt.vel)
        fn = getattr(self, "_" + golpe, None)
        if fn is None:
            raise ValueError(f"golpe desconocido: {golpe}")
        if golpe == "barrido":
            dur_s = max(0.15, float(ctx.tempo.seg(nt.t + nt.dur) - ctx.tempo.seg(nt.t)))
            y = fn(v, g, dur_s)
        else:
            y = fn(v, g)
        if y.ndim == 1:
            pan = self.PAN.get(golpe, 0.0) + nt.x.get("pan", 0.0)
            a = (np.clip(pan, -1, 1) + 1) * np.pi / 4
            y = np.stack([y * np.cos(a), y * np.sin(a)], axis=1)
        y = y * desde_db(self.niveles.get(golpe, -10.0) + self.ganancia_db) * (v ** 1.35)
        y[: int(0.0005 * SR)] *= rampa(int(0.0005 * SR))[:, None]
        return y.astype(np.float32), ctx.muestra(nt.t)

    # ------------------------------------------------------------ golpes
    def _bombo(self, v, g):
        n = int(0.55 * SR)
        t = np.arange(n) / SR
        f1 = 49.0 * self.tono * (1 + g.normal(0, 0.008))
        f0 = (98.0 + 18 * v) * self.tono
        f = f1 + (f0 - f1) * _exp(t, 0.026)
        fase = np.cumsum(2 * np.pi * f / SR)
        # cuerpo corto (bombo apagado, no 808): la cola grave dura ~0,1 s
        cuerpo = np.sin(fase) * _exp(t, 0.095 + g.uniform(-0.008, 0.008))
        cuerpo *= 1 - np.exp(-t / 0.0015)
        golpe = np.sin(2 * fase) * _exp(t, 0.018) * 0.35          # "tum" de la piel
        click = sosfilt(biquad("pb", 1600 + 800 * self.color, 0.7), _ruido(g, n)) * _exp(t, 0.0035)
        y = cuerpo + golpe + 0.12 * v * click
        y = np.tanh(1.5 * y) / 1.2
        return sosfilt(np.vstack([biquad("pb", 3800.0, 0.7), biquad("pa", 32.0, 0.7)]), y)

    def _aro(self, v, g):
        n = int(0.22 * SR)
        t = np.arange(n) / SR
        k = self.tono * (1 + g.normal(0, 0.015))
        y = _modal(t, [980 * k, 1610 * k, 2480 * k, 420 * k], [0.03, 0.018, 0.011, 0.025],
                   [1.0, 0.55, 0.25, 0.35], g)
        clic = sosfilt(biquad("pa", 2500.0), _ruido(g, n)) * _exp(t, 0.0012)
        y += 0.35 * clic
        return sosfilt(biquad("pb", 5200 + 2000 * self.color, 0.6), y) * 0.8

    def _escobilla(self, v, g):
        n = int(0.4 * SR)
        t = np.arange(n) / SR
        r = _ruido(g, n)
        env = (1 - np.exp(-t / 0.004)) * (_exp(t, 0.085 + g.uniform(-0.01, 0.015)) + 0.22 * _exp(t, 0.24))
        s = sosfilt(np.vstack([biquad("pa", 420.0, 0.6), biquad("pb", 4200 + 2500 * self.color, 0.6)]), r) * env
        cuerpo = np.sin(2 * np.pi * 182 * self.tono * t) * _exp(t, 0.045) * 0.25
        bordona = sosfilt(biquad("banda", 3600.0, 0.9), _ruido(g, n)) * _exp(t, 0.1) * 0.35
        return (s + cuerpo + bordona) * 0.9

    def _barrido(self, v, g, dur_s):
        n = int(dur_s * SR)
        t = np.arange(n) / SR
        r = g.standard_normal((n, 2))
        x = t / max(1e-3, dur_s)
        env = np.sin(np.pi * np.clip(x, 0, 1)) ** 1.5
        giro = 0.7 + 0.3 * np.sin(2 * np.pi * (1.0 / max(0.25, dur_s)) * t + g.uniform(0, 6.28))
        sos = np.vstack([biquad("pa", 700.0, 0.6), biquad("pb", 3200 + 1500 * self.color, 0.6)])
        y = sosfilt(sos, r, axis=0) * (env * giro)[:, None]
        return y * 0.8

    def _caja(self, v, g):
        n = int(0.45 * SR)
        t = np.arange(n) / SR
        cuerpo = np.sin(2 * np.pi * 188 * self.tono * t + 0.3) * _exp(t, 0.06)
        cuerpo += 0.4 * np.sin(2 * np.pi * 330 * self.tono * t) * _exp(t, 0.03)
        r = sosfilt(np.vstack([biquad("pa", 320.0), biquad("pb", 6000 + 3000 * self.color, 0.6)]),
                    _ruido(g, n)) * _exp(t, 0.13 + g.uniform(-0.015, 0.015))
        y = 0.55 * cuerpo + 0.6 * r
        return np.tanh(1.3 * y)

    def _shaker(self, v, g):
        n = int(0.13 * SR)
        y = np.zeros((n, 2))
        pico = g.uniform(0.018, 0.032)
        k = int(30 + 30 * v)
        ts = np.clip(g.gamma(3.0, pico / 2.0, k), 0, 0.12)
        for lado in range(2):
            idx = (ts * SR).astype(int) + g.integers(0, 40, k)
            idx = idx[idx < n]
            np.add.at(y[:, lado], idx, g.uniform(-1, 1, len(idx)))
        # granos de 5 muestras (no impulsos sueltos) y techo a 11 kHz: suave, sin clicks
        w = np.hanning(7)[1:-1]
        y = np.stack([np.convolve(y[:, c], w, mode="same") for c in range(2)], axis=1)
        f = (5800 + 2200 * self.color) * (1 + g.normal(0, 0.05))
        y = sosfilt(np.vstack([biquad("banda", f, 1.6), biquad("pa", 2800.0, 0.7),
                               biquad("pb", 11000.0, 0.7)]), y, axis=0)
        return y * 2.6

    def _hat(self, v, g, abierto=False):
        n = int((0.5 if abierto else 0.09) * SR)
        t = np.arange(n) / SR
        tau = (0.2 if abierto else 0.028) * (1 + g.normal(0, 0.06))
        r = sosfilt(np.vstack([biquad("pa", 6500.0, 0.7), biquad("banda", 9500.0, 1.0)]), _ruido(g, n))
        metal = _modal(t, [5410, 7320, 8890, 11180], [tau * 1.3] * 4, [0.05, 0.04, 0.035, 0.03], g)
        y = (r + metal) * _exp(t, tau) * (1 - np.exp(-t / 0.0008))
        return sosfilt(biquad("pb", 12500.0 + 2500 * self.color, 0.6), y) * 0.9

    def _hat_abierto(self, v, g):
        return self._hat(v, g, abierto=True)

    def _tic(self, v, g):
        n = int(0.08 * SR)
        t = np.arange(n) / SR
        k = 1 + g.normal(0, 0.01)
        y = _modal(t, [2450 * k, 3870 * k, 5530 * k], [0.012, 0.008, 0.005], [1, 0.45, 0.2], g)
        return sosfilt(biquad("pb", 7000.0, 0.6), y) * 0.7

    def _tac(self, v, g):
        n = int(0.09 * SR)
        t = np.arange(n) / SR
        k = 1 + g.normal(0, 0.01)
        y = _modal(t, [1480 * k, 2290 * k, 3310 * k], [0.016, 0.01, 0.006], [1, 0.5, 0.2], g)
        return sosfilt(biquad("pb", 6000.0, 0.6), y) * 0.7
