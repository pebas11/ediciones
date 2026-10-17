"""Orquestación: plan + voz → cama musical, mezcla final, informe, envolventes y gráfico."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from . import SR, VERSION
from . import armado, niveles, voz as voz_mod, plan as plan_mod
from .canciones import Catalogo
from .ducking import Control
from .render import Renderizador
from .master import masterizar, escribir_wav


def log(*a):
    print("[mezcla]", *a, flush=True)


def _r(x, n=3):
    return None if x is None else round(float(x), n)


def preparar(plan_path, voz_path=None, extra=None, dir_canciones=None, leer_audio=True):
    cat = Catalogo(Path(dir_canciones) if dir_canciones else None)
    plan = plan_mod.cargar(plan_path, cat, extra)
    voz = None
    if voz_path:
        voz = voz_mod.cargar(voz_path)
        voz_mod.detectar_actividad(voz, plan.parametros["voz"])
    dur = voz.dur if voz is not None else max(t.fin for t in plan.tramos)
    edl = armado.armar(plan, dur, leer_audio=leer_audio)
    return plan, voz, edl


def resumen_edl(edl, plan) -> str:
    filas = []
    for tre in edl.tramos:
        tr = tre.tramo
        an = ""
        if tr.ancla is not None:
            an = f"  ancla {tr.ancla.texto()} → {tre.ancla_t:.3f} s ({tre.ancla_error_ms:+.1f} ms)"
        filas.append(f"  {tr.indice + 1:>2}. {tr.id:<16} {tr.cancion.slug:<12} plan {tr.inicio:7.2f}–{tr.fin:7.2f}"
                     f"  real {tre.t_entrada:7.2f}–{tre.t_fin_musica:7.2f}  compases {tre.ruta_txt()}{an}")
    for t in edl.transiciones:
        dest = f"→ {t.a + 1}" if t.a is not None else "(final)"
        filas.append(f"      {t.de + 1} {dest:<8} {t.tipo:<9} downbeat {t.t:7.3f}  ventana "
                     f"{t.ventana[0]:7.2f}–{t.ventana[1]:7.2f}  {t.detalle}")
    for e in edl.empalmes:
        if e.tipo != "continuo":
            filas.append(f"      {e.tipo:<8} tramo {e.tramo + 1}: compás {e.de} → {e.a} en {e.t:7.3f} s"
                         f" (desfase {e.lag_ms:+.2f} ms)")
    return "\n".join(filas)


def mezclar(voz_path, plan_path, out_dir, extra=None, dir_canciones=None) -> dict:
    t_ini = time.time()
    tiempos = {}

    def marca(nombre, t0):
        tiempos[nombre] = round(time.time() - t0, 2)
        return time.time()

    t0 = time.time()
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    plan, voz, edl = preparar(plan_path, voz_path, extra, dir_canciones)
    P = plan.parametros
    avisos = list(plan.avisos) + list(edl.avisos)
    if voz.lufs_archivo is not None and abs(voz.lufs_archivo - P["voz"]["lufs_esperado"]) > 1.0:
        avisos.append(f"la voz mide {voz.lufs_archivo:.1f} LUFS (se esperaba {P['voz']['lufs_esperado']:g}); "
                      "la mezcla igual llega a −14, pero revisá la entrega de la voz")
    for tr in plan.tramos:
        if tr.fin > voz.dur + 30:
            avisos.append(f"{tr.nombre}: termina {tr.fin - voz.dur:.0f} s después del final de la voz")
    log(f"plan: {len(plan.tramos)} tramos · voz {voz.dur:.1f} s, {len(voz.frases)} frases, "
        f"{voz.lufs_archivo:.2f} LUFS ({voz.canales_origen} canal/es)")
    log("armado:\n" + resumen_edl(edl, plan))
    t0 = marca("armado_s", t0)

    # ---- niveles por bloque (estimación desde la fuente)
    bloques = niveles.construir_bloques(edl)
    bmap = {b.clave: b for b in bloques}
    p_voz = niveles.potencia_k_bloques(voz.x)
    n_sub = int(np.ceil(edl.n_total / niveles.SUB))
    p_voz = np.concatenate([p_voz, np.zeros(max(0, n_sub - len(p_voz)))])
    mask = niveles.mascara_sub(voz, len(p_voz))
    # ---- control de ducking (no depende de los niveles: sirve también para estimarlos)
    trs = edl.tramos
    rangos = [(tre.t_entrada, trs[k + 1].t_entrada if k + 1 < len(trs) else 1e9, tre.tramo.ducking)
              for k, tre in enumerate(trs)]
    ctrl = Control(voz, edl.n_total, P, rangos)
    # ventanas que no se usan para medir ni estimar: donde conviven dos tramos
    excluir = [tr.ventana for tr in edl.transiciones if tr.tipo != "continuo" and tr.a is not None]
    niveles.estimar(bloques, plan, voz, p_voz, mask, niveles.potencias_control(ctrl, len(p_voz), plan),
                    excluir)
    t0 = marca("niveles_s", t0)
    guarda = P["empalmes"]["guarda_ms"] / 1000

    def curvas():
        return {tre.tramo.indice: niveles.CurvaTramo(tre, bmap, P["niveles"]["rampa_bloque_tiempos"], guarda)
                for tre in trs}

    R = Renderizador(edl, plan, ctrl, curvas())
    from .informe import QAStems
    qa = QAStems(edl, R) if P["salidas"]["qa"] else None
    cama = R.cama(por_stem=qa)
    log(f"cama armada ({edl.n_total / SR:.1f} s)")
    t0 = marca("render_1_s", t0)
    pasadas = 1
    if P["niveles"]["corregir"]:
        p_cama = niveles.potencia_k_bloques(cama)
        rel = niveles.relativo_en_habla(p_cama, p_voz, mask)
        t_st = (np.arange(len(rel)) + 0.5) * 0.1
        rel[np.arange(len(rel)) % 5 != 0] = np.nan
        if niveles.corregir(bloques, t_st, rel, P["niveles"]["tolerancia_lu"], excluir):
            log("corrección de niveles: " + ", ".join(
                f"{plan.tramos[b.tramo].id}/{b.seccion} {b.correccion_db:+.1f} dB" for b in bloques
                if abs(b.correccion_db) > 1e-3))
            R.curvas = curvas()
            qa = QAStems(edl, R) if P["salidas"]["qa"] else None
            cama = R.cama(por_stem=qa)
            pasadas = 2
            p_cama = niveles.potencia_k_bloques(cama)
            rel = niveles.relativo_en_habla(p_cama, p_voz, mask)
            t_st = (np.arange(len(rel)) + 0.5) * 0.1
            rel[np.arange(len(rel)) % 5 != 0] = np.nan
            for b in bloques:          # medición final por bloque
                m = niveles.ventanas_del_bloque(b, t_st, excluir)
                v = rel[m & np.isfinite(rel)]
                b.medido_lu = float(np.median(v)) if len(v) >= 3 else b.medido_lu
        t0 = marca("render_2_s", t0)

    # ---- techos (guardia): bajo la voz, en pausas y sin voz; la ganancia del master se prevé
    # con la sonoridad de voz + cama (no están correlacionadas: las potencias se suman)
    guardia = {"activa": False, "max_db": 0.0, "segundos": 0.0}
    p_cama = niveles.potencia_k_bloques(cama)

    def ganancia_prevista(pc):
        m = min(len(pc), len(p_voz))
        lp = niveles.integrado(pc[:m] + p_voz[:m])
        return P["master"]["lufs"] - (lp if lp is not None else P["master"]["lufs"])

    if P["niveles"]["guardia_voz"]:
        cama0 = None
        red = np.zeros(1)
        ultimo = np.inf
        exceso_inicial = None
        for _ in range(5):        # la reducción se promedia en la ventana de 3 s: se itera
            g_prev = ganancia_prevista(p_cama)
            extra, exc = niveles.techos(p_cama, p_voz, mask, voz, bloques, P, voz.lufs_mezcla, g_prev)
            exceso_inicial = exceso_inicial or exc
            if extra.max() <= 0.3 or extra.max() > 0.8 * ultimo:     # listo, o ya no converge
                break
            ultimo = extra.max()
            if cama0 is None:
                cama0 = cama.copy()
            red = extra if len(red) == 1 else red[:len(extra)] + extra[:len(red)]
            red = np.minimum(red, P["niveles"]["guardia_max_db"])
            cama = R.aplicar_guardia(cama0.copy(), red)
            p_cama = niveles.potencia_k_bloques(cama)
        del cama0
        if red.max() > 0.05:
            guardia = {"activa": True, "max_db": round(float(red.max()), 2),
                       "segundos": round(float((red > 0.25).sum() * 0.1), 1),
                       "exceso_antes_db": exceso_inicial,
                       "regiones": _regiones(red, 0.25)}
            log(f"techos (guardia): hasta −{red.max():.1f} dB en {guardia['segundos']:.1f} s")
    t0 = marca("guardia_s", t0)

    # ---- master
    mask_voz = voz.mascara(np.arange(edl.n_total) / SR)
    mezcla, info_master, gr = masterizar(voz.x, cama, P["master"], mask_voz)
    G = info_master["ganancia_master_db"]
    log(f"master: {info_master['lufs_integrado']} LUFS, {info_master['pico_dbtp']} dBTP, "
        f"ganancia {G:+.2f} dB, limitador sobre la voz máx {info_master['limitador']['voz']['max_db']} dB")
    t0 = marca("master_s", t0)

    # ---- salidas de audio: la cama en la escala de la mezcla final (sin limitador)
    p_cama_pre = p_cama                    # potencia de la cama antes de la ganancia del master
    cama *= np.float32(10 ** (G / 20))
    nombre = Path(plan_path).stem
    escribir_wav(out / "mezcla_final.wav", mezcla, f"mezcla|{nombre}")
    escribir_wav(out / "musica_cama.wav", cama, f"cama|{nombre}")
    t0 = marca("escritura_s", t0)

    # ---- informe
    from . import informe as inf
    p_mez = niveles.potencia_k_bloques(mezcla)
    niv = inf.niveles(voz, p_voz, p_cama_pre, p_mez, mask, P, G, bloques)
    duck = inf.ducking(ctrl, voz, P)
    emp = inf.empalmes(edl, qa, P)
    grilla = inf.rejilla(edl)
    clicks = qa.clicks if qa is not None else {}
    lim = info_master["limitador"]
    if lim["voz"]["max_db"] > P["master"]["max_reduccion_voz_db"]:
        avisos.append(f"el limitador baja la voz hasta {lim['voz']['max_db']} dB en algún pico "
                      f"(p99,9 {lim['voz']['p999_db']} dB); con la voz entregada a −3 dBTP no tocaría")
    if info_master["lufs_integrado"] is not None and abs(info_master["lufs_integrado"] - P["master"]["lufs"]) > 0.2:
        avisos.append(f"la mezcla quedó en {info_master['lufs_integrado']} LUFS (objetivo {P['master']['lufs']}): "
                      "llegar exigía limitar más de 12 dB")
    nuevos = sum(v["nuevos"] for v in clicks.values())
    if nuevos:
        avisos.append(f"{nuevos} clicks nuevos detectados en los stems armados (ver qa.clicks)")
    bv = niv.get("musica_bajo_voz_lu") or {}
    for clave, nombre_reg in (("pausas", "las pausas"), ("intro", "la intro"), ("final", "el final")):
        r = niv.get(clave)
        if r and r.get("cumple") is False:
            avisos.append(f"la música en {nombre_reg} llega a {r['max_lufs_st']} LUFS-S (techo {r['techo_lufs_st']})")
    reporte = {
        "version": VERSION,
        "entrada": {"voz": str(voz_path), "plan": str(plan_path), "duracion_voz_s": round(voz.dur, 3),
                    "duracion_mezcla_s": round(edl.n_total / SR, 3)},
        "voz": {"lufs_archivo": _r(voz.lufs_archivo, 2), "lufs_en_mezcla_estereo": _r(voz.lufs_mezcla, 2),
                "lufs_en_mezcla_final": _r(voz.lufs_mezcla + G if voz.lufs_mezcla is not None else None, 2),
                "canales_origen": voz.canales_origen, "sr_origen": voz.sr_origen,
                "nivel_activo_dbfs": _r(voz.nivel_activo_db, 1), "umbral_habla_dbfs": _r(voz.umbral_db, 1),
                **voz_mod.resumen_pausas(voz, P["niveles"]["pausa_larga_s"])},
        "niveles": niv,
        "mezcla": {**info_master, "pasadas_de_nivel": pasadas, "guardia_de_voz": guardia},
        "tramos": [_tramo_info(tre, bloques, plan) for tre in edl.tramos],
        "transiciones": [{"de": t.de + 1, "a": None if t.a is None else t.a + 1, "tipo": t.tipo,
                          "t_downbeat": round(t.t, 3), "ventana": [round(t.ventana[0], 3), round(t.ventana[1], 3)],
                          "t_corte_directo": _r(t.t_corte), "detalle": t.detalle} for t in edl.transiciones],
        "empalmes": emp,
        "qa": {"clicks": clicks, "clicks_nuevos_total": nuevos, "ducking": duck, "grilla": grilla},
        "avisos": avisos,
        "parametros": P,
        "tiempos_s": tiempos,
    }
    # ---- envolventes y gráfico
    from . import envolventes as env
    info_env = env.escribir(out / "envolventes.json", voz, cama, edl, bloques, plan,
                            P["salidas"]["fps"], P["salidas"]["rango_db"], Path(voz_path).name,
                            "musica_cama.wav")
    reporte["envolventes"] = info_env
    t0 = marca("envolventes_s", t0)
    if P["salidas"]["png"]:
        from .grafico import dibujar
        pc = niveles.potencia_k_bloques(cama)            # ya en la escala final
        pv = p_voz * 10 ** (G / 10)
        n = min(len(p_mez), len(pc), len(pv))
        tt, lc = niveles.corto_plazo(pc[:n], salto=1)
        _, lv = niveles.corto_plazo(pv[:n], salto=1)
        _, lm = niveles.corto_plazo(p_mez[:n], salto=1)
        pa = niv.get("pausas") or {}
        it = niv.get("intro") or {}
        sub = (f"mezcla {info_master['lufs_integrado']} LUFS · pico {info_master['pico_dbtp']} dBTP · "
               f"música bajo la voz {bv.get('mediana', '—')} LU (p10 {bv.get('p10', '—')}, p90 {bv.get('p90', '—')}; "
               f"{bv.get('dentro_ventana_pct', '—')} % en {bv.get('ventana_lu', '—')}) · "
               f"pausas máx {pa.get('max_vs_voz_lu', '—')} LU de la voz · intro máx {it.get('max_lufs_st', '—')} LUFS-S · "
               f"limitador sobre la voz máx {lim['voz']['max_db']} dB · clicks nuevos {nuevos}")
        techos = {"bajo_voz": (P["niveles"]["musica_bajo_voz_lu"], P["niveles"]["ventana_lu"]),
                  "pausas": None if voz.lufs_mezcla is None else voz.lufs_mezcla + G + P["niveles"]["techo_pausas_lu"],
                  "sin_voz": P["niveles"]["techo_sin_voz_lufs"]}
        dibujar(out / "mezcla.png", voz, R, ctrl, edl, plan, (tt, lc, lv, lm), gr,
                {"titulo": f"Mezcla de voz y música — {nombre}", "subtitulo": sub, "techos": techos,
                 "ganancia_master_db": G})
        t0 = marca("grafico_s", t0)
    tiempos["total_s"] = round(time.time() - t_ini, 2)
    (out / "informe.json").write_text(json.dumps(reporte, indent=2, ensure_ascii=False, default=_json),
                                      encoding="utf-8")
    log(f"listo en {tiempos['total_s']:.1f} s → {out}")
    return reporte


def _regiones(red, umbral):
    """[(inicio_s, fin_s, max_db)] donde la guardia baja más que `umbral` dB."""
    out = []
    act = red > umbral
    d = np.diff(np.concatenate([[0], act.astype(np.int8), [0]]))
    for a, b in zip(np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]):
        out.append([round(a * 0.1, 1), round(b * 0.1, 1), round(float(red[a:b].max()), 2)])
    return out


def _json(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, (set, tuple)):
        return list(o)
    return str(o)


def _tramo_info(tre, bloques, plan) -> dict:
    tr = tre.tramo
    bl = [b for b in bloques if b.tramo == tr.indice]
    d = {
        "id": tr.id, "cancion": tr.cancion.slug, "secciones": tr.secciones_txt,
        "inicio_plan": tr.inicio, "fin_plan": tr.fin,
        "entrada_real": round(tre.t_entrada, 3), "fin_musica_real": round(tre.t_fin_musica, 3),
        "desvio_entrada_s": round(tre.t_entrada - tr.inicio, 3),
        "compases": tre.ruta_txt(),
        "corridas": [{"compases": [c.c0, c.c1], "t0": round(c.t0 + c.lag, 3), "t1": round(c.t_fin, 3),
                      "union": c.union, "desfase_ms": round(c.lag * 1000, 2)} for c in tre.corridas],
        "loops": sum(1 for c in tre.corridas if c.union == "loop"),
        "transicion": tr.transicion.tipo, "nivel_db": tr.nivel_db,
        "bloques": [{"seccion": b.seccion, "ganancia_db": round(b.ganancia_db, 2),
                     "objetivo_lu": round(b.objetivo_lu, 2), "medido_lu": _r(b.medido_lu, 2),
                     "correccion_db": round(b.correccion_db, 2), "lufs_seccion": _r(b.l_entero, 2),
                     "lufs_seccion_duck": _r(b.l_duck, 2), "voz_lufs": _r(b.l_voz, 2),
                     "estimacion": b.metodo, "relativo_estimado_sin_ganancia": _r(b.rel_estimado, 2),
                     "ventanas_medidas": b.ventanas} for b in bl],
        "avisos": tre.avisos,
    }
    if tr.ancla is not None:
        d["ancla"] = {"pedido": tr.ancla.texto(), "t_real": _r(tre.ancla_t), "error_ms": tre.ancla_error_ms}
    if tr.stems:
        d["stems"] = {s: ("silencio" if v is None else v) for s, v in tr.stems.items()}
    return d
