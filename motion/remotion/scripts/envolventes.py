#!/usr/bin/env python3
"""Precalcula por cuadro el audio que la animación necesita para reaccionar, sin FFT
en tiempo de render. Salida: un JSON compacto que lee src/lib/audio.ts.

Por pista (voz y cada stem de música):
  - nivel: RMS en dB por cuadro, mapeado a 0..1 (u8 en base64)
  - onsets: cuadros con ataques (flujo espectral + selección de picos) y su fuerza
  - bandas (opcional, --bandas): graves / medios / agudos por cuadro, 0..1
Música (desde un cues.json con bpm y downbeats):
  - beats y downbeats en cuadros (+ secciones/marcas si las hay)

Uso:
  python3 scripts/envolventes.py --fps 60 --salida public/datos/envolventes.json \\
      --pista voz=public/audio/voz.wav --pista bajo=stems/bajo.wav --pista pad=stems/pad.wav \\
      --cues ../musica/cues.json --bandas

Formato de cues.json (claves aceptadas, en segundos):
  {"bpm": 72, "compas": 4, "downbeats": [0.52, 3.85, ...]}
  o {"bpm": 72, "compas": 4, "primer_downbeat": 0.52}       (grilla regular)
  o {"beats": [...], "downbeats": [...]}                     (explícitos)
  Alias: tempo=bpm, beats_per_bar/metro=compas, offset=primer_downbeat,
  downbeats_s=downbeats. "secciones"/"marcas": [{"nombre": .., "inicio": s}] pasan tal cual.

Decodifica con ffmpeg: acepta WAV, FLAC, MP3, etc. Requiere numpy.
"""
import argparse
import base64
import json
import math
import pathlib
import subprocess
import sys

import numpy as np

SR = 48000


def decodificar(ruta: str) -> np.ndarray:
    """Audio mono float32 a 48 kHz (mezcla de canales)."""
    cmd = ["ffmpeg", "-v", "error", "-i", ruta, "-f", "f32le", "-ac", "1", "-ar", str(SR), "-"]
    r = subprocess.run(cmd, capture_output=True, check=False)
    if r.returncode != 0:
        sys.exit(f"ffmpeg no pudo leer {ruta}: {r.stderr.decode(errors='replace')}")
    return np.frombuffer(r.stdout, dtype="<f4").astype(np.float64)


def a_u8(v: np.ndarray) -> str:
    return base64.b64encode(np.round(np.clip(v, 0, 1) * 255).astype(np.uint8).tobytes()).decode("ascii")


def normalizar_db(db: np.ndarray, rango: float) -> tuple[np.ndarray, list[float]]:
    """dB → 0..1 tomando como techo el percentil 99,5 y como piso techo − rango."""
    validos = db[db > -119]
    techo = float(np.percentile(validos, 99.5)) if validos.size else 0.0
    piso = techo - rango
    return np.clip((db - piso) / rango, 0, 1), [round(piso, 2), round(techo, 2)]


def rms_por_cuadro(x: np.ndarray, cuadros: int, fps: float) -> np.ndarray:
    """RMS en una ventana de 2 cuadros centrada en el centro de cada cuadro."""
    hop = SR / fps
    c2 = np.concatenate([[0.0], np.cumsum(x * x)])
    centros = (np.arange(cuadros) + 0.5) * hop
    a = np.clip(np.round(centros - hop).astype(int), 0, len(x))
    b = np.clip(np.round(centros + hop).astype(int), 0, len(x))
    n = np.maximum(b - a, 1)
    return np.sqrt(np.maximum(c2[b] - c2[a], 0) / n)


