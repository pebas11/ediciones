"""Orquestación: plan + voz → cama musical, mezcla final, informe, envolventes y gráfico."""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np

from . import SR, STEMS, VERSION
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
    niveles.estimar(bloques, plan, voz, p_voz, mask, niveles.potencias_control(ctrl, len(p_voz), plan))
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
        t_st, rel, *_ = niveles.medir_relativo(p_cama, p_voz, mask)
        excluir = [tr.ventana for tr in edl.transiciones if tr.tipo != "continuo" and tr.a is not None]
        if niveles.corregir(bloques, t_st, rel, P["niveles"]["tolerancia_lu"], excluir):
            log("corrección de niveles: " + ", ".join(
                f"{plan.tramos[b.tramo].id}/{b.seccion} {b.correccion_db:+.1f} dB" for b in bloques
                if abs(b.correccion_db) > 1e-3))
            R.curvas = curvas()
            qa = QAStems(edl, R) if P["salidas"]["qa"] else None
            cama = R.cama(por_stem=qa)
            pasadas = 2
            p_cama = niveles.potencia_k_bloques(cama)
            t_st, rel, *_ = niveles.medir_relativo(p_cama, p_voz, mask)
            for b in bloques:          # medición final por bloque
                m = niveles.ventanas_del_bloque(b, t_st, excluir)
                v = rel[m & np.isfinite(rel)]
                b.medido_lu = float(np.median(v)) if len(v) >= 3 else b.medido_lu
        t0 = marca("render_2_s", t0)

    # ---- master
    mask_voz = voz.mascara(np.arange(edl.n_total) / SR)
    voz_x = np.zeros((edl.n_total, 2), np.float32)
    voz_x[:voz.n] = voz.x
    mezcla, info_master, gr = masterizar(voz_x, cama, P["master"], mask_voz)
    log(f"master: {info_master['lufs_integrado']} LUFS, {info_master['pico_dbtp']} dBTP, "
        f"ganancia {info_master['ganancia_master_db']:+.2f} dB, limitador sobre la voz "
        f"máx {info_master['limitador']['voz']['max_db']} dB")
    t0 = marca("master_s", t0)

    # ---- salidas de audio
    nombre = Path(plan_path).stem
    escribir_wav(out / "mezcla_final.wav", mezcla, f"mezcla|{nombre}")
    escribir_wav(out / "musica_cama.wav", cama, f"cama|{nombre}")
    t0 = marca("escritura_s", t0)

    # ---- informe
    from . import informe as inf
    niv, st_rel = inf.niveles(voz, cama, mezcla, mask, P, voz.frases)
    duck = inf.ducking(ctrl, voz, P)
    emp = inf.empalmes(edl, qa, P)
    grilla = inf.rejilla(edl)
    clicks = qa.clicks if qa is not None else {}
    lim = info_master["limitador"]
    if lim["voz"]["max_db"] > P["master"]["max_reduccion_voz_db"]:
        avisos.append(f"el limitador baja la voz hasta {lim['voz']['max_db']} dB en algún pico "
                      f"(p99,9 {lim['voz']['p999_db']} dB); con la voz entregada a −3 dBTP no tocaría")
    nuevos = sum(v["nuevos"] for v in clicks.values())
    if nuevos:
        avisos.append(f"{nuevos} clicks nuevos detectados en los stems armados (ver qa.clicks)")
    rel = niv.get("relativo_bajo_voz_lu") or {}
    reporte = {
        "version": VERSION,
        "entrada": {"voz": str(voz_path), "plan": str(plan_path), "duracion_voz_s": round(voz.dur, 3),
                    "duracion_mezcla_s": round(edl.n_total / SR, 3)},
        "voz": {"lufs_archivo": _r(voz.lufs_archivo, 2), "lufs_en_mezcla_estereo": _r(voz.lufs_mezcla, 2),
                "canales_origen": voz.canales_origen, "sr_origen": voz.sr_origen,
                "nivel_activo_dbfs": _r(voz.nivel_activo_db, 1), "umbral_habla_dbfs": _r(voz.umbral_db, 1),
                **voz_mod.resumen_pausas(voz, P["niveles"]["pausa_larga_s"])},
        "niveles": niv,
        "mezcla": {**info_master, "pasadas_de_nivel": pasadas},
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
        pm = niveles.potencia_k_bloques(mezcla)
        pc = niveles.potencia_k_bloques(cama)
        n = min(len(pm), len(pc), len(p_voz))
        tt, lc = niveles.corto_plazo(pc[:n], salto=1)
        _, lv = niveles.corto_plazo(p_voz[:n], salto=1)
        _, lm = niveles.corto_plazo(pm[:n], salto=1)
        sub = (f"mezcla {info_master['lufs_integrado']} LUFS · pico {info_master['pico_dbtp']} dBTP · "
               f"cama bajo voz {rel.get('mediana', '—')} LU (p10 {rel.get('p10', '—')}, p90 {rel.get('p90', '—')}) · "
               f"pausas largas {niv.get('cama_pausas_largas_vs_voz_lu', '—')} LU · limitador sobre la voz máx "
               f"{lim['voz']['max_db']} dB · clicks nuevos {nuevos}")
        dibujar(out / "mezcla.png", voz, R, ctrl, edl, plan, (tt, lc, lv, lm), gr,
                {"titulo": f"Mezcla de voz y música — {nombre}", "subtitulo": sub})
        t0 = marca("grafico_s", t0)
    tiempos["total_s"] = round(time.time() - t_ini, 2)
    (out / "informe.json").write_text(json.dumps(reporte, indent=2, ensure_ascii=False, default=_json),
                                      encoding="utf-8")
    log(f"listo en {tiempos['total_s']:.1f} s → {out}")
    return reporte


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
