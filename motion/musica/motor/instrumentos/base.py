"""Base de instrumentos, banco de muestras y caché de notas."""
from __future__ import annotations

import json
from collections import OrderedDict
from pathlib import Path

import numpy as np
import soxr

from ..nucleo import SR, mezclar_en, rampa

DIR_PROC = Path(__file__).resolve().parents[2] / "muestras" / "proc"
_MANIFIESTO = None


def manifiesto() -> dict:
    global _MANIFIESTO
    if _MANIFIESTO is None:
        ruta = DIR_PROC / "manifest.json"
        if not ruta.exists():
            raise FileNotFoundError(
                f"Faltan las muestras: corré `python3 motion/musica/muestras.py` ({ruta})")
        _MANIFIESTO = json.loads(ruta.read_text())
    return _MANIFIESTO


# ------------------------------------------------------------------ caché --
class CacheLRU:
    """Caché con tope de memoria (bytes) para audio remuestreado y notas sintetizadas."""

    def __init__(self, tope_mb: float = 900):
        self.tope = int(tope_mb * 1e6)
        self.datos: OrderedDict = OrderedDict()
        self.bytes = 0
        self.aciertos = 0
        self.fallos = 0

    def get(self, k):
        v = self.datos.get(k)
        if v is not None:
            self.datos.move_to_end(k)
            self.aciertos += 1
        else:
            self.fallos += 1
        return v

    def put(self, k, v: np.ndarray):
        if k in self.datos:
            self.bytes -= self.datos[k].nbytes
        self.datos[k] = v
        self.bytes += v.nbytes
        while self.bytes > self.tope and len(self.datos) > 1:
            _, viejo = self.datos.popitem(last=False)
            self.bytes -= viejo.nbytes


CACHE = CacheLRU()


