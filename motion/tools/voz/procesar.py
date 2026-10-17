#!/usr/bin/env python3
"""Etapa 1: extrae, analiza, limpia y transcribe la voz, y propone la edición.

Uso:
    python procesar.py <entrada.mp4|wav> --out <carpeta> [opciones]

Genera en <carpeta>:
    audio_original.wav    extracción a 48 kHz mono float
    analisis.json         piso de ruido, LUFS, picos/clipping, DC, zumbido, espectro, reverb
                          (del original y del resultado limpio) + pasos de limpieza aplicados
    voz_limpia.wav        limpia y normalizada (−16 LUFS, −1,5 dBTP), SIN cortes
    transcripcion.json    segmentos y palabras (inicio, fin, probabilidad), bordes ajustados
    transcripcion.txt     texto por segmento con tiempos
    edl_propuesta.json    cortes propuestos con motivo, contexto y confianza
    cortes.md             la misma propuesta, legible, para revisar
    espectrogramas/       PNG antes/después
    tiempos.json          segundos por etapa y por minuto de audio
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from vozlib import util  # noqa: E402

HILOS = util.hilos_desde_argv(2)
util.configurar_hilos(HILOS)  # antes de importar numpy/torch

import argparse  # noqa: E402

import numpy as np  # noqa: E402


def extraer(entrada: Path, info: dict, hilos: int) -> tuple[np.ndarray, dict]:
    """Decodifica a 48 kHz y baja a mono con criterio (canal muerto, fase invertida)."""
    canales = min(info["audio"]["canales"], 2)
    x = util.decodificar(entrada, util.SR, canales=canales, hilos=hilos)
    det = {"canales_origen": info["audio"]["canales"], "sr_origen": info["audio"]["sr"]}
    if x.shape[1] == 1:
        det["mezcla"] = "mono"
        return x[:, 0].copy(), det
    L, R = x[:, 0].astype(np.float64), x[:, 1].astype(np.float64)
    rl, rr = np.sqrt(np.mean(L ** 2)) + 1e-12, np.sqrt(np.mean(R ** 2)) + 1e-12
    dif = 20 * np.log10(rl / rr)
    corr = float(np.corrcoef(L, R)[0, 1]) if rl > 1e-9 and rr > 1e-9 else 1.0
    det.update({"dif_canales_db": round(dif, 1), "correlacion": round(corr, 3)})
    if dif > 15:
        det["mezcla"] = "solo izquierdo (el derecho está casi mudo)"
        return x[:, 0].copy(), det
    if dif < -15:
        det["mezcla"] = "solo derecho (el izquierdo está casi mudo)"
        return x[:, 1].copy(), det
    if corr < -0.3:
        det["mezcla"] = "L − R (canales en contrafase)"
        return ((L - R) / 2).astype(np.float32), det
    det["mezcla"] = "(L + R) / 2"
    return ((L + R) / 2).astype(np.float32), det


def main() -> int:
    util.consola_utf8()
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada", type=Path, help="video o audio (mp4, mov, mkv, wav, m4a, mp3…)")
    ap.add_argument("--out", type=Path, required=True, help="carpeta de salida")
    ap.add_argument("--modelo", default=None,
                    help="modelo de faster-whisper: large-v3-turbo (defecto), large-v3, medium… "
                         "Con --reusar y otro modelo, se reusa la limpieza y se vuelve a transcribir")
    ap.add_argument("--compute", default="int8", help="int8 (defecto), int8_float32, float32")
    ap.add_argument("--beam", type=int, default=5, help="beam size (1 = greedy, más rápido)")
    ap.add_argument("--lote", type=int, default=0,
                    help="> 0: transcripción por lotes (BatchedInferencePipeline) de ese tamaño")
    ap.add_argument("--hilos", type=int, default=2, help="hilos de CPU (defecto 2)")
    ap.add_argument("--ruido", default="auto",
                    choices=["auto", "dfn", "dfn-bin", "rnnoise", "noisereduce", "ninguno"],
                    help="backend de reducción de ruido")
    ap.add_argument("--atenuacion", type=float, default=None,
                    help="límite de reducción de ruido en dB (defecto: 12/15/18 según SNR)")
    ap.add_argument("--lufs", type=float, default=-16.0)
    ap.add_argument("--tp", type=float, default=-1.5, help="techo de pico verdadero en dBTP")
    ap.add_argument("--sin-prompt", action="store_true",
                    help="no usar el prompt que pide transcribir muletillas literalmente")
    ap.add_argument("--confianza", type=float, default=0.75,
                    help="confianza mínima para marcar un corte de contenido como aplicar=true")
    ap.add_argument("--reusar", action="store_true",
                    help="reusar salidas existentes (p. ej. para rehacer solo la EDL)")
    ap.add_argument("--sin-espectrogramas", action="store_true")
    args = ap.parse_args()

    from vozlib import analisis, edicion, espectro, limpieza, transcribir

    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    if not args.entrada.exists():
        print(f"No existe {args.entrada}", file=sys.stderr)
        return 2
    info = util.sondear(args.entrada)
    dur = info.get("duracion_s") or 0
    crono = util.Cronometro(dur)
    util.log(f"entrada: {info['archivo']} ({util.fmt_t(dur)}), audio {info['audio']['codec']} "
             f"{info['audio']['sr']} Hz × {info['audio']['canales']}"
             + (f", video {info['video'].get('fps', '?')} fps" if info.get("video") else ""))

    p_orig = out / "audio_original.wav"
    with crono.etapa("extracción"):
        if args.reusar and p_orig.exists():
            x, sr = util.leer_wav(p_orig)
            mezcla = (util.leer_json(out / "analisis.json").get("extraccion", {})
                      if (out / "analisis.json").exists() else {})
        else:
            x, mezcla = extraer(args.entrada, info, HILOS)
            sr = util.SR
            util.escribir_wav(p_orig, x, sr, "FLOAT")
    dur = len(x) / sr
    crono.duracion_audio_s = dur

    p_limpia = out / "voz_limpia.wav"
    p_an = out / "analisis.json"
    if args.reusar and p_limpia.exists() and p_an.exists():
        y, _ = util.leer_wav(p_limpia)
        an_todo = util.leer_json(p_an)
        util.log("reuso voz_limpia.wav y analisis.json")
    else:
        with crono.etapa("análisis del original"):
            an = analisis.analizar(x, sr)
        util.log("original: " + analisis.resumen_corto(an))
        cfg = {"ruido_backend": args.ruido, "ruido_atenuacion_db": args.atenuacion,
               "lufs": args.lufs, "true_peak": args.tp}
        y, pasos = limpieza.limpiar(x, sr, an, cfg, crono, HILOS)
        util.escribir_wav(p_limpia, y, sr, "PCM_24")
        with crono.etapa("análisis del resultado"):
            an2 = analisis.analizar(y, sr)
        util.log("limpio:   " + analisis.resumen_corto(an2))
        an_todo = {"fuente": info, "extraccion": mezcla, "original": an, "limpieza": pasos,
                   "limpio": an2}
        util.guardar_json(p_an, an_todo)

    if not args.sin_espectrogramas:
        with crono.etapa("espectrogramas"):
            d_esp = out / "espectrogramas"
            espectro.comparar([("original", x), ("limpia", y)], sr, d_esp / "completo.png",
                              titulo="Antes / después (completo)")
            # zoom de 12 s en la zona con más voz
            act = analisis.actividad(y, sr)
            vent = int(12 / act["hop_s"])
            if len(act["mask"]) > vent:
                dens = np.convolve(act["mask"].astype(float), np.ones(vent), "valid")
                t0 = float(np.argmax(dens) * act["hop_s"])
            else:
                t0 = 0.0
            espectro.comparar([("original", x), ("limpia", y)], sr, d_esp / "zoom.png",
                              t0=t0, t1=min(dur, t0 + 12), titulo=f"Zoom {t0:.1f}–{t0 + 12:.1f} s")
            espectro.comparar([("original", x), ("limpia", y)], sr, d_esp / "graves.png",
                              t0=t0, t1=min(dur, t0 + 12), fmax=1200, nperseg=16384,
                              titulo="Graves (zumbido, plosivas)")
            espectro.espectro_promedio([("original", x), ("limpia", y)], sr,
                                       d_esp / "espectro_promedio.png")

    p_tr = out / "transcripcion.json"
    modelo = args.modelo or "large-v3-turbo"
    tr_previa = util.leer_json(p_tr) if (args.reusar and p_tr.exists()) else None
    if tr_previa and args.modelo and tr_previa.get("modelo_pedido", tr_previa.get("modelo")) != args.modelo:
        util.log(f"la transcripción guardada es de {tr_previa.get('modelo')}: transcribo con {args.modelo}")
        tr_previa = None
    if tr_previa:
        tr = tr_previa
        util.log(f"reuso transcripción ({tr['modelo']})")
        act = transcribir.mapa_actividad(y, sr)
    else:
        with crono.etapa(f"transcripción ({modelo}, {args.compute})"):
            tr = transcribir.transcribir(
                y, sr, modelo=modelo, hilos=HILOS, compute_type=args.compute,
                beam_size=args.beam, prompt=None if args.sin_prompt else transcribir.PROMPT_DISFLUENCIAS,
                lote=args.lote)
        with crono.etapa("ajuste de bordes por energía"):
            act = transcribir.mapa_actividad(y, sr)
            tr["ajuste_bordes"] = transcribir.ajustar_bordes(tr["palabras"], act, dur)
        for k, w in enumerate(tr["palabras"]):
            w["i"] = k
        util.guardar_json(p_tr, tr)
        util.guardar_texto(out / "transcripcion.txt", transcribir.texto_plano(tr))
        util.log(f"{len(tr['palabras'])} palabras; modelo {tr['modelo']}")

    with crono.etapa("propuesta de edición"):
        edl = edicion.proponer(tr["palabras"], y, sr, act, {"confianza_min_aplicar": args.confianza})
        edl["fuente"] = {"archivo": info["archivo"], "video": info.get("video")}
        edl["transcripcion"] = "transcripcion.json"
        util.guardar_json(out / "edl_propuesta.json", edl)
        util.guardar_texto(out / "cortes.md", edicion.cortes_md(edl, info["archivo"]))
    r = edl["resumen"]
    util.log(f"EDL: {r['cortes_a_aplicar']}/{r['cortes_propuestos']} cortes; "
             f"{util.fmt_t(r['duracion_original_s'])} → {util.fmt_t(r['duracion_estimada_s'])}")

    tiempos = crono.resumen()
    tiempos["modelo"] = tr.get("modelo")
    tiempos["hilos"] = HILOS
    try:  # carga de la máquina al terminar (otros procesos inflan los tiempos)
        tiempos["carga_1_5_15min"] = [round(v, 2) for v in os.getloadavg()]
    except (AttributeError, OSError):  # Windows
        pass
    tiempos["cpus"] = os.cpu_count()
    p_t = out / "tiempos.json"
    if args.reusar and p_t.exists():
        # con --reusar solo corren algunas etapas: se actualizan sin borrar las medidas viejas
        viejo = util.leer_json(p_t)
        viejo.setdefault("etapas", {}).update(tiempos["etapas"])
        tot = sum(v["segundos"] for v in viejo["etapas"].values())
        viejo["total_s"] = round(tot, 2)
        if viejo.get("duracion_audio_s"):
            viejo["total_seg_por_min_audio"] = round(tot / (viejo["duracion_audio_s"] / 60), 2)
        viejo["ultima_corrida_con_reusar"] = tiempos
        tiempos = viejo
    util.guardar_json(p_t, tiempos)
    util.log(f"listo en {tiempos['total_s']:.0f} s "
             f"({tiempos['total_seg_por_min_audio']} s por minuto de audio). Salida: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
