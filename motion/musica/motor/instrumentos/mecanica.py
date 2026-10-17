"""La mecánica del piano como percusión orgánica (apagadores y pedal reales del vertical Knight).

    mec = C.pista("mecanica", Mecanica(), "bateria", vol=-8, envios={"sala": 0.2})
    mec.patron("apagador", "x.....x.....x...", 1, 9, vel=0.5, altura=73)   # 3+3+2 con resto de Do#5
    mec.golpe(1, "pedal", 0.6)                                             # el latido sordo del pedal

Va en el stem "bateria" (el QA trata sus golpes como transitorios a propósito).
"""
from __future__ import annotations

import numpy as np

from ..nucleo import SR, desde_db, rng, cortar
from ..efectos import biquad, sosf
from .base import Instrumento, Banco


def _a_estereo(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float32)
    if x.ndim == 1:
        return np.stack([x, x], axis=1) * np.float32(0.7071)
    if x.shape[1] == 1:
        return np.repeat(x, 2, axis=1) * np.float32(0.7071)
    return x


class Mecanica(Instrumento):
    """La mecánica del piano como percusión. Golpes (nota.x["golpe"], con Pista.patron /
    Pista.golpe, igual que la batería):

    * apagador   el apagador cayendo sobre la cuerda (muestras reales de "release"). La altura
                 de la nota elige la tecla: queda un resto de tono (altura=73 → un Do#5 apagado).
    * pedal      el golpe sordo del pedal de resonancia al soltarse (≈ 40 Hz): un latido.
    * pedal_baja el pedal al bajar (más corto y apagado).

    Cada golpe toma otra tecla vecina (±`vecinas` semitonos) y otro largo (determinista): no es
    un reloj. Nivel: el pico de RMS (10 ms) de cada muestra va a −20 dBFS a vel 1 (× vel^1,4);
    un patrón de negras a vel 0,6 ronda −24 LUFS (apagador con altura 73; con 50, −30) y −35
    (pedal, pedal_baja).
    * ganancia_db · pb_hz (pasabajos del apagador) · largo_s (duración del apagador) ·
      pan (dispersión del apagador) · vecinas
    """
    nombre = "mecanica"
    usa_pedal = False
    _picos: dict = {}

    def __init__(self, ganancia_db=0.0, pb_hz=3000.0, largo_s=0.5, pan=0.25, vecinas=2):
        self.ganancia_db, self.pb_hz, self.largo_s, self.pan = ganancia_db, pb_hz, largo_s, pan
        self.vecinas = int(vecinas)

    def _pico(self, banco, i):
        k = (banco.nombre, i)
        if k not in self._picos:
            x = np.asarray(banco.audio(i)[: int(0.4 * SR)], np.float64).mean(axis=1)
            h = int(0.01 * SR)
            nb = max(1, len(x) // h)
            e = np.sqrt((x[: nb * h].reshape(nb, h) ** 2).mean(axis=1) + 1e-20)
            self._picos[k] = float(e.max())
        return self._picos[k]

    def voz(self, nt, ctx, pista):
        golpe = nt.x.get("golpe", "apagador")
        g = rng(ctx.semilla, "mecanica", pista.nombre if pista else "", golpe, round(nt.t * 960))
        if golpe in ("pedal", "pedal_baja"):
            b = Banco.de("piano_pedal")
            art = "off" if golpe == "pedal" else "on"
            cands = [i for i, e in enumerate(b.muestras) if art in e.get("articulacion", "")]
            cands = cands or list(range(len(b.muestras)))
            i = int(cands[int(g.integers(0, len(cands)))])
            largo, pb, pan = (0.7, 900.0, 0.0) if golpe == "pedal" else (0.45, 1200.0, 0.0)
        elif golpe == "apagador":
            b = Banco.de("piano_soltar")
            i = b.elegir(nt.midi + int(g.integers(-self.vecinas, self.vecinas + 1)), 0)
            largo = self.largo_s * float(g.uniform(0.75, 1.25))
            pb = self.pb_hz
            pan = float(nt.x.get("pan", g.uniform(-self.pan, self.pan)))
        else:
            raise ValueError(f"golpe de mecánica desconocido: {golpe} (apagador, pedal, pedal_baja)")
        x = _a_estereo(cortar(np.asarray(b.audio(i), np.float32), int(largo * SR), 0.12))
        y = x * np.float32(desde_db(self.ganancia_db - 20.0) / max(self._pico(b, i), 1e-9)
                          * max(nt.vel, 1e-3) ** 1.4)
        y = sosf(np.vstack([biquad("pb", pb, 0.6), biquad("pa", 32.0, 0.6)]), y)
        nf = int(0.0015 * SR)
        y[:nf] *= np.linspace(0, 1, nf, dtype=np.float32)[:, None]
        a = (np.clip(pan, -1, 1) + 1) * np.pi / 4
        y = y * np.array([min(1.0, np.cos(a) * np.sqrt(2)), min(1.0, np.sin(a) * np.sqrt(2))],
                         dtype=np.float32)
        return y.astype(np.float32), ctx.muestra(nt.t)
