"""QA sin oídos e informe.json: niveles, clicks en los empalmes, loops, ducking y limitador."""
from __future__ import annotations

import numpy as np

from . import SR, STEMS
from .niveles import potencia_k_bloques, integrado, corto_plazo, fraccion_ventanas, BLOQUE, CORTO

TROZO_CLICKS = 30 * SR


# ================================================================== clicks ==
def detectar_clicks(x: np.ndarray, umbral: float) -> list[float]:
    """El detector del motor (2ª diferencia vs su entorno de 20 ms), por trozos con solape."""
    from motor.analisis import detectar_clicks as det
    out = []
    sol = int(0.05 * SR)
    n = len(x)
    for a in range(0, n, TROZO_CLICKS):
        a0 = max(0, a - sol)
        b = min(n, a + TROZO_CLICKS + sol)
        seg = x[a0:b]
        if np.abs(seg).max() < 1e-6:
            continue
        for t in det(seg, umbral=umbral):
            tt = a0 / SR + t
            if a / SR <= tt < (a + TROZO_CLICKS) / SR:
                out.append(round(tt, 4))
    return out


class QAStems:
    """Se llama con cada stem armado (antes del ducking): clicks nuevos y potencia K."""

    def __init__(self, edl, renderizador):
        self.edl = edl
        self.R = renderizador
        self.clicks: dict = {}
        self.p_pre: np.ndarray | None = None

    def _clicks_fuente(self, cancion, s, umbral):
        return cancion.clicks_fuente(s, umbral, detectar_clicks)

    def __call__(self, s: str, buf: np.ndarray):
        p = potencia_k_bloques(buf)
        self.p_pre = p if self.p_pre is None else self.p_pre[:len(p)] + p[:len(self.p_pre)]
        umbral = 40.0 if s == "bateria" else 14.0
        ev = detectar_clicks(buf, umbral)
        nuevos = []
        for t in ev:
            original = False
            for sg in self.edl.segmentos:
                cr = sg.corrida
                tt = np.array([t])
                env = 1.0
                if sg.entra.get(s) is not None:
                    env *= float(sg.entra[s].entra(tt)[0])
                if sg.sale.get(s) is not None:
                    env *= float(sg.sale[s].sale(tt)[0])
                if env < 0.02 or not (sg.s_ini + cr.off <= t <= sg.s_fin + cr.off):
                    continue
                src = self._clicks_fuente(cr.cancion, s, umbral)
                if len(src) and np.min(np.abs(src - (t - cr.off))) < 0.004:
                    original = True
                    break
            if not original:
                nuevos.append(t)
        self.clicks[s] = {"detectados": len(ev), "nuevos": len(nuevos), "t_nuevos": nuevos[:20]}


# ================================================================ métricas ==
def _st(v):
    v = np.asarray(v, float)
    v = v[np.isfinite(v)]
    if len(v) == 0:
        return None
    return {"mediana": round(float(np.median(v)), 2), "p10": round(float(np.percentile(v, 10)), 2),
            "p90": round(float(np.percentile(v, 90)), 2), "min": round(float(v.min()), 2),
            "max": round(float(v.max()), 2), "n": int(len(v))}


