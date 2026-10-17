"""Figuras de arreglo reutilizables (vinieron de «Espiral»).

    from motor import espiral, columna
    cols = {9: columna(("F#", "G#", "A", "C#")), 25: columna(("B", "C#", "D", "F#"))}
    notas = espiral(piano, 9, 33, cols, patron="0 2 1 3 2 4 3", desplaz=1, vel=0.35)
    tex.clip(nube_acordes(Piano(), [(t - 32, 0.42, m, v) for t, _, _, m, v in notas], dur_s=15), pos=33)
"""
from __future__ import annotations

import numpy as np

from .nucleo import nota


def columna(clases, piso="A3", n: int = 18) -> list[int]:
    """Alturas MIDI ascendentes, desde `piso`, de las clases de altura dadas (nombres sin
    octava o enteros 0–11): columna(("F#", "G#", "A", "C#")) → [57, 61, 66, 68, 69, 73, …]."""
    pcs = set()
    for c in clases:
        if isinstance(c, (int, np.integer)):
            pcs.add(int(c) % 12)
        else:
            pcs.add(nota(f"{c}4") % 12)
    m, out = nota(piso), []
    while len(out) < n:
        if m % 12 in pcs:
            out.append(m)
        m += 1
    return out


def _columna_en(columnas, compas: int):
    if callable(columnas):
        return list(columnas(compas))
    if isinstance(columnas, dict):
        claves = sorted(k for k in columnas if k <= compas)
        if not claves:
            raise ValueError(f"espiral: no hay columna para el compás {compas}")
        return list(columnas[claves[-1]])
    return list(columnas)


def pasos_espiral(tempo, desde, hasta, columnas, patron="0 2 1 3 2 4 3", desplaz=0, paso=0.5,
                  k0=0, retraso=0.0, filtro=None):
    """[(t_tiempos, compás, k, midi)] del ostinato (sin agregar notas)."""
    pasos = patron.split()
    tpc = tempo.tpc
    t = (float(desde) - 1) * tpc + retraso
    t_fin = (float(hasta) - 1) * tpc
    k = k0
    out = []
    while t < t_fin - 1e-9:
        s = pasos[k % len(pasos)]
        c = int(t // tpc) + 1
        if s not in (".", "-") and (filtro is None or filtro(k, c)):
            col = sorted(nota(a) for a in _columna_en(columnas, c))
            out.append((t, c, k, col[int(s) + desplaz]))
        t += paso
        k += 1
    return out


def espiral(p, desde, hasta, columnas, patron="0 2 1 3 2 4 3", desplaz=0, vel=0.36, dur=0.42,
            acento=1.18, cresc=(0.92, 1.08), paso=0.5, retraso=0.0, filtro=None, transponer=0, **x):
    """Ostinato que gira sobre "columnas" de alturas: el paso k toca el índice
    patron[k] + desplaz de la columna vigente en su compás, y el patrón corre continuo a través
    de los compases (una célula de 7 corcheas sobre compases de 8 empieza cada compás en otro
    punto del giro). Acento al comienzo de cada vuelta de la célula, crescendo a lo largo del
    tramo y la cresta de cada giro apenas más fuerte.

    * columnas : lista fija de alturas, dict {compás: alturas} (vale desde ese compás hasta la
                 siguiente entrada) o función compás → alturas; alturas MIDI o nombres
                 (ver `columna` para armarlas desde clases de altura)
    * patron   : índices separados por espacio ("." = silencio) · paso: duración de cada paso
    * desplaz  : corre los índices (sube la figura un escalón por vuelta) · retraso (tiempos)
    * filtro(k, compás) → bool: qué pasos suenan (para desarmar la figura)
    * cresc    : factor de velocidad al principio y al final del tramo · **x: extras de nota
    Devuelve [(t_tiempos, compás, k, midi, vel)] de las notas agregadas (para doblarlas o
    convertirlas en nube con `nube_acordes`)."""
    pasos = patron.split()
    n_pat = len(pasos)
    numeros = [int(z) for z in pasos if z not in (".", "-")]
    media = float(np.mean(numeros)) if numeros else 0.0
    tpc = p.tempo.tpc
    t_a, t_b = (float(desde) - 1) * tpc, (float(hasta) - 1) * tpc
    out = []
    for t, c, k, m in pasos_espiral(p.tempo, desde, hasta, columnas, patron, desplaz, paso, 0,
                                    retraso, filtro):
        f = (t - t_a) / max(1e-9, t_b - t_a)
        v = vel * (cresc[0] + (cresc[1] - cresc[0]) * f) * (acento if k % n_pat == 0 else 1.0)
        v *= 1.0 + 0.035 * (int(pasos[k % n_pat]) - media)   # la cresta de cada giro, apenas más
        v = min(1.0, v)
        p.nota(1 + t / tpc, m + transponer, dur, vel=v, **x)
        out.append((t, c, k, m + transponer, v))
    return out
