"""Prueba de punta a punta sobre el fixture sintético: EDL obtenida contra la esperada.

Corre (o reusa) procesar.py y aplicar.py sobre pruebas/fixtures/sintetico.mp4 y verifica:
    - cada corte esperado (arranque en falso, blooper, muletillas, silencios largos) está en la
      EDL propuesta con aplicar=true, cubre las palabras a sacar y no pisa palabras vecinas;
    - no hay cortes de contenido aplicados que saquen palabras que deben quedar
      ("Bienvenidos de nuevo al canal", "Este intercambio"...);
    - el texto final coincide con el guion sin las tomas fallidas;
    - pausas finales ≤ 0,6 s; loudness −16 LUFS ±0,5 y pico verdadero ≤ −1,4 dBTP;
    - el zumbido, el ruido, el clipping y los clics quedan resueltos;
    - los bordes de palabra quedan cerca de la verdad del TTS;
    - el corte de video sale con la misma duración que la voz.

Uso:
    python -m pytest pruebas/test_pipeline.py -q          (genera el fixture si falta)
    VOZ_TEST_REHACER=1 python -m pytest ...                (fuerza volver a procesar)
    VOZ_TEST_MODELO=medium python -m pytest ...            (modelo de Whisper a usar)
    python pruebas/test_pipeline.py                        (sin pytest: imprime el reporte)
"""

from __future__ import annotations

import difflib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np

AQUI = Path(__file__).resolve().parent
RAIZ = AQUI.parent
sys.path.insert(0, str(RAIZ))

from vozlib import analisis, dsp, edicion, util  # noqa: E402
from vozlib.transcribir import normalizar  # noqa: E402

FIX = AQUI / "fixtures"
SALIDA = RAIZ / "salida" / "test_sintetico"
CONTENIDO = set(edicion.TIPOS_CONTENIDO) - {"sonido_sin_texto", "ruido"}


def _correr(cmd: list[str]):
    r = subprocess.run([sys.executable, *cmd], cwd=RAIZ, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"Falló {' '.join(cmd)}\n{r.stdout[-3000:]}\n{r.stderr[-3000:]}")
    return r


def preparar() -> dict:
    if not (FIX / "sintetico.mp4").exists() or not (FIX / "esperado.json").exists():
        _correr([str(AQUI / "generar_fixture.py")])
    rehacer = os.environ.get("VOZ_TEST_REHACER") == "1"
    modelo = os.environ.get("VOZ_TEST_MODELO", "large-v3-turbo")
    if rehacer or not (SALIDA / "edl_propuesta.json").exists():
        _correr(["procesar.py", str(FIX / "sintetico.mp4"), "--out", str(SALIDA), "--modelo", modelo])
    if rehacer or not (SALIDA / "estadisticas.json").exists() or \
            (SALIDA / "estadisticas.json").stat().st_mtime < (SALIDA / "edl_propuesta.json").stat().st_mtime:
        _correr(["aplicar.py", str(SALIDA), "--edl", "edl_propuesta.json",
                 "--video", str(FIX / "sintetico.mp4")])
    return {
        "esperado": util.leer_json(FIX / "esperado.json"),
        "edl": util.leer_json(SALIDA / "edl_propuesta.json"),
        "tr": util.leer_json(SALIDA / "transcripcion.json"),
        "final": util.leer_json(SALIDA / "palabras_final.json"),
        "an": util.leer_json(SALIDA / "analisis.json"),
        "stats": util.leer_json(SALIDA / "estadisticas.json"),
    }


# ----------------------------------------------------------------------------
# Comparación EDL esperada ↔ obtenida
# ----------------------------------------------------------------------------


def _cubierto(a: float, b: float, iv: list[tuple[float, float]]) -> float:
    if b <= a:
        return 0.0
    return sum(max(0.0, min(b, y) - max(a, x)) for x, y in iv) / (b - a)


