"""Ducking por stems guiado por la voz, realce en pausas y EQ dinámica (curvas de control a 1 kHz).

Control d(t) ∈ [0, 1] (1 = música bajada del todo), construido con rampas coseno a partir de
las frases de la voz (offline: se conoce el futuro, así que el "lookahead" es exacto):

    bajada:   empieza `lookahead_ms` antes de la primera sílaba y dura `ataque_ms`
    meseta:   mientras dura la frase y `mantener_ms` después
    subida:   en cada pausa, rampa de `relajacion_ms` hacia 1 − f(pausa), con
              f = 0 en pausas < `pausa_minima_s` (no sube: sin bombeo entre frases),
              f = 1 en pausas ≥ `pausa_completa_s` (sube del todo) y lineal en el medio.

Por stem: ganancia_dB(t) = profundidad_stem(t) · d(t)  (profundidad por tramo, con transición
suave de 1 s entre tramos). EQ dinámica: campana ancha en la franja de la voz con ganancia
eq_dB · d(t). Realce (común a todos los stems): +realce_pausas_db en pausas largas y
+realce_intro_db antes de la primera palabra y después de la última, con rampas que terminan
antes de que vuelva la voz.
"""
from __future__ import annotations

import numpy as np

from . import SR, STEMS

CTRL_HZ = 1000
PASO = SR // CTRL_HZ        # 48 muestras por punto de control


def _rampa(x):
    return 0.5 - 0.5 * np.cos(np.pi * np.clip(x, 0.0, 1.0))


def curva_ducking(frases, n: int, p: dict) -> np.ndarray:
    d = np.zeros(n, np.float64)
    if not frases:
        return d
    la = p["lookahead_ms"] / 1000
    at = p["ataque_ms"] / 1000
    rel = p["relajacion_ms"] / 1000
    hold = p["mantener_ms"] / 1000
    pmin, pfull = p["pausa_minima_s"], p["pausa_completa_s"]
    t = np.arange(n) / CTRL_HZ

    def idx(x):
        return int(np.clip(round(x * CTRL_HZ), 0, n))

    for i, (on, off) in enumerate(frases):
        a0, a1 = on - la, on - la + at
        i0, i1 = idx(a0), idx(a1)
        v0 = d[i0] if i0 < n else 0.0
        if i1 > i0:
            d[i0:i1] = v0 + (1.0 - v0) * _rampa((t[i0:i1] - a0) / at)
        r0 = off + hold
        d[i1:idx(r0)] = 1.0
        if i + 1 < len(frases):
            pausa = frases[i + 1][0] - off
            f = float(np.clip((pausa - pmin) / max(1e-6, pfull - pmin), 0.0, 1.0))
        else:
            f = 1.0
        j0, j1 = idx(r0), idx(r0 + rel)
        if j1 > j0:
            d[j0:j1] = 1.0 - f * _rampa((t[j0:j1] - r0) / rel)
        d[j1:] = 1.0 - f
    return d


def curva_realce(frases, n: int, dur_voz: float, p_niv: dict, p_duck: dict) -> np.ndarray:
    b = np.zeros(n, np.float64)
    t = np.arange(n) / CTRL_HZ
    rp, ri = p_niv["realce_pausas_db"], p_niv["realce_intro_db"]
    larga, ramp = p_niv["pausa_larga_s"], p_niv["rampa_realce_s"]
    la = p_duck["lookahead_ms"] / 1000
    hold = p_duck["mantener_ms"] / 1000
    if not frases:
        b[:] = ri
        return b
    # intro: realce pleno y bajada de 2 rampas que termina antes de la primera palabra
    f1 = frases[0][0] - la
    if f1 > 0:
        R = 2 * ramp
        f0 = f1 - R
        m = t < f1
        if f0 >= 0:
            b[m] = np.where(t[m] < f0, ri, ri * (1.0 - _rampa((t[m] - f0) / R)))
        else:                       # intro corta: menos realce, misma forma
            b[m] = ri * (f1 / R) * (1.0 - _rampa(t[m] / f1))
    # pausas largas
    for (_, off), (on, _) in zip(frases[:-1], frases[1:]):
        if on - off < larga:
            continue
        r0, f1 = off + hold, on - la
        disp = f1 - r0
        if disp <= 0.05:
            continue
        rr = min(ramp, disp / 2)
        amp = rp * min(1.0, disp / (2 * ramp))
        m = (t >= r0) & (t < f1)
        tt = t[m]
        b[m] = amp * np.minimum(_rampa((tt - r0) / rr), 1.0 - _rampa((tt - (f1 - rr)) / rr))
    # final: sube después de la última palabra
    r0 = frases[-1][1] + hold
    m = t >= r0
    b[m] = np.maximum(b[m], ri * _rampa((t[m] - r0) / (2 * ramp)))
    return b


