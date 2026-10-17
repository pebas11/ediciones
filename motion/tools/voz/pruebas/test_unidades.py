"""Pruebas rápidas (sin Whisper ni red) de las piezas con más lógica.

    python -m pytest pruebas/test_unidades.py -q
"""

from __future__ import annotations

import sys
from fractions import Fraction
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from vozlib import analisis, dsp, edicion, limpieza, render  # noqa: E402

SR = 48000


def _palabras(spec: list[tuple[str, float, float]]) -> list[dict]:
    return [{"i": k, "texto": t, "inicio": a, "fin": b, "prob": 0.9} for k, (t, a, b) in enumerate(spec)]


def _frase(texto: str, t0: float, paso: float = 0.3, dur: float = 0.25) -> list[tuple[str, float, float]]:
    out = []
    t = t0
    for w in texto.split():
        out.append((w, round(t, 3), round(t + dur, 3)))
        t += paso
    return out


def _audio_para(pal: list[dict], dur: float) -> np.ndarray:
    """Ruido de fondo bajo y "voz" (ruido fuerte) donde hay palabras: alcanza para la EDL."""
    rng = np.random.default_rng(0)
    x = rng.standard_normal(int(dur * SR)).astype(np.float32) * 1e-3
    for w in pal:
        a, b = int(w["inicio"] * SR), int(w["fin"] * SR)
        x[a:b] += rng.standard_normal(b - a).astype(np.float32) * 0.2
    return x


def _tipos(edl, aplicados=True):
    return [(c["tipo"], c["texto"]) for c in edl["cortes"]
            if c["tipo"] != "silencio" and (c["aplicar"] or not aplicados)]


# ----------------------------------------------------------------------------
# EDL
# ----------------------------------------------------------------------------


def test_arranque_en_falso_y_trampas():
    spec = (_frase("Hoy vamos a hablar de los hongos.", 0.5)
            + _frase("Los hongos no son...", 3.0)
            + _frase("Los hongos no son plantas, son un reino aparte.", 5.0)
            + _frase("No es una planta. No es un animal.", 9.0)
            + _frase("Bienvenidos de nuevo al canal.", 12.0))
    pal = _palabras(spec)
    edl = edicion.proponer(pal, _audio_para(pal, 15.0), SR)
    t = _tipos(edl)
    assert ("arranque_falso", "Los hongos no son...") in t, t
    assert len(t) == 1, t  # ni "No es…" (anáfora) ni "de nuevo" (contenido)


def test_blooper_con_toma_repetida():
    spec = (_frase("El micelio es enorme.", 0.5)
            + _frase("Puede crecer kilómetros bajo el...", 2.5)
            + _frase("Ay, perdón, de nuevo.", 4.6)
            + _frase("Puede crecer kilómetros bajo el suelo del bosque.", 7.0))
    pal = _palabras(spec)
    edl = edicion.proponer(pal, _audio_para(pal, 10.0), SR)
    bl = [c for c in edl["cortes"] if c["tipo"] == "blooper" and c["aplicar"]]
    assert len(bl) == 1
    assert bl[0]["texto"] == "Puede crecer kilómetros bajo el... Ay, perdón, de nuevo."


def test_muletillas_este_demostrativo():
    spec = (_frase("Y lo más interesante,", 0.5) + [("este...", 1.6, 2.0)]
            + _frase("es cómo se comunican.", 2.6)
            + _frase("Este video es corto.", 4.5)
            + [("Eh,", 6.0, 6.3)] + _frase("vamos.", 6.8))
    pal = _palabras(spec)
    edl = edicion.proponer(pal, _audio_para(pal, 8.0), SR)
    mul = [c["texto"] for c in edl["cortes"] if c["tipo"] == "muletilla" and c["aplicar"]]
    assert "este..." in mul and "Eh," in mul, mul
    assert "Este" not in mul


def test_tartamudeo_y_enfasis():
    spec = _frase("la la idea es esta.", 0.5, paso=0.25) + _frase("No, no, no me gusta.", 3.0)
    pal = _palabras(spec)
    edl = edicion.proponer(pal, _audio_para(pal, 5.0), SR)
    rep = [c["texto"] for c in edl["cortes"] if c["tipo"] == "repeticion" and c["aplicar"]]
    assert rep == ["la"], rep  # "no, no, no" es énfasis o blooper, no tartamudeo