# ------------------------------------------------------------------ banco --
class Banco:
    """Conjunto de muestras de un instrumento (según manifest.json)."""

    _instancias: dict = {}

    @classmethod
    def de(cls, nombre: str) -> "Banco":
        if nombre not in cls._instancias:
            cls._instancias[nombre] = cls(nombre)
        return cls._instancias[nombre]

    def __init__(self, nombre: str):
        d = manifiesto()["instrumentos"][nombre]
        self.nombre = nombre
        self.info = d
        self.muestras = d["muestras"]
        self.n_capas = int(d["n_capas"])
        self.midi = np.array([e.get("midi", 60) for e in self.muestras], dtype=float)
        self.cents = np.array([e.get("cents", 0.0) for e in self.muestras], dtype=float)
        self.capa = np.array([e.get("capa", 0) for e in self.muestras], dtype=int)
        self.rr = np.array([e.get("rr", 1) for e in self.muestras], dtype=int)
        self.dur = np.array([e["dur_s"] for e in self.muestras], dtype=float)
        self.ajuste_db = self._nivelar()
        self._audio = {}

    def _nivelar(self, ref_db: float = -20.0) -> np.ndarray:
        """Iguala niveles entre muestras vecinas (las bibliotecas libres son desparejas).

        Por capa se ajusta una recta rms(midi); se corrige el 85 % del residuo
        y la mitad de la pendiente. Todas las capas quedan a un nivel común
        (la velocidad controla el volumen; la capa, el timbre)."""
        rms = np.array([e["rms_db"] for e in self.muestras], dtype=float)
        aj = np.zeros(len(rms))
        for c in np.unique(self.capa):
            m = self.capa == c
            x, y = self.midi[m], rms[m]
            if m.sum() >= 3 and np.ptp(x) > 0:
                b, a = np.polyfit(x, y, 1)
            else:
                b, a = 0.0, float(np.mean(y))
            med = float(np.median(x))
            fit = a + b * x
            res = np.clip(y - fit, -8, 8)
            aj[m] = (ref_db - (a + b * med)) - 0.85 * res - 0.5 * b * (x - med)
        return np.clip(aj, -30, 30)

    def audio(self, i: int) -> np.ndarray:
        if i not in self._audio:
            self._audio[i] = np.load(DIR_PROC / self.muestras[i]["archivo"], mmap_mode="r")
        return self._audio[i]

    def elegir(self, midi: float, capa: int = 0, clave: int = 0, excluir=()) -> int:
        """Muestra más cercana en altura dentro de la capa (con round robin por `clave`)."""
        m = self.capa == min(capa, self.n_capas - 1)
        if not m.any():
            m = np.ones(len(self.midi), dtype=bool)
        idx = np.nonzero(m)[0]
        idx = np.array([i for i in idx if i not in excluir]) if excluir else idx
        if len(idx) == 0:
            idx = np.nonzero(m)[0]
        d = np.abs(self.midi[idx] - midi) + 0.01 * (self.midi[idx] < midi)  # empate: preferir bajar
        dmin = d.min()
        cands = idx[d <= dmin + 1e-6]
        return int(cands[clave % len(cands)])

    def remuestreado(self, i: int, semitonos: float, n_in: int | None = None) -> np.ndarray:
        """Audio de la muestra i transpuesto `semitonos` (cacheado). Devuelve (n, ch) float32."""
        ratio = 2.0 ** (semitonos / 12.0)
        x = self.audio(i)
        n_full = len(x)
        n_in = n_full if n_in is None else min(n_full, int(n_in))
        clave = (self.nombre, i, round(ratio, 7))
        prev = CACHE.get(clave)
        if prev is not None and (prev.shape[0] >= int(n_in / ratio) - 4 or prev.shape[0] >= int(n_full / ratio) - 4):
            return prev
        # pedir un poco más de lo necesario para reutilizar
        n_pedir = n_full if n_in > 0.6 * n_full else min(n_full, int(n_in * 1.5) + SR // 2)
        seg = np.asarray(x[:n_pedir], dtype=np.float32)
        if abs(ratio - 1.0) < 1e-6:
            y = seg.copy()
        else:
            y = soxr.resample(seg, SR * ratio, SR, quality="HQ").astype(np.float32)
        y = np.ascontiguousarray(y)
        CACHE.put(clave, y)
        return y


# ------------------------------------------------------------ instrumento --
class Instrumento:
    """Interfaz común. Un instrumento renderiza las notas de una pista a (n, 2) float32.

    Por defecto renderiza nota por nota con `voz(nota, ctx, pista)`, que
    devuelve (audio (m, 2), muestra_inicial)."""

    nombre = "instrumento"
    usa_pedal = False

    def render(self, notas, ctx, pista) -> np.ndarray:
        out = np.zeros((ctx.n, 2), dtype=np.float32)
        for nt in notas:
            r = self.voz(nt, ctx, pista)
            if r is None:
                continue
            buf, ini = r
            mezclar_en(out, buf, ini)
        return out

    def voz(self, nt, ctx, pista):
        raise NotImplementedError

    # utilidades comunes
    def fin_nota(self, nt, ctx, pista) -> int:
        """Muestra de fin de nota, extendida por el pedal de resonancia si corresponde."""
        t_fin = nt.t + nt.dur
        if self.usa_pedal and pista is not None and pista.pedales:
            abajo, t_sube = pista.pedal_abajo_en(t_fin - 1e-6)
            if abajo:
                t_fin = max(t_fin, t_sube)
        return ctx.muestra(t_fin)


def envolvente_nota(n_total: int, n_on: int, ataque_s: float, soltar_s: float,
                    forma_soltar: str = "exp") -> np.ndarray:
    """Ataque (coseno) + sostenido + caída tras soltar (exp: −60 dB en soltar_s)."""
    env = np.ones(n_total, dtype=np.float32)
    na = min(n_total, int(ataque_s * SR))
    if na > 0:
        env[:na] = rampa(na)
    n_on = min(n_on, n_total)
    nr = n_total - n_on
    if nr > 0:
        if forma_soltar == "exp":
            t = np.arange(nr) / max(1.0, soltar_s * SR)
            caida = np.exp(-6.91 * t)
            caida *= rampa(nr)[::-1] ** 0.5  # termina en cero exacto
        else:
            caida = rampa(nr)[::-1]
        env[n_on:] *= caida
    return env