def niveles(voz, cama, mezcla, mask_sub, P, voz_regiones):
    """LUFS de la voz, de la cama bajo la voz, en pausas largas, intro y final; relativos ST."""
    pv = potencia_k_bloques(voz.x)
    pc = potencia_k_bloques(cama)
    pm = potencia_k_bloques(mezcla)
    n = min(len(pv), len(pc), len(mask_sub))
    f400 = fraccion_ventanas(mask_sub[:n], BLOQUE)
    out = {}
    out["voz_lufs_archivo"] = None if voz.lufs_archivo is None else round(voz.lufs_archivo, 2)
    out["voz_lufs_en_mezcla_estereo"] = None if voz.lufs_mezcla is None else round(voz.lufs_mezcla, 2)
    out["voz_canales_origen"] = voz.canales_origen
    lc_voz = integrado(pc[:n], f400 >= 0.7)
    out["cama_bajo_voz_lufs"] = None if lc_voz is None else round(lc_voz, 2)
    lv_voz = integrado(pv[:n], f400 >= 0.7)
    out["voz_mientras_habla_lufs"] = None if lv_voz is None else round(lv_voz, 2)
    # relativos de corto plazo
    t, lc = corto_plazo(pc[:n])
    _, lv = corto_plazo(pv[:n])
    fr = fraccion_ventanas(mask_sub[:n], CORTO, 5)[:len(t)]
    rel = np.where((fr >= 0.7) & (lv > -60), lc - lv, np.nan)
    obj = P["niveles"]["musica_bajo_voz_lu"]
    w = P["niveles"]["ventana_lu"]
    vals = rel[np.isfinite(rel)]
    out["relativo_bajo_voz_lu"] = _st(vals)
    # con compuerta de habla: solo los sub-bloques con voz (sin la subida de las pausas)
    from .niveles import relativo_en_habla
    rh = relativo_en_habla(pc[:n], pv[:n], mask_sub[:n])[::5]
    vh = rh[np.isfinite(rh)]
    out["relativo_en_habla_lu"] = _st(vh)
    if len(vh):
        out["relativo_en_habla_lu"]["dentro_18_22_pct"] = round(float(np.mean((vh <= -18) & (vh >= -22))) * 100, 1)
    if len(vals):
        out["relativo_bajo_voz_lu"]["dentro_ventana_pct"] = round(float(np.mean(np.abs(vals - obj) <= w)) * 100, 1)
        out["relativo_bajo_voz_lu"]["dentro_18_22_pct"] = round(float(np.mean((vals <= -18) & (vals >= -22))) * 100, 1)
        out["relativo_bajo_voz_lu"]["objetivo"] = obj
    # regiones sin voz
    dur = len(cama) / SR
    larga = P["niveles"]["pausa_larga_s"]
    pausas = [(a, b) for (a, b) in voz.pausas() if b - a >= larga]
    intro = [(0.0, voz.frases[0][0])] if voz.frases and voz.frases[0][0] > 1.0 else []
    final = [(voz.frases[-1][1], dur)] if voz.frases else [(0.0, dur)]

    def lufs_regiones(p, regs, margen=0.5):
        sel = np.zeros(len(p), bool)
        for a, b in regs:
            i0, i1 = int((a + margen) / 0.1), int((b - margen) / 0.1)
            if i1 > i0:
                sel[max(0, i0):min(len(p), i1)] = True
        m = fraccion_ventanas(sel, BLOQUE) >= 1.0
        if m.sum() < 5:
            return None
        v = integrado(p, m)
        return None if v is None else round(v, 2)

    out["cama_pausas_largas_lufs"] = lufs_regiones(pc, pausas)
    out["cama_intro_lufs"] = lufs_regiones(pc, intro)
    out["cama_final_lufs"] = lufs_regiones(pc, final)
    out["pausas_largas"] = [[round(a, 2), round(b, 2)] for a, b in pausas]
    lv_int = voz.lufs_mezcla
    for k in ("cama_pausas_largas_lufs", "cama_intro_lufs", "cama_final_lufs", "cama_bajo_voz_lufs"):
        if out[k] is not None and lv_int is not None:
            out[k.replace("_lufs", "_vs_voz_lu")] = round(out[k] - lv_int, 2)
    lcama = integrado(pc)
    out["cama_integrado_lufs"] = None if lcama is None else round(lcama, 2)
    # mezcla final: voz y música en la escala de la mezcla
    lm = integrado(pm)
    out["mezcla_integrado_lufs"] = None if lm is None else round(lm, 2)
    return out, (t, rel, lc, lv)


def ducking(ctrl, voz, P):
    """Profundidad realizada por stem (habla vs pausas largas), pendientes máximas y bombeo."""
    t = ctrl.t
    habla = voz.mascara(t) if voz.frases else np.zeros(len(t), bool)
    larga = P["niveles"]["pausa_larga_s"]
    en_pausa = np.zeros(len(t), bool)
    for a, b in voz.pausas():
        if b - a >= larga:
            en_pausa |= (t >= a + 1.2) & (t < b - 0.3)
    out = {"stems": {}}
    for s in STEMS:
        g = ctrl.duck_db(s) + ctrl.realce
        pend = np.abs(np.diff(g)) * 1000.0           # dB/s
        out["stems"][s] = {
            "en_habla_db": round(float(g[habla].mean()), 2) if habla.any() else None,
            "en_pausas_largas_db": round(float(g[en_pausa].mean()), 2) if en_pausa.any() else None,
            "pendiente_max_db_s": round(float(pend.max()), 1),
        }
    # bombeo: subidas de más de 2 dB (melodía) que duran menos de 1,5 s dentro de una frase
    g = ctrl.duck_db("melodia")
    subidas = 0
    cortas = 0
    for a, b in voz.pausas():
        m = (t >= a) & (t < b + 0.2)
        if not m.any():
            continue
        sube = float(g[m].max() - g[m][0]) if len(g[m]) else 0.0
        if sube > 2.0:
            subidas += 1
            if b - a < P["ducking"]["pausa_minima_s"]:
                cortas += 1
    out["subidas_en_pausas"] = subidas
    out["subidas_en_pausas_cortas"] = cortas
    out["pausas_sin_subida"] = int(sum(1 for a, b in voz.pausas() if b - a < P["ducking"]["pausa_minima_s"]))
    return out


