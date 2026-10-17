#!/usr/bin/env python3
"""Descarga y prepara las muestras de instrumentos reales (idempotente).

Uso (desde cualquier carpeta):
    python3 motion/musica/muestras.py            # baja lo que falte y procesa lo nuevo
    python3 motion/musica/muestras.py --forzar   # reprocesa todo (no vuelve a bajar)

Fuentes (todas CC0 1.0, dominio público, sin obligación de atribución):
  * VSCO-2 Community Edition  https://github.com/sgossner/VSCO-2-CE  (cuerdas)
  * Versilian Community Sample Library (VCSL)  https://github.com/sgossner/VCSL
    (piano vertical, arpa, vibráfono, glockenspiel)

Se clonan con `git clone --filter=blob:none --sparse` y `git sparse-checkout`
solo con las carpetas necesarias (el proxy bloquea los ZIP de codeload).

Después cada muestra se convierte a 48 kHz float32 (.npy, se lee con mmap),
se recorta el silencio, se le quita el DC, se mide su afinación real con FFT
(corrige convenciones de octava y desafinaciones) y se anota en
`muestras/proc/manifest.json`, que es lo único que lee el motor.

Nivelación (ver `CATALOGO[...]["nivel"]` y `NIVELES.md`): de cada muestra se mide la
loudness K-ponderada (BS.1770) del tramo estable (sostenidos) o de una ventana corta
después del ataque promediada con la de sus primeros 2 s (percusivos), y se anota el
ajuste que la lleva a la referencia de su capa. Las capas quedan separadas por
`capas_db` (suave < fuerte). Las muestras defectuosas (`excluir`) quedan marcadas y el
motor transpone las vecinas. Todo es determinista y queda cacheado en el manifiesto
(`version_nivel`): si cambia el catálogo, se recalcula solo lo que falta.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import soundfile as sf
import soxr
from scipy.signal import butter, sosfilt

SR = 48000
RAIZ = Path(__file__).resolve().parent
DIR_MUESTRAS = RAIZ / "muestras"
DIR_PROC = DIR_MUESTRAS / "proc"
MANIFIESTO = DIR_PROC / "manifest.json"
VERSION_PROCESO = 3

REPOS = {
    "VSCO-2-CE": {
        "url": "https://github.com/sgossner/VSCO-2-CE",
        "licencia": "CC0-1.0",
        "patrones": [
            "/LICENSE*", "/README.md",
            "/Strings/Violin Section/susVib/",
            "/Strings/Violin Section/Trem/",
            "/Strings/Violin Section/Pizz/",
            "/Strings/Viola Section/susvib/",
            "/Strings/Viola Section/trem/",
            "/Strings/Cello Section/susvib/",
            "/Strings/Cello Section/trem/",
            "/Strings/Cello Section/pizzT/",
            "/Strings/Solo Contrabass/SusNV/",
            "/Strings/Solo Contrabass/Pizz/",
        ],
    },
    "VCSL": {
        "url": "https://github.com/sgossner/VCSL",
        "licencia": "CC0-1.0",
        "patrones": [
            "/LICENSE*", "/README.md",
            "/Chordophones/Zithers/Upright Piano, Knight/",
            "/Chordophones/Composite Chordophones/Concert Harp/",
            "/Idiophones/Struck Idiophones/Vibraphone/Soft Mallets/",
            "/Idiophones/Struck Idiophones/Vibraphone/Bowed/",
            "/Idiophones/Struck Idiophones/Glockenspiel/",
        ],
    },
}

# ---------------------------------------------------------------------------
# Catálogo: qué archivos forman cada instrumento del motor.
#   carpeta : ruta dentro del repo
#   filtro  : regex sobre el nombre de archivo (se queda con los que matchean)
#   capas   : traducción de la marca de dinámica del nombre a capa 0..N (suave→fuerte)
#   tono    : False para ruidos sin altura (pedal del piano)
#   ventana : (inicio_s, largo_s) del tramo donde se mide la afinación
#   nivel   : nivelación de las muestras (sin "nivel" = nivelación vieja del motor, solo
#             para los ruidos del piano):
#       tipo     "sostenido": loudness K del tramo estable (el mismo que usan los bucles)
#                "percusivo": promedio (dB) de la loudness K de una ventana corta después
#                del ataque (`corta_s`) y la integrada de los primeros 2 s
#       capas_db nivel de cada capa (de suave a fuerte) respecto de la más fuerte: la capa
#                suave suena `-capas_db[0]` dB menos que la fuerte a igual velocidad
#       excluir  alturas MIDI defectuosas (int = todas las capas, (midi, capa) = una sola)
#       domar    True = vibráfonos: se analizan sus parciales y se miden ya domados
# ---------------------------------------------------------------------------
_PERC = dict(tipo="percusivo", corta_s=0.4)
_SOST = dict(tipo="sostenido")
CATALOGO = {
    "piano": dict(repo="VCSL", carpeta="Chordophones/Zithers/Upright Piano, Knight/Sustains", octava=1,
                  filtro=r"^Player_vl\d_rr\d_.*\.wav$", ventana=(0.08, 0.6),
                  nivel=dict(_PERC, capas_db=(-8.0, 0.0))),
    "piano_soltar": dict(repo="VCSL", carpeta="Chordophones/Zithers/Upright Piano, Knight/Releases", octava=1, afinar=False,
                         filtro=r"^Player_rel_rr\d_.*\.wav$", ventana=(0.0, 0.25)),
    "piano_pedal": dict(repo="VCSL", carpeta="Chordophones/Zithers/Upright Piano, Knight/Pedal",
                        filtro=r"^Player_Ped(On|Off)_\d+\.wav$", tono=False),
    # arpa Re2 (38): cuerda apagada (cae ~10 dB más rápido que sus vecinas, en las dos capas)
    "arpa": dict(repo="VCSL", carpeta="Chordophones/Composite Chordophones/Concert Harp", octava=0,
                 filtro=r"^KSHarp_.*\.wav$", capas={"p": 0, "mp": 0, "mf": 0, "f": 1},
                 ventana=(0.05, 0.5), nivel=dict(_PERC, capas_db=(-7.0, 0.0), excluir=(38,))),
    # vibráfono Fa3 (53): grabada con la lámina apagada (−25 dB a los 0,5 s; las vecinas, −3 dB)
    "vibrafono": dict(repo="VCSL", carpeta="Idiophones/Struck Idiophones/Vibraphone/Soft Mallets", octava=1,
                      filtro=r"^Vibes_soft_.*\.wav$", ventana=(0.05, 0.5),
                      nivel=dict(_PERC, capas_db=(-10.0, 0.0), excluir=(53,), domar=True)),
    # arco La3 (57): casi vacía y mal rotulada (sin fundamental: su energía está en 880 Hz)
    "vibrafono_arco": dict(repo="VCSL", carpeta="Idiophones/Struck Idiophones/Vibraphone/Bowed", octava=1,
                           filtro=r"^Vibes_bowed_.*\.wav$", ventana=(0.6, 0.8),
                           nivel=dict(_SOST, excluir=(57,), domar=True)),
    "glock": dict(repo="VCSL", carpeta="Idiophones/Struck Idiophones/Glockenspiel", octava=1,
                  filtro=r"^glock_.*\.wav$", capas={"soft": 0, "medium": 1, "loud": 2},
                  ventana=(0.02, 0.3),
                  # Sol5 suave (79, capa 0): cae 6 dB en 0,1 s (las vecinas, 1 dB): irregular
                  nivel=dict(_PERC, capas_db=(-10.0, -4.0, 0.0), excluir=((79, 0),))),
    "violines": dict(repo="VSCO-2-CE", octava=1, carpeta="Strings/Violin Section/susVib",
                     filtro=r"\.wav$", ventana=(0.4, 0.7), nivel=dict(_SOST, capas_db=(-8.0, 0.0))),
    "violines_trem": dict(repo="VSCO-2-CE", octava=1, afinar=False, carpeta="Strings/Violin Section/Trem",
                          filtro=r"\.wav$", ventana=(0.4, 0.7), nivel=dict(_SOST, capas_db=(-8.0, 0.0))),
    "violines_pizz": dict(repo="VSCO-2-CE", octava=1, afinar=False, carpeta="Strings/Violin Section/Pizz",
                          filtro=r"\.wav$", ventana=(0.03, 0.25),
                          nivel=dict(_PERC, corta_s=0.3, capas_db=(-8.0, 0.0))),
    # viola Sol5 suave (79, capa 0): reguladores de 8 dB dentro de la toma (no tiene tramo estable)
    "violas": dict(repo="VSCO-2-CE", octava=1, carpeta="Strings/Viola Section/susvib",
                   filtro=r"\.wav$", ventana=(0.4, 0.7),
                   nivel=dict(_SOST, capas_db=(-8.0, 0.0), excluir=((79, 0),))),
    "violas_trem": dict(repo="VSCO-2-CE", octava=1, afinar=False, carpeta="Strings/Viola Section/trem",
                        filtro=r"\.wav$", ventana=(0.4, 0.7), nivel=dict(_SOST, capas_db=(-8.0, 0.0))),
    "chelos": dict(repo="VSCO-2-CE", octava=1, carpeta="Strings/Cello Section/susvib",
                   filtro=r"\.wav$", ventana=(0.4, 0.7), nivel=dict(_SOST, capas_db=(-8.0, 0.0))),
    "chelos_trem": dict(repo="VSCO-2-CE", octava=1, afinar=False, carpeta="Strings/Cello Section/trem",
                        filtro=r"\.wav$", ventana=(0.4, 0.7), nivel=dict(_SOST, capas_db=(-8.0, 0.0))),
    "chelos_pizz": dict(repo="VSCO-2-CE", octava=1, afinar=False, carpeta="Strings/Cello Section/pizzT",
                        filtro=r"\.wav$", ventana=(0.03, 0.3),
                        nivel=dict(_PERC, corta_s=0.3, capas_db=(-8.0, 0.0))),
    "contrabajo": dict(repo="VSCO-2-CE", octava=1, carpeta="Strings/Solo Contrabass/SusNV",
                       filtro=r"\.wav$", ventana=(0.4, 0.8), nivel=dict(_SOST, capas_db=(-8.0, 0.0))),
    "contrabajo_pizz": dict(repo="VSCO-2-CE", octava=1, afinar=False, carpeta="Strings/Solo Contrabass/Pizz",
                            filtro=r"\.wav$", ventana=(0.05, 0.4),
                            nivel=dict(_PERC, corta_s=0.3, capas_db=(-8.0, 0.0))),
}
REF_NIVEL_DB = -20.0   # nivel de la capa más fuerte (la calibración del motor fija el nivel final)

NOTAS_PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
RE_NOTA = re.compile(r"(?<![A-Za-z])([A-G])(#|b)?(-?\d)(?![0-9])")
DINAMICAS = {"pp": 1, "p": 2, "mp": 3, "mf": 4, "f": 5, "ff": 6,
             "soft": 1, "medium": 2, "loud": 3}


def log(*a):
    print("[muestras]", *a, flush=True)


# ---------------------------------------------------------------- descarga --
def git(args, cwd=None):
    r = subprocess.run(["git", "-c", "core.quotepath=off", *args], cwd=cwd,
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}\n{r.stderr}")
    return r.stdout


def bajar_repos():
    DIR_MUESTRAS.mkdir(parents=True, exist_ok=True)
    for nombre, info in REPOS.items():
        destino = DIR_MUESTRAS / nombre
        if not (destino / ".git").exists():
            log(f"clonando {nombre} (sparse, sin blobs)…")
            git(["clone", "--filter=blob:none", "--sparse", "--depth", "1",
                 info["url"], str(destino)])
        actuales = []
        try:
            actuales = git(["sparse-checkout", "list"], cwd=destino).splitlines()
        except RuntimeError:
            pass
        if [p.strip() for p in actuales] != info["patrones"]:
            log(f"{nombre}: sparse-checkout de {len(info['patrones'])} rutas (baja los blobs)…")
            git(["sparse-checkout", "set", "--no-cone", *info["patrones"]], cwd=destino)
        else:
            log(f"{nombre}: ya estaba bajado")


# ---------------------------------------------------------------- análisis --
def nota_a_midi(nombre_nota: str) -> int:
    m = RE_NOTA.fullmatch(nombre_nota)
    letra, alt, octava = m.group(1), m.group(2), int(m.group(3))
    pc = NOTAS_PC[letra] + (1 if alt == "#" else -1 if alt == "b" else 0)
    return 12 * (octava + 1) + pc


def parsear_nombre(nombre: str, capas_map: dict | None):
    base = nombre.rsplit(".", 1)[0]
    m = None
    for m in RE_NOTA.finditer(base):
        pass  # la última nota del nombre (evita falsos positivos al principio)
    midi_nom = nota_a_midi(m.group(0)) if m else None
    tokens = re.split(r"[_\-]", base)
    capa_raw = None
    for t in tokens:
        tl = t.lower()
        if RE_NOTA.fullmatch(t):
            continue  # "F0" es una nota, no la dinámica f
        mv = re.fullmatch(r"vl?(\d)", tl)
        if mv:
            capa_raw = int(mv.group(1))
        md = re.fullmatch(r"(pp|p|mp|mf|f|ff|soft|medium|loud)(\d*)", tl)
        if md and capas_map is None:
            capa_raw = DINAMICAS[md.group(1)]
        if md and capas_map is not None:
            capa_raw = capas_map.get(md.group(1), capa_raw)
    rr = 1
    mr = re.search(r"rr(\d+)", base, re.I)
    if mr:
        rr = int(mr.group(1))
    else:
        mt = re.search(r"_(\d)$", base)
        if mt:
            rr = int(mt.group(1))
    art = None
    mp = re.search(r"Ped(On|Off)", base)
    if mp:
        art = "pedal_" + mp.group(1).lower()
    return midi_nom, capa_raw, rr, art


def cargar_48k(ruta: Path) -> np.ndarray:
    x, sr = sf.read(str(ruta), dtype="float32", always_2d=True)
    if sr != SR:
        x = soxr.resample(x, sr, SR, quality="VHQ").astype(np.float32)
    return np.ascontiguousarray(x)


def limpiar(x: np.ndarray, umbral_db=-45.0):
    """Quita DC, recorta silencio inicial/final y aplica fundidos cortos."""
    sos = butter(2, 12.0, "highpass", fs=SR, output="sos")
    x = sosfilt(sos, x, axis=0).astype(np.float32)
    mono = np.abs(x).max(axis=1)
    pico = float(mono.max()) + 1e-12
    idx = np.nonzero(mono > pico * 10 ** (umbral_db / 20))[0]
    ini = max(0, int(idx[0]) - int(0.004 * SR)) if len(idx) else 0
    # final: envolvente suavizada por debajo de -80 dB del pico
    env = np.maximum.reduceat(mono, np.arange(0, len(mono), 480))
    vivos = np.nonzero(env > pico * 10 ** (-80 / 20))[0]
    fin = min(len(x), (int(vivos[-1]) + 1) * 480 + int(0.05 * SR)) if len(vivos) else len(x)
    x = x[ini:fin].copy()
    n_in = min(len(x), int(0.002 * SR))
    if n_in > 1:
        x[:n_in] *= (0.5 - 0.5 * np.cos(np.linspace(0, np.pi, n_in)))[:, None]
    n_out = min(len(x), int(0.03 * SR))
    if n_out > 1:
        x[-n_out:] *= (0.5 + 0.5 * np.cos(np.linspace(0, np.pi, n_out)))[:, None]
    return x


def candidatos_f0(x: np.ndarray, f_nom: float, ventana):
    """Pico espectral cerca de f_nom·2^k (k=-2..2). Devuelve {k: (f, mag)}."""
    mono = x.mean(axis=1)
    a = int(ventana[0] * SR)
    n = int(ventana[1] * SR)
    seg = mono[a:a + n]
    if len(seg) < 2048:
        seg = mono[: max(2048, len(mono))]
    w = np.hanning(len(seg))
    nfft = 1 << 18
    mag = np.abs(np.fft.rfft(seg * w, nfft))
    df = SR / nfft
    out = {}
    for k in (-2, -1, 0, 1, 2):
        fc = f_nom * 2.0 ** k
        if fc < 20 or fc > SR / 2.2:
            continue
        lo = int(fc * 2 ** (-60 / 1200) / df)
        hi = int(fc * 2 ** (60 / 1200) / df) + 1
        b = lo + int(np.argmax(mag[lo:hi]))
        if 1 <= b < len(mag) - 1:
            y0, y1, y2 = np.log(mag[b - 1:b + 2] + 1e-12)
            d = 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2 + 1e-12)
        else:
            d = 0.0
        out[k] = ((b + d) * df, float(mag[b]))
    return out


V_AFIN = 3


def afinacion_precisa(x: np.ndarray, midi: int, inicio_s: float):
    """Desvío en cents medido en varias ventanas sobre el 1er y 2do armónico.

    Se queda con el armónico más estable (menor desvío absoluto mediano entre
    ventanas). Si ninguno es estable (vibrato fuerte, notas muy graves) → None.
    """
    mono = x.mean(axis=1).astype(np.float64)
    f_ref = 440.0 * 2 ** ((midi - 69) / 12)
    n = int(0.35 * SR)
    if len(mono) < int(inicio_s * SR) + n:
        n = max(2048, len(mono) - int(inicio_s * SR))
    hop = int(0.15 * SR)
    a0 = int(inicio_s * SR)
    starts = list(range(a0, max(a0 + 1, min(len(mono) - n, a0 + int(2.2 * SR))), hop))[:12]
    nfft = 1 << 19
    df = SR / nfft
    w = np.hanning(n)
    res = {}
    for h in (1, 2):
        fh = f_ref * h
        if fh > SR / 2.5:
            continue
        cs = []
        for a in starts:
            seg = mono[a:a + n]
            if len(seg) < n:
                break
            mag = np.abs(np.fft.rfft(seg * w, nfft))
            lo = int(fh * 2 ** (-60 / 1200) / df)
            hi = int(fh * 2 ** (60 / 1200) / df) + 1
            b = lo + int(np.argmax(mag[lo:hi]))
            y0, y1, y2 = np.log(mag[b - 1:b + 2] + 1e-12)
            d = 0.5 * (y0 - y2) / (y0 - 2 * y1 + y2 + 1e-12)
            cs.append(1200 * np.log2((b + d) * df / fh))
        if cs:
            cs = np.array(cs)
            med = float(np.median(cs))
            res[h] = (med, float(np.median(np.abs(cs - med))) if len(cs) > 1 else 5.0)
    if not res:
        return None, None, None
    h = min(res, key=lambda k: res[k][1])
    # la fundamental manda en la altura percibida: preferirla si es estable
    # (en el piano, el 2º parcial está estirado por la inarmonicidad)
    if 1 in res and res[1][1] <= 6.0:
        h = 1
    med, mad = res[h]
    if mad > 10.0:
        return None, round(mad, 1), h
    return med, round(mad, 1), h


# ------------------------------------------------------------- nivelación ----
def _estereo64(x) -> np.ndarray:
    """Como lo lee el motor: mono → estéreo × 0,7071 (misma potencia sumada)."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1) * 0.7071
    return x


