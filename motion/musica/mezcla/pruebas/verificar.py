#!/usr/bin/env python3
"""Pruebas del mezclador con criterios medibles (sin oídos).

    python3 motion/musica/mezcla/pruebas/verificar.py            # Umbral + entre canciones (~2–3 min)
    python3 motion/musica/mezcla/pruebas/verificar.py --largo    # + voz real de 8:44 con las 5 canciones (~3 min más)

Genera la voz de prueba si falta (edge-tts) y deja cada mezcla en salida/_mezcla_pruebas/<prueba>/.
Si existe la copia fija salida/_mezcla_pruebas/canciones/ se usa para las pruebas entre canciones
(las canciones originales se pueden estar re-renderizando).
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
MUSICA = AQUI.parents[1]
sys.path.insert(0, str(MUSICA))

from mezcla import pipeline                           # noqa: E402
from mezcla.plan import ErrorPlan, validar            # noqa: E402
from mezcla.canciones import Catalogo                 # noqa: E402

SAL = MUSICA / "salida" / "_mezcla_pruebas"
COPIA = SAL / "canciones"


def asegurar_voz(nombre: str, extra: list[str]):
    if not (SAL / f"{nombre}.wav").exists():
        subprocess.run([sys.executable, str(AQUI / "voz_prueba.py"), *extra], check=True)


class Chequeo:
    def __init__(self):
        self.filas = []

    def __call__(self, prueba, criterio, ok, valor):
        self.filas.append((prueba, criterio, bool(ok), valor))

    def imprimir(self) -> bool:
        ancho = max(len(c) for _, c, _, _ in self.filas)
        prueba_ant = None
        for p, c, ok, v in self.filas:
            if p != prueba_ant:
                print(f"\n== {p}")
                prueba_ant = p
            print(f"  [{'OK ' if ok else 'MAL'}] {c:<{ancho}}  {v}")
        malos = sum(1 for f in self.filas if not f[2])
        print(f"\n{len(self.filas) - malos}/{len(self.filas)} criterios OK")
        return malos == 0


def revisar(ch: Chequeo, nombre: str, plan: Path, voz: Path, dir_canciones=None):
    out = SAL / nombre
    rep = pipeline.mezclar(str(voz), str(plan), str(out), None, dir_canciones)
    P = rep["parametros"]
    n = rep["niveles"]
    m = rep["mezcla"]
    ch(nombre, "mezcla final −14 LUFS (±0,1)", abs(m["lufs_integrado"] - P["master"]["lufs"]) <= 0.1,
       f"{m['lufs_integrado']} LUFS")
    ch(nombre, "pico real ≤ −1 dBTP", m["pico_dbtp"] <= P["master"]["techo_dbtp"] + 0.01, f"{m['pico_dbtp']} dBTP")
    lv = m["limitador"]["voz"]
    ch(nombre, "limitador sobre la voz ≤ 1 dB", lv["max_db"] <= P["master"]["max_reduccion_voz_db"],
       f"máx {lv['max_db']} dB, p99,9 {lv['p999_db']} dB")
    bv = n["musica_bajo_voz_lu"]
    obj = P["niveles"]["musica_bajo_voz_lu"]
    ch(nombre, f"música bajo la voz: mediana {obj:+g} LU (±1)", abs(bv["mediana"] - obj) <= 1.0,
       f"mediana {bv['mediana']} LU (p10 {bv['p10']}, p90 {bv['p90']})")
    ch(nombre, "música bajo la voz: ≥ 85 % en la ventana del tramo", bv["dentro_ventana_del_tramo_pct"] >= 85,
       f"{bv['dentro_ventana_del_tramo_pct']} % (por encima {bv['por_encima_del_tramo_pct']} %)")
    for clave, texto in (("pausas", "pausas ≤ voz − 10 LU"), ("intro", "intro ≤ −20 LUFS-S"),
                         ("final", "final ≤ −20 LUFS-S"), ("maximo_musica", "nunca a tope (máx ≤ −20 LUFS-S)")):
        r = n.get(clave)
        if r:
            ch(nombre, texto, r["cumple"], f"máx {r['max_lufs_st']} LUFS-S ({r.get('max_vs_voz_lu')} LU de la voz)")
    ch(nombre, "sin clicks nuevos en los stems armados", rep["qa"]["clicks_nuevos_total"] == 0,
       {s: v["nuevos"] for s, v in rep["qa"]["clicks"].items()})
    emp = [e for e in rep["empalmes"] if e["tipo"] != "continuo"]
    malos = [(e["t_downbeat"], e["salto_nivel_db"]) for e in emp if e["ok_nivel"] is False]
    ch(nombre, "empalmes y loops sin saltos de nivel", not malos,
       f"{len(emp)} empalmes; saltos máx {max([abs(e['salto_nivel_db'] or 0) for e in emp], default=0):.2f} dB"
       + (f"; fuera: {malos}" if malos else ""))
    cerca = sum(e["clicks_nuevos_cerca"] for e in emp)
    ch(nombre, "sin clicks cerca de empalmes", cerca == 0, cerca)
    g = rep["qa"]["grilla"]["max_ms"]
    ch(nombre, "loops sin saltos de fase (grilla ≤ 10 ms)", g <= 10.0, f"{g} ms")
    for t in rep["tramos"]:
        if "ancla" in t:
            err = t["ancla"]["error_ms"]
            ch(nombre, f"ancla «{t['id']}» exacta (≤ 1 ms)", err is not None and abs(err) <= 1.0, f"{err} ms")
    d = rep["qa"]["ducking"]
    mel = d["stems"]["melodia"]
    ch(nombre, "ducking presente (melodía bajo la voz)", (mel["en_habla_db"] or 0) <= -8.0,
       f"melodía {mel['en_habla_db']} dB en habla, {mel['en_pausas_largas_db']} dB en pausas largas")
    ch(nombre, "ducking suave: no sube en pausas cortas (sin bombeo)", d["subidas_en_pausas_cortas"] == 0,
       f"{d['subidas_en_pausas']} subidas en pausas, {d['pausas_sin_subida']} pausas cortas sin subida")
    # estructura: batería y bajo no se superponen entre canciones distintas
    plan_v, voz_v, edl = pipeline.preparar(str(plan), str(voz), None, dir_canciones, leer_audio=False)
    choques = []
    for k, (tre, tre_b) in enumerate(zip(edl.tramos[:-1], edl.tramos[1:])):
        A, B = tre.corridas[-1], tre_b.corridas[0]
        if A.cancion is B.cancion:
            continue
        sa = next(sg for sg in edl.segmentos if sg.corrida is A)
        sb = next(sg for sg in edl.segmentos if sg.corrida is B)
        for s in P["empalmes"]["stems_ritmicos"]:
            fin_a = sa.sale[s].t1 if sa.sale.get(s) is not None else float("inf")
            ini_b = sb.entra[s].t0
            if fin_a > ini_b + 1e-3:
                choques.append((k + 1, s, round(fin_a - ini_b, 3)))
    distintas = sum(1 for a, b in zip(edl.tramos[:-1], edl.tramos[1:])
                    if a.corridas[-1].cancion is not b.corridas[0].cancion)
    if distintas:
        ch(nombre, "batería y bajo no se superponen entre canciones", not choques,
           f"{distintas} transiciones entre canciones" + (f"; choques {choques}" if choques else ""))
    ch(nombre, "tiempo de proceso", True, f"{rep['tiempos_s']['total_s']} s para {rep['entrada']['duracion_mezcla_s']:.0f} s")
    return rep


def validacion(ch: Chequeo, dir_canciones=None):
    cat = Catalogo(dir_canciones)
    malo = {"parametros": {"ducking": {"atake_ms": 60}},
            "tramos": [{"cancion": "umbrall", "secciones": ["umbral"], "inicio": 0, "fin": 20},
                       {"cancion": "umbral", "secciones": ["cumbre3"], "inicio": 20, "fin": 40,
                        "transicion": {"tipo": "fade"}},
                       {"cancion": "umbral", "seccion": "pulso", "inicio": 40, "fin": 60, "nivel": 3}]}
    esperados = ["¿quisiste decir 'ataque_ms'?", "la canción 'umbrall' no existe", "¿quisiste decir 'cumbre'?",
                 "transicion.tipo 'fade' no válido", "¿quisiste decir 'nivel_db'?"]
    try:
        validar(malo, cat)
        ch("validación del plan", "un plan roto se rechaza", False, "no dio error")
    except ErrorPlan as e:
        faltan = [x for x in esperados if x not in str(e)]
        ch("validación del plan", "errores claros, todos juntos y con sugerencias", not faltan,
           f"{len(e.errores)} errores" + (f"; faltan {faltan}" if faltan else ""))
    hueco = {"tramos": [{"cancion": "umbral", "secciones": ["umbral"], "inicio": 0, "fin": 30},
                        {"cancion": "umbral", "secciones": ["arpa"], "inicio": 33, "fin": 60}]}
    try:
        validar(hueco, cat)
        ch("validación del plan", "hueco sin 'pausa' se rechaza", False, "no dio error")
    except ErrorPlan as e:
        ch("validación del plan", "hueco sin 'pausa' se rechaza", "hueco" in str(e), e.errores[0][:80])


def main():
    ch = Chequeo()
    asegurar_voz("voz_prueba", [])
    copia = COPIA if (COPIA / "02-deriva" / "cues.json").exists() else None
    validacion(ch)
    revisar(ch, "umbral", AQUI / "plan_umbral.json", SAL / "voz_prueba.wav")
    revisar(ch, "canciones_mix", AQUI / "plan_canciones.json", SAL / "voz_prueba.wav", copia)
    if "--largo" in sys.argv:
        asegurar_voz("voz_librivox", ["--librivox"])
        revisar(ch, "largo", AQUI / "plan_largo.json", SAL / "voz_librivox.wav", copia)
    ok = ch.imprimir()
    (SAL / "verificacion.json").write_text(json.dumps(
        [{"prueba": p, "criterio": c, "ok": o, "valor": str(v)} for p, c, o, v in ch.filas],
        indent=2, ensure_ascii=False), encoding="utf-8")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
