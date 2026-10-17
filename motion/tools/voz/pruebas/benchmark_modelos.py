"""Compara modelos de faster-whisper en esta máquina: segundos por minuto de audio y
diferencias de texto (WER contra un texto de referencia o contra el modelo más grande).

    python pruebas/benchmark_modelos.py salida/librivox_escuerzo/voz_limpia.wav --desde 60 --dur 180
    python pruebas/benchmark_modelos.py salida/test_sintetico/voz_limpia.wav --ref-fixture

Guarda el resultado en <carpeta del wav>/benchmark_modelos.json.
"""

from __future__ import annotations

import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))

from vozlib import util  # noqa: E402

HILOS = util.hilos_desde_argv(2)
util.configurar_hilos(HILOS)

import argparse  # noqa: E402
import difflib  # noqa: E402
import os  # noqa: E402
import time  # noqa: E402

CONFIGS = {
    "turbo": dict(modelo="large-v3-turbo", beam_size=5),
    "turbo-beam1": dict(modelo="large-v3-turbo", beam_size=1),
    "turbo-lote8": dict(modelo="large-v3-turbo", beam_size=5, lote=8),
    "large-v3": dict(modelo="large-v3", beam_size=5),
    "large-v3-beam1": dict(modelo="large-v3", beam_size=1),
    "medium": dict(modelo="medium", beam_size=5),
}


def wer(ref: list[str], hip: list[str]) -> float:
    sm = difflib.SequenceMatcher(a=ref, b=hip, autojunk=False)
    err = sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal")
    return err / max(len(ref), 1)


def main():
    util.consola_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("wav", type=Path)
    ap.add_argument("--desde", type=float, default=0.0)
    ap.add_argument("--dur", type=float, default=None)
    ap.add_argument("--configs", nargs="*", default=["turbo", "turbo-beam1", "medium", "large-v3"])
    ap.add_argument("--ref-fixture", action="store_true",
                    help="usar el guion del fixture como referencia (WER real)")
    ap.add_argument("--hilos", type=int, default=2)
    a = ap.parse_args()
    from vozlib import transcribir

    x, sr = util.leer_wav(a.wav)
    i0 = int(a.desde * sr)
    i1 = int((a.desde + a.dur) * sr) if a.dur else len(x)
    x = x[i0:i1]
    mins = len(x) / sr / 60
    res = {"archivo": str(a.wav), "desde_s": a.desde, "duracion_s": round(len(x) / sr, 2),
           "hilos": HILOS, "cpus": os.cpu_count(), "resultados": {}}
    textos = {}
    for nombre in a.configs:
        cfg = CONFIGS[nombre]
        try:
            carga0 = os.getloadavg()[0]
        except (AttributeError, OSError):
            carga0 = None
        t0 = time.perf_counter()
        tr = transcribir.transcribir(x, sr, modelo=cfg["modelo"], hilos=HILOS, beam_size=cfg["beam_size"],
                                     lote=cfg.get("lote", 0))
        dt = time.perf_counter() - t0
        textos[nombre] = [transcribir.normalizar(w["texto"]) for w in tr["palabras"]]
        textos[nombre] = [t for t in textos[nombre] if t]
        res["resultados"][nombre] = {
            "modelo": tr["modelo"], "beam": cfg["beam_size"],
            "carga_s": tr["tiempo_carga_s"], "transcripcion_s": tr["tiempo_transcripcion_s"],
            "seg_por_min_audio": round(tr["tiempo_transcripcion_s"] / mins, 1),
            "total_s": round(dt, 1), "palabras": len(tr["palabras"]),
            "carga_maquina_al_empezar": carga0,
            "texto": " ".join(w["texto"] for w in tr["palabras"])[:4000],
        }
        util.log(f"{nombre}: {res['resultados'][nombre]['seg_por_min_audio']} s/min")
    if a.ref_fixture:
        esp = util.leer_json(AQUI / "fixtures" / "esperado.json")
        ref = [w["norm"] for w in esp["palabras"]]
        res["referencia"] = "guion del fixture (todas las palabras dichas, incluidas las tomas fallidas)"
    else:
        ref = textos.get("large-v3") or next(iter(textos.values()))
        res["referencia"] = "large-v3" if "large-v3" in textos else a.configs[0]
    for nombre, t in textos.items():
        res["resultados"][nombre]["wer_vs_referencia"] = round(wer(ref, t), 3)
    salida = a.wav.parent / "benchmark_modelos.json"
    util.guardar_json(salida, res)
    for nombre, r in res["resultados"].items():
        print(f"{nombre:12s} {r['seg_por_min_audio']:6.1f} s/min  WER {r['wer_vs_referencia']:.3f}  "
              f"(carga {r['carga_s']} s, máquina {r['carga_maquina_al_empezar']})")
    print(f"→ {salida}")


if __name__ == "__main__":
    main()