def comparar_edl(esp: dict, edl: dict) -> dict:
    aplicados = [c for c in edl["cortes"] if c["aplicar"]]
    union_todos = edicion.union_intervalos([(c["inicio"], c["fin"]) for c in aplicados])
    pal = esp["palabras"]
    filas = []
    usados = set()
    for e in esp["cortes_esperados"]:
        if e["tipo"] == "silencio":
            gap0, gap1 = e["palabras_inicio"], e["palabras_fin"]
            quitado = _cubierto(gap0, gap1, union_todos) * (gap1 - gap0)
            queda = (gap1 - gap0) - quitado
            ids = [c["id"] for c in aplicados if c["fin"] > gap0 and c["inicio"] < gap1]
            usados.update(ids)
            ok = 0.15 <= queda <= 0.60
            filas.append({"esperado": e["tipo"], "texto": e["texto"], "t": round(gap0, 2),
                          "obtenido": ids, "detalle": f"pausa {gap1 - gap0:.2f} s → {queda:.2f} s",
                          "ok": ok})
            continue
        a, b = e["palabras_inicio"], e["palabras_fin"]
        cand = [c for c in aplicados if c["tipo"] in CONTENIDO and c["fin"] > a and c["inicio"] < b]
        usados.update(c["id"] for c in cand)
        union = edicion.union_intervalos([(c["inicio"], c["fin"]) for c in cand])
        cobertura = _cubierto(a, b, union)
        # ¿pisa la palabra que queda antes o después?
        vecinos = [w for w in pal if w["rol"] == "mantener" and
                   (abs(w["fin"] - e["margen_izq"]) < 1e-3 or
                    (e["margen_der"] is not None and abs(w["inicio"] - e["margen_der"]) < 1e-3))]
        pisa = max([_cubierto(w["inicio"], w["fin"], union) for w in vecinos] or [0.0])
        tipos = sorted({c["tipo"] for c in cand})
        ok = cobertura >= 0.9 and pisa <= 0.1
        filas.append({"esperado": e["tipo"], "texto": e["texto"], "t": round(a, 2),
                      "obtenido": [f"{c['id']}:{c['tipo']}({c['confianza']:.2f})" for c in cand],
                      "detalle": f"cubre {100 * cobertura:.0f} % de las palabras, pisa vecinas "
                                 f"{100 * pisa:.0f} %, tipos {tipos}",
                      "ok": ok, "tipo_coincide": e["tipo"] in tipos or (
                          e["tipo"] in ("arranque_falso", "repeticion", "blooper") and
                          bool(set(tipos) & {"arranque_falso", "repeticion", "blooper"}))})
    # cortes de contenido aplicados que no corresponden a nada esperado
    extras = []
    keep = [w for w in pal if w["rol"] == "mantener"]
    for c in aplicados:
        if c["tipo"] == "silencio" or c["id"] in usados:
            continue
        saca = [w["texto"] for w in keep if _cubierto(w["inicio"], w["fin"], [(c["inicio"], c["fin"])]) > 0.3]
        extras.append({"id": c["id"], "tipo": c["tipo"], "t": c["inicio"], "texto": c["texto"],
                       "saca_palabras_buenas": saca})
    return {"filas": filas, "extras": extras}


def precision_bordes(esp: dict, tr: dict) -> dict:
    A = [normalizar(w["texto"]) for w in tr["palabras"]]
    B = [w["norm"] for w in esp["palabras"]]
    sm = difflib.SequenceMatcher(a=A, b=B, autojunk=False)
    pares = [(m.a + k, m.b + k) for m in sm.get_matching_blocks() for k in range(m.size)]
    d_ini_w, d_ini, d_fin = [], [], []
    for i, j in pares:
        w, g = tr["palabras"][i], esp["palabras"][j]
        d_ini_w.append(w.get("inicio_whisper", w["inicio"]) - g["inicio"])
        d_ini.append(w["inicio"] - g["inicio"])
        sig = esp["palabras"][j + 1]["inicio"] if j + 1 < len(esp["palabras"]) else 1e9
        if sig - g["fin"] > 0.25:
            d_fin.append(w["fin"] - g["fin"])

    def st(v):
        a = np.abs(np.array(v))
        return {"mediana_ms": round(float(np.median(a)) * 1000), "p90_ms": round(float(np.percentile(a, 90)) * 1000),
                "sesgo_ms": round(float(np.median(v)) * 1000)}

    return {"palabras_alineadas": len(pares), "de": len(B), "inicio_whisper": st(d_ini_w),
            "inicio_ajustado": st(d_ini), "fin_antes_de_pausa": st(d_fin)}


