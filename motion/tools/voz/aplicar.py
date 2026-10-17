#!/usr/bin/env python3
"""Etapa 2: aplica la EDL revisada sobre voz_limpia.wav.

Uso:
    python aplicar.py <carpeta> --edl edl_final.json [--video original.mp4]

Genera en <carpeta>:
    voz_final.wav           voz editada (48 kHz, 24 bits, −16 LUFS, −1,5 dBTP)
    palabras_final.json     palabras re-mapeadas a la nueva línea de tiempo (+ frases)
    subtitulos_final.srt    frases cortas, por si se quieren subtítulos en CapCut
    cortar_video.ffscript   filtro de ffmpeg para cortar el video igual
    cortar_video.sh / .bat  el comando listo (Linux/Mac y Windows)
    estadisticas.json       duración antes/después, cortes por tipo, pausas, loudness
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vozlib import util  # noqa: E402

HILOS = util.hilos_desde_argv(2)
util.configurar_hilos(HILOS)

import argparse  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402


def main() -> int:
    util.consola_utf8()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("carpeta", type=Path, help="carpeta de salida de procesar.py")
    ap.add_argument("--edl", type=Path, default=None,
                    help="EDL a aplicar (defecto: edl_final.json, o edl_propuesta.json si no existe)")
    ap.add_argument("--fundido-ms", type=float, default=None, help="fundido en cada corte (10–30 ms)")
    ap.add_argument("--video", type=Path, default=None,
                    help="si se pasa el video original, también lo corta (video_editado.mp4)")
    ap.add_argument("--fps", default=None,
                    help="cuadros por segundo del video para el script de corte (p. ej. 30000/1001); "
                         "por defecto, los del archivo que se procesó (o los de --video)")
    ap.add_argument("--lufs", type=float, default=-16.0)
    ap.add_argument("--tp", type=float, default=-1.5)
    ap.add_argument("--hilos", type=int, default=2)
    args = ap.parse_args()

    from vozlib import analisis, limpieza, render

    d = args.carpeta
    t0 = time.perf_counter()
    edl_path = args.edl
    if edl_path is None:
        edl_path = d / "edl_final.json"
        if not edl_path.exists():
            edl_path = d / "edl_propuesta.json"
            util.log("no hay edl_final.json: aplico edl_propuesta.json tal cual")
    elif not edl_path.is_absolute() and not edl_path.exists():
        edl_path = d / edl_path
    edl = util.leer_json(edl_path)
    x, sr = util.leer_wav(d / edl.get("audio", "voz_limpia.wav"))
    dur = len(x) / sr
    tr = util.leer_json(d / edl.get("transcripcion", "transcripcion.json"))
    palabras = tr["palabras"]
    fundido = args.fundido_ms or edl.get("parametros", {}).get("fundido_ms", 20)
    fundido = float(min(max(fundido, 10), 30))

    quitar, avisos, cortes = render.cortes_aplicados(edl, palabras, dur)
    for a in avisos:
        util.log("aviso: " + a)
    segs = render.mantener(quitar, dur)
    segs_n = render.refinar(segs, x, sr, palabras)
    segs_s = [(a / sr, b / sr) for a, b in segs_n]
    quitar_real = []
    t = 0.0
    for a, b in segs_s:
        if a > t:
            quitar_real.append((t, a))
        t = b
    if t < dur:
        quitar_real.append((t, dur))
    y, fundidos = render.renderizar(x, sr, segs_n, fundido, palabras)
    y, info_lufs = limpieza.ajustar_loudness_final(y, sr, args.lufs, args.tp)
    util.escribir_wav(d / "voz_final.wav", y, sr, "PCM_24")

    mapa = render.Mapa(segs_s)
    pal_final = render.remapear(palabras, quitar_real, mapa)
    frases = render.frases_desde_palabras(pal_final)
    util.guardar_json(d / "palabras_final.json", {
        "audio": "voz_final.wav", "duracion_s": round(len(y) / sr, 3), "sr": sr,
        "palabras": pal_final, "frases": frases,
        "nota": "tiempos en segundos sobre voz_final.wav; i_original apunta a transcripcion.json"})
    util.guardar_texto(d / "subtitulos_final.srt", render.srt(frases))

    info_video = dict((edl.get("fuente") or {}).get("video") or {})
    if args.video and args.video.exists():
        info_video = dict(util.sondear(args.video).get("video") or info_video)
    if args.fps:
        if "/" in args.fps:
            info_video["fps_fraccion"] = args.fps
        else:
            fr = util._fps_fraccion(float(args.fps))
            info_video["fps_fraccion"] = f"{fr.numerator}/{fr.denominator}"
    if not info_video.get("fps_fraccion"):
        util.log("aviso: la fuente no tenía video; el script de corte asume 30 fps (usá --fps)")
    vid = render.script_video(d, segs_s, info_video or None)

    # estadísticas
    por_tipo: dict[str, dict] = {}
    for c in edl.get("cortes", []):
        e = por_tipo.setdefault(c.get("tipo", "?"), {"propuestos": 0, "aplicados": 0, "segundos": 0.0})
        e["propuestos"] += 1
    for c in cortes:
        e = por_tipo.setdefault(c.get("tipo", "?"), {"propuestos": 0, "aplicados": 0, "segundos": 0.0})
        e["aplicados"] += 1
        e["segundos"] = round(e["segundos"] + (c["fin"] - c["inicio"]), 2)

    def pausas(pal):
        g = [b["inicio"] - a["fin"] for a, b in zip(pal, pal[1:])]
        g = np.array([v for v in g if v > 0.05]) if g else np.array([])
        if not len(g):
            return {}
        return {"media_s": round(float(g.mean()), 3), "p95_s": round(float(np.percentile(g, 95)), 3),
                "max_s": round(float(g.max()), 3), "mayores_0_6s": int(np.sum(g > 0.6))}

    pal_orig_quedan = [palabras[p["i_original"]] for p in pal_final]
    stats = {
        "edl": edl_path.name,
        "duracion_antes_s": round(dur, 3),
        "duracion_despues_s": round(len(y) / sr, 3),
        "segundos_quitados": round(dur - len(y) / sr, 3),
        "porcentaje_quitado": round(100 * (dur - len(y) / sr) / dur, 1) if dur else 0,
        "cortes_aplicados": len(cortes),
        "segmentos": len(segs_n),
        "por_tipo": por_tipo,
        "palabras_antes": len(palabras),
        "palabras_despues": len(pal_final),
        "pausas_antes": pausas(pal_orig_quedan),
        "pausas_despues": pausas(pal_final),
        "fundido_ms": fundido,
        "fundidos_medios_ms": round(2000 * float(np.mean(fundidos)) / sr, 1) if fundidos else 0,
        "loudness": {**info_lufs, "lufs_medido": round(analisis.loudness(y, sr), 2)},
        "video": vid,
        "avisos": avisos,
        "tiempo_s": round(time.perf_counter() - t0, 2),
    }
    if args.video:
        util.log("cortando el video…")
        tv = time.perf_counter()
        salida = render.cortar_video(d, args.video, d / "video_editado.mp4", HILOS)
        stats["video"]["archivo"] = salida.name
        stats["video"]["tiempo_s"] = round(time.perf_counter() - tv, 1)
    util.guardar_json(d / "estadisticas.json", stats)
    util.log(f"voz_final.wav: {util.fmt_t(dur)} → {util.fmt_t(len(y) / sr)} "
             f"(−{stats['porcentaje_quitado']} %), {len(cortes)} cortes, "
             f"{stats['loudness']['lufs_medido']} LUFS")
    for tipo, e in por_tipo.items():
        util.log(f"  {tipo:16s} {e['aplicados']:3d}/{e['propuestos']:3d}  {e['segundos']:7.2f} s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