def stft_por_cuadro(x: np.ndarray, cuadros: int, fps: float, nfft: int = 2048, bloque: int = 2048):
    """Genera (inicio, |X|) por bloques: un espectro por cuadro.

    Ventana CAUSAL que termina al final del cuadro: un ataque aparece en el cuadro en que
    empieza a sonar, no antes (con una ventana centrada los onsets salían 1 cuadro antes).
    """
    hop = SR / fps
    ventana = np.hanning(nfft)
    pad = np.concatenate([np.zeros(nfft), x, np.zeros(nfft)])
    for ini in range(0, cuadros, bloque):
        fin = min(cuadros, ini + bloque)
        finales = np.round((np.arange(ini, fin) + 1) * hop).astype(int) + nfft
        idx = finales[:, None] - nfft + np.arange(nfft)[None, :]
        yield ini, np.abs(np.fft.rfft(pad[idx] * ventana, axis=1))


BANDAS = {"graves": (20, 200), "medios": (200, 2000), "agudos": (2000, 12000)}


def analizar(x: np.ndarray, cuadros: int, fps: float, rango: float, con_bandas: bool, sensibilidad: float):
    nivel, rango_db = normalizar_db(20 * np.log10(rms_por_cuadro(x, cuadros, fps) + 1e-9), rango)

    nfft = 2048
    frecs = np.fft.rfftfreq(nfft, 1 / SR)
    flujo = np.zeros(cuadros)
    energia_bandas = {k: np.zeros(cuadros) for k in BANDAS}
    previo = None
    for ini, mag in stft_por_cuadro(x, cuadros, fps, nfft):
        logm = np.log1p(100 * mag)
        if previo is None:
            previo = logm[:1]
        dif = np.diff(np.concatenate([previo, logm]), axis=0)
        flujo[ini:ini + len(mag)] = np.maximum(dif, 0).sum(axis=1)
        previo = logm[-1:]
        if con_bandas:
            pot = mag ** 2
            for k, (lo, hi) in BANDAS.items():
                sel = (frecs >= lo) & (frecs < hi)
                energia_bandas[k][ini:ini + len(mag)] = pot[:, sel].sum(axis=1)

    onsets, fuerzas = detectar_onsets(flujo, fps, sensibilidad)
    res = {"nivel": a_u8(nivel), "rangoDb": rango_db, "onsets": onsets, "fuerzaOnsets": fuerzas}
    if con_bandas:
        res["bandas"] = {}
        for k, e in energia_bandas.items():
            v, _ = normalizar_db(10 * np.log10(e + 1e-12), rango)
            res["bandas"][k] = a_u8(v)
    return res


def detectar_onsets(flujo: np.ndarray, fps: float, sensibilidad: float):
    """Selección de picos al estilo librosa: máximo local + sobre la media local + espera."""
    if flujo.max() <= 0:
        return [], []
    f = flujo / (np.percentile(flujo, 99) + 1e-9)
    pre_max = post_max = max(1, round(0.03 * fps))
    pre_avg = post_avg = max(1, round(0.10 * fps))
    espera = max(1, round(0.10 * fps))
    delta = 0.07 / max(sensibilidad, 1e-3)
    onsets, fuerzas, ultimo = [], [], -10**9
    for i in range(len(f)):
        a, b = max(0, i - pre_max), min(len(f), i + post_max + 1)
        if f[i] < f[a:b].max() or f[i] <= 0:
            continue
        a2, b2 = max(0, i - pre_avg), min(len(f), i + post_avg + 1)
        if f[i] < f[a2:b2].mean() + delta:
            continue
        if i - ultimo < espera:
            continue
        onsets.append(int(i))
        fuerzas.append(round(float(min(1.0, f[i])), 3))
        ultimo = i
    return onsets, fuerzas


