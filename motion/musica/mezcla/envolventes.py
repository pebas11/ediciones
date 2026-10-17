"""envolventes.json: por cuadro (60 fps), la voz y la cama musical, y los downbeats efectivos.

Formato compatible con `motion/remotion/src/lib/audio.ts` (crearEnvolventes): se puede copiar
tal cual a `motion/remotion/public/datos/envolventes.json`.

    {"version": 1, "fps": 60, "cuadros": N, "duracion": s, "sampleRate": 48000,
     "pistas": {"voz":    {"nivel": <u8 base64>, "rangoDb": [piso, techo], "onsets": [...], "fuerzaOnsets": [...], "bandas": {}},
                "musica": {..., "bandas": {"graves": ..., "medios": ..., "agudos": ...}}},
     "rmsDb": {"voz": [dBFS por cuadro], "musica": [...]},           RMS real (1 decimal)
     "vozActiva": [[cuadro_inicio, cuadro_fin], ...],                 frases de la voz
     "musica": {"bpm", "compas", "beats": [cuadros], "downbeats": [cuadros], "downbeats_s": [s],
                "secciones": [...], "tramos": [...], "transiciones": [...]}}

nivel: RMS en dB → 0..1 con techo en el percentil 99,5 y un rango de `rango_db` (48 dB).
"""
from __future__ import annotations

import base64
import json
import math

import numpy as np

from . import SR

BANDAS = {"graves": (20, 200), "medios": (200, 2000), "agudos": (2000, 12000)}


def a_u8(v: np.ndarray) -> str:
    return base64.b64encode(np.round(np.clip(v, 0, 1) * 255).astype(np.uint8).tobytes()).decode("ascii")


def normalizar_db(db: np.ndarray, rango: float):
    validos = db[db > -119]
    techo = float(np.percentile(validos, 99.5)) if validos.size else 0.0
    piso = techo - rango
    return np.clip((db - piso) / rango, 0, 1), [round(piso, 2), round(techo, 2)]


def rms_por_cuadro(x: np.ndarray, cuadros: int, fps: float) -> np.ndarray:
    """RMS (mono) en una ventana de 2 cuadros centrada en el centro de cada cuadro."""
    m = x.mean(axis=1).astype(np.float64) if x.ndim == 2 else x.astype(np.float64)
    hop = SR / fps
    c2 = np.concatenate([[0.0], np.cumsum(m * m)])
    centros = (np.arange(cuadros) + 0.5) * hop
    a = np.clip(np.round(centros - hop).astype(np.int64), 0, len(m))
    b = np.clip(np.round(centros + hop).astype(np.int64), 0, len(m))
    nn = np.maximum(b - a, 1)
    return np.sqrt(np.maximum(c2[b] - c2[a], 0) / nn)


def flujo_y_bandas(x: np.ndarray, cuadros: int, fps: float, con_bandas: bool):
    """Flujo espectral por cuadro (ventana causal que termina al final del cuadro: el ataque cae
    en el cuadro en que suena) y energía por bandas."""
    m = x.mean(axis=1).astype(np.float64) if x.ndim == 2 else x.astype(np.float64)
    nfft = 2048
    hop = SR / fps
    ventana = np.hanning(nfft)
    frecs = np.fft.rfftfreq(nfft, 1 / SR)
    pad = np.concatenate([np.zeros(nfft), m, np.zeros(nfft)])
    flujo = np.zeros(cuadros)
    bandas = {k: np.zeros(cuadros) for k in BANDAS} if con_bandas else {}
    previo = None
    for ini in range(0, cuadros, 2048):
        fin = min(cuadros, ini + 2048)
        finales = np.round((np.arange(ini, fin) + 1) * hop).astype(np.int64) + nfft
        idx = finales[:, None] - nfft + np.arange(nfft)[None, :]
        idx = np.clip(idx, 0, len(pad) - 1)
        mag = np.abs(np.fft.rfft(pad[idx] * ventana, axis=1))
        logm = np.log1p(100 * mag)
        if previo is None:
            previo = logm[:1]
        dif = np.diff(np.concatenate([previo, logm]), axis=0)
        flujo[ini:fin] = np.maximum(dif, 0).sum(axis=1)
        previo = logm[-1:]
        if con_bandas:
            pot = mag ** 2
            for k, (lo, hi) in BANDAS.items():
                sel = (frecs >= lo) & (frecs < hi)
                bandas[k][ini:fin] = pot[:, sel].sum(axis=1)
    return flujo, bandas


def onsets(flujo: np.ndarray, fps: float, sensibilidad: float = 1.0):
    """Picos del flujo: máximo local, por encima de la media local y con espera mínima."""
    if flujo.max() <= 0:
        return [], []
    f = flujo / (np.percentile(flujo, 99) + 1e-9)
    pre = max(1, round(0.03 * fps))
    avg = max(1, round(0.10 * fps))
    espera = max(1, round(0.10 * fps))
    delta = 0.07 / max(sensibilidad, 1e-3)
    # máximos locales y medias locales vectorizados
    from scipy.ndimage import maximum_filter1d, uniform_filter1d
    mx = maximum_filter1d(f, size=2 * pre + 1, mode="nearest")
    med = uniform_filter1d(f, size=2 * avg + 1, mode="nearest")
    cand = np.nonzero((f >= mx) & (f > 0) & (f >= med + delta))[0]
    out, fu, ult = [], [], -10 ** 9
    for i in cand:
        if i - ult < espera:
            continue
        out.append(int(i))
        fu.append(round(float(min(1.0, f[i])), 3))
        ult = i
    return out, fu


