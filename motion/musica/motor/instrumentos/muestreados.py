"""Instrumentos con muestras reales (VSCO-2 CE y VCSL, CC0).

Las muestras llegan niveladas desde el manifiesto (ver muestras.py y NIVELES.md). Acá:
* cruce de capas de dinámica sin cancelaciones (`mezclar_capas`);
* domado de parciales de los vibráfonos (`domar_parciales`);
* bucles para notas largas (`extender`).
"""
from __future__ import annotations

import numpy as np
import scipy.fft as sfft

from ..nucleo import SR, desde_db, rng, rampa, mezclar_en, cortar
from ..efectos import biquad, sosf
from .base import Banco, Instrumento, envolvente_nota, CACHE


def _a_estereo(seg: np.ndarray) -> np.ndarray:
    if seg.shape[1] == 2:
        return seg
    return np.repeat(seg, 2, axis=1) * np.float32(0.7071)


def _balance(y: np.ndarray, pan: float, ancho: float = 1.0) -> np.ndarray:
    if ancho != 1.0:
        m = 0.5 * (y[:, 0] + y[:, 1])
        s = 0.5 * (y[:, 0] - y[:, 1]) * ancho
        y = np.stack([m + s, m - s], axis=1)
    if pan:
        a = (np.clip(pan, -1, 1) + 1) * np.pi / 4
        y = y * np.array([min(1.0, np.cos(a) * np.sqrt(2)), min(1.0, np.sin(a) * np.sqrt(2))],
                         dtype=np.float32)
    return y