def test_pausas_resultantes():
    spec = _frase("Primera frase.", 0.5) + _frase("Segunda frase sigue", 4.0) + _frase("después.", 7.0)
    pal = _palabras(spec)
    edl = edicion.proponer(pal, _audio_para(pal, 9.0), SR)
    quedan = sorted(c["pausa_resultante_s"] for c in edl["cortes"]
                    if c["tipo"] == "silencio" and "pausa_resultante_s" in c and c["inicio"] > 0.1
                    and c["fin"] < 8.9)
    assert len(quedan) == 2
    assert 0.25 <= quedan[0] <= 0.33  # dentro de la oración
    assert 0.40 <= quedan[1] <= 0.50  # tras punto


# ----------------------------------------------------------------------------
# aplicar: nunca cortar dentro de una palabra que queda; mapa y video exactos
# ----------------------------------------------------------------------------


def test_cortes_no_pisan_palabras_que_quedan():
    rng = np.random.default_rng(1)
    pal = _palabras(_frase(" ".join(f"p{k}" for k in range(60)), 0.3, paso=0.4, dur=0.3))
    cortes = []
    for k in range(25):
        a = float(rng.uniform(0, 24))
        cortes.append({"id": f"c{k}", "tipo": "manual", "inicio": a, "fin": a + float(rng.uniform(0.05, 0.5)),
                       "aplicar": True})
    quitar, avisos, aplicados = render.cortes_aplicados({"cortes": cortes}, pal, 25.0)
    for w in pal:
        tapado = sum(max(0.0, min(b, w["fin"]) - max(a, w["inicio"])) for a, b in quitar)
        assert tapado < 1e-6 or tapado / (w["fin"] - w["inicio"]) > 0.5, (w, tapado)


def test_mapa_y_render_conservan_duracion():
    rng = np.random.default_rng(2)
    x = rng.standard_normal(SR * 10).astype(np.float32) * 0.1
    quitar = [(1.0, 1.5), (3.2, 3.9), (6.0, 6.01), (8.0, 9.0)]
    segs = render.mantener(quitar, 10.0)
    segs_n = [(int(a * SR), int(b * SR)) for a, b in segs]
    y, h = render.renderizar(x, SR, segs_n, 20.0, [])
    assert len(y) == sum(b - a for a, b in segs_n)
    mapa = render.Mapa([(a / SR, b / SR) for a, b in segs_n])
    assert abs(mapa.t(2.0) - 1.5) < 1e-6
    assert abs(mapa.t(1.2, "inicio") - 1.0) < 1e-6 and abs(mapa.t(1.2, "fin") - 1.0) < 1e-6
    assert abs(mapa.total - len(y) / SR) < 1e-6


