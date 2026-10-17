#!/usr/bin/env python3
"""Verifica un video renderizado con <CodigoDeCuadro> (prop depuracion de PruebaTecnica):

1. Cuadros: lee el número binario de cada cuadro (fila de 23 celdas abajo a la izquierda)
   y comprueba que sean consecutivos: sin cuadros perdidos ni repetidos (uniones de tramos).
2. Video vs. hoja: las marcas de sincronía (celda 23) caen en los cuadros de sync.json.
3. Audio vs. video: detecta los clics (ráfagas agudas) en el audio del archivo y mide su
   desfase contra el cuadro marcado. Pasa si todos quedan a menos de medio cuadro.

Uso:
  python3 scripts/verificar-sync.py out/tramos/PruebaTecnica/youtube.mp4 \\
      [--sync public/datos/sync-prueba.json] [--desde 0]
Sale con código 0 si todo está bien y 1 si no.
"""
import argparse
import json
import pathlib
import subprocess
import sys

import numpy as np
from scipy import signal

CELDA = 16
BITS = 20
CELDAS = BITS + 3  # guarda blanca + bits + guarda negra + marca


def ffprobe_json(ruta, *args):
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", *args, ruta],
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def leer_codigos(ruta, ancho, alto):
    filtro = f"crop={CELDAS * CELDA}:{CELDA}:0:{alto - CELDA},scale={CELDAS}:1:flags=area,format=gray"
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", ruta, "-map", "0:v:0", "-vf", filtro,
                        "-f", "rawvideo", "-"], capture_output=True, check=True)
    datos = np.frombuffer(r.stdout, dtype=np.uint8).reshape(-1, CELDAS)
    resultado = []
    for fila in datos:
        valido = fila[0] > 160 and fila[BITS + 1] < 96
        bits = fila[1:BITS + 1] > 128
        numero = int("".join("1" if b else "0" for b in bits), 2)
        resultado.append((numero if valido else None, bool(fila[BITS + 2] > 128)))
    return resultado


def leer_audio(ruta, sr=48000):
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", ruta, "-map", "0:a:0", "-ac", "1", "-ar", str(sr),
                        "-f", "f32le", "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype="<f4").astype(np.float64)


def detectar_clics(x, sr=48000):
    """Inicio de cada ráfaga aguda: pasa-altos 5 kHz, envolvente, cruce del 25 % del pico local."""
    sos = signal.butter(6, 5000, "high", fs=sr, output="sos")
    hp = np.abs(signal.sosfiltfilt(sos, x))
    umbral = 0.25 * hp.max()
    idx = np.flatnonzero(hp > umbral)
    if idx.size == 0:
        return []
    grupos = np.split(idx, np.flatnonzero(np.diff(idx) > int(0.005 * sr)) + 1)  # clics de 2 ms; 149 y 150 están a 16,7 ms
    inicios = []
    for g in grupos:
        a, b = g[0], g[-1]
        pico = a + int(np.argmax(hp[a:b + 1]))
        # La ráfaga dura 2 ms con ventana de Hann: el pico de energía cae a ~1 ms del inicio.
        inicios.append((pico - 0.001 * sr) / sr)
    return inicios


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--sync", default="public/datos/sync-prueba.json")
    ap.add_argument("--desde", type=int, default=None, help="primer cuadro esperado (por defecto, el leído)")
    a = ap.parse_args()

    info = ffprobe_json(a.video, "-show_streams")
    v = next(s for s in info["streams"] if s["codec_type"] == "video")
    num, den = (int(x) for x in v["r_frame_rate"].split("/"))
    fps = num / den
    ancho, alto = int(v["width"]), int(v["height"])
    sync = json.loads(pathlib.Path(a.sync).read_text())
    ok = True

    # 1. Continuidad de cuadros
    codigos = leer_codigos(a.video, ancho, alto)
    numeros = [c for c, _ in codigos]
    invalidos = [k for k, c in enumerate(numeros) if c is None]
    primero = a.desde if a.desde is not None else next(c for c in numeros if c is not None)
    errores = [(k, c) for k, c in enumerate(numeros) if c is not None and c != primero + k]
    print(f"Video: {len(codigos)} cuadros a {fps:g} fps, {ancho}×{alto}; códigos {primero}…{numeros[-1]}")
    if invalidos:
        ok = False
        print(f"  ✗ {len(invalidos)} cuadros sin código legible (primeros: {invalidos[:5]})")
    if errores:
        ok = False
        print(f"  ✗ {len(errores)} cuadros fuera de secuencia, p. ej. posición {errores[0][0]} trae {errores[0][1]}")
    if not invalidos and not errores:
        print("  ✓ todos los cuadros presentes y en orden (sin perdidos ni repetidos)")

    # 2. Marcas de video
    marcas = [numeros[k] for k, (_, m) in enumerate(codigos) if m]
    esperadas = [c for c in sync["clics"] if primero <= c <= primero + len(codigos) - 1]
    if marcas == esperadas:
        print(f"  ✓ marcas de sincronía en los cuadros esperados: {marcas}")
    else:
        ok = False
        print(f"  ✗ marcas en {marcas}, se esperaban {esperadas}")

    # 3. Audio contra video
    if not any(s["codec_type"] == "audio" for s in info["streams"]):
        print("  (sin pista de audio)")
        return 0 if ok else 1
    x = leer_audio(a.video)
    dur_a, dur_v = len(x) / 48000, len(codigos) / fps
    print(f"Audio: {dur_a:.4f} s; video: {dur_v:.4f} s; diferencia {1000 * (dur_a - dur_v):+.1f} ms")
    clics = detectar_clics(x)
    tolerancia = 0.5 / fps
    peor = 0.0
    for c in esperadas:
        t_video = (c - primero) / fps
        cerca = min(clics, key=lambda t: abs(t - t_video)) if clics else None
        if cerca is None or abs(cerca - t_video) > 0.1:
            ok = False
            print(f"  ✗ cuadro {c}: no se encontró el clic en el audio")
            continue
        d = cerca - t_video
        peor = max(peor, abs(d))
        marca = "✓" if abs(d) <= tolerancia else "✗"
        if abs(d) > tolerancia:
            ok = False
        print(f"  {marca} cuadro {c}: clic a {1000 * d:+.2f} ms de su cuadro")
    print(f"Peor desfase audio/video: {1000 * peor:.2f} ms (tolerancia ±{1000 * tolerancia:.1f} ms = medio cuadro)")
    print("RESULTADO:", "OK" if ok else "FALLA")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
