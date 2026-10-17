"""Efectos y procesos de audio (numba donde hay recursión muestra a muestra).

Efectos de inserción para pistas (se pasan en `efectos=[...]` de `C.pista`):
    EQ, Filtro, Saturacion, Chorus, Tremolo, Ducking, Compresor, Ancho, Paneo
Todos aceptan parámetros fijos o `Auto(...)` donde se indica.

Procesos de bus (los usa mezcla.py): reverb por convolución con IR generada,
sala corta, eco sincronizado, cinta, compresor de bus, limitador true-peak.
"""
from __future__ import annotations

import numpy as np
import numba as nb
import scipy.fft as sfft
import soxr
from scipy.signal import sosfilt, stft, istft

from .nucleo import SR, valor, desde_db, rng, ruido_suave

FFT_HILOS = 2


# =========================================================== núcleos numba ==
@nb.njit(cache=True, fastmath=True)
def _svf(x, g_arr, k, modo):
    """Filtro de estado variable TPT (Zavalishin). g = tan(pi fc / sr), k = 1/Q.
    modo 0 = pasabajos, 1 = pasaaltos, 2 = pasabanda (ganancia unidad en el pico)."""
    n = x.shape[0]
    y = np.empty(n)
    ic1 = 0.0
    ic2 = 0.0
    for i in range(n):
        g = g_arr[i]
        a1 = 1.0 / (1.0 + g * (g + k))
        a2 = g * a1
        a3 = g * a2
        v3 = x[i] + 1e-20 - ic2
        v1 = a1 * ic1 + a2 * v3
        v2 = ic2 + a2 * ic1 + a3 * v3
        ic1 = 2.0 * v1 - ic1
        ic2 = 2.0 * v2 - ic2
        if modo == 0:
            y[i] = v2
        elif modo == 1:
            y[i] = x[i] - k * v1 - v2
        else:
            y[i] = k * v1
    return y


@nb.njit(cache=True, fastmath=True)
def _retardo_variable(x, d):
    """Retardo fraccional variable (d en muestras, >= 2) con interpolación Hermite cúbica."""
    n = x.shape[0]
    y = np.zeros(n)
    for i in range(n):
        pos = i - d[i]
        j = int(np.floor(pos))
        f = pos - j
        if j - 1 < 0 or j + 2 >= n:
            continue
        xm1 = x[j - 1]
        x0 = x[j]
        x1 = x[j + 1]
        x2 = x[j + 2]
        c1 = 0.5 * (x1 - xm1)
        c2 = xm1 - 2.5 * x0 + 2.0 * x1 - 0.5 * x2
        c3 = 0.5 * (x2 - xm1) + 1.5 * (x0 - x1)
        y[i] = ((c3 * f + c2) * f + c1) * f + x0
    return y


@nb.njit(cache=True, fastmath=True)
def _eco(xl, xr, d, fb, a_lp, a_hp, pingpong):
    """Delay estéreo con realimentación filtrada (pasabajos + pasaaltos de 1 polo)."""
    n = xl.shape[0]
    yl = np.zeros(n)
    yr = np.zeros(n)
    bl = np.zeros(d)
    br = np.zeros(d)
    lpl = 0.0
    lpr = 0.0
    hpl = 0.0
    hpr = 0.0
    idx = 0
    for i in range(n):
        rl = bl[idx]
        rr = br[idx]
        # filtros en el lazo: cada repetición más oscura y sin graves
        lpl += a_lp * (rl - lpl)
        lpr += a_lp * (rr - lpr)
        hpl += a_hp * (lpl - hpl)
        hpr += a_hp * (lpr - hpr)
        fl = lpl - hpl
        fr = lpr - hpr
        if abs(lpl) < 1e-25:
            lpl = 0.0
            hpl = 0.0
        if abs(lpr) < 1e-25:
            lpr = 0.0
            hpr = 0.0
        if pingpong:
            bl[idx] = 0.5 * (xl[i] + xr[i]) + fb * fr
            br[idx] = fb * fl
        else:
            bl[idx] = xl[i] + fb * fl
            br[idx] = xr[i] + fb * fr
        yl[i] = rl
        yr[i] = rr
        idx += 1
        if idx >= d:
            idx = 0
    return yl, yr


