"""Master: ganancia hasta −14 LUFS integrados, limitador de pico real con anticipo, dither y WAV.

El limitador mira el pico real (sobremuestreo ×4 con soxr, por trozos y en streaming: la
memoria no se multiplica por 4) y calcula una ganancia con anticipo: mínimo hacia adelante en
una ventana de `lookahead_ms`, media móvil de la misma ventana (la reducción llega justo al
pico, sin sobrepasos) y relajación de un polo. Se aplica sin retardar la señal (offline).
"""
from __future__ import annotations

import numba as nb
import numpy as np
import soundfile as sf
import soxr

from . import SR
from .niveles import potencia_k_bloques, integrado

TROZO = 1 << 20


@nb.njit(cache=True)
def _min_adelante(g, L):
    """out[i] = min(g[i : i+L]) con deque monotónica (O(n))."""
    n = g.shape[0]
    out = np.empty(n)
    dq = np.empty(n, dtype=np.int64)
    cab = 0
    col = 0
    j = 0
    for i in range(n):
        lim = min(n - 1, i + L - 1)
        while j <= lim:
            while col > cab and g[dq[col - 1]] >= g[j]:
                col -= 1
            dq[col] = j
            col += 1
            j += 1
        while dq[cab] < i:
            cab += 1
        out[i] = g[dq[cab]]
    return out


@nb.njit(cache=True)
def _relajar(g, a_rel):
    n = g.shape[0]
    y = np.empty(n)
    e = 1.0
    for i in range(n):
        if g[i] < e:
            e = g[i]
        else:
            e += a_rel * (g[i] - e)
        y[i] = e
    return y


def picos_reales(x: np.ndarray) -> np.ndarray:
    """Pico por muestra considerando los 4 puntos sobremuestreados que la rodean (y la muestra)."""
    n = len(x)
    pk = np.abs(x).max(axis=1).astype(np.float32)
    st = soxr.ResampleStream(SR, SR * 4, 2, dtype="float32", quality="HQ")
    pend = np.zeros((0, 2), np.float32)
    pos = 0                                   # muestra original correspondiente a pend[0]
    for a in range(0, n, TROZO):
        b = min(n, a + TROZO)
        y = st.resample_chunk(np.ascontiguousarray(x[a:b], dtype=np.float32), last=(b >= n))
        if len(pend):
            y = np.concatenate([pend, y])
        k = len(y) // 4
        if k:
            m = np.abs(y[:k * 4]).max(axis=1).reshape(k, 4).max(axis=1)
            hasta = min(n, pos + k)
            pk[pos:hasta] = np.maximum(pk[pos:hasta], m[:hasta - pos])
            pos += k
        pend = y[k * 4:]
    return pk


def pico_real_db(x: np.ndarray) -> float:
    return float(20 * np.log10(float(picos_reales(x).max()) + 1e-12))


def ganancia_limitador(pk: np.ndarray, techo: float, L: int, relaj_s: float) -> np.ndarray:
    g_req = np.minimum(1.0, techo / (pk.astype(np.float64) + 1e-12))
    if g_req.min() >= 1.0:
        return np.ones(len(pk), np.float32)
    g = _min_adelante(g_req, L)
    gp = np.concatenate([np.full(L - 1, g[0]), g])
    cs = np.concatenate([[0.0], np.cumsum(gp)])
    g = (cs[L:] - cs[:-L]) / L
    g = np.minimum(g, g_req)
    a = 1.0 - np.exp(-1.0 / max(1.0, relaj_s * SR))
    return _relajar(g, a).astype(np.float32)


