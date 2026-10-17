"""Texturas hechas con las propias fuentes: nubes granulares y swells invertidos.

Se usan como clips de una pista con instrumento `Textura()`:

    tex = C.pista("textura", Textura(), stem="textura", envios={"reverb": 0.5})
    tex.clip(swell(Piano(), ["D3", "A3", "E4", "F#4"], largo_tiempos=4), fin=9)
    tex.clip(nube(Celesta(), "A5/0.5 E6 D6 G#5/1.5 A5/1", dur_s=20), pos=57)
    tex.clip(nube_de_banco("vibrafono_arco", "A4", dur_s=30), pos=1)
    tex.clip(nube_acordes(Piano(), [(0, 2, ["D3", "A3", "E4"]), (2, 2, ["D4", "F#4"])], dur_s=18), pos=81)
"""
from __future__ import annotations

import numpy as np
import soxr

from ..nucleo import SR, rng, rampa, nota as _nota
from ..efectos import biquad, sosf
from .base import Instrumento, Banco


class Textura(Instrumento):
    """Pista de audio libre: solo suena lo que se agregue con pista.clip(...)."""
    nombre = "textura"

    def render(self, notas, ctx, pista):
        return np.zeros((ctx.n, 2), dtype=np.float32)


def _estereo(x):
    x = np.asarray(x, dtype=np.float32)
    if x.ndim == 1:
        return np.stack([x, x], axis=1)
    if x.shape[1] == 1:
        return np.repeat(x, 2, axis=1)
    return x


def nube_granular(fuente, dur_s: float, semilla=0, grano=(0.07, 0.2), densidad=16.0,
                  estirar=10.0, dispersion=0.12, tonos=(0,), pesos=None, pan=0.8,
                  ataque=2.0, caida=4.0, desde=0.0, hasta=1.0, brillo_hz=None):
    """Nube granular estirada a partir de un audio fuente.

    * estirar   : cuántas veces más lento avanza la lectura de la fuente
    * densidad  : granos por segundo · grano: (mín, máx) en segundos
    * dispersion: desorden de la posición de lectura (s)
    * tonos     : transposiciones posibles de cada grano (semitonos), con `pesos`
    * desde/hasta: tramo de la fuente que se recorre (fracción 0..1)
    """
    src = _estereo(fuente)
    g = rng("nube", semilla)
    n = int(dur_s * SR)
    out = np.zeros((n, 2), dtype=np.float64)
    tonos = list(tonos)
    p = np.array(pesos if pesos else [1.0] * len(tonos), dtype=float)
    p /= p.sum()
    vers = {}
    for tn in tonos:
        r = 2.0 ** (tn / 12.0)
        vers[tn] = src if tn == 0 else soxr.resample(src, SR * r, SR, quality="HQ").astype(np.float32)
    K = int(dur_s * densidad)
    ts = np.sort(g.uniform(0, dur_s, K))
    gl_med = 0.0
    for t in ts:
        tn = tonos[int(g.choice(len(tonos), p=p))]
        s = vers[tn]
        L = int(g.uniform(*grano) * SR)
        if L < 64 or len(s) <= L + 2:
            continue
        a = desde * len(s)
        b = max(a + 1, hasta * len(s) - L)
        pos = a + (t / estirar) * SR * (len(s) / len(src))
        pos = a + ((pos - a) % max(1.0, b - a))
        pos += g.normal(0, dispersion * SR)
        pos = int(np.clip(pos, 0, len(s) - L - 1))
        w = np.hanning(L)
        gr = s[pos:pos + L].astype(np.float64) * w[:, None]
        pp = g.uniform(-pan, pan)
        ang = (pp + 1) * np.pi / 4
        gr = gr.mean(axis=1, keepdims=True) * np.array([[np.cos(ang), np.sin(ang)]]) * 1.414 * 0.6 + gr * 0.4
        i = int(t * SR)
        m = min(L, n - i)
        if m > 0:
            out[i:i + m] += gr[:m]
        gl_med += L
    if K:
        gl_med /= K
        out /= np.sqrt(max(1.0, densidad * gl_med / SR))
    na, nc = min(n, int(ataque * SR)), min(n, int(caida * SR))
    if na:
        out[:na] *= rampa(na)[:, None]
    if nc:
        out[-nc:] *= rampa(nc)[::-1, None]
    if brillo_hz:
        out = sosf(biquad("pb", brillo_hz, 0.6), out)
    return out.astype(np.float32)