def test_fundido_igual_potencia_sin_saltos():
    t = np.arange(SR * 2) / SR
    x = (0.5 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
    segs = [(0, int(0.73 * SR)), (int(1.31 * SR), len(x))]
    y, _ = render.renderizar(x, SR, segs, 20.0, [])
    # sin discontinuidades: la diferencia entre muestras no supera la de la senoide sola
    assert np.max(np.abs(np.diff(y))) <= np.max(np.abs(np.diff(x))) * 1.6


def test_video_sin_deriva():
    rng = np.random.default_rng(3)
    t, segs = 0.0, []
    for _ in range(400):
        a = t + float(rng.uniform(0.05, 0.6))
        b = a + float(rng.uniform(0.3, 4.0))
        segs.append((a, b))
        t = b
    fps = Fraction(30000, 1001)
    rangos = render.cuadros_video(segs, fps)
    acum_audio = np.cumsum([b - a for a, b in segs])
    acum_video = np.cumsum([b - a for a, b in rangos]) / float(fps)
    assert np.max(np.abs(acum_audio - acum_video)) <= 0.5 / float(fps) + 1e-9


# ----------------------------------------------------------------------------
# DSP
# ----------------------------------------------------------------------------


def test_loudness_igual_a_pyloudnorm():
    import pyloudnorm

    rng = np.random.default_rng(4)
    x = (rng.standard_normal(SR * 8) * 0.05).astype(np.float32)
    x[SR * 2 : SR * 3] = 0.0
    nuestro = analisis.loudness(x, SR)
    ref = pyloudnorm.Meter(SR).integrated_loudness(x.astype(np.float64))
    assert abs(nuestro - ref) < 0.1, (nuestro, ref)


def test_normalizacion_y_true_peak():
    rng = np.random.default_rng(5)
    x = (rng.standard_normal(SR * 6) * 0.02).astype(np.float32)
    x[SR : SR + 200] += 0.9  # pico
    y, info = limpieza.normalizar(x, SR, -16.0, -1.5)
    assert abs(analisis.loudness(y, SR) + 16.0) <= 0.15
    assert dsp.db_amp(dsp.true_peak(y)) <= -1.45


def test_declip_mejora_y_detector_no_da_falsos_positivos():
    t = np.arange(SR) / SR
    s = (np.sin(2 * np.pi * 180 * t) + 0.5 * np.sin(2 * np.pi * 523 * t + 1) +
         0.25 * np.sin(2 * np.pi * 1310 * t + 2)) * np.hanning(SR) * 1.4
    rec = np.clip(s, -1, 1).astype(np.float32)
    info, regs = analisis._clipping(rec, SR)
    assert info["hay"] and regs
    dec, _ = limpieza.declip(rec, SR, {"regiones_muestras": regs, "techo": info.get("techo_estimado")})

    def snr(r, v):
        return 10 * np.log10(np.sum(r ** 2) / np.sum((r - v) ** 2))

    assert snr(s, dec) > snr(s, rec) + 3
    assert not analisis.detectar_clipping((s / np.max(np.abs(s)) * 0.9).astype(np.float32), SR)["hay"]


def test_fps_de_celular_a_tasa_estandar():
    from vozlib import util

    assert util._fps_fraccion(29.98) == Fraction(30000, 1001)
    assert util._fps_fraccion(30.02) == Fraction(30)
    assert util._fps_fraccion(59.94) == Fraction(60000, 1001)
    assert util._fps_fraccion(25.0) == Fraction(25)


def test_zumbido_frecuencia_exacta_y_notch():
    rng = np.random.default_rng(6)
    n = SR * 20
    t = np.arange(n) / SR
    hum = sum(10 ** (-40 / 20) / k * np.sin(2 * np.pi * 49.97 * k * t) for k in (1, 2, 3, 5))
    x = (rng.standard_normal(n) * 1e-3 + hum).astype(np.float32)
    z = analisis.detectar_zumbido(x, SR)
    assert z["hay"] and abs(z["f0_estimada_hz"] - 49.97) < 0.005, z["f0_estimada_hz"]
    y, info = limpieza.quitar_zumbido(x, SR, z["f0_estimada_hz"], z["armonicos_a_filtrar"])
    resto = analisis.detectar_zumbido(y, SR)
    assert not resto["hay"], resto["armonicos"][:4]


def test_resta_de_zumbido_no_suena_despues_de_la_voz():
    """Un tono de "voz" que justo cae en 100 Hz se corta de golpe: el notch dejaba un sonido
    después; la resta no tiene que agregar nada en el silencio que sigue."""
    rng = np.random.default_rng(7)
    n = SR * 12
    t = np.arange(n) / SR
    hum = 10 ** (-45 / 20) * np.sin(2 * np.pi * 50.0 * t)
    voz = np.where((t > 5) & (t < 6), 0.3 * np.sin(2 * np.pi * 100.0 * t), 0.0)
    x = (rng.standard_normal(n) * 1e-4 + hum + voz).astype(np.float32)
    y, _ = limpieza.quitar_zumbido(x, SR, 50.0, [1, 2, 3])
    despues = y[int(6.05 * SR):int(6.5 * SR)].astype(np.float64)
    assert 20 * np.log10(np.sqrt(np.mean(despues ** 2))) < -60
    notch = limpieza.quitar_zumbido_notch(x, SR, 50.0, [1, 2, 3], 1.5)
    dn = notch[int(6.05 * SR):int(6.5 * SR)].astype(np.float64)
    assert 20 * np.log10(np.sqrt(np.mean(dn ** 2))) > -40  # el notch sí suena (por eso no se usa)
