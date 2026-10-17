#!/usr/bin/env python3
"""Mezclador final de música y voz (ver motion/musica/MEZCLA.md).

    python3 motion/musica/mezcla_voz.py --voz voz_final.wav --plan plan.json --out salida/mezcla
    python3 motion/musica/mezcla_voz.py --plan plan.json --validar [--voz voz_final.wav]   # solo armado, sin audio
    python3 motion/musica/mezcla_voz.py ... --param ducking.ataque_ms=60 --param niveles.musica_bajo_voz_lu=-21

Salidas en --out: mezcla_final.wav (48 kHz, 24 bit, −14 LUFS, ≤ −1 dBTP), musica_cama.wav (la
música armada y duckeada, en la escala de la voz: voz + cama = mezcla previa al master),
informe.json, mezcla.png y envolventes.json (por cuadro a 60 fps, formato de Remotion).
"""
import os
import sys

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ.setdefault(_v, "2")

import argparse  # noqa: E402
import json  # noqa: E402
from pathlib import Path  # noqa: E402

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))


def parametros_cli(lista):
    """["a.b=1", "c.d=[\"x\"]"] → {"a": {"b": 1}, "c": {"d": ["x"]}}."""
    out: dict = {}
    for item in lista:
        if "=" not in item:
            raise SystemExit(f"--param espera ruta=valor (p. ej. ducking.ataque_ms=60), no {item!r}")
        ruta, valor = item.split("=", 1)
        try:
            v = json.loads(valor)
        except json.JSONDecodeError:
            v = valor
        nodo = out
        partes = ruta.strip().split(".")
        for p in partes[:-1]:
            nodo = nodo.setdefault(p, {})
        nodo[partes[-1]] = v
    return out


def main():
    ap = argparse.ArgumentParser(description="Mezcla final de música y voz",
                                 formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    ap.add_argument("--voz", help="voz editada (WAV, idealmente 48 kHz a −16 LUFS)")
    ap.add_argument("--plan", required=True, help="plan musical (JSON)")
    ap.add_argument("--out", help="carpeta de salida")
    ap.add_argument("--param", action="append", default=[], help="ruta.al.parametro=valor (repetible)")
    ap.add_argument("--canciones", default=None, help="carpeta con las canciones (por defecto motion/musica/salida)")
    ap.add_argument("--validar", action="store_true", help="solo valida el plan e imprime el armado (sin audio)")
    a = ap.parse_args()

    from mezcla.plan import ErrorPlan
    from mezcla.canciones import ErrorCancion
    from mezcla import pipeline
    extra = parametros_cli(a.param)
    try:
        if a.validar:
            plan, voz, edl = pipeline.preparar(a.plan, a.voz, extra, a.canciones, leer_audio=False)
            print(f"plan válido: {len(plan.tramos)} tramos" + (f" · voz {voz.dur:.1f} s, {len(voz.frases)} frases"
                                                              if voz else ""))
            print(pipeline.resumen_edl(edl, plan))
            for av in plan.avisos + edl.avisos:
                print("aviso:", av)
            return
        if not a.voz or not a.out:
            ap.error("--voz y --out son obligatorios (salvo con --validar)")
        pipeline.mezclar(a.voz, a.plan, a.out, extra, a.canciones)
    except (ErrorPlan, ErrorCancion) as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