@nb.njit(cache=True, fastmath=True)
def _seguidor(x, a_at, a_rel):
    """Envolvente con ataque y relajación (coeficientes de 1 polo)."""
    n = x.shape[0]
    y = np.empty(n)
    e = 0.0
    for i in range(n):
        v = x[i]
        if v > e:
            e += a_at * (v - e)
        else:
            e += a_rel * (v - e)
            if e < 1e-30 and e > -1e-30:
                e = 0.0
        y[i] = e
    return y


@nb.njit(cache=True, fastmath=True)
def _min_adelante(g, L):
    """Mínimo deslizante hacia adelante: out[i] = min(g[i : i+L]) (deque monotónica)."""
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


@nb.njit(cache=True, fastmath=True)
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


def coef(tiempo_s: float) -> float:
    """Coeficiente de un polo para una constante de tiempo dada (s)."""
    return 1.0 - np.exp(-1.0 / max(1.0, tiempo_s * SR))


# ============================================================ biquads (RBJ) ==
def biquad(tipo: str, f: float, q: float = 0.707, g_db: float = 0.0):
    """Coeficientes sos (1, 6) para sosfilt. tipo: pb pa banda campana graves agudos notch."""
    A = 10 ** (g_db / 40)
    w = 2 * np.pi * min(f, SR * 0.49) / SR
    cw, sw = np.cos(w), np.sin(w)
    al = sw / (2 * q)
    if tipo == "pb":
        b = [(1 - cw) / 2, 1 - cw, (1 - cw) / 2]
        a = [1 + al, -2 * cw, 1 - al]
    elif tipo == "pa":
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
        a = [1 + al, -2 * cw, 1 - al]
    elif tipo == "banda":
        b = [al, 0, -al]
        a = [1 + al, -2 * cw, 1 - al]
    elif tipo == "notch":
        b = [1, -2 * cw, 1]
        a = [1 + al, -2 * cw, 1 - al]
    elif tipo == "campana":
        b = [1 + al * A, -2 * cw, 1 - al * A]
        a = [1 + al / A, -2 * cw, 1 - al / A]
    elif tipo in ("graves", "agudos"):
        s = 1.0
        al = sw / 2 * np.sqrt((A + 1 / A) * (1 / s - 1) + 2)
        sa = 2 * np.sqrt(A) * al
        if tipo == "graves":
            b = [A * ((A + 1) - (A - 1) * cw + sa), 2 * A * ((A - 1) - (A + 1) * cw),
                 A * ((A + 1) - (A - 1) * cw - sa)]
            a = [(A + 1) + (A - 1) * cw + sa, -2 * ((A - 1) + (A + 1) * cw),
                 (A + 1) + (A - 1) * cw - sa]
        else:
            b = [A * ((A + 1) + (A - 1) * cw + sa), -2 * A * ((A - 1) + (A + 1) * cw),
                 A * ((A + 1) + (A - 1) * cw - sa)]
            a = [(A + 1) - (A - 1) * cw + sa, 2 * ((A - 1) - (A + 1) * cw),
                 (A + 1) - (A - 1) * cw - sa]
    else:
        raise ValueError(tipo)
    b = np.array(b) / a[0]
    a = np.array(a) / a[0]
    return np.concatenate([b, a]).reshape(1, 6)


ANTI_DENORMAL = 1e-18  # piso inaudible (−360 dB): evita números denormales (lentísimos)


def sosf(sos: np.ndarray, x: np.ndarray, axis: int = 0) -> np.ndarray:
    """sosfilt rápido y sin denormales; devuelve el mismo dtype de la entrada."""
    y = sosfilt(sos, x + x.dtype.type(ANTI_DENORMAL), axis=axis)
    return y.astype(x.dtype, copy=False)


def filtrar(x: np.ndarray, sos: np.ndarray) -> np.ndarray:
    return sosf(sos, x.astype(np.float32, copy=False))


def una_polo_pb(x: np.ndarray, fc: float) -> np.ndarray:
    a = 1 - np.exp(-2 * np.pi * fc / SR)
    sos = np.array([[a, 0, 0, 1, -(1 - a), 0]])
    return sosf(sos, x)


# ============================================================ efectos pista ==
class Efecto:
    """Interfaz: procesar(x (n,2) float32, ctx, pista) → (n,2)."""

    def procesar(self, x, ctx, pista):
        raise NotImplementedError