def empalmes(edl, qa: QAStems | None, P):
    """Por empalme y transición: salto de nivel (stems sumados, antes del ducking), desfase,
    correlación y clicks nuevos cerca. El salto se compara con la variación típica entre compases
    de la propia sección en la canción original."""
    res = []
    p = qa.p_pre if qa is not None else None
    nuevos = []
    if qa is not None:
        for s, v in qa.clicks.items():
            nuevos.extend(v["t_nuevos"])
    nuevos = np.array(sorted(nuevos))

    def lvl(a, b):
        if p is None:
            return None
        i0, i1 = int(np.floor(a / 0.1)), int(np.ceil(b / 0.1))
        i0, i1 = max(0, i0), min(len(p), i1)
        if i1 <= i0:
            return None
        return float(10 * np.log10(p[i0:i1].mean() + 1e-20))

    tipicos = {}

    def tipico(cancion, compas):
        sec = cancion.seccion_de(compas)
        k = (cancion.slug, sec.nombre)
        if k not in tipicos:
            n_sub = len(cancion.potencias_k()["armonia"])
            tot = cancion.potencia_mezcla({s: 1.0 for s in STEMS}, np.arange(n_sub))
            ds = []
            for c in range(sec.c0 + 1, sec.c1 + 1):
                t = cancion.t(c)
                pu = cancion.pulso_s(c)
                a = tot[int((t - pu) / 0.1):int(t / 0.1)]
                b = tot[int(t / 0.1):int((t + pu) / 0.1)]
                if len(a) and len(b) and a.mean() > 1e-12 and b.mean() > 1e-12:
                    ds.append(10 * np.log10(b.mean() / a.mean()))
            tipicos[k] = (float(np.median(np.abs(ds))) if ds else 0.0,
                          float(np.percentile(np.abs(ds), 90)) if ds else 0.0)
        return tipicos[k]

    for e in edl.empalmes:
        a, b = e.ventana
        pulso = (b - a) / max(1e-6, P["empalmes"]["loop_tiempos"] if e.tipo == "loop" else
                              P["empalmes"]["empalme_tiempos"])
        antes = lvl(a - pulso, a)
        despues = lvl(e.t, e.t + pulso)
        salto = None if antes is None or despues is None else round(despues - antes, 2)
        tram = edl.tramos[e.tramo]
        c = tram.corridas[0].cancion
        med, p90 = tipico(c, e.a)
        cerca = int(np.sum(np.abs(nuevos - e.t) < 0.15)) if len(nuevos) else 0
        res.append({"tipo": e.tipo, "tramo": e.tramo + 1, "cancion": e.cancion,
                    "t_downbeat": round(e.t, 3), "de_compas": e.de, "a_compas": e.a,
                    "ventana": [round(a, 3), round(b, 3)], "desfase_ms": e.lag_ms,
                    "correlacion": e.r, "salto_nivel_db": salto,
                    "variacion_tipica_db": round(med, 2), "variacion_p90_db": round(p90, 2),
                    "ok_nivel": None if salto is None else bool(abs(salto) <= max(3.0, p90 + 1.5)),
                    "clicks_nuevos_cerca": cerca})
    return res


def rejilla(edl) -> dict:
    """Continuidad de la grilla en los empalmes internos: el downbeat que entra cae donde termina
    el compás que sale; la diferencia es solo el desfase de alineación de fase (ms)."""
    saltos = []
    for tre in edl.tramos:
        for A, B in zip(tre.corridas[:-1], tre.corridas[1:]):
            saltos.append(round((B.t0 + B.lag - A.t_fin) * 1000.0, 2))
    return {"saltos_de_grilla_ms": saltos, "max_ms": max([abs(x) for x in saltos], default=0.0)}
