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
# ---------------------------------------------------------------------------
CATALOGO = {
    "piano": dict(repo="VCSL", carpeta="Chordophones/Zithers/Upright Piano, Knight/Sustains", octava=1,
                  filtro=r"^Player_vl\d_rr\d_.*\.wav$", ventana=(0.08, 0.6)),
    "piano_soltar": dict(repo="VCSL", carpeta="Chordophones/Zithers/Upright Piano, Knight/Releases", octava=1, afinar=False,
                         filtro=r"^Player_rel_rr\d_.*\.wav$", ventana=(0.0, 0.25)),
    "piano_pedal": dict(repo="VCSL", carpeta="Chordophones/Zithers/Upright Piano, Knight/Pedal",
                        filtro=r"^Player_Ped(On|Off)_\d+\.wav$", tono=False),
    "arpa": dict(repo="VCSL", carpeta="Chordophones/Composite Chordophones/Concert Harp", octava=0,
                 filtro=r"^KSHarp_.*\.wav$", capas={"p": 0, "mp": 0, "mf": 0, "f": 1},
                 ventana=(0.05, 0.5)),
    "vibrafono": dict(repo="VCSL", carpeta="Idiophones/Struck Idiophones/Vibraphone/Soft Mallets", octava=1,
                      filtro=r"^Vibes_soft_.*\.wav$", ventana=(0.05, 0.5)),
    "vibrafono_arco": dict(repo="VCSL", carpeta="Idiophones/Struck Idiophones/Vibraphone/Bowed", octava=1,
                           filtro=r"^Vibes_bowed_.*\.wav$", ventana=(0.6, 0.8)),
    "glock": dict(repo="VCSL", carpeta="Idiophones/Struck Idiophones/Glockenspiel", octava=1,
                  filtro=r"^glock_.*\.wav$", capas={"soft": 0, "medium": 1, "loud": 2},
                  ventana=(0.02, 0.3)),
    "violines": dict(repo="VSCO-2-CE", octava=1, carpeta="Strings/Violin Section/susVib",
                     filtro=r"\.wav$", ventana=(0.4, 0.7)),
    "violines_trem": dict(repo="VSCO-2-CE", octava=1, afinar=False, carpeta="Strings/Violin Section/Trem",
                          filtro=r"\.wav$", ventana=(0.4, 0.7)),
    "violines_pizz": dict(repo="VSCO-2-CE", octava=1, afinar=False, carpeta="Strings/Violin Section/Pizz",
                          filtro=r"\.wav$", ventana=(0.03, 0.25)),
    "violas": dict(repo="VSCO-2-CE", octava=1, carpeta="Strings/Viola Section/susvib",
                   filtro=r"\.wav$", ventana=(0.4, 0.7)),
    "violas_trem": dict(repo="VSCO-2-CE", octava=1, afinar=False, carpeta="Strings/Viola Section/trem",
                        filtro=r"\.wav$", ventana=(0.4, 0.7)),
    "chelos": dict(repo="VSCO-2-CE", octava=1, carpeta="Strings/Cello Section/susvib",
                   filtro=r"\.wav$", ventana=(0.4, 0.7)),
    "chelos_trem": dict(repo="VSCO-2-CE", octava=1, afinar=False, carpeta="Strings/Cello Section/trem",
                        filtro=r"\.wav$", ventana=(0.4, 0.7)),
    "chelos_pizz": dict(repo="VSCO-2-CE", octava=1, afinar=False, carpeta="Strings/Cello Section/pizzT",
                        filtro=r"\.wav$", ventana=(0.03, 0.3)),
    "contrabajo": dict(repo="VSCO-2-CE", octava=1, carpeta="Strings/Solo Contrabass/SusNV",
                       filtro=r"\.wav$", ventana=(0.4, 0.8)),
    "contrabajo_pizz": dict(repo="VSCO-2-CE", octava=1, afinar=False, carpeta="Strings/Solo Contrabass/Pizz",
                            filtro=r"\.wav$", ventana=(0.05, 0.4)),
}

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
        info = REPOS[repo]
        manifest["instrumentos"][inst] = {
            "fuente": f"{repo} ({info['url']})",
            "licencia": info["licencia"],
            "carpeta": cfg["carpeta"],
            "n_capas": max(1, len(crudas)),
            "muestras": sorted(entradas, key=lambda e: (e.get("midi") or 0, e["capa"], e["rr"])),
        }
    MANIFIESTO.write_text(json.dumps(manifest, indent=1, ensure_ascii=False, default=_json))
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
