"""Voz: carga, sonoridad, actividad (frases y pausas) y envolvente.

La voz llega editada a −16 LUFS (herramienta `motion/tools/voz`: 48 kHz, 24 bit, mono).
Una voz mono se ubica al centro como mono doble a ganancia unidad (L = R = x), igual que
la pone un editor (CapCut, Premiere) en una línea de tiempo estéreo. Por eso, en el
dominio estéreo de la mezcla, una voz mono de −16 LUFS mide ≈ −13 LUFS: lo que importa
es la relación con la música, y el master lleva el total a −14 LUFS.

Actividad (sin modelos, la voz ya viene limpia): nivel RMS en 100 Hz–6 kHz cada 10 ms,
umbral relativo al nivel activo del habla (percentil 95) con histéresis, sin ráfagas
cortas, y con los huecos entre palabras rellenados → frases. Lo que queda entre frases
son las pausas.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import soundfile as sf
import soxr
from scipy.signal import sosfilt

from . import SR
from .niveles import potencia_k_bloques, integrado

HOP = int(0.010 * SR)      # 10 ms


def _biquad(tipo, f, q=0.707):
    w = 2 * np.pi * f / SR
    cw, sw = np.cos(w), np.sin(w)
    al = sw / (2 * q)
    if tipo == "pb":
        b = [(1 - cw) / 2, 1 - cw, (1 - cw) / 2]
    else:
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
    a = [1 + al, -2 * cw, 1 - al]
    return np.concatenate([np.array(b) / a[0], np.array(a) / a[0]]).reshape(1, 6)


@dataclass
class Voz:
    ruta: str
    x: np.ndarray                 # (n, 2) float32, 48 kHz (mono → L = R)
    canales_origen: int
    sr_origen: int
    lufs_archivo: float | None    # medido sobre los canales originales (mono = 1 canal)
    lufs_mezcla: float | None     # medido como suena en la mezcla estéreo
    tp_archivo: float | None = None
    frases: list = field(default_factory=list)      # [(inicio_s, fin_s)]
    nivel_db: np.ndarray | None = None              # RMS en dBFS cada 10 ms (banda de habla)
    umbral_db: float | None = None
    nivel_activo_db: float | None = None

    @property
    def n(self) -> int:
        return len(self.x)

    @property
    def dur(self) -> float:
        return len(self.x) / SR

    def pausas(self) -> list[tuple[float, float]]:
        """Huecos entre frases (sin contar el principio ni el final)."""
        return [(a[1], b[0]) for a, b in zip(self.frases[:-1], self.frases[1:])]

    def mascara(self, t: np.ndarray, margen_s: float = 0.0) -> np.ndarray:
        """True donde hay habla (con un margen opcional a cada lado)."""
        m = np.zeros(len(t), bool)
        if not self.frases:
            return m
        on = np.array([f[0] for f in self.frases]) - margen_s
        off = np.array([f[1] for f in self.frases]) + margen_s
        i = np.searchsorted(on, t, side="right") - 1
        ok = i >= 0
        m[ok] = t[ok] < off[i[ok]]
        return m


def cargar(ruta: str) -> Voz:
    try:
        x, sr = sf.read(str(ruta), dtype="float32", always_2d=True)
    except Exception as e:
        raise ValueError(f"no puedo leer la voz {ruta}: {e}") from None
    canales = x.shape[1]
    if len(x) == 0:
        raise ValueError(f"la voz {ruta} está vacía")
    lufs_arch = integrado(potencia_k_bloques(x[:, :2] if canales >= 2 else x[:, 0])) \
        if sr == SR else None
    if sr != SR:
        x = soxr.resample(x, sr, SR, quality="VHQ").astype(np.float32)
        lufs_arch = integrado(potencia_k_bloques(x[:, :2] if canales >= 2 else x[:, 0]))
    if canales == 1:
        x = np.repeat(x, 2, axis=1)
    elif canales > 2:
        x = np.ascontiguousarray(x[:, :2])
    lufs_mez = integrado(potencia_k_bloques(x))
    return Voz(str(ruta), np.ascontiguousarray(x), canales, sr, lufs_arch, lufs_mez)


def detectar_actividad(v: Voz, p: dict) -> Voz:
    """Frases de habla (inicio, fin) en segundos. Ver docstring del módulo."""
    m = v.x.mean(axis=1).astype(np.float64)
    sos = np.vstack([_biquad("pa", 100.0), _biquad("pb", 6000.0)])
    y = sosfilt(sos, m + 1e-12)
    nfr = len(y) // HOP
    e = (y[: nfr * HOP].reshape(nfr, HOP) ** 2).mean(axis=1)
    # ventana de 30 ms centrada (suaviza sin correr los bordes)
    e = np.convolve(e, np.ones(3) / 3, mode="same")
    nivel = 10 * np.log10(e + 1e-14)
    v.nivel_db = nivel.astype(np.float32)
    vivos = nivel[nivel > -70]
    if len(vivos) < 10:
        v.frases = []
        return v
    activo = float(np.percentile(vivos, 95))
    on_t = activo + p["umbral_db"]
    off_t = on_t - p["histeresis_db"]
    v.nivel_activo_db, v.umbral_db = activo, on_t
    act = np.zeros(nfr, bool)
    estado = False
    for i in range(nfr):            # histéresis (60k cuadros para 10 min: rápido)
        if estado:
            estado = nivel[i] > off_t
        else:
            estado = nivel[i] > on_t
        act[i] = estado
    # tramos
    d = np.diff(np.concatenate([[0], act.astype(np.int8), [0]]))
    on = np.nonzero(d == 1)[0]
    off = np.nonzero(d == -1)[0]
    tramos = [(a, b) for a, b in zip(on, off) if (b - a) * HOP / SR * 1000 >= p["min_habla_ms"]]
    # rellenar huecos entre palabras
    hueco = p["hueco_palabras_ms"] / 1000 * SR / HOP
    frases = []
    for a, b in tramos:
        if frases and a - frases[-1][1] < hueco:
            frases[-1][1] = b
        else:
            frases.append([a, b])
    v.frases = [(a * HOP / SR, b * HOP / SR) for a, b in frases]
    return v


def resumen_pausas(v: Voz, larga_s: float) -> dict:
    ps = [b - a for a, b in v.pausas()]
    habla = sum(b - a for a, b in v.frases)
    return {
        "frases": len(v.frases),
        "habla_s": round(habla, 2),
        "primera_palabra_s": round(v.frases[0][0], 3) if v.frases else None,
        "ultima_palabra_s": round(v.frases[-1][1], 3) if v.frases else None,
        "pausas": len(ps),
        "pausa_media_s": round(float(np.mean(ps)), 3) if ps else None,
        "pausa_max_s": round(float(np.max(ps)), 3) if ps else None,
        "pausas_largas": int(sum(1 for x in ps if x >= larga_s)),
    }
