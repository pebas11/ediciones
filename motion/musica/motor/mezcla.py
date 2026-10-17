"""Mezcla y entrega: pistas → stems (con sus retornos de reverb/eco y cinta) → master.

Los stems se procesan por separado con los mismos buses (la reverb por
convolución y el eco son lineales), así que la suma de los cinco stems es
exactamente la mezcla previa al bus master. El bus master solo agrega
compresión de pegamento, normalización a −14 LUFS y limitador true-peak.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np
import pyloudnorm as pyln
import soundfile as sf

from .nucleo import SR, desde_db, mezclar_en, rampa, rng
from .secuencia import STEMS
from . import efectos as fx
from .instrumentos.base import CACHE

RAIZ_MUSICA = Path(__file__).resolve().parents[1]
DIR_SALIDA = RAIZ_MUSICA / "salida"
DIR_MP3 = RAIZ_MUSICA.parent / "renders" / "musica"


def log(*a):
    print("[motor]", *a, flush=True)


class Contexto:
    """Lo que ven los instrumentos al renderizar."""

    def __init__(self, cancion, n: int, semilla, hall=None):
        self.cancion = cancion
        self.tempo = cancion.tempo
        self.n = int(n)
        self.semilla = semilla
        self._hall = hall

    def muestra(self, t: float) -> int:
        return int(round(self.tempo.seg(t) * SR))

    def seg(self, t: float) -> float:
        return float(self.tempo.seg(t))

    def aislado(self, instrumento, notas, cola_s: float = 2.0) -> np.ndarray:
        """Renderiza notas (tiempos relativos a 0) de un instrumento, en seco."""
        fin = max(nt.t + nt.dur for nt in notas)
        n = int((self.tempo.seg(fin) + cola_s) * SR) + SR // 2
        sub = Contexto(self.cancion, n, (self.semilla, "aislado"), self._hall)
        return instrumento.render(sorted(notas, key=lambda z: z.t), sub, None)

    def reverb(self, x: np.ndarray) -> np.ndarray:
        if self._hall is None:
            return x
        cola = int(self._hall.irs.shape[1])
        xx = np.concatenate([x, np.zeros((cola, 2), np.float32)])
        return self._hall.procesar(xx)


# ------------------------------------------------------------------ pistas --
def render_pista(p, ctx) -> np.ndarray:
    notas = [nt for nt in p.notas_humanizadas() if ctx.muestra(nt.t) < ctx.n]
    buf = p.instrumento.render(notas, ctx, p)
    for c in p.clips:
        y = c["gen"](ctx)
        if c["fin"] is not None:
            ini = ctx.muestra(c["fin"]) - len(y)
        else:
            ini = ctx.muestra(c["pos"] or 0.0)
        mezclar_en(buf, y * np.float32(desde_db(c["db"])), ini)
    for e in p.efectos:
        buf = e.procesar(buf, ctx, p)
    g = float(desde_db(p.vol))
    if "vol" in p.autos:
        curva = desde_db(p.autos["vol"].en_muestras(ctx.n, ctx.tempo)).astype(np.float32)
        buf = buf * (g * curva)[:, None]
    else:
        buf = buf * np.float32(g)
    if "pan" in p.autos:
        buf = fx.Paneo(p.autos["pan"]).procesar(buf, ctx, p)
    elif p.pan:
        buf = fx.Paneo(p.pan).procesar(buf, ctx, p)
    return buf.astype(np.float32)


def curva_hueco_voz(C, n: int) -> np.ndarray:
    """0..1 por muestra: 1 dentro de secciones bajo voz (rampa de 1 compás en los bordes)."""
    t = np.arange(0, n, 64)
    beats = C.tempo.tiempos(t / SR)
    v = np.zeros(len(t))
    tpc = C.tempo.tpc
    for s in C.secciones:
        if not s.voz:
            continue
        a, b = (s.compas_ini - 1) * tpc, (s.compas_fin - 1) * tpc
        sube = np.clip((beats - a) / tpc + 0.5, 0, 1)
        baja = np.clip((b - beats) / tpc + 0.5, 0, 1)
        v = np.maximum(v, np.minimum(sube, baja))
    v = 0.5 - 0.5 * np.cos(np.pi * v)
    return np.interp(np.arange(n), t, v)


# ------------------------------------------------------------------ render --
def niveles_por_seccion(C, buf) -> dict:
    """LUFS de una pista (seca, post-fader) en cada sección donde suena."""
    from .analisis import lufs
    out = {}
    for s in C.secciones:
        a = int(C.tempo.seg(C.tempo.pos(s.compas_ini)) * SR)
        b = min(len(buf), int(C.tempo.seg(C.tempo.pos(s.compas_fin)) * SR))
        seg = buf[a:b]
        if len(seg) < SR or np.abs(seg).max() < 1e-5:
            continue
        v = lufs(seg)
        if v is not None and np.isfinite(v) and v > -70:
            out[s.nombre] = round(v, 1)
    return out


def render_cancion(C, salida=None, solo=None, hasta_compas=None, escribir=True, qa=True,
                   mp3=True, imagenes=True, niveles=True):
    """Renderiza la canción completa y escribe master, stems, cues, mp3 y QA.

    * solo         : lista de nombres de pista a renderizar (pruebas)
    * hasta_compas : corta la canción en ese compás (+ cola) para pruebas rápidas
    """
    t0 = time.time()
    carpeta = Path(salida) if salida else DIR_SALIDA / C.slug
    dur = C.duracion_s
    if hasta_compas is not None:
        dur = float(C.tempo.seg(C.tempo.pos(hasta_compas))) + C.cola_s
    n = int(dur * SR)
    log(f"«{C.titulo}»: {dur:.1f} s, {len(C.pistas)} pistas, {C.compases_total} compases a {C.tempo.bpm} bpm")
    rv = C.fx["reverb"]
    hall = fx.Convolver(fx.generar_ir(rv["dur"], rv["predelay_ms"], rv["brillo"], rv["ancho"],
                                      rv["tipo"], C.semilla))
    sl = C.fx["sala"]
    sala = fx.Convolver(fx.generar_ir(sl["dur"], sl["predelay_ms"], sl["brillo"], sl["ancho"],
                                      sl["tipo"], C.semilla))
    ctx = Contexto(C, n, C.semilla, hall)
    cinta_cfg = C.fx["cinta"]
    mod = fx.modulacion_cinta(n, C.semilla, cinta_cfg["wow"], cinta_cfg["flutter"]) \
        if (cinta_cfg["wow"] or cinta_cfg["flutter"]) else None
    hv = C.fx["hueco_voz"]
    g_voz = curva_hueco_voz(C, n) * (1 - float(desde_db(-hv["profundidad_db"])))
    sos_voz = fx.biquad("banda", hv["frecuencia"], hv["q"])
    stems = {}
    tiempos = {}
    niveles_pistas = {}
    for stem in STEMS:
        pistas = [p for p in C.pistas.values() if p.stem == stem and (not solo or p.nombre in solo)]
        seco = np.zeros((n, 2), np.float32)
        envios = {}
        for p in pistas:
            tp = time.time()
            buf = render_pista(p, ctx)
            if niveles:
                niveles_pistas[p.nombre] = niveles_por_seccion(C, buf)
            seco += buf
            for bus, nivel in p.envios.items():
                if nivel <= 0:
                    continue
                if bus not in envios:
                    envios[bus] = np.zeros((n, 2), np.float32)
                envios[bus] += buf * np.float32(nivel)
            tiempos[p.nombre] = time.time() - tp
            del buf
        if "eco" in envios:
            e = fx.eco(envios.pop("eco"), C.tempo, **C.fx["eco"])
            seco += e
            if C.fx["eco"].get("a_reverb", 0) > 0:
                envios.setdefault("reverb", np.zeros((n, 2), np.float32))
                envios["reverb"] += e * np.float32(C.fx["eco"]["a_reverb"])
        if "sala" in envios:
            seco += sala.procesar(envios.pop("sala"))
        if "reverb" in envios:
            seco += hall.procesar(envios.pop("reverb"))
        if stem in hv["stems"] and g_voz.max() > 0:
            seco = seco - (fx.sosf(sos_voz, seco) * g_voz[:, None]).astype(np.float32)
        if pistas or stem == "textura":
            seco = fx.cinta(seco, mod, cinta_cfg["saturacion"], cinta_cfg["brillo"])
        if stem == "textura" and cinta_cfg["hiss_db"] is not None:
            h = fx.hiss(n, cinta_cfg["hiss_db"], C.semilla)
            na = min(n, int(2.0 * SR))
            h[:na] *= rampa(na)[:, None].astype(np.float32)   # la cinta "arranca" sin escalón
            seco += h
        stems[stem] = seco
        log(f"  stem {stem:8s} listo ({', '.join(f'{p.nombre} {tiempos[p.nombre]:.1f}s' for p in pistas) or 'vacío'})")
    # final en silencio (la cola de la canción ya está incluida)
    nf = int(min(1.5, C.cola_s * 0.5) * SR)
    for s in stems.values():
        s[-nf:] *= rampa(nf)[::-1, None].astype(np.float32)
        s[: int(0.002 * SR)] *= rampa(int(0.002 * SR))[:, None].astype(np.float32)
    premaster = sum(stems.values())
    # margen común para stems y premaster (sin limitar nada)
    pico = float(np.abs(premaster).max())
    pico_st = max(float(np.abs(s).max()) for s in stems.values())
    gan = min(desde_db(-3.0) / max(pico, 1e-9), desde_db(-1.0) / max(pico_st, 1e-9))
    for k in stems:
        stems[k] *= np.float32(gan)
    premaster = premaster * np.float32(gan)
    master, info_master = masterizar(premaster, C.fx["master"])
    dt = time.time() - t0
    log(f"render listo en {dt:.1f} s · master {info_master['lufs']:.2f} LUFS, "
        f"{info_master['dbtp']:.2f} dBTP · caché {CACHE.bytes / 1e6:.0f} MB "
        f"({CACHE.aciertos} aciertos/{CACHE.fallos} fallos)")
    # niveles relativos al premaster ya escalado (para mezclar sin oídos)
    off = float(20 * np.log10(gan))
    niveles_pistas = {k: {s: round(v + off, 1) for s, v in d.items()} for k, d in niveles_pistas.items()}
    res = {"master": master, "stems": stems, "premaster": premaster, "info_master": info_master,
           "carpeta": carpeta, "segundos_render": dt, "tiempos_pistas": tiempos, "n": n,
           "niveles_pistas": niveles_pistas}
    if niveles and niveles_pistas:
        imprimir_niveles(C, niveles_pistas)
    if escribir:
        escribir_salidas(C, res, mp3=mp3)
    if qa:
        from .analisis import analizar
        res["qa"] = analizar(C, res, imagenes=imagenes)
    return res


def imprimir_niveles(C, niv):
    secs = [s.nombre for s in C.secciones]
    print("\nLUFS por pista y sección (seco, post-fader, escala del premaster):")
    print(f"{'':12s}" + "".join(f"{s[:9]:>10s}" for s in secs))
    for k, d in niv.items():
        print(f"{k:12s}" + "".join(f"{d.get(s, ''):>10}" for s in secs))


def masterizar(x: np.ndarray, cfg: dict):
    """Pegamento suave → normalización a LUFS objetivo → limitador true-peak (iterativo)."""
    from .analisis import lufs as lufs_rapido
    medidor = pyln.Meter(SR)
    lufs0 = lufs_rapido(x)
    glue = cfg.get("glue", 0.5)
    y = x
    if glue > 0:
        comp = fx.Compresor(umbral_db=lufs0 + 5.0, ratio=1 + 0.8 * glue, ataque_ms=30,
                            relaj_ms=260, rodilla_db=8)
        y = comp.procesar(y)
    sos = [fx.biquad("pa", 22.0, 0.6)]
    if cfg.get("aire_db", 0):
        sos.append(fx.biquad("agudos", 10000.0, 0.7, cfg["aire_db"]))   # brillo de master
    y = fx.filtrar(y, np.vstack(sos))
    objetivo = cfg.get("lufs", -14.0)
    techo = cfg.get("techo_dbtp", -1.0)
    gan_db = objetivo - lufs_rapido(y)
    z = y
    for it in range(5):
        z = fx.limitador(y * np.float32(desde_db(gan_db)), techo - 0.15)
        lufs = medidor.integrated_loudness(z.astype(np.float64))
        tp = fx.pico_real(z)
        if tp > techo:
            z = fx.limitador(z, techo - 0.15 - (tp - techo) - 0.05)
            tp = fx.pico_real(z)
            lufs = medidor.integrated_loudness(z.astype(np.float64))
        if abs(lufs - objetivo) < 0.06 and tp <= techo:
            break
        gan_db += objetivo - lufs
    return z.astype(np.float32), {"lufs": float(lufs), "dbtp": float(tp), "ganancia_db": float(gan_db),
                                  "lufs_premaster": float(lufs0), "iteraciones": it + 1}


def _dither24(x: np.ndarray, semilla) -> np.ndarray:
    g = rng("dither", semilla)
    lsb = 1.0 / (2 ** 23)
    d = (g.random(x.shape) - g.random(x.shape)) * lsb
    return np.clip(x + d.astype(np.float32), -1.0, 1.0 - lsb)


def escribir_salidas(C, res, mp3=True):
    carpeta: Path = res["carpeta"]
    (carpeta / "stems").mkdir(parents=True, exist_ok=True)
    sf.write(carpeta / "master.wav", _dither24(res["master"], (C.semilla, "m")), SR, subtype="PCM_24")
    for k, s in res["stems"].items():
        sf.write(carpeta / "stems" / f"{k}.wav", _dither24(s, (C.semilla, k)), SR, subtype="PCM_24")
    cues = construir_cues(C, res)
    (carpeta / "cues.json").write_text(json.dumps(cues, indent=2, ensure_ascii=False))
    res["cues"] = cues
    if mp3:
        DIR_MP3.mkdir(parents=True, exist_ok=True)
        destino = DIR_MP3 / f"{C.slug}.mp3"
        ff = shutil.which("ffmpeg")
        if ff is None:
            import imageio_ffmpeg
            ff = imageio_ffmpeg.get_ffmpeg_exe()
        subprocess.run([ff, "-y", "-loglevel", "error", "-i", str(carpeta / "master.wav"),
                        "-codec:a", "libmp3lame", "-b:a", "320k", "-ar", "48000",
                        "-metadata", f"title={C.titulo}", str(destino)], check=True)
        res["mp3"] = destino
    log(f"escrito en {carpeta}")


def construir_cues(C, res) -> dict:
    tempo = C.tempo
    from .analisis import lufs as lufs_rapido
    m = res["master"]
    secciones = []
    for s in C.secciones:
        a = float(tempo.seg(tempo.pos(s.compas_ini)))
        b = float(tempo.seg(tempo.pos(s.compas_fin)))
        seg = m[int(a * SR): int(b * SR)]
        lufs = lufs_rapido(seg) if len(seg) > SR * 0.5 else None
        la, lb = s.loop
        secciones.append({
            "nombre": s.nombre, "compas_inicio": s.compas_ini, "compas_fin": s.compas_fin - 1,
            "inicio_s": round(a, 3), "fin_s": round(b, 3), "energia": s.energia,
            "emocion": s.emocion, "bajo_voz": s.voz,
            "lufs": None if lufs is None or not np.isfinite(lufs) else round(lufs, 2),
            "loop": {"compas_inicio": la, "compas_fin": lb - 1,
                     "inicio_s": round(float(tempo.seg(tempo.pos(la))), 3),
                     "fin_s": round(float(tempo.seg(tempo.pos(lb))), 3)},
            "notas": s.notas,
        })
    downbeats = [round(float(tempo.seg(tempo.pos(c))), 4) for c in range(1, C.compases_total + 2)]
    armonia = [{"inicio_s": round(float(tempo.seg(a)), 3), "fin_s": round(float(tempo.seg(b)), 3),
                "acorde": s} for a, b, s in C.armonia]
    fin_musica = float(tempo.seg(C.tiempos_total))
    return {
        "titulo": C.titulo, "slug": C.slug, "bpm": C.tempo.bpm,
        "compas": f"{C.compas[0]}/{C.compas[1]}", "tonalidad": C.tonalidad,
        "duracion_s": round(res["n"] / SR, 3), "sr": SR,
        "lufs_integrado": round(res["info_master"]["lufs"], 2),
        "pico_dbtp": round(res["info_master"]["dbtp"], 2),
        "secciones": secciones,
        "downbeats_s": downbeats,
        "armonia": armonia,
        "marcas": [{"t_s": round(float(tempo.seg(t)), 3), "texto": x} for t, x in C.marcas],
        "cola": {"inicio_s": round(fin_musica, 3), "fin_s": round(res["n"] / SR, 3)},
        "stems": list(STEMS),
        "nota": "Tiempos en segundos desde el inicio del master. Los loops van de downbeat a downbeat.",
    }