def metricas_audio(esp: dict) -> dict:
    x, sr = util.leer_wav(SALIDA / "audio_original.wav")
    y, _ = util.leer_wav(SALIDA / "voz_limpia.wav")
    f, _ = util.leer_wav(SALIDA / "voz_final.wav")
    seco, _ = util.leer_wav(FIX / "sintetico_seco.wav")
    from scipy import signal

    res = {}
    # ruido en silencios conocidos (relativo a la voz de cada señal)
    sil = [(e["inicio"] + 0.6, e["fin"] - 0.4) for e in esp["eventos"]
           if e["tipo"] == "silencio" and e["fin"] - e["inicio"] >= 1.5]

    def nivel(s, iv):
        v = np.concatenate([s[int(a * sr):int(b * sr)] for a, b in iv])
        return float(dsp.db_amp(np.sqrt(np.mean(v.astype(np.float64) ** 2))))

    voz_iv = [(w["inicio"], w["fin"]) for w in esp["palabras"]]
    snr_x = nivel(x, voz_iv) - nivel(x, sil)
    snr_y = nivel(y, voz_iv) - nivel(y, sil)
    res["snr_silencios_db"] = {"antes": round(snr_x, 1), "despues": round(snr_y, 1),
                               "mejora": round(snr_y - snr_x, 1)}
    # zumbido: prominencia de 50/100/150 Hz en el resultado
    z = analisis.detectar_zumbido(y, sr)
    res["zumbido_despues"] = {a["k"] * 50: a["prominencia_db"] for a in z["armonicos"][:5]}
    res["zumbido_hay_despues"] = z["hay"]
    # clipping: (1) el resultado no tiene mesetas; (2) prueba aislada del de-clip: el grito
    # seco recortado 4 dB por encima del fondo de escala, ¿cuánto se parece al original?
    from vozlib import limpieza

    res["clipping_antes"] = analisis.detectar_clipping(x, sr)["hay"]
    res["clipping_despues"] = analisis.detectar_clipping(y, sr)["hay"]
    ev = [e for e in esp["eventos"] if e["tipo"] == "voz" and e["rol"] == "mantener_fuerte"][0]
    g = seco[int(ev["inicio"] * sr):int(ev["fin"] * sr)].astype(np.float64)
    g = g / np.max(np.abs(g)) * 10 ** (4 / 20)
    rec = np.clip(g, -1, 1).astype(np.float32)
    reg = limpieza.regiones_clipping(rec, sr)
    dec, _ = limpieza.declip(rec, sr, {"regiones_muestras": reg})

    def snr(ref, s):
        return float(10 * np.log10(np.sum(ref ** 2) / np.sum((ref - s) ** 2)))

    res["declip_aislado_snr_db"] = {"recortado": round(snr(g, rec), 1),
                                    "reparado": round(snr(g, dec.astype(np.float64)), 1),
                                    "regiones": len(reg)}
    # clics: nivel > 3 kHz en ±15 ms del clic relativo al fondo cercano
    sosc = signal.butter(4, 3000, "highpass", fs=sr, output="sos")

    def clic(s, tc):
        a = s[int((tc - 0.015) * sr):int((tc + 0.015) * sr)].astype(np.float64)
        b = s[int((tc - 0.25) * sr):int((tc - 0.10) * sr)].astype(np.float64)
        ha, hb = signal.sosfilt(sosc, a), signal.sosfilt(sosc, b)
        return float(dsp.db_amp(np.sqrt(np.mean(ha ** 2)) / (np.sqrt(np.mean(hb ** 2)) + 1e-12)))

    res["clics_sobre_fondo_db"] = {"antes": [round(clic(x, t), 1) for t in esp["degradaciones"]["clics"]],
                                   "despues": [round(clic(y, t), 1) for t in esp["degradaciones"]["clics"]]}
    # plosivas: energía < 100 Hz en 60 ms del golpe, relativa al nivel de la palabra
    sosp = signal.butter(4, 100, "lowpass", fs=sr, output="sos")

    def golpe(s, t):
        seg = s[int((t - 0.05) * sr):int((t + 0.35) * sr)].astype(np.float64)
        lp = signal.sosfiltfilt(sosp, seg)
        i0, i1 = int(0.04 * sr), int(0.10 * sr)
        return float(dsp.db_amp(np.sqrt(np.mean(lp[i0:i1] ** 2)) / np.sqrt(np.mean(seg ** 2))))

    res["plosivas_graves_db"] = {
        "seco": [round(golpe(seco, t), 1) for t in esp["degradaciones"]["plosivas"]],
        "antes": [round(golpe(x, t), 1) for t in esp["degradaciones"]["plosivas"]],
        "despues": [round(golpe(y, t), 1) for t in esp["degradaciones"]["plosivas"]]}
    res["loudness"] = {"limpia_lufs": round(analisis.loudness(y, sr), 2),
                       "limpia_tp": round(float(dsp.db_amp(dsp.true_peak(y))), 2),
                       "final_lufs": round(analisis.loudness(f, sr), 2),
                       "final_tp": round(float(dsp.db_amp(dsp.true_peak(f))), 2)}
    return res