def leer_cues(ruta: str, fps: float, duracion: float, extrapolar: bool):
    c = json.loads(pathlib.Path(ruta).read_text(encoding="utf-8"))
    bpm = float(c.get("bpm", c.get("tempo", 0)) or 0)
    compas = int(c.get("compas", c.get("beats_per_bar", c.get("metro", 4))))
    downs = [float(t) for t in c.get("downbeats", c.get("downbeats_s", []))]
    beats = [float(t) for t in c.get("beats", [])]
    primer = c.get("primer_downbeat", c.get("offset"))
    periodo = 60.0 / bpm if bpm > 0 else None

    if not downs and primer is not None and periodo:
        t = float(primer)
        while t < duracion:
            downs.append(t)
            t += periodo * compas
    if downs and extrapolar and periodo:
        t = downs[-1] + periodo * compas
        while t < duracion:
            downs.append(t)
            t += periodo * compas
    if not beats and downs:
        for k, d in enumerate(downs):
            sig = downs[k + 1] if k + 1 < len(downs) else (d + periodo * compas if periodo else None)
            if sig is None:
                beats.append(d)
                continue
            paso = (sig - d) / compas
            beats.extend(d + j * paso for j in range(compas))
    a_cuadro = lambda t: int(round(t * fps))  # noqa: E731
    cuadros_max = int(math.ceil(duracion * fps))
    res = {
        "bpm": bpm,
        "compas": compas,
        "beats": sorted({a_cuadro(t) for t in beats if 0 <= a_cuadro(t) < cuadros_max}),
        "downbeats": sorted({a_cuadro(t) for t in downs if 0 <= a_cuadro(t) < cuadros_max}),
    }
    for clave in ("secciones", "marcas"):
        if isinstance(c.get(clave), list):
            res[clave] = [
                {**m, "cuadro": a_cuadro(float(m.get("inicio", m.get("t", m.get("tiempo", 0)))))}
                for m in c[clave]
                if isinstance(m, dict)
            ]
    return res


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pista", action="append", default=[], help="nombre=ruta (repetible)")
    ap.add_argument("--salida", required=True)
    ap.add_argument("--fps", type=float, default=60)
    ap.add_argument("--cues", help="cues.json de la música (bpm y downbeats)")
    ap.add_argument("--duracion", type=float, help="segundos (por defecto, la pista más larga)")
    ap.add_argument("--rango-db", type=float, default=48, help="rango dinámico mapeado a 0..1")
    ap.add_argument("--bandas", action="store_true", help="calcular graves/medios/agudos")
    ap.add_argument("--sensibilidad", type=float, default=1.0, help=">1 detecta más onsets")
    ap.add_argument("--sin-extrapolar", action="store_true", help="no extender downbeats con el bpm")
    a = ap.parse_args()
    if not a.pista and not a.cues:
        ap.error("hace falta al menos una --pista o --cues")

    senales = {}
    for p in a.pista:
        if "=" not in p:
            ap.error(f"--pista espera nombre=ruta, no {p!r}")
        nombre, ruta = p.split("=", 1)
        senales[nombre] = (ruta, decodificar(ruta))
    duracion = a.duracion or max((len(x) / SR for _, x in senales.values()), default=0)
    cuadros = int(math.ceil(duracion * a.fps))

    pistas = {}
    for nombre, (ruta, x) in senales.items():
        pistas[nombre] = {"archivo": ruta, **analizar(x, cuadros, a.fps, a.rango_db, a.bandas, a.sensibilidad)}
        print(f"  {nombre}: {len(pistas[nombre]['onsets'])} onsets, rango {pistas[nombre]['rangoDb']} dB")

    salida = {
        "version": 1,
        "fps": a.fps,
        "cuadros": cuadros,
        "duracion": round(duracion, 4),
        "sampleRate": SR,
        "pistas": pistas,
        "musica": leer_cues(a.cues, a.fps, duracion, not a.sin_extrapolar) if a.cues else None,
    }
    pathlib.Path(a.salida).parent.mkdir(parents=True, exist_ok=True)
    pathlib.Path(a.salida).write_text(json.dumps(salida, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    kb = pathlib.Path(a.salida).stat().st_size / 1024
    print(f"{a.salida}: {cuadros} cuadros a {a.fps:g} fps, {kb:.0f} KB")


if __name__ == "__main__":
    main()