def _inicio_ataque(p: np.ndarray) -> int:
    """Primera muestra (bloques de 5 ms) donde la potencia K llega a −20 dB de su máximo inicial."""
    h = int(0.005 * SR)
    nb = max(1, min(len(p) // h, int(0.5 * SR) // h))
    e = p[: nb * h].reshape(nb, h).mean(axis=1)
    return int(np.nonzero(e >= e.max() * 0.01)[0][0]) * h


def _nivel_espectral(f, mag_db, fc, tol=0.03):
    sel = (f > fc * (1 - tol)) & (f < fc * (1 + tol))
    if not sel.any():
        return fc, -200.0
    i = int(np.argmax(np.where(sel, mag_db, -400.0)))
    return float(f[i]), float(mag_db[i])


def analizar_modos(x, f0: float, sostenido: bool) -> dict:
    """Parciales que hay que domar en las láminas del vibráfono, relativos a la fundamental:
    el de dos octavas (4·f0, afinado en la lámina) y el 3er modo (~10·f0, sin afinar)."""
    from motor.analisis import _potencia_k
    from motor.instrumentos.muestreados import zona_estable
    x = _estereo64(x)
    mono = x.mean(axis=1)
    k = _inicio_ataque(_potencia_k(x))
    if sostenido:
        s0, s1, _ = zona_estable(mono)
        ventanas = {"ataque": (s0, s1), "sost": (s0, s1)}
    else:
        ventanas = {"ataque": (k + int(0.02 * SR), k + int(0.35 * SR)),
                    "sost": (k + int(0.5 * SR), min(len(mono), k + int(2.0 * SR)))}
    nfft = 1 << 18
    f = np.fft.rfftfreq(nfft, 1 / SR)
    out = {"p4": {}, "m3": {}}
    for nom, (a, b) in ventanas.items():
        seg = mono[a:b]
        if len(seg) < 2048:
            seg = mono[k:k + 4096]
        mag = 20 * np.log10(np.abs(np.fft.rfft(seg * np.hanning(len(seg)), nfft)) + 1e-12)
        _, l1 = _nivel_espectral(f, mag, f0)
        f4, l4 = _nivel_espectral(f, mag, 4 * f0)
        sel = (f > 9.0 * f0) & (f < 12.0 * f0) & (f < 0.45 * SR)
        if sel.any():
            i3 = int(np.argmax(np.where(sel, mag, -400.0)))
            f3, l3 = float(f[i3]), float(mag[i3])
        else:
            f3, l3 = 10.5 * f0, l1 - 200.0
        out["p4"][f"db_{nom}"] = round(l4 - l1, 1)
        out["m3"][f"db_{nom}"] = round(l3 - l1, 1)
        if nom == "ataque":
            out["p4"]["razon"] = round(f4 / f0, 4)
            out["m3"]["razon"] = round(f3 / f0, 4)
    return out


def medir_nivel(x, tipo: str, corta_s: float = 0.4, cadena: dict | None = None,
                midi: float = 60.0) -> dict:
    """Loudness K (BS.1770) de la muestra según su tipo (ver CATALOGO[...]["nivel"]), pasada
    por la cadena con que la toca el motor por defecto (paneo, ancho, `abrir`, `tope_hz`).
    Sostenidos: potencia media de los primeros 5 s del tramo estable (bloques de 0,5 s
    recortados a +3 dB de su mediana)."""
    from motor.analisis import _potencia_k, lufs
    from motor.efectos import biquad, sosf
    from motor.instrumentos.muestreados import zona_estable, _balance
    x = _estereo64(x)
    c = cadena or {}
    if c.get("tope_hz"):
        x = sosf(biquad("pb", c["tope_hz"], 0.6), x)
    pan = c.get("pan", 0.0) + c.get("abrir", 0.0) * float(np.clip((midi - 62) / 24, -1, 1))
    if pan or c.get("ancho", 1.0) != 1.0:
        x = _balance(x, pan, c.get("ancho", 1.0))
    p = _potencia_k(x)
    if tipo == "sostenido":
        s0, s1, _ = zona_estable(x.mean(axis=1))
        s1 = min(s1, s0 + 5 * SR)        # los primeros 5 s del sostenido: lo que más se oye
        h = int(0.5 * SR)
        nb = max(1, (s1 - s0) // h)
        bloques = p[s0:s0 + nb * h].reshape(nb, -1).mean(axis=1)
        # potencia media con los bloques recortados a +2,5 dB de la mediana: un regulador de la
        # toma (algunas violas suaves crecen 5–8 dB y vuelven) no decide el nivel de la muestra
        bloques = np.minimum(bloques, np.median(bloques) * 10 ** 0.25)
        lk = -0.691 + 10 * np.log10(bloques.mean() + 1e-30)
        return {"lk": round(float(lk), 2), "zona_s": [round(s0 / SR, 3), round(s1 / SR, 3)]}
    k = _inicio_ataque(p)
    corta = -0.691 + 10 * np.log10(p[k:k + int(corta_s * SR)].mean() + 1e-30)
    seg = x[k:k + 2 * SR]
    dos = lufs(np.pad(seg, ((0, max(0, int(0.4 * SR) - len(seg))), (0, 0))))
    if dos is None or not np.isfinite(dos):
        dos = corta
    lk = 0.5 * (corta + dos)
    return {"lk": round(float(lk), 2), "corta": round(float(corta), 2), "dos_s": round(float(dos), 2),
            "inicio_s": round(k / SR, 4)}


def _excluida(e, excluir) -> bool:
    for z in excluir or ():
        if isinstance(z, (tuple, list)):
            if int(e.get("midi", -1)) == int(z[0]) and int(e.get("capa", 0)) == int(z[1]):
                return True
        elif int(e.get("midi", -1)) == int(z):
            return True
    return False


def nivelar(inst: str, cfg: dict, entradas: list) -> int:
    """Mide (lo que falte) y anota en cada muestra `usable` y `ajuste_db` (dB que la llevan a la
    referencia de su capa: REF_NIVEL_DB + capas_db[capa]). Devuelve cuántas midió."""
    niv = cfg.get("nivel")
    if not niv:
        return 0
    from motor.instrumentos.base import VERSION_NIVEL
    from motor.instrumentos.muestreados import DOMAR_POR_BANCO, domar_parciales, cadena_de_banco
    cadena = cadena_de_banco(inst)
    firma = (f"{niv['tipo']}:{niv.get('corta_s', 0)}:{'domar' if niv.get('domar') else ''}:"
             f"{sorted(cadena.items())}:potencia5r25:{VERSION_NIVEL}")
    if niv.get("domar"):
        firma += ":" + repr(sorted(DOMAR_POR_BANCO.get(inst, {}).items()))
    medidas = 0
    for e in entradas:
        if e.get("midi") is None:
            continue
        if e.get("nivel", {}).get("firma") == firma:
            continue
        x = np.asarray(np.load(DIR_PROC / e["archivo"], mmap_mode="r"), dtype=np.float32)
        if niv.get("domar"):
            f0 = 440.0 * 2 ** ((e["midi"] - 69) / 12) * 2 ** (e.get("cents", 0.0) / 1200)
            e["modos"] = analizar_modos(x, f0, niv["tipo"] == "sostenido")
            y = x if x.ndim == 2 and x.shape[1] == 2 else _estereo64(x).astype(np.float32)
            x = domar_parciales(y, f0, e["modos"], 1.0, **DOMAR_POR_BANCO.get(inst, {}))
        e["nivel"] = medir_nivel(x, niv["tipo"], niv.get("corta_s", 0.4), cadena, e["midi"])
        e["nivel"]["firma"] = firma
        medidas += 1
    capas_db = list(niv.get("capas_db", (0.0,)))
    for e in entradas:
        if e.get("midi") is None or "nivel" not in e:
            continue
        rel = capas_db[min(int(e.get("capa", 0)), len(capas_db) - 1)]
        e["usable"] = not _excluida(e, niv.get("excluir"))
        e["ajuste_db"] = round(REF_NIVEL_DB + rel - e["nivel"]["lk"], 2)
    return medidas


# --------------------------------------------------------------- proceso ----
def procesar(forzar=False):
    DIR_PROC.mkdir(parents=True, exist_ok=True)
    previo = {}
    if MANIFIESTO.exists() and not forzar:
        try:
            m = json.loads(MANIFIESTO.read_text())
            if m.get("version_proceso") == VERSION_PROCESO:
                for inst, d in m["instrumentos"].items():
                    for e in d["muestras"]:
                        previo[(inst, e["origen"])] = e
        except Exception:
            previo = {}
    manifest = {"version_proceso": VERSION_PROCESO, "sr": SR, "instrumentos": {}}
    for inst, cfg in CATALOGO.items():
        repo = cfg["repo"]
        carpeta = DIR_MUESTRAS / repo / cfg["carpeta"]
        if not carpeta.exists():
            log(f"AVISO: falta {carpeta}")
            continue
        archivos = sorted(p for p in carpeta.rglob("*")
                          if p.is_file() and re.search(cfg["filtro"], p.name))
        destino = DIR_PROC / inst
        destino.mkdir(parents=True, exist_ok=True)
        entradas = []
        nuevos = 0
        for p in archivos:
            origen = f"{repo}/{p.relative_to(DIR_MUESTRAS / repo)}"
            npy = destino / (p.stem + ".npy")
            e = previo.get((inst, origen))
            if e and npy.exists():
                midi_nom, capa_raw, rr, art = parsear_nombre(p.name, cfg.get("capas"))
                e.update(midi_nominal=midi_nom, capa_raw=capa_raw, rr=rr)
                entradas.append(e)
                continue
            midi_nom, capa_raw, rr, art = parsear_nombre(p.name, cfg.get("capas"))
            x = limpiar(cargar_48k(p))
            np.save(npy, x)
            nuevos += 1
            mono = x.mean(axis=1)
            n200 = min(len(mono), int(0.2 * SR))
            e = {
                "origen": origen,
                "archivo": str(npy.relative_to(DIR_PROC)),
                "canales": int(x.shape[1]),
                "dur_s": round(len(x) / SR, 4),
                "pico_db": round(float(20 * np.log10(np.abs(x).max() + 1e-12)), 2),
                "rms_db": round(float(10 * np.log10(np.mean(mono[:n200] ** 2) + 1e-20)), 2),
                "midi_nominal": midi_nom,
                "capa_raw": capa_raw,
                "rr": rr,
            }
            if art:
                e["articulacion"] = art
            if cfg.get("tono", True) and midi_nom is not None:
                f_nom = 440.0 * 2 ** ((midi_nom - 69) / 12)
                c = candidatos_f0(x, f_nom, cfg.get("ventana", (0.05, 0.5)))
                e["candidatos"] = {str(k): [round(float(f), 3), round(float(m), 3)]
                                   for k, (f, m) in c.items()}
            entradas.append(e)
        if nuevos:
            log(f"{inst}: {nuevos} muestras procesadas")
        # --- afinación: octava común del instrumento (votación) y cents finos
        if cfg.get("tono", True):
            votos = Counter()
            for e in entradas:
                c = e.get("candidatos")
                if not c:
                    continue
                k = max(c, key=lambda kk: c[kk][1])
                votos[int(k)] += 1
            k_voto = votos.most_common(1)[0][0] if votos else 0
            k_inst = cfg.get("octava", k_voto)
            if k_voto != k_inst:
                log(f"  {inst}: la votación sugiere octava {k_voto:+d}, se usa {k_inst:+d} (convención del banco)")
            for e in entradas:
                if e["midi_nominal"] is None:
                    continue
                midi = e["midi_nominal"] + 12 * k_inst
                if e.get("midi") == midi and e.get("v_afin") == V_AFIN:
                    continue  # ya medido con este método
                e["midi"] = midi
                e.pop("afinacion_dudosa", None)
                cents, mad, h = 0.0, None, None
                if cfg.get("afinar", True) and not (inst.startswith("piano") and midi < 45):
                    x = np.load(DIR_PROC / e["archivo"], mmap_mode="r")
                    cents, mad, h = afinacion_precisa(np.asarray(x), midi, cfg.get("ventana", (0.05, 0.5))[0])
                    if cents is None or abs(cents) > 40:
                        e["afinacion_dudosa"] = True
                        cents = 0.0
                e["cents"] = round(float(cents), 2)
                e["afin"] = {"mad": mad, "armonico": h}
                e["v_afin"] = V_AFIN
        # --- capas ordenadas 0..N-1
        crudas = sorted({e["capa_raw"] for e in entradas if e.get("capa_raw") is not None})
        for e in entradas:
            e["capa"] = crudas.index(e["capa_raw"]) if e.get("capa_raw") in crudas else 0
        # --- nivelación (mide solo lo que falte; el ajuste se recalcula siempre)
        medidas = nivelar(inst, cfg, entradas)
        if medidas:
            log(f"{inst}: nivel medido en {medidas} muestras")
        info = REPOS[repo]
        manifest["instrumentos"][inst] = {
            "fuente": f"{repo} ({info['url']})",
            "licencia": info["licencia"],
            "carpeta": cfg["carpeta"],
            "n_capas": max(1, len(crudas)),
            "muestras": sorted(entradas, key=lambda e: (e.get("midi") or 0, e["capa"], e["rr"])),
        }
        if cfg.get("nivel"):
            manifest["instrumentos"][inst]["nivel"] = {k: list(v) if isinstance(v, tuple) else v
                                                       for k, v in cfg["nivel"].items()}
    from motor.instrumentos.base import VERSION_NIVEL
    manifest["version_nivel"] = VERSION_NIVEL
    tmp = MANIFIESTO.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(manifest, indent=1, ensure_ascii=False, default=_json))
    tmp.replace(MANIFIESTO)          # atómico: un render en paralelo nunca lee un manifiesto a medias
    return manifest


def _json(o):
    if isinstance(o, np.generic):
        return o.item()
    raise TypeError(type(o))


def resumen(manifest):
    for inst, d in manifest["instrumentos"].items():
        ms = d["muestras"]
        notas = [e["midi"] for e in ms if "midi" in e]
        rango = f"{min(notas)}–{max(notas)}" if notas else "sin altura"
        dudosas = sum(1 for e in ms if e.get("afinacion_dudosa"))
        cents = [abs(e.get("cents", 0)) for e in ms]
        log(f"{inst:16s} {len(ms):3d} muestras, capas={d['n_capas']}, midi {rango}, "
            f"|cents| máx={max(cents) if cents else 0:.1f}, dudosas={dudosas}")


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--forzar", action="store_true", help="reprocesa todas las muestras")
    ap.add_argument("--sin-bajar", action="store_true", help="no toca git, solo procesa")
    a = ap.parse_args()
    if not a.sin_bajar:
        bajar_repos()
    m = procesar(forzar=a.forzar)
    resumen(m)
    log(f"listo → {MANIFIESTO}")


if __name__ == "__main__":
    sys.exit(main())