def texto_final(esp: dict, final: dict) -> dict:
    obt = [normalizar(w["texto"]) for w in final["palabras"]]
    exp = [normalizar(t) for t in esp["texto_final_esperado"].split()]
    sm = difflib.SequenceMatcher(a=exp, b=obt, autojunk=False)
    errores = sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal")
    return {"wer": round(errores / max(len(exp), 1), 3),
            "diferencias": [(op, " ".join(exp[i1:i2]), " ".join(obt[j1:j2]))
                            for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal"]}


def pausas_finales(final: dict) -> dict:
    p = final["palabras"]
    g = [b["inicio"] - a["fin"] for a, b in zip(p, p[1:])]
    return {"max_s": round(max(g), 3), "mayores_0_6": int(sum(v > 0.6 for v in g))}


def reporte(d: dict) -> dict:
    return {
        "edl": comparar_edl(d["esperado"], d["edl"]),
        "bordes": precision_bordes(d["esperado"], d["tr"]),
        "texto": texto_final(d["esperado"], d["final"]),
        "pausas": pausas_finales(d["final"]),
        "audio": metricas_audio(d["esperado"]),
        "duracion": {"antes": d["stats"]["duracion_antes_s"], "despues": d["stats"]["duracion_despues_s"]},
        "video": d["stats"]["video"],
    }


def imprimir(rep: dict) -> None:
    print("\nEDL esperada vs obtenida")
    print(f"{'esperado':16s} {'t':>7s}  {'ok':3s} obtenido / detalle")
    for f in rep["edl"]["filas"]:
        print(f"{f['esperado']:16s} {f['t']:7.2f}  {'sí' if f['ok'] else 'NO':3s} "
              f"{', '.join(f['obtenido']) or '—'}  [{f['detalle']}]  «{f['texto'][:50]}»")
    for e in rep["edl"]["extras"]:
        print(f"EXTRA {e['id']} {e['tipo']} {e['t']:.2f} «{e['texto']}» saca buenas: {e['saca_palabras_buenas']}")
    print("\nbordes:", json.dumps(rep["bordes"], ensure_ascii=False))
    print("texto final:", json.dumps(rep["texto"], ensure_ascii=False))
    print("pausas:", rep["pausas"], "| duración:", rep["duracion"])
    print("audio:", json.dumps(rep["audio"], ensure_ascii=False, indent=1))
    print("video:", rep["video"])


# ----------------------------------------------------------------------------
# Tests (pytest)
# ----------------------------------------------------------------------------

_D = None
_R = None


def _datos():
    global _D, _R
    if _D is None:
        _D = preparar()
        _R = reporte(_D)
        util.guardar_json(SALIDA / "reporte_test.json", _R)
    return _D, _R


def test_cortes_esperados_presentes():
    _, r = _datos()
    malos = [f for f in r["edl"]["filas"] if not f["ok"]]
    assert not malos, f"cortes esperados que fallan: {malos}"


def test_tipos_de_contenido():
    _, r = _datos()
    malos = [f for f in r["edl"]["filas"] if f["esperado"] != "silencio" and not f.get("tipo_coincide")]
    assert not malos, f"tipo distinto del esperado: {malos}"


def test_sin_cortes_que_saquen_palabras_buenas():
    _, r = _datos()
    malos = [e for e in r["edl"]["extras"] if e["saca_palabras_buenas"]]
    assert not malos, f"cortes aplicados que sacan palabras que deben quedar: {malos}"


def test_texto_final():
    _, r = _datos()
    assert r["texto"]["wer"] <= 0.10, r["texto"]


def test_pausas_finales():
    _, r = _datos()
    assert r["pausas"]["max_s"] <= 0.65, r["pausas"]


def test_loudness():
    _, r = _datos()
    L = r["audio"]["loudness"]
    assert abs(L["limpia_lufs"] + 16) <= 0.5 and abs(L["final_lufs"] + 16) <= 0.5, L
    assert L["limpia_tp"] <= -1.4 and L["final_tp"] <= -1.4, L


def test_limpieza():
    _, r = _datos()
    a = r["audio"]
    assert a["snr_silencios_db"]["mejora"] >= 8, a["snr_silencios_db"]
    assert not a["zumbido_hay_despues"], a["zumbido_despues"]
    assert a["clipping_antes"] and not a["clipping_despues"]
    d = a["declip_aislado_snr_db"]
    assert d["reparado"] >= d["recortado"] + 2, d
    assert max(a["clics_sobre_fondo_db"]["despues"]) <= 8, a["clics_sobre_fondo_db"]
    p = a["plosivas_graves_db"]
    assert np.mean(p["despues"]) <= np.mean(p["antes"]) - 3, p


def test_bordes_de_palabra():
    _, r = _datos()
    b = r["bordes"]
    assert b["palabras_alineadas"] >= 0.9 * b["de"], b
    assert b["inicio_ajustado"]["mediana_ms"] <= 60, b
    assert b["fin_antes_de_pausa"]["mediana_ms"] <= 60, b


def test_video_misma_duracion():
    d, r = _datos()
    v = r["video"]
    assert abs(v["duracion_video_s"] - d["stats"]["duracion_despues_s"]) <= 0.05, v
    mp4 = SALIDA / "video_editado.mp4"
    assert mp4.exists()
    info = util.sondear(mp4)
    assert abs(info["duracion_s"] - d["stats"]["duracion_despues_s"]) <= 0.1, info


if __name__ == "__main__":
    util.consola_utf8()
    d = preparar()
    rep = reporte(d)
    util.guardar_json(SALIDA / "reporte_test.json", rep)
    imprimir(rep)