class EQ(Efecto):
    """EQ estática por bandas:
        EQ(("pa", 90), ("graves", 200, -2), ("campana", 2500, -3, 1.0), ("agudos", 9000, 2), ("pb", 12000))
    pa/pb: (tipo, f[, q]) · graves/agudos: (tipo, f, dB) · campana: (tipo, f, dB[, q])."""

    def __init__(self, *bandas):
        sos = []
        for b in bandas:
            t = b[0]
            if t in ("pa", "pb"):
                sos.append(biquad(t, b[1], b[2] if len(b) > 2 else 0.707))
            elif t in ("graves", "agudos"):
                sos.append(biquad(t, b[1], 0.707, b[2]))
            elif t == "campana":
                sos.append(biquad(t, b[1], b[3] if len(b) > 3 else 1.0, b[2]))
            else:
                raise ValueError(t)
        self.sos = np.vstack(sos)

    def procesar(self, x, ctx=None, pista=None):
        return filtrar(x, self.sos)


class Filtro(Efecto):
    """Filtro resonante de estado variable con corte automatizable y "respiración".

    Filtro("pasabajos", corte=Auto([(1, 400), (25, 4000, "exp")]), q=0.8, polos=4,
           respira=0.25, respira_hz=0.07)
    * respira: profundidad en octavas de un LFO lento sobre el corte (filtro que respira)
    """
    MODOS = {"pasabajos": 0, "pasaaltos": 1, "pasabanda": 2}

    def __init__(self, tipo="pasabajos", corte=1000.0, q=0.707, polos=2, respira=0.0,
                 respira_hz=0.08, mezcla=1.0):
        self.modo = self.MODOS[tipo]
        self.corte, self.q, self.polos = corte, q, polos
        self.respira, self.respira_hz, self.mezcla = respira, respira_hz, mezcla

    def procesar(self, x, ctx, pista=None):
        n = len(x)
        fc = valor(self.corte, n, ctx.tempo)
        if self.respira:
            t = np.arange(n) / SR
            fase = rng(ctx.semilla, "respira", id(self) % 997).uniform(0, 2 * np.pi)
            lfo = np.sin(2 * np.pi * self.respira_hz * t + fase)
            lfo += 0.35 * np.sin(2 * np.pi * self.respira_hz * 2.37 * t + 1.3 * fase)
            fc = fc * 2.0 ** (self.respira * lfo / 1.35)
        fc = np.clip(fc, 15.0, SR * 0.45)
        g = np.tan(np.pi * fc / SR)
        k = 1.0 / self.q
        y = np.empty_like(x)
        for c in range(x.shape[1]):
            s = x[:, c].astype(np.float64)
            for _ in range(max(1, self.polos // 2)):
                s = _svf(s, g, k if _ == 0 else 1.0 / 0.707, self.modo)
            y[:, c] = s
        if self.mezcla < 1:
            return (x * (1 - self.mezcla) + y * self.mezcla).astype(np.float32)
        return y.astype(np.float32)


class Saturacion(Efecto):
    """Saturación suave (tanh) con compensación: drive en dB, tipo "suave" o "tubo"
    (asimétrica, agrega pares), mezcla paralela y pasabajos posterior opcional."""

    def __init__(self, drive_db=6.0, tipo="suave", mezcla=1.0, pb=None):
        self.drive, self.tipo, self.mezcla, self.pb = drive_db, tipo, mezcla, pb

    def procesar(self, x, ctx=None, pista=None):
        d = float(desde_db(self.drive))
        if self.tipo == "tubo":
            z = d * x + 0.15 * d * x * x
            y = np.tanh(z) / d
            y = filtrar(y, biquad("pa", 12.0))
        else:
            y = np.tanh(d * x) / d
        if self.pb:
            y = filtrar(y, biquad("pb", self.pb))
        if self.mezcla < 1:
            y = x * (1 - self.mezcla) + y * self.mezcla
        return y.astype(np.float32)


@nb.njit(cache=True, fastmath=True)
def _chorus(xl, xr, base, prof, hz, fases, voces, sr):
    """Voces de chorus: retardos modulados por seno (interpolación cúbica), estéreo."""
    n = xl.shape[0]
    yl = np.zeros(n)
    yr = np.zeros(n)
    for v in range(voces):
        for c in range(2):
            f = hz * (1 + 0.23 * v + 0.07 * c)
            fase = fases[2 * v + c]
            b = base + 2.1 * v
            w = 2 * np.pi * f / sr
            for i in range(n):
                d = (b + prof * np.sin(w * i + fase)) * sr / 1000.0
                pos = i - d
                j = int(np.floor(pos))
                fr = pos - j
                if j - 1 < 0 or j + 2 >= n:
                    continue
                if c == 0:
                    xm1 = 0.6 * xl[j - 1] + 0.2 * (xl[j - 1] + xr[j - 1])
                    x0 = 0.6 * xl[j] + 0.2 * (xl[j] + xr[j])
                    x1 = 0.6 * xl[j + 1] + 0.2 * (xl[j + 1] + xr[j + 1])
                    x2 = 0.6 * xl[j + 2] + 0.2 * (xl[j + 2] + xr[j + 2])
                else:
                    xm1 = 0.6 * xr[j - 1] + 0.2 * (xl[j - 1] + xr[j - 1])
                    x0 = 0.6 * xr[j] + 0.2 * (xl[j] + xr[j])
                    x1 = 0.6 * xr[j + 1] + 0.2 * (xl[j + 1] + xr[j + 1])
                    x2 = 0.6 * xr[j + 2] + 0.2 * (xl[j + 2] + xr[j + 2])
                c1 = 0.5 * (x1 - xm1)
                c2 = xm1 - 2.5 * x0 + 2.0 * x1 - 0.5 * x2
                c3 = 0.5 * (x2 - xm1) + 1.5 * (x0 - x1)
                val = (((c3 * fr + c2) * fr + c1) * fr + x0) / voces
                if c == 0:
                    yl[i] += val
                else:
                    yr[i] += val
    return yl, yr


class Chorus(Efecto):
    """Chorus estéreo de 3 voces (retardos modulados, interpolación cúbica)."""

    def __init__(self, mezcla=0.35, base_ms=14.0, prof_ms=3.0, hz=0.35, voces=3):
        self.mezcla, self.base, self.prof, self.hz, self.voces = mezcla, base_ms, prof_ms, hz, voces

    def procesar(self, x, ctx, pista=None):
        g = rng(ctx.semilla, "chorus", pista.nombre if pista else "")
        fases = g.uniform(0, 2 * np.pi, 2 * self.voces)
        yl, yr = _chorus(x[:, 0].astype(np.float64), x[:, 1].astype(np.float64), float(self.base),
                         float(self.prof), float(self.hz), fases, int(self.voces), float(SR))
        y = np.stack([yl, yr], axis=1)
        return (x * (1 - self.mezcla * 0.5) + y * self.mezcla).astype(np.float32)


class Tremolo(Efecto):
    """Trémolo / autopan: hz (o división en tiempos con `division`), prof 0..1,
    estereo=True desfasa L/R (autopan tipo Rhodes Suitcase)."""

    def __init__(self, hz=4.5, prof=0.3, estereo=True, division=None, forma="seno"):
        self.hz, self.prof, self.estereo, self.division, self.forma = hz, prof, estereo, division, forma

    def procesar(self, x, ctx, pista=None):
        n = len(x)
        t = np.arange(n) / SR
        if self.division:
            beats = ctx.tempo.tiempos(t)
            fase = 2 * np.pi * beats / self.division
        else:
            fase = 2 * np.pi * self.hz * t
        prof = valor(self.prof, n, ctx.tempo)
        lfo_l = np.sin(fase)
        lfo_r = np.sin(fase + (np.pi if self.estereo else 0))
        gl = 1 - prof * (0.5 + 0.5 * lfo_l)
        gr = 1 - prof * (0.5 + 0.5 * lfo_r)
        return (x * np.stack([gl, gr], axis=1)).astype(np.float32)


class Ducking(Efecto):
    """Bombeo suave disparado por los golpes de otra pista (sin detector: usa sus notas).

    Ducking(fuente="bateria", golpe="bombo", prof_db=3, ataque_ms=8, relaj_ms=180)
    """

    def __init__(self, fuente="bateria", golpe="bombo", prof_db=3.0, ataque_ms=8.0,
                 relaj_ms=180.0, prof=None):
        self.fuente, self.golpe, self.prof_db = fuente, golpe, prof_db
        self.at, self.rel = ataque_ms, relaj_ms

    def procesar(self, x, ctx, pista=None):
        p = ctx.cancion.pistas.get(self.fuente)
        if p is None:
            return x
        n = len(x)
        imp = np.zeros(n)
        hold = int(0.012 * SR)
        hasta = getattr(ctx, "t_hasta", None)     # --hasta: sin los golpes del corte en adelante
        for nt in p.notas_humanizadas(hasta=hasta):
            if nt.x.get("golpe") != self.golpe:
                continue
            i = ctx.muestra(nt.t)
            if 0 <= i < n:
                imp[i:i + hold] = np.maximum(imp[i:i + hold], nt.vel)
        env = _seguidor(imp, coef(self.at / 1000), coef(self.rel / 1000))
        g = desde_db(-self.prof_db * env)
        return (x * g[:, None]).astype(np.float32)


class Compresor(Efecto):
    """Compresor feed-forward estéreo enlazado (RMS corto), rodilla suave."""

    def __init__(self, umbral_db=-18.0, ratio=2.0, ataque_ms=20.0, relaj_ms=200.0,
                 rodilla_db=6.0, compensar_db=0.0, mezcla=1.0):
        self.u, self.r, self.at, self.rel = umbral_db, ratio, ataque_ms, relaj_ms
        self.kn, self.mk, self.mezcla = rodilla_db, compensar_db, mezcla

    def ganancia(self, x):
        p = (x.astype(np.float64) ** 2).mean(axis=1)
        p = _seguidor(p, coef(0.005), coef(0.005))
        nivel = 10 * np.log10(p + 1e-12)
        sobre = nivel - self.u
        kn = self.kn
        gr = np.where(sobre <= -kn / 2, 0.0,
                      np.where(sobre >= kn / 2, sobre * (1 - 1 / self.r),
                               (1 - 1 / self.r) * (sobre + kn / 2) ** 2 / (2 * kn)))
        gr = _seguidor(gr, coef(self.at / 1000), coef(self.rel / 1000))
        return desde_db(-gr + self.mk)

    def procesar(self, x, ctx=None, pista=None):
        g = self.ganancia(x)
        y = x * g[:, None]
        if self.mezcla < 1:
            y = x * (1 - self.mezcla) + y * self.mezcla
        return y.astype(np.float32)


class Ancho(Efecto):
    """Ancho estéreo M/S: 0 = mono, 1 = igual, >1 = más ancho. Graves mono por debajo de `mono_hz`."""

    def __init__(self, ancho=1.2, mono_hz=None):
        self.ancho, self.mono_hz = ancho, mono_hz

    def procesar(self, x, ctx, pista=None):
        m = (x[:, 0] + x[:, 1]) * 0.5
        s = (x[:, 0] - x[:, 1]) * 0.5
        w = valor(self.ancho, len(x), ctx.tempo)
        s = s * w
        if self.mono_hz:
            s = s - sosf(biquad("pb", self.mono_hz), s)
        return np.stack([m + s, m - s], axis=1).astype(np.float32)


class Paneo(Efecto):
    """Paneo automatizable (balance de potencia constante): Paneo(Auto([(1, -0.4), (9, 0.4)]))."""

    def __init__(self, pan):
        self.pan = pan

    def procesar(self, x, ctx, pista=None):
        p = np.clip(valor(self.pan, len(x), ctx.tempo), -1, 1)
        a = (p + 1) * np.pi / 4
        gl = np.minimum(1.0, np.cos(a) * np.sqrt(2))
        gr = np.minimum(1.0, np.sin(a) * np.sqrt(2))
        return (x * np.stack([gl, gr], axis=1)).astype(np.float32)


# ================================================================ reverb ====
def generar_ir(dur=3.6, predelay_ms=25.0, brillo=0.5, ancho=1.0, tipo="sala_grande",
               semilla=1) -> np.ndarray:
    """IR estéreo verdadera (4, n): LL, LR, RL, RR, a partir de ruido con caída
    dependiente de la frecuencia (T60 más largo en graves, más corto en agudos),
    densidad que crece al comienzo, reflexiones tempranas y predelay.
    Las cuatro respuestas usan ruidos independientes (estéreo decorrelacionado)."""
    g = rng("ir", tipo, dur, predelay_ms, brillo, semilla)
    n_cola = int(dur * 1.25 * SR)
    pre = int(predelay_ms * SR / 1000)
    nper = 1024
    f = np.fft.rfftfreq(nper, 1 / SR)
    f_d = 1500 + 7000 * brillo  # frecuencia de amortiguación de agudos
    t60 = dur * (1.0 + 0.18 / (1 + (f / 180.0) ** 2)) / (1 + (f / f_d) ** 1.3)
    t60 = np.maximum(t60, 0.18)
    irs = np.zeros((4, n_cola + pre), dtype=np.float64)
    tau_dens = 0.018 if tipo == "sala_grande" else 0.005
    for k in range(4):
        ruido = g.standard_normal(n_cola)
        _, tt, Z = stft(ruido, SR, nperseg=nper, noverlap=nper * 3 // 4)
        Z = Z * np.exp(-6.91 * tt[None, :] / t60[:, None])
        _, y = istft(Z, SR, nperseg=nper, noverlap=nper * 3 // 4)
        y = y[:n_cola]
        if len(y) < n_cola:
            y = np.pad(y, (0, n_cola - len(y)))
        t = np.arange(n_cola) / SR
        y *= 1 - np.exp(-t / tau_dens)
        # reflexiones tempranas (más para sala chica)
        n_ref = 10 if tipo == "sala_grande" else 16
        span = 0.075 if tipo == "sala_grande" else 0.035
        for j in range(n_ref):
            tj = g.uniform(0.002, span) * (1 + 0.15 * k)
            aj = g.uniform(0.3, 1.0) * np.exp(-tj / span * 1.5) * (0.9 if tipo == "sala" else 0.55)
            ij = int(tj * SR)
            if ij < n_cola:
                y[ij] += aj * g.choice([-1, 1]) * np.sqrt(np.mean(y[: int(0.2 * SR)] ** 2)) * 25
        irs[k, pre:] = y
    # oscurecer las reflexiones (1 polo) y sacar sub-graves del retorno
    irs = sosfilt(biquad("pb", 3500 + 9000 * brillo, 0.6), irs, axis=1)
    irs = sosfilt(biquad("pa", 110.0 if tipo == "sala_grande" else 160.0, 0.6), irs, axis=1)
    cruz = 0.55 * ancho
    irs[1] *= cruz
    irs[2] *= cruz
    # normalizar energía: retorno ≈ mismo nivel RMS que el envío
    e = np.sqrt((irs[0] ** 2).sum() + (irs[2] ** 2).sum())
    irs /= e
    # final suave
    nf = int(0.2 * SR)
    irs[:, -nf:] *= np.linspace(1, 0, nf) ** 2
    return irs.astype(np.float32)


class Convolver:
    """Convolución FFT de una señal completa con una IR estéreo verdadera (cachea espectros)."""

    def __init__(self, irs: np.ndarray):
        self.irs = irs
        self._esp = {}

    def procesar(self, x: np.ndarray) -> np.ndarray:
        """Convolución lineal; solo se calcula sobre el tramo con señal (+ la cola de la IR)."""
        n = len(x)
        out = np.zeros((n, 2), dtype=np.float32)
        vivo = np.nonzero(np.abs(x).max(axis=1) > 1e-9)[0]
        if len(vivo) == 0:
            return out
        a, b = int(vivo[0]), int(vivo[-1]) + 1
        seg = x[a:b]
        m = len(seg)
        nfft = sfft.next_fast_len(m + self.irs.shape[1], real=True)
        H = self._esp.get(nfft)
        if H is None:
            H = sfft.rfft(self.irs, nfft, axis=1, workers=FFT_HILOS)
            self._esp[nfft] = H
            if len(self._esp) > 3:
                self._esp.pop(next(iter(self._esp)))
        XL = sfft.rfft(seg[:, 0], nfft, workers=FFT_HILOS)
        XR = sfft.rfft(seg[:, 1], nfft, workers=FFT_HILOS)
        largo = min(n - a, m + self.irs.shape[1])
        yl = sfft.irfft(XL * H[0] + XR * H[2], nfft, workers=FFT_HILOS)[:largo]
        yr = sfft.irfft(XR * H[3] + XL * H[1], nfft, workers=FFT_HILOS)[:largo]
        out[a:a + largo, 0] = yl
        out[a:a + largo, 1] = yr
        return out


def eco(x: np.ndarray, tempo, division=0.75, realim=0.38, corte=3200.0, graves=250.0,
        pingpong=True, **_):
    """Delay sincronizado al tempo (división en tiempos: 0.75 = corchea con puntillo)."""
    d = int(round(division * 60.0 / tempo.bpm * SR))
    a_lp = 1 - np.exp(-2 * np.pi * corte / SR)
    a_hp = 1 - np.exp(-2 * np.pi * graves / SR)
    yl, yr = _eco(x[:, 0].astype(np.float64), x[:, 1].astype(np.float64), d, realim, a_lp, a_hp,
                  pingpong)
    return np.stack([yl, yr], axis=1).astype(np.float32)


# ================================================================== cinta ===
def modulacion_cinta(n: int, semilla, wow=0.0012, flutter=0.0004) -> np.ndarray:
    """Retardo en muestras (≥ 2) que produce wow (≈0.5 Hz + deriva) y flutter (≈7 Hz).
    wow/flutter = desviación relativa de velocidad (0.0012 = 0.12 %)."""
    g = rng("cinta", semilla)
    t = np.arange(n) / SR
    # desviación de velocidad v(t); el retardo es su integral
    v = wow * (0.7 * np.sin(2 * np.pi * 0.53 * t + g.uniform(0, 6.28))
               + 0.5 * ruido_suave(n, int(1.7 * SR), g))
    v += flutter * (np.sin(2 * np.pi * 6.9 * t + g.uniform(0, 6.28))
                    + 0.4 * np.sin(2 * np.pi * 11.3 * t + g.uniform(0, 6.28))
                    + 0.3 * ruido_suave(n, int(0.03 * SR), g))
    d = np.cumsum(v)  # en muestras
    d -= d.min()
    return d + 3.0


def cinta(x: np.ndarray, mod: np.ndarray | None, saturacion=0.25, brillo=15000.0, **_):
    """Wow & flutter (retardo modulado común), saturación suave, 'head bump' y pérdida de agudos."""
    y = np.empty_like(x, dtype=np.float32)
    for c in range(x.shape[1]):
        s = x[:, c].astype(np.float64)
        if mod is not None:
            s = _retardo_variable(s, mod)
        y[:, c] = s
    if saturacion > 0:
        d = 1.0 + 3.0 * saturacion
        y = (np.tanh(d * y) / d).astype(np.float32)
    sos = np.vstack([biquad("graves", 95.0, 0.7, 0.8), biquad("pb", brillo, 0.6)])
    return filtrar(y, sos)


def hiss(n: int, nivel_db: float, semilla) -> np.ndarray:
    """Soplido de cinta muy bajo: ruido estéreo independiente, algo más presente en agudos."""
    g = rng("hiss", semilla)
    r = g.standard_normal((n, 2)).astype(np.float32)
    sos = np.vstack([biquad("pa", 400.0, 0.6), biquad("agudos", 4000.0, 0.7, 3.0),
                     biquad("pb", 14000.0, 0.6)])
    r = filtrar(r, sos)
    r *= float(desde_db(nivel_db)) / (np.sqrt(np.mean(r ** 2)) + 1e-12)
    return r


# ================================================================ master ====
def pico_real(x: np.ndarray, sobremuestreo: int = 4) -> float:
    """Pico real (dBTP) por sobremuestreo ×4."""
    up = soxr.resample(x.astype(np.float64), SR, SR * sobremuestreo, quality="HQ")
    return float(20 * np.log10(np.abs(up).max() + 1e-12))


def limitador(x: np.ndarray, techo_dbtp=-1.0, anticipo_ms=4.0, relaj_ms=150.0) -> np.ndarray:
    """Limitador con anticipo sobre picos reales (sobremuestreo ×4 del detector)."""
    techo = float(desde_db(techo_dbtp))
    L = max(2, int(anticipo_ms * SR / 1000))
    up = soxr.resample(x.astype(np.float64), SR, SR * 4, quality="HQ")
    pk = np.abs(up).max(axis=1)
    pk = pk[: len(x) * 4].reshape(-1, 4).max(axis=1) if len(pk) >= len(x) * 4 else \
        np.pad(pk, (0, len(x) * 4 - len(pk))).reshape(-1, 4).max(axis=1)
    pk = np.maximum(pk, np.abs(x).max(axis=1))
    g_req = np.minimum(1.0, techo / (pk + 1e-12))
    g = _min_adelante(g_req, L)
    gp = np.concatenate([np.full(L - 1, g[0]), g])
    cs = np.concatenate([[0.0], np.cumsum(gp)])
    g = (cs[L:] - cs[:-L]) / L                    # media móvil causal de L muestras
    g = np.minimum(g, g_req)
    g = _relajar(g, coef(relaj_ms / 1000))
    return (x * g[:, None]).astype(np.float32)
