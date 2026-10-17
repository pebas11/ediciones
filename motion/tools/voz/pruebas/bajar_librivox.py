"""Baja grabaciones reales de dominio público en español (LibriVox, archive.org) para probar
la limpieza y la transcripción con voz humana.

    python pruebas/bajar_librivox.py            → pruebas/librivox/*.mp3

Por defecto:
    escuerzo.mp3   "El escuerzo" de Leopoldo Lugones (8:20), Antología de Cuentos Fantásticos
    itati.mp3      "La bruja de Itatí" (14:29), misma antología
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
BASE = "https://archive.org/download/antologia_de_cuentos_fantasticos_1905_librivox/"
ARCHIVOS = {
    "escuerzo.mp3": BASE + "antologiacuentosfantasticos_11_various.mp3",
    "itati.mp3": BASE + "antologiacuentosfantasticos_06_various.mp3",
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=AQUI / "librivox")
    ap.add_argument("--solo", nargs="*", default=None, help="nombres a bajar (defecto: todos)")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    for nombre, url in ARCHIVOS.items():
        if a.solo and nombre not in a.solo:
            continue
        dst = a.out / nombre
        if dst.exists():
            print(f"ya está: {dst}")
            continue
        print(f"bajando {url}", file=sys.stderr)
        with urllib.request.urlopen(url, timeout=120) as r, open(dst, "wb") as f:
            while True:
                b = r.read(1 << 20)
                if not b:
                    break
                f.write(b)
        print(f"listo: {dst} ({dst.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
