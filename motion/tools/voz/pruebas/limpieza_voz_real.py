"""Limpieza sobre voz humana real con degradaciones conocidas.

Toma un tramo de una grabación limpia (LibriVox), le aplica la misma cadena de "grabación
casera" del fixture (reverb de habitación, ruido rosa, zumbido de 50 Hz, recorte y AAC) y
compara la voz limpiada con el original limpio:

    - ruido en las pausas relativo a la voz (antes / después)
    - distancia espectral logarítmica (LSD, dB) contra la referencia, en cuadros con voz
    - correlación de envolventes espectrales por banda (proxy de inteligibilidad)

    python pruebas/limpieza_voz_real.py pruebas/librivox/escuerzo.mp3 --desde 60 --dur 120
"""

from __future__ import annotations

import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))
sys.path.insert(0, str(AQUI))

from vozlib import util  # noqa: E402

HILOS = util.hilos_desde_argv(2)
util.configurar_hilos(HILOS)

import argparse  # noqa: E402

import numpy as np  # noqa: E402
from scipy import signal  # noqa: E402

SR = 48000


def lsd(ref: np.ndarray, x: np.ndarray, mask: np.ndarray, nper: int = 1024) -> float:
    """Distancia espectral logarítmica media (dB) en los cuadros con voz."""
    _, _, R = signal.stft(ref, fs=SR, nperseg=nper)
    _, _, X = signal.stft(x, fs=SR, nperseg=nper)
    n = min(R.shape[1], X.shape[1], len(mask))
    R, X, m = R[:, :n], X[:, :n], mask[:n]
    lr = 10 * np.log10(np.abs(R) ** 2 + 1e-10)
    lx = 10 * np.log10(np.abs(X) ** 2 + 1e-10)
    d = np.sqrt(np.mean((lr - lx) ** 2, axis=0))
    return float(np.mean(d[m]))


def main():
    util.consola_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("entrada", type=Path)
    ap.add_argument("--desde", type=float, default=60)
    ap.add_argument("--dur", type=float, default=120)
    ap.add_argument("--out", type=Path, default=None)
    ap.add_argument("--sin-reverb", action="store_true",
                    help="solo ruido + zumbido + recorte + AAC (para medir el ruido sin la cola de la sala)")
    a = ap.parse_args()
    import generar_fixture as gf
    from vozlib import analisis, espectro, limpieza

    if a.out is None:
        a.out = AQUI.parent / "salida" / ("voz_real_degradada" + ("_sin_reverb" if a.sin_reverb else ""))
    a.out.mkdir(parents=True, exist_ok=True)
    x = util.decodificar(a.entrada, SR).mean(axis=1)
    ref = x[int(a.desde * SR): int((a.desde + a.dur) * SR)].astype(np.float64)
    ref *= 10 ** ((-27 - analisis.loudness(ref, SR)) / 20)
    # degradación casera (la misma del fixture)
    deg = ref.copy() if a.sin_reverb else signal.oaconvolve(ref, gf.rir_habitacion())[: len(ref)]
    deg += gf.ruido_rosa(len(deg)) * 10 ** (-56 / 20) + gf.zumbido(len(deg))
    pico = np.max(np.abs(deg))
    deg = np.clip(deg * (10 ** (2 / 20) / pico), -1, 1)  # el pico más fuerte recorta 2 dB
    tmp = a.out / "_deg.wav"
    util.escribir_wav(tmp, deg)
    util.correr_ffmpeg(["-i", tmp, "-c:a", "aac", "-b:a", "128k", a.out / "degradada.m4a"])
    tmp.unlink()
    d = util.decodificar(a.out / "degradada.m4a", SR)[:, 0][: len(ref)].astype(np.float32)
    an = analisis.analizar(d, SR)
    y, pasos = limpieza.limpiar(d, SR, an, hilos=HILOS)
    util.escribir_wav(a.out / "limpia.wav", y)
    util.escribir_wav(a.out / "referencia.wav", ref.astype(np.float32))
    # comparación (se iguala el nivel a la referencia)
    act = analisis.actividad(ref.astype(np.float32), SR)
    hop = int(act["hop_s"] * SR)
    voz = act["mask"]
    pausa = act["db"] < act["piso"] + 6
    res = {}
    for nombre, s in (("degradada", d), ("limpia", y)):
        s = s.astype(np.float64)[: len(ref)]
        g = np.sqrt(np.sum(ref ** 2) / (np.sum(s ** 2) + 1e-12))
        s = s * g
        n = min(len(voz), len(s) // hop)
        e = np.array([np.mean(s[k * hop:(k + 1) * hop] ** 2) for k in range(n)])
        nv = 10 * np.log10(np.mean(e[voz[:n]]) + 1e-20)
        # mediana: las pausas de la referencia incluyen bordes de palabras (la compuerta de
        # LibriVox corta antes que el oído); la mediana mide el piso real
        npau = 10 * np.log10(np.median(e[pausa[:n]]) + 1e-20)
        # máscara de voz para la STFT (nper=1024 → paso 512 muestras)
        t_stft = np.arange(len(s) // 512 + 2) * 512 / SR
        m_stft = voz[np.clip((t_stft / act["hop_s"]).astype(int), 0, len(voz) - 1)]
        res[nombre] = {"voz_sobre_pausas_db": round(nv - npau, 1),
                       "lsd_db_en_voz": round(lsd(ref, s, m_stft), 2)}
    er = np.array([np.mean(ref[k * hop:(k + 1) * hop] ** 2) for k in range(len(voz))])
    res["referencia"] = {"voz_sobre_pausas_db": round(
        10 * np.log10(np.mean(er[voz]) / (np.median(er[pausa]) + 1e-20)), 1)}
    res["pasos"] = {k: pasos[k] for k in ("declip", "zumbido", "ruido", "declick", "plosivas", "deesser", "eq")}
    res["analisis_degradada"] = analisis.resumen_corto(an)
    res["analisis_limpia"] = analisis.resumen_corto(analisis.analizar(y, SR))
    util.guardar_json(a.out / "comparacion.json", res)
    espectro.comparar([("referencia limpia (LibriVox)", ref), ("degradada (casera simulada)", d),
                       ("limpiada por el pipeline", y)], SR, a.out / "espectrograma.png",
                      t0=20, t1=32)
    import json

    print(json.dumps({k: v for k, v in res.items() if k != "pasos"}, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