class Control:
    """Curvas de control (1 kHz) para toda la mezcla."""

    def __init__(self, voz, n_muestras: int, params: dict, tramos=None):
        self.p = params
        pd = params["ducking"]
        self.n = int(np.ceil(n_muestras / PASO)) + 2
        self.t = np.arange(self.n) / CTRL_HZ
        frases = voz.frases if voz is not None else []
        activo = pd["activo"]
        self.d = curva_ducking(frases, self.n, pd) if activo else np.zeros(self.n)
        self.realce = curva_realce(frases, self.n, voz.dur if voz else 0.0, params["niveles"], pd)
        self.guardia = np.zeros(self.n)      # dB (≤ 0): guardia de voz, se completa después del render
        # profundidad por stem y EQ, por tramo (transición de 1 s centrada en cada entrada)
        base = {s: float(pd["profundidad_db"].get(s, 0.0)) for s in STEMS}
        eq_base = float(pd["eq"]["ganancia_db"]) if pd["eq"]["activo"] else 0.0
        self.prof = {s: np.full(self.n, base[s]) for s in STEMS}
        self.eq = np.full(self.n, eq_base)
        if tramos:
            segs = []
            for k, (t0, t1, duck) in enumerate(tramos):
                if duck is False:
                    vals = {s: 0.0 for s in STEMS}
                    eqv = 0.0
                elif isinstance(duck, dict):
                    vals = dict(base)
                    vals.update(duck.get("profundidad_db", {}))
                    eqv = duck.get("eq_db", eq_base) if pd["eq"]["activo"] else 0.0
                else:
                    vals, eqv = base, eq_base
                segs.append((t0, t1, vals, eqv))
            for s in STEMS:
                self.prof[s] = self._escalonada([(a, b, v[s]) for a, b, v, _ in segs], base[s])
            self.eq = self._escalonada([(a, b, e) for a, b, _, e in segs], eq_base)
        if not activo:
            for s in STEMS:
                self.prof[s][:] = 0.0
            self.eq[:] = 0.0

    def _escalonada(self, tramos, defecto):
        """Valores por tramo con rampas coseno de 1 s centradas en cada cambio."""
        out = np.full(self.n, float(defecto))
        if not tramos:
            return out
        cambios = []
        actual = tramos[0][2]
        out[:] = actual
        for (a, _b, v) in tramos[1:]:
            if v != actual:
                cambios.append((a, actual, v))
                actual = v
        for (tc, v0, v1) in cambios:
            x = (self.t - (tc - 0.5)) / 1.0
            out += (v1 - v0) * _rampa(x)
        return out

    # ------------------------------------------------------------ consultas
    def duck_db(self, stem: str) -> np.ndarray:
        return self.prof[stem] * self.d

    def eq_db(self) -> np.ndarray:
        return self.eq * self.d

    def en_muestras(self, curva: np.ndarray, a: int, b: int) -> np.ndarray:
        """Interpola una curva de control a las muestras [a, b)."""
        x = np.arange(a, b, dtype=np.float64) / PASO
        return np.interp(x, np.arange(len(curva)), curva).astype(np.float32)

    def en_t(self, curva: np.ndarray, t: np.ndarray) -> np.ndarray:
        return np.interp(t, self.t, curva)


def sos_eq(desde_hz: float, hasta_hz: float):
    """Pasabanda RBJ de pico 0 dB centrado en √(f1·f2), un poco más ancho que la franja
    (Q ≈ 0,72 × Q de los bordes): con y = x − (1 − g)·BP(x), g en el centro y ≈ g/2 (en dB)
    en los bordes de la franja."""
    from motor.efectos import biquad
    fc = float(np.sqrt(desde_hz * hasta_hz))
    n_oct = np.log2(hasta_hz / desde_hz)
    q = 0.72 * (2 ** (n_oct / 2)) / (2 ** n_oct - 1)
    return biquad("banda", fc, q)