def swell_invertido(fuente, largo_s: float, curva: float = 1.8, fin_ms: float = 12.0):
    """Invierte un audio (típicamente una cola de reverb) para que crezca y termine
    exactamente al final del clip, con un fundido mínimo que evita el click."""
    y = _estereo(fuente)[::-1]
    n = int(largo_s * SR)
    if len(y) >= n:
        y = y[-n:]
    else:
        y = np.concatenate([np.zeros((n - len(y), 2), np.float32), y])
    x = np.linspace(0, 1, n)
    env = x ** curva
    nf = int(fin_ms * SR / 1000)
    env[-nf:] *= rampa(nf)[::-1]
    return (y * env[:, None]).astype(np.float32)


# --------------------------------------------------------------- helpers ----
def swell(instrumento, alturas, largo_tiempos: float = 4.0, vel: float = 0.55,
          reverb: float = 1.0, seco: float = 0.1, curva: float = 1.8, brillo_hz=None):
    """Generador de clip: acorde de `instrumento` → reverb de la canción → invertido.
    Usar con pista.clip(swell(...), fin=compás) para que desemboque en ese downbeat."""
    from ..secuencia import Nota

    def gen(ctx):
        notas = [Nota(0.0, 2.0, float(_nota(a)), vel) for a in alturas]
        seco_a = ctx.aislado(instrumento, notas, cola_s=1.5)
        wet = ctx.reverb(seco_a)
        seco_p = np.zeros_like(wet)
        seco_p[: len(seco_a)] = seco_a[: len(wet)]
        src = seco * seco_p + reverb * wet
        largo_s = largo_tiempos * 60.0 / ctx.tempo.bpm
        y = swell_invertido(src, largo_s, curva)
        if brillo_hz:
            y = sosf(biquad("pb", brillo_hz, 0.6), y)
        return y
    return gen


def nube(instrumento, texto_melodia: str, dur_s: float, vel: float = 0.6, **kw):
    """Generador de clip: toca una melodía (mini-notación) con `instrumento` y la
    convierte en nube granular estirada de `dur_s` segundos."""
    from ..secuencia import Nota, melodia

    def gen(ctx):
        notas_t, largo = melodia(texto_melodia, vel)
        notas = [Nota(t, d, float(a), v, x) for (t, d, a, v, x) in notas_t]
        src = ctx.aislado(instrumento, notas, cola_s=2.5)
        kw.setdefault("semilla", (ctx.semilla, "nube", texto_melodia))
        return nube_granular(src, dur_s, **kw)
    return gen


def nube_acordes(instrumento, acordes, dur_s: float, vel: float = 0.55, **kw):
    """Generador de clip: toca acordes [(t_tiempos, dur, alturas[, vel])] con `instrumento` y
    los convierte en nube granular (los mismos parámetros que `nube`). `alturas` es una lista
    o una sola nota: sirve también para notas sueltas (p. ej. la salida de `espiral`).
    (Con la mini-notación también se puede: nube(instr, "[D3 A3 E4]/2 [D4 F#4 A4]/2", …).)"""
    from ..secuencia import Nota

    def gen(ctx):
        notas = []
        for item in acordes:
            t, d, alts = item[0], item[1], item[2]
            v = float(item[3]) if len(item) > 3 else vel
            if isinstance(alts, (str, int, float, np.integer, np.floating)):
                alts = [alts]
            notas += [Nota(float(t), float(d), float(_nota(a)), v) for a in alts]
        src = ctx.aislado(instrumento, notas, cola_s=2.5)
        kw.setdefault("semilla", (ctx.semilla, "nube_acordes", repr(acordes)))
        return nube_granular(src, dur_s, **kw)
    return gen


def nube_de_banco(banco: str, altura, dur_s: float, **kw):
    """Generador de clip: nube granular a partir de una muestra real del banco
    (p. ej. "vibrafono_arco", "chelos", "piano") en la altura más cercana. Usa la muestra
    cruda (sin nivelar: el nivel se ajusta con `ganancia_db` del clip) y nunca una muestra
    marcada como defectuosa en el catálogo."""
    def gen(ctx):
        b = Banco.de(banco)
        m = _nota(altura)
        i = b.elegir(m, 0)
        semis = m - b.midi[i] - b.cents[i] / 100.0
        src = b.remuestreado(i, semis, None)
        kw.setdefault("semilla", (ctx.semilla, "nube_banco", banco, m))
        return nube_granular(src, dur_s, **kw)
    return gen