def masterizar(voz_x: np.ndarray, cama: np.ndarray, p: dict, mascara_voz=None):
    """Suma voz + cama, lleva a `p['lufs']` y limita a `p['techo_dbtp']`. Devuelve (mezcla, info, gr).

    El pico real escala con la ganancia: se sobremuestrea una sola vez la mezcla previa y, al final,
    se verifica el pico real de la mezcla limitada (si se pasa, otra vuelta con más margen)."""
    n = max(len(voz_x), len(cama))
    pre = np.zeros((n, 2), np.float32)
    pre[:len(cama)] += cama
    pre[:len(voz_x)] += voz_x
    objetivo, techo_db = p["lufs"], p["techo_dbtp"]
    L = max(2, int(p["lookahead_ms"] / 1000 * SR))
    p_pre = potencia_k_bloques(pre)
    l0 = integrado(p_pre)
    gan_db = objetivo - (l0 if l0 is not None else objetivo)
    margen = p["margen_db"]
    info = {"lufs_premaster": None if l0 is None else round(l0, 2)}
    pk0 = picos_reales(pre)
    y = g_lim = None
    lu = tp = None
    it = 0
    for vuelta in range(6):                   # verificación del pico real
        for it in range(6):                   # ganancia ↔ sonoridad (el limitador casi no la mueve)
            g = float(10 ** (gan_db / 20))
            g_lim = ganancia_limitador(pk0 * np.float32(g), 10 ** ((techo_db - margen) / 20), L,
                                       p["relajacion_ms"] / 1000)
            if g_lim.min() >= 1.0:            # sin limitador: la sonoridad escala exacta
                lu = None if l0 is None else l0 + gan_db
            else:
                y = pre * (g_lim * np.float32(g))[:, None]
                lu = integrado(potencia_k_bloques(y))
            if lu is None or abs(lu - objetivo) < 0.05:
                break
            if lu < objetivo and g_lim.min() < 10 ** (-12 / 20):
                break                         # no perseguir la sonoridad aplastando picos (> 12 dB)
            gan_db += objetivo - lu
        y = pre * (g_lim * np.float32(10 ** (gan_db / 20)))[:, None]
        if g_lim.min() >= 1.0:                # sin limitación el pico real escala exacto
            tp = float(20 * np.log10(float(pk0.max()) * 10 ** (gan_db / 20) + 1e-12))
        else:
            tp = pico_real_db(y)
        if tp <= techo_db + 0.005:
            break
        margen += (tp - techo_db) + 0.05
    if tp > techo_db + 0.005:                 # seguridad: el techo nunca se pasa (casos extremos)
        y *= np.float32(10 ** ((techo_db - 0.02 - tp) / 20))
        tp = pico_real_db(y)
    lu = integrado(potencia_k_bloques(y))
    gr = (-20 * np.log10(np.maximum(g_lim, 1e-9))).astype(np.float32)
    info.update({
        "lufs_integrado": None if lu is None else round(lu, 2),
        "pico_dbtp": round(tp, 2),
        "ganancia_master_db": round(gan_db, 2),
        "iteraciones": it + 1,
        "limitador": resumen_reduccion(gr, mascara_voz),
    })
    return y, info, gr


def resumen_reduccion(gr: np.ndarray, mascara_voz=None) -> dict:
    """Estadísticas de la reducción del limitador (dB): total, mientras habla la voz y sin voz.
    Casi todas las muestras valen 0: los percentiles se calculan solo sobre las que no."""
    def pct(nz_ordenado, n, q):
        rango = q / 100.0 * (n - 1)
        ceros = n - len(nz_ordenado)
        if rango < ceros or len(nz_ordenado) == 0:
            return 0.0
        return float(nz_ordenado[min(len(nz_ordenado) - 1, int(rango - ceros))])

    def st(v):
        n = len(v)
        if n == 0:
            return {"max_db": 0.0, "p99_db": 0.0, "p999_db": 0.0, "pct_mas_05db": 0.0, "pct_mas_1db": 0.0}
        nz = np.sort(v[v > 1e-6])
        return {"max_db": round(float(nz[-1]) if len(nz) else 0.0, 2),
                "p99_db": round(pct(nz, n, 99), 3),
                "p999_db": round(pct(nz, n, 99.9), 3),
                "pct_mas_05db": round(float(np.count_nonzero(nz > 0.5)) / n * 100, 3),
                "pct_mas_1db": round(float(np.count_nonzero(nz > 1.0)) / n * 100, 3)}
    out = {"total": st(gr)}
    if mascara_voz is not None:
        m = mascara_voz[:len(gr)]
        out["voz"] = st(gr[:len(m)][m])
        out["sin_voz"] = st(gr[:len(m)][~m])
    return out


def dither24(x: np.ndarray, semilla: str) -> np.ndarray:
    import hashlib
    h = int.from_bytes(hashlib.blake2b(semilla.encode(), digest_size=8).digest(), "little")
    g = np.random.default_rng(h)
    lsb = 1.0 / (2 ** 23)
    out = np.empty_like(x)
    for a in range(0, len(x), TROZO):
        b = min(len(x), a + TROZO)
        d = (g.random((b - a, x.shape[1])) - g.random((b - a, x.shape[1]))) * lsb
        out[a:b] = np.clip(x[a:b] + d.astype(np.float32), -1.0, 1.0 - lsb)
    return out


def escribir_wav(ruta, x: np.ndarray, semilla: str):
    sf.write(str(ruta), dither24(x, semilla), SR, subtype="PCM_24")