def zona_estable(mono: np.ndarray):
    """(inicio, fin, nivel_rms) del sostenido: donde la envolvente queda a ±4 dB de su mediana
    (deja afuera el ataque lento de las capas suaves y la caída final de la muestra). Es el
    mismo tramo que mide la nivelación (muestras.py) y el que usan los bucles."""
    L = len(mono)
    h = int(0.05 * SR)
    nb = max(1, L // h)
    e = np.sqrt((mono[: nb * h].reshape(nb, h) ** 2).mean(axis=1) + 1e-12)
    k = 6
    e = np.sqrt(np.convolve(e ** 2, np.ones(k) / k, mode="same"))
    edb = 20 * np.log10(e)
    a, b = int(0.2 * nb), max(int(0.2 * nb) + 1, int(0.8 * nb))
    med = float(np.median(edb[a:b]))
    ok = np.nonzero(edb >= med - 4.0)[0]
    ok = ok[ok >= int(0.12 * nb)]
    if len(ok) < 10:
        return int(0.35 * L), int(0.85 * L), 10 ** (med / 20)
    s0 = (ok[0] + 6) * h
    s1 = (ok[-1] - 6) * h
    if s1 - s0 < int(1.2 * SR):
        s0, s1 = int(0.35 * L), int(0.85 * L)
    # nivel = potencia media dentro del tramo (no la mediana del 20–80 % de la muestra): los
    # bucles quedan al nivel del sostenido que midió la nivelación (también en las muestras
    # que decaen al final)
    a, b = max(0, s0 // h), min(nb, max(s0 // h + 1, s1 // h))
    return s0, s1, float(np.sqrt(np.mean(e[a:b] ** 2)))


def extender(a: np.ndarray, n_total: int, semilla) -> np.ndarray:
    """Alarga una muestra sostenida con bucles de fundido largo, alineados por correlación.

    La zona de bucle se detecta en la envolvente (sin ataque ni caída final) y
    su nivel se aplana suavemente para que el sostenido no "serruche". Cada
    salto vuelve a un punto distinto de esa zona, así una nota de 20 s no repite
    el mismo ciclo. El fundido compensa la correlación entre los dos tramos."""
    L = len(a)
    if L >= n_total:
        return a[:n_total]
    g = rng("extender", semilla)
    mono0 = a.mean(axis=1).astype(np.float64)
    s0, s1, nivel = zona_estable(mono0)
    # aplanar el nivel desde s0 (rampa de 0,5 s): ganancia = nivel / envolvente lenta
    h = int(0.05 * SR)
    nb = L // h + 1
    pad = np.pad(mono0, (0, nb * h - L))
    e = np.sqrt((pad.reshape(nb, h) ** 2).mean(axis=1) + 1e-12)
    e = np.sqrt(np.convolve(e ** 2, np.ones(8) / 8, mode="same"))
    gan = np.clip(nivel / e, 0.5, 2.0)
    gan = np.interp(np.arange(L), (np.arange(nb) + 0.5) * h, gan)
    w = np.clip((np.arange(L) - s0) / (0.5 * SR) + 1.0, 0, 1)
    gan = 1.0 + (gan - 1.0) * w
    a = (a * gan[:, None]).astype(np.float32)
    X = int(0.32 * SR)
    if s1 - s0 < 3 * X:
        X = max(2048, (s1 - s0) // 3)
    mono = a.mean(axis=1).astype(np.float64)
    partes = [a[:s1].astype(np.float32)]
    total = s1
    p = s1  # posición de la fuente donde termina lo copiado
    W = 4096
    P = 600
    partes = [a[:s1].astype(np.float32)]
    while total < n_total:
        lo = s0 + X
        hi = max(lo + 1, p - X - int(0.45 * SR))
        q0 = int(g.integers(lo, hi)) if hi > lo else lo
        # alinear q con la forma de onda alrededor del centro del fundido
        cen_p = p - X // 2
        tpl = mono[cen_p - W // 2: cen_p + W // 2]
        a0 = max(W // 2, q0 - X // 2 - P)
        b0 = min(L - W // 2, q0 - X // 2 + P)
        big = mono[a0 - W // 2: b0 + W // 2]
        if len(big) > len(tpl) and len(tpl) == W:
            cc = np.correlate(big, tpl, mode="valid")
            q = a0 + int(np.argmax(cc)) + X // 2
        else:
            q = q0
        q = int(np.clip(q, X, L - 1))
        xa = a[p - X:p].astype(np.float64)
        xb = a[q - X:q].astype(np.float64)
        ma, mb = xa.mean(axis=1), xb.mean(axis=1)
        rho = float(np.dot(ma, mb) / (np.sqrt(np.dot(ma, ma) * np.dot(mb, mb)) + 1e-12))
        t = (np.arange(X) + 0.5) / X
        ga, gb = np.cos(np.pi * t / 2), np.sin(np.pi * t / 2)
        norm = 1.0 / np.sqrt(np.maximum(0.25, ga ** 2 + gb ** 2 + 2 * rho * ga * gb))
        cruce = (xa * (ga * norm)[:, None] + xb * (gb * norm)[:, None]).astype(np.float32)
        partes[-1] = partes[-1][:-X] if len(partes[-1]) > X else partes[-1][:0]
        partes.append(cruce)
        cuerpo = a[q:p].astype(np.float32)
        partes.append(cuerpo)
        total = sum(len(z) for z in partes)
    y = np.concatenate(partes, axis=0)
    return y[:n_total]


# ============================================== domado de parciales (vibráfonos) ==
# Las láminas del vibráfono tienen afinado el parcial de dos octavas (4·f0): en las notas
# sostenidas (y con arco, siempre) queda como un silbido fijo en la banda de la voz. Las
# láminas graves además tienen el 3er modo (~10,4–10,9·f0, sin afinar) muy fuerte en el ataque
# (resonancias angostas en 2,2–2,9 kHz). muestras.py mide en cada muestra la razón y el nivel
# de esos dos parciales ("modos" en el manifiesto) y la nota los recorta con filtros que
# siguen la transposición. Valores de `domar=1` por banco:
DOMAR_POR_BANCO = {
    # p4_db: recorte del parcial 4·f0 después del ataque (ataque_s) con una rampa (rampa_s)
    # m3_techo_db: el 3er modo queda, como mucho, a este nivel de la fundamental (recorte ≤ m3_max_db)
    "vibrafono": dict(p4_db=-8.0, ataque_s=0.06, rampa_s=0.2, m3_techo_db=-30.0, m3_max_db=36.0),
    "vibrafono_arco": dict(p4_db=-12.0, ataque_s=0.0, rampa_s=0.0, m3_techo_db=-30.0, m3_max_db=36.0),
}


def domar_parciales(y: np.ndarray, f0: float, modos: dict | None, domar: float = 1.0,
                    p4_db: float = -8.0, ataque_s: float = 0.06, rampa_s: float = 0.2,
                    m3_techo_db: float = -30.0, m3_max_db: float = 36.0) -> np.ndarray:
    """Recorta el parcial 4·f0 (dinámico: respeta el ataque) y el 3er modo de la lámina de una
    nota (y: (n, 2) que empieza en el ataque; f0 de la nota). `domar` escala los recortes en dB
    (0 = timbre crudo, 1 = el de `DOMAR_POR_BANCO`, 2 = el doble)."""
    if not modos or domar <= 0 or len(y) == 0:
        return y
    n = len(y)
    y = np.asarray(y, dtype=np.float32)
    p4 = modos.get("p4") or {}
    fc = float(p4.get("razon", 4.0)) * f0
    if p4_db < 0 and fc < 0.45 * SR:
        g_fin = float(desde_db(p4_db * domar))
        g = np.full(n, g_fin, dtype=np.float64)
        na = min(n, int(ataque_s * SR))
        g[:na] = 1.0
        nr = min(n - na, int(rampa_s * SR))
        if nr > 0:
            g[na:na + nr] = 1.0 + (g_fin - 1.0) * rampa(nr)
        bp = sosf(biquad("banda", fc, 6.0), y)
        y = (y - bp * (1.0 - g)[:, None].astype(np.float32)).astype(np.float32)
    m3 = modos.get("m3") or {}
    fc = float(m3.get("razon", 10.5)) * f0
    corte = min(m3_max_db, max(0.0, float(m3.get("db_ataque", -200.0)) - m3_techo_db)) * domar
    if corte > 0.5 and fc < 0.45 * SR:
        bp = sosf(biquad("banda", fc, 8.0), y)
        y = (y - bp * np.float32(1.0 - desde_db(-corte))).astype(np.float32)
    return y


# ======================================================= cruce de capas ======
# Las capas de dinámica de una misma nota son la misma cuerda o lámina grabada dos veces:
# después de corregir la afinación quedan en fase fija (correlación de −0,98 a +0,99 en el
# piano, el vibráfono, el glock, el arpa, los pizzicatos y el contrabajo solista). Sumadas
# tal cual, el cruce cancelaba (La4 del piano a vel 0,6 sonaba 3 dB menos que la capa suave
# sola). Las secciones de cuerdas, en cambio, son casi incoherentes (|r| < 0,4).
_ALINEACION: dict = {}


def _desplazar(x: np.ndarray, k: int) -> np.ndarray:
    """Retrasa (k > 0) o adelanta (k < 0) x en k muestras, sin cambiar el largo."""
    if k == 0:
        return x
    out = np.zeros_like(x)
    if abs(k) >= len(x):
        return out
    if k > 0:
        out[k:] = x[:len(x) - k]
    else:
        out[:len(x) + k] = x[-k:]
    return out


def _alinear(ref: np.ndarray, otro: np.ndarray, L: int):
    """(desfase, polaridad, r): desfase (≤ L muestras) y polaridad que maximizan la correlación
    de `otro` con `ref`; (0, 1, r0) si las señales casi no se parecen (|r| < 0,3)."""
    e = np.sqrt(np.dot(ref, ref) * np.dot(otro, otro)) + 1e-30
    if e < 1e-24 or len(ref) < 64:
        return 0, 1, 0.0
    N = sfft.next_fast_len(len(ref) + len(otro), real=True)
    c = sfft.irfft(sfft.rfft(ref, N) * np.conj(sfft.rfft(otro, N)), N)
    lags = np.concatenate([np.arange(0, L + 1), np.arange(-L, 0)])
    vals = np.concatenate([c[:L + 1], c[N - L:]]) / e
    j = int(np.argmax(np.abs(vals)))
    r = float(vals[j])
    if abs(r) < 0.3:
        return 0, 1, float(c[0] / e)
    return int(lags[j]), (1 if r >= 0 else -1), r


def _ganancia_local(tr, W, n, hop=2400, win=19200):
    """Compensación que sigue el tiempo (capas coherentes y largas: su fase relativa deriva):
    potencias y correlación K en ventanas de 0,4 s cada 50 ms, interpoladas."""
    cs = [np.concatenate([[0.0], np.cumsum((t * t).sum(axis=1))]) for t in tr]
    cx = {}
    for j in range(len(tr)):
        for k in range(j + 1, len(tr)):
            cx[j, k] = np.concatenate([[0.0], np.cumsum((tr[j] * tr[k]).sum(axis=1))])
    c = np.arange(0, n, hop)
    a, b = np.clip(c - win // 2, 0, n), np.clip(c + win // 2, 0, n)
    Wc = [w[c] if w.ndim else np.full(len(c), float(w)) for w in W]
    pt = sum(w * w * (q[b] - q[a]) for w, q in zip(Wc, cs))
    pm = pt.copy()
    for (j, k), q in cx.items():
        pm = pm + 2.0 * Wc[j] * Wc[k] * (q[b] - q[a])
    g = np.sqrt(pt / np.maximum(pm, 1e-12 * pt + 1e-30))
    g = np.clip(np.nan_to_num(g, nan=1.0, posinf=2.0), 0.5, 2.0)
    return np.interp(np.arange(n), c, g)


def mezclar_capas(segs, pesos, ventana, f0: float, clave=None, ventana_pot=None) -> np.ndarray:
    """Suma capas de dinámica (segs: [(n, 2)], pesos: escalares o curvas (n,)) sin cancelaciones.

    1. Cada capa se alinea con la más fuerte (la última): desfase de hasta media onda de la
       fundamental (≤ 6 ms) y polaridad, si están correlacionadas (en `ventana`).
    2. Se compensa la potencia K-ponderada: la mezcla suena como Σ peso²·potencia, el cruce
       de potencia constante que se pretende, sin el pozo o el pico de la interferencia. Con
       pesos fijos (percusivos) se mide en `ventana_pot`; con curvas y capas coherentes
       (contrabajo solista), en ventanas que siguen el tiempo (la fase relativa deriva).
    `ventana`, `ventana_pot` = (a, b) en muestras."""
    from ..analisis import _K_SOS
    from scipy.signal import sosfilt
    n = len(segs[0])
    a, b = max(0, int(ventana[0])), min(n, int(ventana[1]))
    if b - a < 256:
        a, b = 0, n
    ref = len(segs) - 1
    L = max(1, min(int(0.006 * SR), int(0.5 * SR / max(f0, 20.0)) + 1))
    m_ref = segs[ref][a:b].astype(np.float64).mean(axis=1)
    out = list(segs)
    coherentes = False
    for k in range(len(segs)):
        if k == ref:
            continue
        clave_k = None if clave is None else (clave, k, a, b)
        al = _ALINEACION.get(clave_k) if clave_k is not None else None
        if al is None:
            al = _alinear(m_ref, segs[k][a:b].astype(np.float64).mean(axis=1), L)
            if clave_k is not None:
                _ALINEACION[clave_k] = al
        lag, signo, r = al
        coherentes = coherentes or abs(r) >= 0.3
        if lag or signo < 0:
            out[k] = _desplazar(segs[k], lag) * np.float32(signo)
    W = [np.asarray(w, dtype=np.float64) for w in pesos]
    if coherentes and any(w.ndim for w in W) and n > 4800:
        tr = [sosfilt(_K_SOS, s.astype(np.float64) + 1e-18, axis=0) for s in out]
        g = _ganancia_local(tr, W, n)
    else:
        pa, pb = ventana_pot if ventana_pot is not None else (a, b)
        pa, pb = max(0, int(pa)), min(n, int(pb))
        if pb - pa < 256:
            pa, pb = 0, n
        tr = [sosfilt(_K_SOS, s[pa:pb].astype(np.float64) + 1e-18, axis=0) for s in out]
        P = [float(np.sum(t * t)) for t in tr]
        pt = sum(w * w * p for w, p in zip(W, P))
        pm = pt
        for j in range(len(out)):
            for k in range(j + 1, len(out)):
                pm = pm + 2.0 * W[j] * W[k] * float(np.sum(tr[j] * tr[k]))
        g = np.sqrt(np.asarray(pt, dtype=np.float64) / np.maximum(np.asarray(pm, dtype=np.float64),
                                                                    1e-12 * np.asarray(pt) + 1e-30))
        g = np.clip(np.nan_to_num(g, nan=1.0, posinf=2.0), 0.5, 2.0)
    y = np.zeros((n, 2), dtype=np.float32)
    for w, s in zip(W, out):
        y += s * (np.float32(w) if w.ndim == 0 else w[:, None].astype(np.float32))
    return y * (np.float32(g) if np.ndim(g) == 0 else g[:, None].astype(np.float32))


class Muestreador(Instrumento):
    """Instrumento genérico de muestras con capas de velocidad.

    * banco      : nombre en manifest.json ("piano", "arpa", "violines", …)
    * rango_db   : rango dinámico de la velocidad (vel 1 = 0 dB)
    * capas_vel  : velocidades donde empieza y termina el cruce entre capas
    * ataque     : fundido de entrada (s) · soltar: caída al soltar (s)
    * sostener   : True = la nota suena hasta apagarse sola (arpa, glock),
                   salvo que la nota tenga apagar=True
    * largo_max  : tope de duración cuando sostiene (s)
    * abrir      : paneo según altura (graves a la izquierda, agudos a la derecha)
    * ancho      : ancho estéreo de la muestra · tope_hz: pasabajos fijo

    Curva de nivel: calibración + rango_db·(vel^curva − 1) + el cruce de capas en potencia
    (la capa suave está `capas_db` por debajo de la fuerte, ver muestras.py): siempre monótona.
    """
    bucle = False   # True = las notas más largas que la muestra se alargan con bucles

    def __init__(self, banco: str, rango_db=24.0, curva=1.0, capas_vel=(0.3, 0.85),
                 ataque=0.0015, soltar=0.3, sostener=False, largo_max=10.0, pan=0.0,
                 abrir=0.0, ancho=1.0, tope_hz=None, ganancia_db=0.0, transponer=0):
        self.banco_nombre = banco
        self.rango_db, self.curva, self.capas_vel = rango_db, curva, capas_vel
        self.ataque, self.soltar, self.sostener, self.largo_max = ataque, soltar, sostener, largo_max
        self.pan, self.abrir, self.ancho, self.tope_hz = pan, abrir, ancho, tope_hz
        self.ganancia_db, self.transponer = ganancia_db, transponer
        self.nombre = banco
        # calibración: una nota a vel 0.6 ronda −26 LUFS (ver README y NIVELES.md)
        self.calib_db = self.CALIB.get(banco, 0.0)

    # medida con muestras.py (VERSION_NIVEL) y NIVELES.md: mediana a vel 0,6 en las alturas de
    # las muestras = −26 LUFS (sostenidos: tramo estable; percusivos: primeros 2 s)
    CALIB = {"piano": 10.4, "arpa": 9.6, "glock": 9.6, "vibrafono": 6.9, "vibrafono_arco": 2.4,
             "violines": 3.2, "violas": 3.1, "chelos": 3.4, "contrabajo": 2.3,
             "violines_trem": 3.3, "violas_trem": 3.1, "chelos_trem": 3.4,
             "violines_pizz": 6.8, "chelos_pizz": 7.8, "contrabajo_pizz": 9.5}

    @property
    def banco(self) -> Banco:
        return Banco.de(self.banco_nombre)

    # ------------------------------------------------------------ helpers
    def pesos_capas(self, vel: float):
        L = self.banco.n_capas
        if L == 1:
            return [(0, 1.0)]
        v0, v1 = self.capas_vel
        p = np.clip((vel - v0) / max(1e-6, v1 - v0), 0, 1) * (L - 1)
        c0 = int(np.floor(p))
        f = p - c0
        if c0 >= L - 1:
            return [(L - 1, 1.0)]
        if f < 0.04:
            return [(c0, 1.0)]
        if f > 0.96:
            return [(c0 + 1, 1.0)]
        # potencia constante entre capas
        return [(c0, float(np.cos(f * np.pi / 2))), (c0 + 1, float(np.sin(f * np.pi / 2)))]

    def soltar_de(self, midi: float, nt) -> float:
        return float(nt.x.get("soltar", self.soltar))

    def ganancia(self, vel: float) -> float:
        return float(desde_db(self.calib_db + self.ganancia_db +
                              self.rango_db * (max(vel, 1e-3) ** self.curva - 1)))

    def pan_de(self, midi: float, nt) -> float:
        p = nt.x.get("pan", self.pan)
        if self.abrir:
            p += self.abrir * np.clip((midi - 62) / 24, -1, 1)
        return float(np.clip(p, -1, 1))

    def filtrar_muestra(self, seg: np.ndarray, i: int, midi: float) -> np.ndarray:
        """Filtro propio de cada muestra (por defecto, ninguno; los vibráfonos doman parciales)."""
        return seg

    def leer(self, midi, capa, n_total, offset, clave, sostenida=False, semilla=0, excluir=(),
             cents=0.0):
        """Audio (n_total, 2) de la capa para esa altura, transpuesto y alargado si hace falta.
        `excluir`: índices de muestras a evitar · `cents`: desafinación extra (sin cambiar la
        muestra elegida)."""
        b = self.banco
        i = b.elegir(midi, capa, clave, excluir)
        semis = midi - b.midi[i] - b.cents[i] / 100.0 + cents / 100.0
        ratio = 2.0 ** (semis / 12)
        n_in = int((n_total + offset) * ratio) + 64
        a = b.remuestreado(i, semis, n_in)
        if sostenida and len(a) < n_total + offset:
            k = ("ext", b.nombre, i, round(ratio, 7))
            ext = CACHE.get(k)
            if ext is None or len(ext) < n_total + offset:
                ext = extender(b.remuestreado(i, semis, None), int((n_total + offset) * 1.15) + SR,
                               (b.nombre, i, round(ratio, 6)))
                CACHE.put(k, ext)
            a = ext
        seg = a[offset: offset + n_total]
        seg = _a_estereo(np.asarray(seg, dtype=np.float32)) * np.float32(desde_db(b.ajuste_db[i]))
        if len(seg) < n_total:
            seg = np.concatenate([seg, np.zeros((n_total - len(seg), 2), np.float32)])
        return self.filtrar_muestra(seg, i, midi)

    def leer_capas(self, midi, pesos, n_total, offset, clave, sostenida=False):
        """Suma de las capas [(capa, peso)] de la nota: peso escalar o curva (n_total,).
        Con dos capas alinea y compensa la potencia (ver `mezclar_capas`)."""
        if len(pesos) == 1:
            capa, w = pesos[0]
            y = self.leer(midi, capa, n_total, offset, clave, sostenida=sostenida)
            return y * (np.float32(w) if np.ndim(w) == 0 else np.asarray(w, np.float32)[:, None])
        segs = [self.leer(midi, c, n_total, offset, clave, sostenida=sostenida) for c, _ in pesos]
        idx = tuple(self.banco.elegir(midi, c, clave) for c, _ in pesos)
        # alineación en el ataque (o el arranque del sostenido); potencia en el primer segundo
        ventana, ventana_pot = (((0.15 * SR, 1.5 * SR), (0.15 * SR, 2.0 * SR)) if sostenida
                                else ((0, 0.35 * SR), (0, 1.0 * SR)))
        f0 = 440.0 * 2 ** ((midi - 69) / 12)
        return mezclar_capas(segs, [w for _, w in pesos], ventana, f0,
                             clave=(self.banco_nombre, idx, round(float(midi), 4), int(offset)),
                             ventana_pot=ventana_pot)

    def fin_sonoro(self, nt, tempo) -> float:
        """Fin (en tiempos) de lo que suena de la nota (para revisar_grave). Si deja sonar
        (arpa, glock, pizzicato) cuenta hasta que la muestra cae 30 dB, con tope largo_max."""
        fin = nt.t + nt.dur
        if not self.sostener or nt.x.get("apagar"):
            return fin
        b = self.banco
        midi = nt.midi + self.transponer
        i = b.elegir(midi, 0)
        s = min(self.largo_max, b.caida_s(i) / 2.0 ** ((midi - b.midi[i]) / 12.0))
        return max(fin, float(tempo.tiempos(float(tempo.seg(nt.t)) + s)))

    def post_nota(self, y, nt, midi, ctx, pista, n_on):
        return y

    def render(self, notas, ctx, pista):
        out = super().render(notas, ctx, pista)
        if self.tope_hz:  # filtro fijo: aplicarlo a la suma equivale a hacerlo nota por nota
            out = sosf(biquad("pb", self.tope_hz, 0.6), out)
        return out

    # ------------------------------------------------------------ voz
    def voz(self, nt, ctx, pista):
        midi = nt.midi + self.transponer
        i0 = ctx.muestra(nt.t)
        n_on = max(32, self.fin_nota(nt, ctx, pista) - i0)
        if self.sostener and not nt.x.get("apagar"):
            # suena hasta apagarse sola: el largo natural de la muestra (tope largo_max)
            b = self.banco
            i = b.elegir(midi, 0)
            natural = int(b.dur[i] * SR / 2.0 ** ((midi - b.midi[i]) / 12.0))
            n_on = min(int(self.largo_max * SR), max(n_on, natural))
        n_sol = int(self.soltar_de(midi, nt) * SR)
        n_total = n_on + n_sol
        clave = int(round(nt.t * 4)) + int(midi)
        y = self.leer_capas(midi, self.pesos_capas(nt.vel), n_total, 0, clave, sostenida=self.bucle)
        y *= envolvente_nota(n_total, n_on, nt.x.get("ataque", self.ataque), n_sol / SR)[:, None]
        y = self.post_nota(y, nt, midi, ctx, pista, n_on)
        y *= np.float32(self.ganancia(nt.vel))
        y = _balance(y, self.pan_de(midi, nt), self.ancho)
        return y, i0


# =================================================================== piano ==
class Piano(Muestreador):
    """Piano de fieltro: piano vertical real (VCSL, Knight) tocado suave y apagado con fieltro.

    * fieltro  : 0..1, cuánto se oscurece y se ablanda el ataque
    * brillo   : 0..1, corrimiento general del pasabajos
    * mecanica : 0..1, ruiditos reales de apagadores (muestras de "release") y del pedal
    * Usa pedal de resonancia: `pista.pedal_por_compas(...)` o `pista.pedal(a, b)`.
    * Al subir el pedal caen juntos los apagadores de todas las notas que sostenía: el ruido
      de cada uno se reparte en ~25 ms y su nivel baja con √k (k = notas apagadas a la vez),
      así no hay golpe. Igual se apagan todas: para que el último acorde se extinga solo,
      subí el pedal después del final de la canción.
    """
    usa_pedal = True
    CALIB_RUIDOS = 4.7    # calibración con la que se ajustó el nivel de los apagadores

    def __init__(self, fieltro=0.65, brillo=0.5, mecanica=0.5, rango_db=26.0, **kw):
        kw.setdefault("capas_vel", (0.35, 0.9))
        kw.setdefault("ataque", 0.002)
        super().__init__("piano", rango_db=rango_db, **kw)
        self.fieltro, self.brillo, self.mecanica = fieltro, brillo, mecanica
        self.nombre = "piano"
        self._apagados: dict = {}

    def soltar_de(self, midi, nt):
        if "soltar" in nt.x:
            return nt.x["soltar"]
        if midi >= 89:  # sin apagadores en el agudo extremo
            return 1.8
        return float(np.interp(midi, [36, 60, 84], [0.5, 0.3, 0.16]))

    def corte(self, midi, vel):
        base = 1600.0 * 2 ** (1.6 * (self.brillo - 0.5)) * 2 ** (-1.1 * self.fieltro)
        return float(np.clip(base * 2 ** (2.6 * vel) * 2 ** ((midi - 60) / 22), 500, 12000))

    def post_nota(self, y, nt, midi, ctx, pista, n_on):
        fc = self.corte(midi, nt.vel)
        y2 = sosf(biquad("pb", fc, 0.62), y)
        if self.fieltro > 0:
            # ataque de fieltro: arranca más oscuro y se abre en ~30 ms
            na = min(len(y2), int((0.012 + 0.03 * self.fieltro) * SR))
            if na > 8:
                muy = sosf(biquad("pb", max(250.0, fc * 0.3), 0.6), y[:na])
                w = rampa(na)[:, None]
                y2[:na] = muy * (1 - w) + y2[:na] * w
        y2 = y2.astype(np.float32)
        # ruido de apagador al soltar (muestras reales de release)
        if self.mecanica > 0 and midi < 89:
            try:
                rb = Banco.de("piano_soltar")
                i = rb.elegir(midi, 0)
                r = cortar(np.asarray(rb.audio(i)), int(0.9 * SR), 0.08)
                k = self._apagados.get(id(nt), 1)          # notas que apaga el mismo pedal
                # el ruido pasa después por la ganancia de la nota: se descuenta el cambio de
                # calibración para que su nivel no dependa de la nivelación del piano
                g = (desde_db(rb.ajuste_db[i] - 15 + 6 * nt.vel + self.CALIB_RUIDOS - self.calib_db)
                     * self.mecanica / np.sqrt(k))
                r = _a_estereo(r) * np.float32(g)
                r = sosf(biquad("pb", 2500.0, 0.6), r)
                ini = min(n_on, len(y2) - 1)
                if k > 1:   # los apagadores no caen en la misma muestra: se reparten en ~25 ms
                    ini += int(rng(ctx.semilla, "apagador", round(nt.t * 480), int(midi)).uniform(0, 0.025) * SR)
                if ini + len(r) > len(y2):
                    y2 = np.concatenate([y2, np.zeros((ini + len(r) - len(y2), 2), np.float32)])
                y2[ini:ini + len(r)] += r
            except KeyError:
                pass
        return y2

    def render(self, notas, ctx, pista):
        # notas que se apagan juntas al subir cada pedal (para repartir sus apagadores)
        self._apagados = {}
        if pista is not None and pista.pedales:
            grupos: dict = {}
            for nt in notas:
                t_fin = nt.t + nt.dur
                abajo, t_sube = pista.pedal_abajo_en(t_fin - 1e-6)
                if abajo and t_sube > t_fin:
                    grupos.setdefault(round(t_sube, 6), []).append(id(nt))
            for ids in grupos.values():
                for k in ids:
                    self._apagados[k] = len(ids)
        out = super().render(notas, ctx, pista)
        self._apagados = {}
        if self.mecanica > 0 and pista is not None and pista.pedales:
            try:
                pb = Banco.de("piano_pedal")
            except KeyError:
                return out
            on = [i for i, e in enumerate(pb.muestras) if "on" in e.get("articulacion", "")]
            off = [i for i, e in enumerate(pb.muestras) if "off" in e.get("articulacion", "")]
            for k, (a, b) in enumerate(pista.pedales):
                for t, lista, gdb in ((a, on, -30), (b, off, -33)):
                    if not lista:
                        continue
                    i = lista[k % len(lista)]
                    s = _a_estereo(cortar(np.asarray(pb.audio(i)), int(1.2 * SR), 0.15))
                    s = s * np.float32(desde_db(gdb) * self.mecanica)
                    s = sosf(biquad("pb", 1800.0, 0.6), s)
                    mezclar_en(out, s, ctx.muestra(t))
        return out


# ===================================================== percusión afinada ====
class Arpa(Muestreador):
    """Arpa de concierto (VCSL). Deja sonar las cuerdas (apagar=True en la nota para cortar)."""

    def __init__(self, rango_db=22.0, largo_max=6.0, **kw):
        kw.setdefault("capas_vel", (0.45, 0.95))
        kw.setdefault("abrir", 0.25)
        kw.setdefault("tope_hz", 9000.0)
        super().__init__("arpa", rango_db=rango_db, sostener=True, largo_max=largo_max,
                         soltar=0.25, **kw)
        self.nombre = "arpa"


class Glock(Muestreador):
    """Glockenspiel (VCSL, 3 capas). Suena tal cual se escribe (rango G5–C8)."""

    def __init__(self, rango_db=20.0, largo_max=4.5, **kw):
        kw.setdefault("capas_vel", (0.3, 0.9))
        kw.setdefault("tope_hz", 10000.0)
        super().__init__("glock", rango_db=rango_db, sostener=True, largo_max=largo_max,
                         soltar=0.2, **kw)
        self.nombre = "glock"


class _Domado:
    """Mezcla para los vibráfonos: cada muestra pasa por `domar_parciales` (sus modos medidos)."""
    domar = 1.0

    def filtrar_muestra(self, seg, i, midi):
        if self.domar <= 0:
            return seg
        b = self.banco
        f0 = 440.0 * 2 ** ((midi - 69) / 12)
        return domar_parciales(seg, f0, b.muestras[i].get("modos"), self.domar,
                               **DOMAR_POR_BANCO.get(b.nombre, {}))


class Vibrafono(_Domado, Muestreador):
    """Vibráfono con baquetas blandas (VCSL) y motor simulado.

    El motor modula en amplitud la banda de la fundamental (como los discos de
    los resonadores), con fase global para que todas las notas laten juntas.
    * motor_hz: velocidad del motor (0 = apagado) · motor_prof: 0..1
    * domar: cuánto se doman el parcial 4·f0 (−8 dB después del ataque) y el 3er modo de las
      láminas graves (a ≤ −30 dB de la fundamental): 0 = timbre crudo, 1 = normal, 2 = el doble
    * Usa pedal (pista.pedal...) y apaga al soltar."""
    usa_pedal = True

    def __init__(self, motor_hz=5.0, motor_prof=0.35, rango_db=22.0, domar=1.0, **kw):
        kw.setdefault("capas_vel", (0.3, 0.85))
        kw.setdefault("soltar", 0.35)
        kw.setdefault("tope_hz", 9000.0)
        super().__init__("vibrafono", rango_db=rango_db, **kw)
        self.motor_hz, self.motor_prof, self.domar = motor_hz, motor_prof, domar
        self.nombre = "vibrafono"

    def post_nota(self, y, nt, midi, ctx, pista, n_on):
        if self.motor_hz <= 0 or self.motor_prof <= 0:
            return y
        f0 = 440 * 2 ** ((midi - 69) / 12)
        low = sosf(biquad("pb", f0 * 1.6, 0.7), y)
        t = (ctx.muestra(nt.t) + np.arange(len(y))) / SR
        am = 1 - self.motor_prof * (0.5 + 0.5 * np.sin(2 * np.pi * self.motor_hz * t))
        return (y - low + low * am[:, None]).astype(np.float32)


class VibrafonoArco(_Domado, Muestreador):
    """Vibráfono frotado con arco (VCSL, sin motor): notas largas que aparecen despacio, sin
    ataque; la lámina sigue sonando al soltar. Notas más largas que la muestra: bucles.
    * domar: recorte del parcial 4·f0 (−12 dB con domar=1), el silbido fijo de 2,2–2,4 kHz
      que deja el arco en la banda de la voz (0 = timbre crudo)
    * La muestra de La3 está defectuosa (catálogo): debajo de Mi4 se transpone Mi4 (rango útil desde Do4).
    """
    bucle = True

    def __init__(self, rango_db=20.0, ataque=0.3, soltar=2.5, domar=1.0, **kw):
        kw.setdefault("tope_hz", 9000.0)
        kw.setdefault("abrir", 0.15)
        super().__init__("vibrafono_arco", rango_db=rango_db, ataque=ataque, soltar=soltar, **kw)
        self.domar = domar
        self.nombre = "vibrafono_arco"


# ================================================================ cuerdas ===
def cadena_de_banco(banco: str) -> dict:
    """Cómo suena por defecto cada banco después de leer la muestra: paneo, ancho estéreo,
    paneo por altura (`abrir`) y pasabajos fijo (`tope_hz`). La nivelación se mide con esta
    misma cadena: el cierre M/S quita más nivel a las muestras más abiertas (en el contrabajo,
    hasta 2,4 dB entre vecinas) y el pasabajos, más a las más brillantes (glock: 1,7 dB)."""
    base = banco.split("_")[0]
    if base in Cuerdas.PAN:      # cuerdas, trémolos y pizzicatos: paneo y cierre por sección
        return dict(pan=Cuerdas.PAN[base], ancho=Cuerdas.ANCHO[base], abrir=0.0, tope_hz=None)
    return {"arpa": dict(pan=0.0, ancho=1.0, abrir=0.25, tope_hz=9000.0),
            "glock": dict(pan=0.0, ancho=1.0, abrir=0.0, tope_hz=10000.0),
            "vibrafono": dict(pan=0.0, ancho=1.0, abrir=0.0, tope_hz=9000.0),
            "vibrafono_arco": dict(pan=0.0, ancho=1.0, abrir=0.15, tope_hz=9000.0),
            }.get(banco, dict(pan=0.0, ancho=1.0, abrir=0.0, tope_hz=None))


class Cuerdas(Muestreador):
    """Sección de cuerdas real (VSCO-2 CE) con crescendos que cambian de timbre.

    * banco: "violines", "violas", "chelos", "contrabajo" (o "*_trem" para trémolo)
    * La dinámica de cada nota es vel (→ vel_fin si se indica en la nota, con
      curva suave) multiplicada por la automatización 'expresion' (0..1) de la
      pista. La dinámica cruza las capas (p → f), sube el volumen y abre el brillo.
    * legato=True en la nota (o "_" en la mini-notación): entra sin el golpe de
      arco y con ataque lento, fundiéndose con la anterior.
    * doble=True: duplica con otra muestra levemente desplazada (sección más grande).
    """

    PAN = {"violines": -0.35, "violas": 0.12, "chelos": 0.3, "contrabajo": 0.42}
    # las muestras de sección son muy abiertas (pares espaciados): se cierran un poco para
    # que la imagen tenga centro y sea compatible en mono (el contrabajo, casi mono)
    ANCHO = {"violines": 0.7, "violas": 0.9, "chelos": 0.8, "contrabajo": 0.5}

    def __init__(self, banco="violines", rango_db=22.0, ataque=0.08, soltar=0.55, doble=False,
                 legato_offset=0.11, **kw):
        base = banco.split("_")[0]
        kw.setdefault("pan", self.PAN.get(base, 0.0))
        kw.setdefault("ancho", self.ANCHO.get(base, 1.0))
        kw.setdefault("capas_vel", (0.3, 0.8))
        super().__init__(banco, rango_db=rango_db, ataque=ataque, soltar=soltar, **kw)
        self.doble, self.legato_offset = doble, legato_offset
        self.nombre = banco

    def voz(self, nt, ctx, pista):
        midi = nt.midi + self.transponer
        i0 = ctx.muestra(nt.t)
        n_on = max(32, self.fin_nota(nt, ctx, pista) - i0)
        n_sol = int(nt.x.get("soltar", self.soltar) * SR)
        n_total = n_on + n_sol
        legato = bool(nt.x.get("legato"))
        offset = int(self.legato_offset * SR) if legato else 0
        ataque = nt.x.get("ataque", 0.17 if legato else self.ataque)
        clave = int(round(nt.t * 4)) + int(midi)
        # dinámica en el tiempo
        v0 = nt.vel
        v1 = nt.x.get("vel_fin", v0)
        f = np.linspace(0, 1, n_total)
        f = np.clip(f * n_total / max(1, n_on), 0, 1)
        dyn = v0 + (v1 - v0) * (0.5 - 0.5 * np.cos(np.pi * f))
        if pista is not None and "expresion" in pista.autos:
            dyn = dyn * pista.autos["expresion"].en_muestras(n_total, ctx.tempo, i0)
        dyn = np.clip(dyn, 0.0, 1.0)
        L = self.banco.n_capas
        if L >= 2:
            a, b = self.capas_vel
            w1 = np.clip((dyn - a) / (b - a), 0, 1)
            w1 = w1 * w1 * (3 - 2 * w1)
            pesos = [(c, w) for c, w in ((0, np.cos(w1 * np.pi / 2)), (L - 1, np.sin(w1 * np.pi / 2)))
                     if w.max() >= 0.02]
            y = self.leer_capas(midi, pesos, n_total, offset, clave, sostenida=True)
        else:
            y = self.leer(midi, 0, n_total, offset, clave, sostenida=True)
        if self.doble:
            # la copia es otra muestra (otra toma o la vecina), 5 cents arriba y 13 ms después;
            # pasa por leer(): misma nivelación, exclusiones y filtros que la principal
            capa = 0 if dyn.mean() < 0.55 else L - 1
            i_pri = self.banco.elegir(midi, capa, clave)
            d = int(0.013 * SR)
            s2 = self.leer(midi, capa, n_total, offset, clave + 1, sostenida=True,
                           excluir=(i_pri,), cents=5.0) * np.float32(desde_db(-4.0))
            s2 = np.concatenate([np.zeros((d, 2), np.float32), s2])[:n_total]
            # la copia se abre apenas hacia el otro lado (sin invertir canales: imagen
            # compatible en mono)
            lado = 0.3 if self.pan_de(midi, nt) <= 0 else -0.3
            y += _balance(s2, lado)
        env = envolvente_nota(n_total, n_on, ataque, n_sol / SR, "cos")
        gain = desde_db(self.calib_db + self.ganancia_db + self.rango_db * (np.maximum(dyn, 1e-3) ** 0.9 - 1))
        y *= (env * gain)[:, None].astype(np.float32)
        y = _balance(y, self.pan_de(midi, nt), self.ancho)
        return y, i0


def Violines(**kw):
    return Cuerdas("violines", **kw)


def Violas(**kw):
    return Cuerdas("violas", **kw)


def Chelos(**kw):
    return Cuerdas("chelos", **kw)


def Contrabajo(**kw):
    kw.setdefault("rango_db", 20.0)
    return Cuerdas("contrabajo", **kw)


def CuerdasTrem(seccion="chelos", **kw):
    """Trémolo de sección (violines, violas o chelos): tensión, misterio."""
    kw.setdefault("ataque", 0.05)
    return Cuerdas(f"{seccion}_trem", **kw)


class Pizzicato(Muestreador):
    """Pizzicato de sección: "violines", "chelos" o "contrabajo"."""

    def __init__(self, seccion="violines", rango_db=20.0, **kw):
        kw.setdefault("pan", Cuerdas.PAN.get(seccion, 0.0))
        kw.setdefault("ancho", Cuerdas.ANCHO.get(seccion, 1.0))
        kw.setdefault("capas_vel", (0.35, 0.9))
        super().__init__(f"{seccion}_pizz", rango_db=rango_db, sostener=True, largo_max=2.5,
                         soltar=0.15, **kw)
        self.nombre = f"{seccion}_pizz"
