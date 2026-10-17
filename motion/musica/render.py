#!/usr/bin/env python3
"""Renderiza canciones de `canciones/`.

    python3 motion/musica/render.py umbral            # una (por nombre, número o archivo)
    python3 motion/musica/render.py todas             # todas, una tras otra
    python3 motion/musica/render.py 01 --hasta 17     # prueba rápida: corta en el compás 17
    python3 motion/musica/render.py 01 --solo piano,arpa --sin-mp3
    python3 motion/musica/render.py 01 --partitura    # imprime cifrado y melodías (sin audio)
    python3 motion/musica/render.py 01 --pianola      # solo la imagen del arreglo (sin audio)

Salida: motion/musica/salida/<slug>/{master.wav, stems/*.wav, cues.json, qa.json, *.png}
y motion/renders/musica/<slug>.mp3 (320 kbps).
"""
import os
import sys

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ.setdefault(_v, "2")

import argparse  # noqa: E402
import importlib  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))


def listar():
    return sorted(p.stem for p in (AQUI / "canciones").glob("[0-9][0-9]_*.py"))


def buscar(nombre: str) -> str:
    nombre = Path(nombre).stem.lower()
    for s in listar():
        num, _, nom = s.partition("_")
        if nombre in (s, num, nom, str(int(num))):
            return s
    raise SystemExit(f"no encuentro la canción '{nombre}'. Hay: {', '.join(listar())}")


def cargar(stem: str):
    mod = importlib.import_module(f"canciones.{stem}")
    if hasattr(mod, "cancion"):
        return mod.cancion()
    raise SystemExit(f"canciones/{stem}.py debe definir cancion() → Cancion")


def partitura(C):
    """Cifrado por compás y notas de cada pista melódica, por sección (revisión musical)."""
    from motor.nucleo import nombre_nota
    tpc = C.tempo.tpc
    for s in C.secciones:
        a, b = (s.compas_ini - 1) * tpc, (s.compas_fin - 1) * tpc
        print(f"\n## {s.nombre}  c{s.compas_ini}–{s.compas_fin - 1}  energía {s.energia}  "
              f"{s.emocion}{'  [bajo voz]' if s.voz else ''}")
        compases = []
        for c in range(s.compas_ini, s.compas_fin):
            t0, t1 = (c - 1) * tpc, c * tpc
            ac = [x for (x0, x1, x) in C.armonia if x1 > t0 + 1e-9 and x0 < t1 - 1e-9]
            compases.append(" ".join(ac) or "—")
        print("   cifrado: | " + " | ".join(compases) + " |")
        for p in C.pistas.values():
            ns = [n for n in p.notas if a - 1e-9 <= n.t < b - 1e-9]
            if not ns or p.stem in ("bateria",):
                continue
            if p.stem in ("melodia",) or len(ns) <= 48:
                txt = " ".join(f"{nombre_nota(n.midi)}@{(n.t - a) / tpc + s.compas_ini:.2f}" for n in ns[:64])
                print(f"   {p.nombre:>10s}: {txt}{' …' if len(ns) > 64 else ''}")
            else:
                lo = min(n.midi for n in ns)
                hi = max(n.midi for n in ns)
                print(f"   {p.nombre:>10s}: {len(ns)} notas, {nombre_nota(lo)}–{nombre_nota(hi)}")


def asegurar_muestras():
    """Si faltan las muestras, las baja y procesa (muestras.py es idempotente)."""
    if not (AQUI / "muestras" / "proc" / "manifest.json").exists():
        print("[render] faltan las muestras: corriendo muestras.py (una sola vez)…")
        import muestras
        muestras.bajar_repos()
        muestras.resumen(muestras.procesar())


def main():
    ap = argparse.ArgumentParser(description="Renderiza canciones del proyecto")
    ap.add_argument("cancion", help="nombre, número, archivo o 'todas'")
    ap.add_argument("--hasta", type=float, default=None, help="cortar en este compás (prueba)")
    ap.add_argument("--solo", default=None, help="pistas a renderizar, separadas por coma")
    ap.add_argument("--sin-qa", action="store_true")
    ap.add_argument("--sin-mp3", action="store_true")
    ap.add_argument("--sin-imagenes", action="store_true")
    ap.add_argument("--partitura", action="store_true", help="imprimir cifrado y melodías, sin audio")
    ap.add_argument("--pianola", action="store_true", help="solo la imagen del arreglo, sin audio")
    ap.add_argument("--salida", default=None, help="carpeta de salida (por defecto salida/<slug>)")
    a = ap.parse_args()
    stems = listar() if a.cancion == "todas" else [buscar(a.cancion)]
    if not (a.partitura or a.pianola):
        asegurar_muestras()
    for st in stems:
        t0 = time.time()
        C = cargar(st)
        print(f"[render] {st}: armado de la partitura en {time.time() - t0:.1f} s")
        if a.partitura:
            partitura(C)
            from motor.analisis import revisar_grave
            gr = revisar_grave(C)
            print(f"\nclusters en el grave: {len(gr)}" + ("" if not gr else f" → {gr[:8]}"))
            continue
        if a.pianola:
            from motor.analisis import pianola
            from motor.mezcla import DIR_SALIDA
            d = Path(a.salida) if a.salida else DIR_SALIDA / C.slug
            d.mkdir(parents=True, exist_ok=True)
            pianola(C, d / "pianola.png")
            print(f"[render] {d / 'pianola.png'}")
            continue
        solo = a.solo.split(",") if a.solo else None
        salida = a.salida
        if salida is None and (a.hasta or solo):
            from motor.mezcla import DIR_SALIDA
            salida = DIR_SALIDA / "_pruebas" / (C.slug + ("_hasta%g" % a.hasta if a.hasta else "") +
                                               ("_" + "-".join(solo) if solo else ""))
        C.render(salida=salida, solo=solo, hasta_compas=a.hasta, qa=not a.sin_qa,
                 mp3=not a.sin_mp3 and not (a.hasta or solo), imagenes=not a.sin_imagenes)
        print(f"[render] {st}: total {time.time() - t0:.1f} s")


if __name__ == "__main__":
    main()