def pista(x: np.ndarray, cuadros: int, fps: float, rango: float, con_bandas: bool, archivo: str):
    rms = rms_por_cuadro(x, cuadros, fps)
    db = 20 * np.log10(rms + 1e-9)
    nivel, rango_db = normalizar_db(db, rango)
    flujo, bandas = flujo_y_bandas(x, cuadros, fps, con_bandas)
    on, fu = onsets(flujo, fps)
    res = {"archivo": archivo, "nivel": a_u8(nivel), "rangoDb": rango_db, "onsets": on,
           "fuerzaOnsets": fu, "bandas": {}}
    for k, e in bandas.items():
        v, _ = normalizar_db(10 * np.log10(e + 1e-12), rango)
        res["bandas"][k] = a_u8(v)
    return res, np.round(np.maximum(db, -120.0), 1)


def pulsos_efectivos(edl):
    """Downbeats y pulsos que de verdad suenan (envolvente ≥ 0,5 en la armonía o la batería)."""
    downs, beats = [], []
    for sg in edl.segmentos:
        cr = sg.corrida

        def suena(t):
            tt = np.array([t])
            mejor = 0.0
            for s in ("armonia", "bateria", "melodia", "textura", "bajo"):
                v = 1.0
                if sg.entra.get(s) is not None:
                    v *= float(sg.entra[s].entra(tt)[0])
                if sg.sale.get(s) is not None:
                    v *= float(sg.sale[s].sale(tt)[0])
                mejor = max(mejor, v)
            return mejor >= 0.5

        for c in range(cr.c0, cr.c1 + 1):
            t = cr.tl(c)
            if suena(t + 0.001):
                downs.append(t)
            for j in range(1, cr.cancion.pulsos + 1):
                tb = cr.tl(c, j)
                if suena(tb + 0.001):
                    beats.append(tb)
    def limpiar(v):
        v = sorted(v)
        out = []
        for t in v:
            if not out or t - out[-1] > 0.05:
                out.append(t)
        return out
    return limpiar(downs), limpiar(beats)


def escribir(ruta, voz, cama, edl, bloques, plan, fps: float, rango: float, archivo_voz: str,
             archivo_cama: str):
    dur = max(len(cama), voz.n) / SR
    cuadros = int(math.ceil(dur * fps))
    xv = np.zeros((max(voz.n, len(cama)), 2), np.float32)
    xv[:voz.n] = voz.x
    pv, dbv = pista(xv, cuadros, fps, rango, False, archivo_voz)
    pc, dbc = pista(cama, cuadros, fps, rango, True, archivo_cama)
    downs, beats = pulsos_efectivos(edl)
    f = lambda t: int(round(t * fps))   # noqa: E731
    primero = edl.tramos[0].corridas[0].cancion
    secciones = []
    for bl in sorted(bloques, key=lambda b: b.inicio):
        sec = bl.cancion.seccion(bl.seccion)
        # rangos contiguos
        rr = sorted(bl.rangos)
        grupos = [[rr[0][0], rr[0][1]]]
        for a, b in rr[1:]:
            if a - grupos[-1][1] < 0.01:
                grupos[-1][1] = b
            else:
                grupos.append([a, b])
        for a, b in grupos:
            secciones.append({"nombre": bl.seccion, "cancion": bl.cancion.slug, "tramo": bl.tramo + 1,
                              "inicio": round(a, 3), "fin": round(b, 3), "cuadro": f(a), "cuadro_fin": f(b),
                              "energia": sec.energia, "emocion": sec.emocion})
    secciones.sort(key=lambda s: s["inicio"])
    tramos = [{"id": t.tramo.id, "cancion": t.tramo.cancion.slug, "inicio": round(t.t_entrada, 3),
               "fin": round(t.t_fin_musica, 3), "cuadro": f(t.t_entrada), "cuadro_fin": f(t.t_fin_musica),
               "bpm": t.tramo.cancion.bpm, "compas": t.tramo.cancion.compas_txt,
               "ruta_compases": t.ruta_txt()} for t in edl.tramos]
    trans = [{"tipo": tr.tipo, "t": round(tr.t, 3), "cuadro": f(tr.t),
              "ventana": [round(tr.ventana[0], 3), round(tr.ventana[1], 3)],
              "cuadros": [f(tr.ventana[0]), f(tr.ventana[1])]} for tr in edl.transiciones]
    salida = {
        "version": 1, "fps": fps, "cuadros": cuadros, "duracion": round(dur, 4), "sampleRate": SR,
        "generador": "motion/musica/mezcla_voz.py",
        "pistas": {"voz": pv, "musica": pc},
        "rmsDb": {"voz": dbv.tolist(), "musica": dbc.tolist()},
        "vozActiva": [[f(a), f(b)] for a, b in voz.frases],
        "musica": {"bpm": primero.bpm, "compas": primero.pulsos,
                   "beats": [f(t) for t in beats if 0 <= f(t) < cuadros],
                   "downbeats": [f(t) for t in downs if 0 <= f(t) < cuadros],
                   "downbeats_s": [round(t, 4) for t in downs],
                   "secciones": secciones, "tramos": tramos, "transiciones": trans},
    }
    with open(ruta, "w", encoding="utf-8") as fh:
        json.dump(salida, fh, ensure_ascii=False, separators=(",", ":"))
    return {"cuadros": cuadros, "downbeats": len(downs), "beats": len(beats),
            "onsets_voz": len(pv["onsets"]), "onsets_musica": len(pc["onsets"])}
