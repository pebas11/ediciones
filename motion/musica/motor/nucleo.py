"""Núcleo: constantes, conversiones, azar determinista, tempo y automatizaciones."""
from __future__ import annotations

import hashlib
import re

import numpy as np

SR = 48000  # frecuencia de muestreo interna (y de salida)
DT = np.float32

# ------------------------------------------------------------ conversiones --
def db(x):
    """Amplitud lineal → dB."""
    return 20.0 * np.log10(np.maximum(np.abs(x), 1e-12))


def desde_db(d):
    """dB → amplitud lineal."""
    return 10.0 ** (np.asarray(d, dtype=np.float64) / 20.0)


def midi_a_hz(m):
    return 440.0 * 2.0 ** ((np.asarray(m, dtype=np.float64) - 69.0) / 12.0)


def hz_a_midi(f):
    return 69.0 + 12.0 * np.log2(np.asarray(f, dtype=np.float64) / 440.0)


_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
_RE_NOTA = re.compile(r"^([A-Ga-g])(#|b|##|bb)?(-?\d+)$")
_NOMBRES_SOST = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
_NOMBRES_BEM = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]


def nota(n) -> int:
    """'D4' → 62, 'F#3' → 54, 'Bb2' → 46 (C4 = 60 = Do central). Enteros pasan igual."""
    if isinstance(n, (int, np.integer)):
        return int(n)
    if isinstance(n, float):
        return int(round(n))
    m = _RE_NOTA.match(n.strip())
    if not m:
        raise ValueError(f"nota inválida: {n!r}")
    letra, alt, octava = m.group(1).upper(), m.group(2) or "", int(m.group(3))
    pc = _PC[letra] + {"": 0, "#": 1, "##": 2, "b": -1, "bb": -2}[alt]
    return 12 * (octava + 1) + pc


def nombre_nota(m: int, bemoles=False) -> str:
    m = int(round(m))
    nombres = _NOMBRES_BEM if bemoles else _NOMBRES_SOST
    return f"{nombres[m % 12]}{m // 12 - 1}"


# ----------------------------------------------------------- azar estable --
def rng(*claves) -> np.random.Generator:
    """Generador determinista a partir de cualquier combinación de claves.

    No usa hash() de Python (cambia entre procesos): el resultado es idéntico
    en cada ejecución y en cada máquina.
    """
    h = hashlib.blake2b(repr(claves).encode("utf-8"), digest_size=8).digest()
    return np.random.default_rng(int.from_bytes(h, "little"))


