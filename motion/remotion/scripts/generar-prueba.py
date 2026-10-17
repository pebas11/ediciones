#!/usr/bin/env python3
"""Genera los recursos sintéticos de la composición PruebaTecnica (10 s).

  public/audio/prueba-musica.wav   pad + bombo a 90 bpm (sin agudos)
  public/audio/prueba-voz.wav      "voz" sintética alineada con la transcripción
  public/audio/prueba-clics.wav    clics de sincronía (ráfagas agudas de 2 ms)
  public/datos/transcripcion-prueba.json
  public/datos/musica-cues-prueba.json   (bpm, compás y downbeats en segundos)
  public/datos/sync-prueba.json          (cuadros con clic)

Todo es determinista (semilla fija). Uso:  python3 scripts/generar-prueba.py
"""
import json
import pathlib
import wave

import numpy as np
from scipy import signal

RAIZ = pathlib.Path(__file__).resolve().parent.parent
SR = 48000
FPS = 60
DUR = 10.0
N = int(SR * DUR)
rng = np.random.default_rng(1234)

BPM = 90
COMPAS = 4
PRIMER_DOWNBEAT = 0.5
CLICS = [60, 149, 150, 300, 451, 512, 599]  # incluye uniones de tramos de 150 cuadros y el último

PALABRAS = [
    ("Esto", 0.90, 1.12), ("es", 1.18, 1.30), ("una", 1.36, 1.58), ("prueba", 1.64, 2.05),
    ("de", 2.11, 2.22), ("sueño", 2.30, 2.72), ("lúcido,", 2.80, 3.30),
    ("con", 3.95, 4.12), ("voz,", 4.20, 4.55), ("música", 4.75, 5.20), ("y", 5.27, 5.36),
    ("luz.", 5.44, 5.95),
    ("Todo", 6.70, 7.00), ("sincronizado", 7.08, 7.85), ("al", 7.92, 8.04), ("cuadro.", 8.10, 8.70),
]


def guardar_wav(ruta: pathlib.Path, x: np.ndarray) -> None:
    """x: (n,) o (n, 2) en [-1, 1] → WAV PCM 16 bits estéreo 48 kHz."""
    if x.ndim == 1:
        x = np.stack([x, x], axis=1)
    pcm = (np.clip(x, -1, 1) * 32767).astype("<i2")
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(ruta), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())


def pasabajos(x: np.ndarray, fc: float, orden: int = 4) -> np.ndarray:
    sos = signal.butter(orden, fc, "low", fs=SR, output="sos")
    return signal.sosfilt(sos, x)


def musica() -> np.ndarray:
    t = np.arange(N) / SR
    # Pad: acorde cálido (re menor con novena), armónicos suaves y respiración por compás.
    notas = [146.83, 220.0, 261.63, 329.63, 349.23]
    pad = np.zeros(N)
    for k, f in enumerate(notas):
        for h, a in ((1, 1.0), (2, 0.35), (3, 0.15)):
            for detune in (-0.18, 0.18):
                pad += a * np.sin(2 * np.pi * (f * h + detune) * t + k * 1.3 + h)
    compas_s = 60 / BPM * COMPAS
    respiro = 0.75 + 0.25 * np.sin(2 * np.pi * (t - PRIMER_DOWNBEAT) / compas_s - np.pi / 2)
    pad = pasabajos(pad * respiro, 2200) / 30.0

    # Bombo en cada pulso: seno con caída de tono (sin contenido agudo).
    bombo = np.zeros(N)
    beat_s = 60 / BPM
    k = 0
    tb = PRIMER_DOWNBEAT
    while tb < DUR:
        i0 = int(round(tb * SR))
        n = min(int(0.45 * SR), N - i0)
        tt = np.arange(n) / SR
        frec = 48 + 62 * np.exp(-tt / 0.035)
        fase = 2 * np.pi * np.cumsum(frec) / SR
        amp = (0.55 if k % COMPAS == 0 else 0.32) * np.exp(-tt / 0.12)
        bombo[i0:i0 + n] += amp * np.sin(fase)
        k += 1
        tb = PRIMER_DOWNBEAT + k * beat_s
    x = pad + pasabajos(bombo, 900)
    # Fundido de 30 ms en los bordes
    f = int(0.03 * SR)
    x[:f] *= np.linspace(0, 1, f)
    x[-f:] *= np.linspace(1, 0, f)
    return x / np.max(np.abs(x)) * 0.5


def voz() -> np.ndarray:
    """Tono vocal con formantes y modulación silábica en cada palabra (< 3,5 kHz)."""
    x = np.zeros(N)
    formantes = [(650, 110, 1.0), (1150, 130, 0.55), (2500, 170, 0.25)]
    for palabra, ini, fin in PALABRAS:
        i0, i1 = int(ini * SR), int(fin * SR)
        n = i1 - i0
        tt = np.arange(n) / SR
        f0 = 155 - 25 * tt / max(fin - ini, 1e-3) + 4 * np.sin(2 * np.pi * 5.5 * tt)
        fase = 2 * np.pi * np.cumsum(f0) / SR
        sonoro = np.zeros(n)
        for h in range(1, 22):
            fh = 150 * h
            peso = sum(a / (1 + ((fh - fc) / bw) ** 2) for fc, bw, a in formantes)
            sonoro += peso * np.sin(h * fase)
        aire = pasabajos(rng.standard_normal(n), 3000) * 0.05
        silabas = max(1, round(len(palabra.strip(".,")) / 2.6))
        mod = 0.55 + 0.45 * np.sin(np.pi * silabas * tt / max(fin - ini, 1e-3)) ** 2
        env = np.minimum(1, tt / 0.015) * np.minimum(1, (fin - ini - tt) / 0.05).clip(0, 1)
        x[i0:i1] += (sonoro / 6 + aire) * mod * env
    x = pasabajos(x, 3400, 6)
    return x / np.max(np.abs(x)) * 0.6


def clics() -> np.ndarray:
    """Ráfaga de ruido de 2 ms con énfasis en agudos en cada cuadro de CLICS."""
    x = np.zeros(N)
    largo = int(0.002 * SR)
    ventana = np.hanning(largo)
    for c in CLICS:
        i0 = int(round(c / FPS * SR))
        r = np.diff(rng.standard_normal(largo + 1)) * ventana
        n = min(largo, N - i0)
        x[i0:i0 + n] += r[:n]
    return x / np.max(np.abs(x)) * 0.85


def main() -> None:
    audio = RAIZ / "public/audio"
    datos = RAIZ / "public/datos"
    datos.mkdir(parents=True, exist_ok=True)
    guardar_wav(audio / "prueba-musica.wav", musica())
    guardar_wav(audio / "prueba-voz.wav", voz())
    guardar_wav(audio / "prueba-clics.wav", clics())

    (datos / "transcripcion-prueba.json").write_text(
        json.dumps([{"word": w, "start": s, "end": e} for w, s, e in PALABRAS], ensure_ascii=False, indent=1),
        encoding="utf-8",
    )
    beat_s = 60 / BPM
    downbeats = []
    t = PRIMER_DOWNBEAT
    while t < DUR:
        downbeats.append(round(t, 4))
        t += beat_s * COMPAS
    (datos / "musica-cues-prueba.json").write_text(
        json.dumps({"bpm": BPM, "compas": COMPAS, "downbeats": downbeats}, indent=1), encoding="utf-8"
    )
    (datos / "sync-prueba.json").write_text(json.dumps({"fps": FPS, "clics": CLICS}, indent=1), encoding="utf-8")
    print("Recursos de prueba generados en public/audio y public/datos")


if __name__ == "__main__":
    main()
