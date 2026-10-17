"""Primitivas de DSP compartidas (numpy/scipy, sin dependencias exóticas)."""

from __future__ import annotations

import math

import numpy as np
from scipy import signal

EPS = 1e-12


def db(x):
    return 10.0 * np.log10(np.maximum(x, EPS))


def db_amp(x):
    return 20.0 * np.log10(np.maximum(np.abs(x), EPS))


def rms_frames(x: np.ndarray, sr: int, win_s: float = 0.02, hop_s: float = 0.01):
    """RMS por cuadro con sumas acumuladas. Devuelve (centros_s, potencia_media)."""
    win = max(1, int(round(win_s * sr)))
    hop = max(1, int(round(hop_s * sr)))
    x64 = x.astype(np.float64)
    c = np.concatenate([[0.0], np.cumsum(x64 * x64)])
    n = len(x)
    if n < win:
        return np.array([n / 2 / sr]), np.array([c[-1] / max(n, 1)])
    starts = np.arange(0, n - win + 1, hop)
    pot = (c[starts + win] - c[starts]) / win
    centros = (starts + win / 2) / sr
    return centros, np.maximum(pot, 0.0)


def potencia_centrada(x: np.ndarray, sr: int, win_s: float, hop: int):
    """Potencia media en ventana centrada, evaluada cada `hop` muestras (control rate)."""
    win = max(1, int(round(win_s * sr)))
    x64 = x.astype(np.float64)
    c = np.concatenate([[0.0], np.cumsum(x64 * x64)])
    n = len(x)
    centros = np.arange(0, n, hop)
    a = np.clip(centros - win // 2, 0, n)
    b = np.clip(centros + win // 2 + 1, 0, n)
    pot = (c[b] - c[a]) / np.maximum(b - a, 1)
    return centros, np.maximum(pot, 0.0)


def corridas(mask: np.ndarray):
    """Inicio y largo de las corridas de True."""
    m = np.asarray(mask, dtype=np.int8)
    if m.size == 0:
        return np.array([], dtype=int), np.array([], dtype=int)
    d = np.diff(np.concatenate([[0], m, [0]]))
    ini = np.flatnonzero(d == 1)
    fin = np.flatnonzero(d == -1)
    return ini, fin - ini


def true_peak(x: np.ndarray, factor: int = 4, bloque: int = 480000) -> float:
    """Pico verdadero (sobremuestreo x4, como BS.1770) por bloques para no gastar memoria."""
    n = len(x)
    if n == 0:
        return 0.0
    pad = 256
    mx = 0.0
    for a in range(0, n, bloque):
        lo = max(0, a - pad)
        hi = min(n, a + bloque + pad)
        up = signal.resample_poly(x[lo:hi].astype(np.float64), factor, 1)
        i0 = (a - lo) * factor
        i1 = i0 + (min(n, a + bloque) - a) * factor
        mx = max(mx, float(np.max(np.abs(up[i0:i1]))))
    return mx


def envolvente_pico_os(x: np.ndarray, hop: int, factor: int = 4, bloque: int = 480000):
    """Máximo |x| sobremuestreado por bloque de `hop` muestras (para el limitador)."""
    n = len(x)
    nb = (n + hop - 1) // hop
    out = np.zeros(nb)
    pad = 256
    bloque = max(hop, (bloque // hop) * hop)  # cada bloque empieza en múltiplo de hop
    for a in range(0, n, bloque):
        lo = max(0, a - pad)
        hi = min(n, a + bloque + pad)
        up = np.abs(signal.resample_poly(x[lo:hi].astype(np.float64), factor, 1))
        i0 = (a - lo) * factor
        b_ = min(n, a + bloque)
        seg = up[i0 : i0 + (b_ - a) * factor]
        # por muestra original: máximo de sus `factor` submuestras
        porm = seg[: (len(seg) // factor) * factor].reshape(-1, factor).max(axis=1)
        porm = np.maximum(porm, np.abs(x[a:b_][: len(porm)]))
        k0 = a // hop
        # a es múltiplo de hop porque bloque lo es (se fuerza abajo)
        m = len(porm)
        nbl = (m + hop - 1) // hop
        tmp = np.zeros(nbl * hop)
        tmp[:m] = porm
        out[k0 : k0 + nbl] = np.maximum(out[k0 : k0 + nbl], tmp.reshape(nbl, hop).max(axis=1))
    return out


# ----------------------------------------------------------------------------
# Filtros (RBJ Audio EQ Cookbook) como SOS
# ----------------------------------------------------------------------------


def _sos(b, a):
    b = np.asarray(b, dtype=np.float64) / a[0]
    a = np.asarray(a, dtype=np.float64) / a[0]
    return np.concatenate([b, a])[None, :]


def peaking(f0: float, q: float, gain_db: float, sr: int):
    A = 10 ** (gain_db / 40)
    w0 = 2 * math.pi * f0 / sr
    alpha = math.sin(w0) / (2 * q)
    cw = math.cos(w0)
    b = [1 + alpha * A, -2 * cw, 1 - alpha * A]
    a = [1 + alpha / A, -2 * cw, 1 - alpha / A]
    return _sos(b, a)


def high_shelf(f0: float, gain_db: float, sr: int, s: float = 0.8):
    A = 10 ** (gain_db / 40)
    w0 = 2 * math.pi * f0 / sr
    cw, sw = math.cos(w0), math.sin(w0)
    alpha = sw / 2 * math.sqrt((A + 1 / A) * (1 / s - 1) + 2)
    sa = 2 * math.sqrt(A) * alpha
    b = [A * ((A + 1) + (A - 1) * cw + sa), -2 * A * ((A - 1) + (A + 1) * cw),
         A * ((A + 1) + (A - 1) * cw - sa)]
    a = [(A + 1) - (A - 1) * cw + sa, 2 * ((A - 1) - (A + 1) * cw), (A + 1) - (A - 1) * cw - sa]
    return _sos(b, a)


def low_shelf(f0: float, gain_db: float, sr: int, s: float = 0.8):
    A = 10 ** (gain_db / 40)
    w0 = 2 * math.pi * f0 / sr
    cw, sw = math.cos(w0), math.sin(w0)
    alpha = sw / 2 * math.sqrt((A + 1 / A) * (1 / s - 1) + 2)
    sa = 2 * math.sqrt(A) * alpha
    b = [A * ((A + 1) - (A - 1) * cw + sa), 2 * A * ((A - 1) - (A + 1) * cw),
         A * ((A + 1) - (A - 1) * cw - sa)]
    a = [(A + 1) + (A - 1) * cw + sa, -2 * ((A - 1) + (A + 1) * cw), (A + 1) + (A - 1) * cw - sa]
    return _sos(b, a)


def notch(f0: float, q: float, sr: int):
    b, a = signal.iirnotch(f0, q, fs=sr)
    return _sos(b, a)


def respuesta_db(sos, freqs, sr):
    w, h = signal.sosfreqz(sos, worN=np.asarray(freqs, dtype=float), fs=sr)
    return db_amp(h)


# ----------------------------------------------------------------------------
# Bandas de tercio de octava
# ----------------------------------------------------------------------------

TERCIOS = np.array([
    50, 63, 80, 100, 125, 160, 200, 250, 315, 400, 500, 630, 800, 1000, 1250, 1600, 2000,
    2500, 3150, 4000, 5000, 6300, 8000, 10000, 12500, 16000, 20000,
], dtype=float)


def bandas_tercio(freqs: np.ndarray, pot: np.ndarray, centros=TERCIOS):
    """Suma de potencia por banda de 1/3 de octava (en dB)."""
    out = []
    k = 2 ** (1 / 6)
    for fc in centros:
        sel = (freqs >= fc / k) & (freqs < fc * k)
        out.append(db(np.sum(pot[sel])) if np.any(sel) else -120.0)
    return np.array(out)


# ----------------------------------------------------------------------------
# Suavizado ataque/liberación a tasa de control (bucle simple, rápido a 1 kHz)
# ----------------------------------------------------------------------------


def suavizar_ganancia(objetivo_db: np.ndarray, ataque_s: float, liberacion_s: float,
                      tasa_hz: float) -> np.ndarray:
    """Suaviza una reducción de ganancia (dB ≤ 0): baja rápido (ataque), sube lento."""
    ca = math.exp(-1.0 / max(ataque_s * tasa_hz, 1e-9))
    cr = math.exp(-1.0 / max(liberacion_s * tasa_hz, 1e-9))
    out = np.empty_like(objetivo_db)
    g = 0.0
    obj = objetivo_db.tolist()
    for i, t in enumerate(obj):
        if t < g:
            g = ca * g + (1 - ca) * t
        else:
            g = cr * g + (1 - cr) * t
        out[i] = g
    return out


def minimo_movil(x: np.ndarray, ventana: int) -> np.ndarray:
    """Mínimo en ventana centrada (para anticipar la reducción del limitador)."""
    from scipy.ndimage import minimum_filter1d

    if ventana <= 1:
        return x.copy()
    return minimum_filter1d(x, size=ventana, mode="nearest")


def maximo_movil(x: np.ndarray, ventana: int) -> np.ndarray:
    from scipy.ndimage import maximum_filter1d

    if ventana <= 1:
        return x.copy()
    return maximum_filter1d(x, size=ventana, mode="nearest")


def a_tasa_audio(ganancia_ctrl: np.ndarray, hop: int, n: int) -> np.ndarray:
    """Interpola una curva de control (un valor cada `hop` muestras) a tasa de audio."""
    pos = np.arange(len(ganancia_ctrl)) * hop
    return np.interp(np.arange(n), pos, ganancia_ctrl).astype(np.float32)


def resample(x: np.ndarray, sr_in: int, sr_out: int) -> np.ndarray:
    if sr_in == sr_out:
        return x
    g = math.gcd(sr_in, sr_out)
    return signal.resample_poly(x, sr_out // g, sr_in // g).astype(np.float32)