def ruido_suave(n: int, paso: int, gen: np.random.Generator) -> np.ndarray:
    """Ruido de valor interpolado (−1..1) con un punto de control cada `paso` muestras
    (curva S entre puntos; se calcula a tasa de control y se interpola)."""
    paso = max(1, int(paso))
    k = n // paso + 3
    pts = gen.uniform(-1, 1, k)
    sub = max(1, min(64, paso // 8))
    xs = np.arange(0, n + sub, sub) / paso
    i = np.floor(xs).astype(np.int64)
    f = xs - i
    f = f * f * (3 - 2 * f)
    v = pts[i] * (1 - f) + pts[i + 1] * f
    return np.interp(np.arange(n), np.arange(len(v)) * sub, v)


# ------------------------------------------------------------------ tempo --
class Tempo:
    """Mapa de tempo en negras.

    * `bpm` siempre se mide en negras por minuto (también en 6/8).
    * Las posiciones internas son "tiempos" = negras desde el comienzo (float).
    * Un compás dura num·4/den tiempos (4/4 → 4, 6/8 → 3, 3/4 → 3).
    """

    def __init__(self, bpm: float, compas=(4, 4)):
        self.bpm = float(bpm)
        self.num, self.den = compas
        self.tpc = self.num * 4.0 / self.den  # tiempos por compás
        # segmentos: (inicio_tiempo, bpm_inicio, pendiente_bpm_por_tiempo)
        self._seg = [(0.0, self.bpm, 0.0)]
        self._prep()

    def ritardando(self, desde_t: float, hasta_t: float, bpm_final: float):
        """Rampa lineal de tempo entre dos posiciones (en tiempos); después queda fijo."""
        bpm_ini = self.bpm_en(desde_t)
        segs = [s for s in self._seg if s[0] < desde_t]
        k = (bpm_final - bpm_ini) / max(1e-9, hasta_t - desde_t)
        segs.append((desde_t, bpm_ini, k))
        segs.append((hasta_t, bpm_final, 0.0))
        self._seg = segs
        self._prep()

    def _prep(self):
        ini = np.array([s[0] for s in self._seg])
        b0 = np.array([s[1] for s in self._seg])
        k = np.array([s[2] for s in self._seg])
        acum = [0.0]
        for i in range(len(ini) - 1):
            acum.append(acum[-1] + self._integral(b0[i], k[i], ini[i + 1] - ini[i]))
        self._ini, self._b0, self._k, self._acum = ini, b0, k, np.array(acum)

    @staticmethod
    def _integral(b0, k, d):
        d = np.asarray(d, dtype=np.float64)
        if np.isscalar(k) or np.ndim(k) == 0:
            if abs(k) < 1e-12:
                return 60.0 * d / b0
            return 60.0 / k * np.log((b0 + k * d) / b0)
        out = 60.0 * d / b0
        m = np.abs(k) > 1e-12
        out[m] = 60.0 / k[m] * np.log((b0[m] + k[m] * d[m]) / b0[m])
        return out

    def bpm_en(self, t: float) -> float:
        i = max(0, int(np.searchsorted(self._ini, t, side="right")) - 1)
        return float(self._b0[i] + self._k[i] * (t - self._ini[i]))

    def seg(self, t):
        """Tiempos (negras) → segundos. Acepta escalares o arrays."""
        t = np.asarray(t, dtype=np.float64)
        i = np.clip(np.searchsorted(self._ini, t, side="right") - 1, 0, len(self._ini) - 1)
        d = t - self._ini[i]
        out = self._acum[i] + self._integral(self._b0[i], self._k[i], np.atleast_1d(d)).reshape(d.shape)
        return float(out) if out.ndim == 0 else out

    def tiempos(self, s):
        """Segundos → tiempos (negras)."""
        s = np.asarray(s, dtype=np.float64)
        i = np.clip(np.searchsorted(self._acum, s, side="right") - 1, 0, len(self._acum) - 1)
        ds = s - self._acum[i]
        b0, k = self._b0[i], self._k[i]
        lin = self._ini[i] + ds * b0 / 60.0
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            ram = self._ini[i] + b0 * (np.exp(k * ds / 60.0) - 1.0) / np.where(np.abs(k) > 1e-12, k, 1.0)
        out = np.where(np.abs(k) > 1e-12, ram, lin)
        return float(out) if out.ndim == 0 else out

    def pos(self, p) -> float:
        """Posición musical → tiempos.

        * número: compás (1 = comienzo; 25.5 = mitad del compás 25)
        * "25:3" o "25:3.5": compás 25, tiempo 3 (o 3½), contando desde 1
        """
        if isinstance(p, str):
            c, _, t = p.partition(":")
            return (float(c) - 1.0) * self.tpc + (float(t or 1) - 1.0)
        return (float(p) - 1.0) * self.tpc

    def muestra(self, t) -> int:
        return int(round(self.seg(t) * SR))


# --------------------------------------------------------- automatización --
class Auto:
    """Automatización por puntos.

        Auto([(1, 200), (9, 800, "exp"), (17, 800), (25, 3000, "suave")])

    * Cada punto es (posición, valor[, curva]); la posición es un compás
      (float, 1 = inicio) o "compás:tiempo". La curva describe el tramo que
      LLEGA a ese punto: "lin" (por defecto), "exp" (para frecuencias y
      ganancias, valores > 0), "suave" (S coseno) o "paso" (salto al llegar).
    * Antes del primer punto y después del último se mantiene el valor.
    """

    def __init__(self, puntos, nombre: str = ""):
        if isinstance(puntos, (int, float)):
            puntos = [(1, float(puntos))]
        self.puntos = [tuple(p) for p in puntos]
        self.nombre = nombre

    def _resolver(self, tempo: Tempo):
        ts, vs, cs = [], [], []
        for p in self.puntos:
            ts.append(tempo.pos(p[0]))
            vs.append(float(p[1]))
            cs.append(p[2] if len(p) > 2 else "lin")
        orden = np.argsort(ts, kind="stable")
        return np.array(ts)[orden], np.array(vs)[orden], [cs[i] for i in orden]

    def en_tiempos(self, t, tempo: Tempo):
        """Valor en posiciones dadas en tiempos (negras)."""
        ts, vs, cs = self._resolver(tempo)
        t = np.atleast_1d(np.asarray(t, dtype=np.float64))
        out = np.full(t.shape, vs[0])
        for i in range(1, len(ts)):
            a, b = ts[i - 1], ts[i]
            va, vb = vs[i - 1], vs[i]
            m = (t >= a) & (t < b) if b > a else np.zeros_like(t, dtype=bool)
            if m.any():
                f = (t[m] - a) / (b - a)
                c = cs[i]
                if c == "exp" and va > 0 and vb > 0:
                    out[m] = va * (vb / va) ** f
                elif c == "suave":
                    out[m] = va + (vb - va) * (0.5 - 0.5 * np.cos(np.pi * f))
                elif c == "paso":
                    out[m] = va
                else:
                    out[m] = va + (vb - va) * f
            out[t >= b] = vb
        return out

    def en_muestras(self, n: int, tempo: Tempo, inicio: int = 0, paso: int = 32):
        """Curva por muestra (n muestras desde `inicio`), calculada a tasa de control."""
        k = n // paso + 2
        idx = inicio + np.arange(k) * paso
        v = self.en_tiempos(tempo.tiempos(idx / SR), tempo)
        x = np.arange(n) / paso
        return np.interp(x, np.arange(k), v)


def valor(param, n: int, tempo: Tempo, inicio: int = 0):
    """Devuelve un parámetro como array por muestra (acepta número, Auto o array)."""
    if isinstance(param, Auto):
        return param.en_muestras(n, tempo, inicio)
    if callable(param):
        t = (inicio + np.arange(n)) / SR
        return np.asarray(param(t), dtype=np.float64)
    if np.ndim(param) == 0:
        return np.full(n, float(param))
    a = np.asarray(param, dtype=np.float64)
    return a[inicio:inicio + n]


def es_constante(param) -> bool:
    return np.ndim(param) == 0 and not isinstance(param, Auto) and not callable(param)


# ------------------------------------------------------------- envolventes --
def rampa(n: int, forma: str = "cos") -> np.ndarray:
    """Rampa 0→1 de n muestras ("cos", "lin", "exp")."""
    if n <= 0:
        return np.zeros(0)
    x = np.linspace(0.0, 1.0, n, endpoint=False) + 0.5 / n
    if forma == "lin":
        return x
    if forma == "exp":
        return (np.exp(4 * x) - 1) / (np.e ** 4 - 1)
    return 0.5 - 0.5 * np.cos(np.pi * x)


def adsr(n: int, a: float, d: float, s: float, r: float, n_nota: int) -> np.ndarray:
    """ADSR en muestras: a, d, r en segundos, s nivel; la nota se suelta en n_nota."""
    env = np.zeros(n)
    na, nd = int(a * SR), int(d * SR)
    t = np.arange(n)
    if na > 0:
        m = t < na
        env[m] = 0.5 - 0.5 * np.cos(np.pi * t[m] / na)
    m = (t >= na)
    env[m] = s + (1 - s) * np.exp(-(t[m] - na) / max(1, nd) * 3.0)
    nr = max(1, int(r * SR))
    nivel = env[min(n_nota, n - 1)] if n_nota < n else env[-1]
    m = t >= n_nota
    env[m] = nivel * np.exp(-(t[m] - n_nota) / nr * 4.6)  # −40 dB en r segundos
    return env


def paneo(pan: float):
    """Ley de potencia constante: pan −1 (izq) … +1 (der) → (gL, gR)."""
    a = (np.clip(pan, -1, 1) + 1) * np.pi / 4
    return np.cos(a), np.sin(a)


def a_estereo(x: np.ndarray, pan: float = 0.0) -> np.ndarray:
    """Mono (N,) o (N,1) → estéreo (N,2) con paneo de potencia constante (centro = −3 dB)."""
    if x.ndim == 2 and x.shape[1] == 2:
        if pan == 0:
            return x
        gl = np.cos((np.clip(pan, -1, 1) + 1) * np.pi / 4) * np.sqrt(2)
        gr = np.sin((np.clip(pan, -1, 1) + 1) * np.pi / 4) * np.sqrt(2)
        return np.stack([x[:, 0] * min(1, gl), x[:, 1] * min(1, gr)], axis=1)
    m = x.reshape(-1)
    a = (np.clip(pan, -1, 1) + 1) * np.pi / 4
    return np.stack([m * np.cos(a), m * np.sin(a)], axis=1)


def cortar(x: np.ndarray, n: int, fundido_s: float = 0.03) -> np.ndarray:
    """x[:n] con fundido de salida si hubo que recortar (nunca cortes secos)."""
    if len(x) <= n:
        return x
    y = np.array(x[:n], dtype=np.float32)
    nf = min(n, int(fundido_s * SR))
    if nf > 1:
        f = rampa(nf)[::-1].astype(np.float32)
        y[-nf:] *= f[:, None] if y.ndim == 2 else f
    return y


def mezclar_en(dest: np.ndarray, x: np.ndarray, inicio: int):
    """Suma x en dest a partir de `inicio` (recorta lo que se sale)."""
    if inicio >= len(dest) or len(x) == 0:
        return
    if inicio < 0:
        x = np.array(x[-inicio:], dtype=dest.dtype)
        nf = min(len(x), int(0.002 * SR))
        if nf > 1:
            f = rampa(nf).astype(dest.dtype)
            x[:nf] *= f[:, None] if x.ndim == 2 else f
        inicio = 0
    n = min(len(x), len(dest) - inicio)
    if n > 0:
        dest[inicio:inicio + n] += x[:n]
