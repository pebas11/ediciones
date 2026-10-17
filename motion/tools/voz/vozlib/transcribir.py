"""Transcripción con faster-whisper (CPU, int8) y ajuste de bordes de palabra por energía."""

from __future__ import annotations

import re
import time
import unicodedata
from pathlib import Path

import numpy as np
from scipy import signal

from . import dsp, util

# Whisper "limpia" las disfluencias. Un prompt inicial escrito con muletillas y reinicios le
# indica que transcriba literal (técnica del cookbook de OpenAI). Sin palabras de blooper
# ("perdón", "de nuevo"): no queremos sugerirle que las alucine.
PROMPT_DISFLUENCIAS = (
    "Eh... bueno, este... la verdad es que, mmm, no sé. O sea, la, la idea es esa, ¿viste? "
    "Ehm, vamos a ver."
)
MODELOS_RESPALDO = ["medium", "small"]
PREPEND = "\"'“¿¡([{-"
APPEND = "\"'.。,，!！?？:：”)]}、…;"

# Frases típicas que Whisper alucina en silencios en español
ALUCINACIONES = [
    "subtitulos realizados por la comunidad de amara",
    "subtitulos por la comunidad de amara",
    "amara.org",
    "gracias por ver el video",
    "suscribete al canal",
    "subtitulado por",
    "transcripcion por",
]


def normalizar(texto: str) -> str:
    """minúsculas, sin tildes ni puntuación (para comparar textos)."""
    t = unicodedata.normalize("NFKD", texto.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = t.replace("ñ", "n")
    return re.sub(r"[^a-z0-9]+", "", t)


def cargar_modelo(nombre: str, hilos: int, compute_type: str = "int8", modelos: Path | None = None):
    from faster_whisper import WhisperModel

    modelos = Path(modelos) if modelos else util.directorio_modelos()
    return WhisperModel(nombre, device="cpu", compute_type=compute_type, cpu_threads=hilos,
                        num_workers=1, download_root=str(modelos / "whisper"))


def transcribir(x: np.ndarray, sr: int, modelo: str = "large-v3-turbo", hilos: int = 2,
                compute_type: str = "int8", modelos: Path | None = None, beam_size: int = 5,
                prompt: str | None = PROMPT_DISFLUENCIAS, idioma: str = "es", lote: int = 0) -> dict:
    """Devuelve {'modelo', 'segmentos', 'palabras', ...} con tiempos de Whisper (sin ajustar).
    lote > 0 usa BatchedInferencePipeline (trozos cortados por VAD, procesados de a `lote`)."""
    import ctranslate2

    ctranslate2.set_random_seed(1234)  # reproducible aun con temperaturas de respaldo
    a16 = dsp.resample(x.astype(np.float32), sr, 16000)
    dur = len(x) / sr
    intentos = [modelo] + [m for m in MODELOS_RESPALDO if m != modelo]
    ultimo_error = None
    for nombre in intentos:
        try:
            t0 = time.perf_counter()
            mdl = cargar_modelo(nombre, hilos, compute_type, modelos)
            t_carga = time.perf_counter() - t0
            break
        except Exception as e:  # sin red, sin disco, modelo inexistente...
            ultimo_error = e
            util.log(f"  no pude cargar {nombre}: {e}; pruebo el siguiente")
    else:
        raise RuntimeError(f"No se pudo cargar ningún modelo de Whisper: {ultimo_error}")

    params = dict(
        language=idioma, task="transcribe", beam_size=beam_size, best_of=5,
        word_timestamps=True, vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 700, "speech_pad_ms": 300},
        condition_on_previous_text=False, initial_prompt=prompt,
        temperature=[0.0, 0.2, 0.4, 0.6, 0.8], compression_ratio_threshold=2.4,
        log_prob_threshold=-1.0, no_speech_threshold=0.6,
        prepend_punctuations=PREPEND, append_punctuations=APPEND,
    )
    t0 = time.perf_counter()
    if lote and lote > 0:
        from faster_whisper import BatchedInferencePipeline

        bp = {k: v for k, v in params.items() if k not in ("condition_on_previous_text",)}
        bp["batch_size"] = lote
        segs_it, info = BatchedInferencePipeline(mdl).transcribe(a16, **bp)
        params["lote"] = lote
    else:
        segs_it, info = mdl.transcribe(a16, **params)
    segmentos, palabras = [], []
    ultimo_log = time.perf_counter()
    for s in segs_it:
        texto = s.text.strip()
        seg = {"id": len(segmentos), "inicio": round(s.start, 3), "fin": round(s.end, 3),
               "texto": texto, "avg_logprob": round(s.avg_logprob, 3),
               "no_speech_prob": round(s.no_speech_prob, 3),
               "compression_ratio": round(s.compression_ratio, 2), "palabras": []}
        for w in s.words or []:
            t = w.word.strip()
            if not t:
                continue
            seg["palabras"].append(len(palabras))
            palabras.append({"texto": t, "norm": normalizar(t), "inicio": round(w.start, 3),
                             "fin": round(w.end, 3), "prob": round(w.probability, 3),
                             "seg": seg["id"]})
        segmentos.append(seg)
        if time.perf_counter() - ultimo_log > 20:
            ultimo_log = time.perf_counter()
            util.log(f"  transcribiendo… {util.fmt_t(s.end)} / {util.fmt_t(dur)}")
    t_trans = time.perf_counter() - t0
    filtrar_alucinaciones(segmentos, palabras)
    return {
        "modelo": nombre,
        "modelo_pedido": modelo,
        "compute_type": compute_type,
        "hilos": hilos,
        "idioma": info.language,
        "prob_idioma": round(info.language_probability, 3),
        "duracion_s": round(dur, 3),
        "parametros": {k: v for k, v in params.items() if k != "vad_parameters"} | {
            "vad_parameters": params["vad_parameters"]},
        "tiempo_carga_s": round(t_carga, 2),
        "tiempo_transcripcion_s": round(t_trans, 2),
        "segmentos": segmentos,
        "palabras": palabras,
    }


def filtrar_alucinaciones(segmentos: list, palabras: list) -> None:
    """Marca como dudosas las frases típicas alucinadas (se quitan después si no hay voz)."""
    for s in segmentos:
        n = normalizar(s["texto"])
        if any(normalizar(a) in n for a in ALUCINACIONES):
            s["sospecha_alucinacion"] = True
            for i in s["palabras"]:
                palabras[i]["sospecha_alucinacion"] = True


# ----------------------------------------------------------------------------
# Actividad acústica y ajuste de bordes
# ----------------------------------------------------------------------------


def mapa_actividad(x: np.ndarray, sr: int, hop_s: float = 0.005) -> dict:
    """Actividad de voz por cuadros de 5 ms: banda media (100–4000 Hz) o banda alta
    (4–10 kHz, para que las fricativas sordas como la "s" no queden afuera)."""
    sos_m = signal.butter(4, [100, 4000], btype="bandpass", fs=sr, output="sos")
    sos_h = signal.butter(4, [4000, min(10000, sr / 2 * 0.9)], btype="bandpass", fs=sr, output="sos")
    xm = signal.sosfiltfilt(sos_m, x.astype(np.float64))
    xh = signal.sosfiltfilt(sos_h, x.astype(np.float64))
    _, pm = dsp.rms_frames(xm, sr, 0.010, hop_s)
    _, ph = dsp.rms_frames(xh, sr, 0.010, hop_s)
    Lm, Lh = dsp.db(pm), dsp.db(ph)
    res = {"hop_s": hop_s, "n": len(Lm), "db": Lm}
    masks = []
    for L, minimo, frac in ((Lm, 9.0, 0.25), (Lh, 12.0, 0.30)):
        piso = float(np.percentile(L, 10))
        alto = float(np.percentile(L, 97))
        umbral = piso + max(minimo, frac * (alto - piso))
        masks.append(L > umbral)
    act = masks[0] | (masks[1] & (Lm > np.percentile(Lm, 10) + 3))
    # cierre (rellena huecos < 30 ms) y apertura (quita islas < 20 ms)
    from scipy.ndimage import binary_closing, binary_opening

    act = binary_closing(act, structure=np.ones(7, dtype=bool))
    act = binary_opening(act, structure=np.ones(4, dtype=bool))
    res["mask"] = act
    res["piso_db"] = float(np.percentile(Lm, 10))
    res["voz_db"] = float(np.percentile(Lm, 97))
    return res


def estimar_sesgo(palabras: list, act: dict, dur: float, caida_db: float = 20.0) -> dict:
    """Corrimiento sistemático de los tiempos de Whisper, medido donde la energía da la verdad:
    el final de las palabras que terminan antes de una pausa (fin del sonido directo, sin la
    cola de la sala). Dentro del habla continua la energía no permite corregir palabra por
    palabra, pero sí este corrimiento global (en el fixture Whisper adelanta ~0,08–0,1 s).
    El primer arranque tras un silencio no sirve para medirlo: ahí Whisper suele empezar
    mucho antes y con mucha dispersión (eso lo arregla el ajuste por palabra)."""
    m = act["mask"]
    L = act["db"]
    hop = act["hop_s"]
    n = len(m)
    sil = int(0.20 / hop)
    medidas = []
    for k, w in enumerate(palabras):
        sig = palabras[k + 1]["inicio"] if k + 1 < len(palabras) else dur
        if sig - w["fin"] < 0.25:
            continue
        i0 = int(w["inicio"] / hop)
        i1 = min(n - 1, int((w["fin"] + 0.4) / hop), int(sig / hop))
        if i1 - i0 < 4 or not m[i0:i1].any():
            continue
        pico = float(L[i0:i1].max())
        mf = m[i0:i1] & (L[i0:i1] >= pico - caida_db)
        idx = np.flatnonzero(mf)
        if not len(idx):
            continue
        j = i0 + int(idx[-1]) + 1  # primer cuadro después del sonido directo
        if j + sil < n and m[j : j + sil].any() and (L[j : j + sil] >= pico - caida_db).any():
            continue  # no hay silencio claro después: no sirve como referencia
        medidas.append(j * hop - w["fin"])
    if len(medidas) < 5:
        return {"sesgo_s": 0.0, "n": len(medidas), "aplicado": False, "motivo": "pocas medidas"}
    arr = np.array(medidas)
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)))
    aplicar = 0.02 <= abs(med) <= 0.25 and mad <= 0.06
    return {"sesgo_s": round(med if aplicar else 0.0, 3), "mediana_s": round(med, 3),
            "mad_s": round(mad, 3), "n": len(medidas), "aplicado": aplicar}


def ajustar_bordes(palabras: list, act: dict, dur: float, max_atras: float = 0.25,
                   max_adelante: float = 0.30, caida_db: float = 20.0) -> dict:
    """Corrige inicio/fin de Whisper con la energía real.

    0. Corre todo por el sesgo sistemático medido (ver estimar_sesgo).
    1. Si el borde cae en silencio, se mueve hacia la voz (dentro de la palabra).
    2. Si cae en plena voz y esa voz empezó/terminó cerca (≤ 0,25–0,30 s) sin pisar a la
       palabra vecina, se lleva hasta el ataque/caída real.
    El final se mide con un umbral relativo (pico de la palabra − 20 dB) para no incluir la
    cola de reverberación de la sala, que no es parte de la palabra.
    Nunca se cruzan palabras vecinas. Devuelve estadísticas del ajuste.
    """
    sesgo = estimar_sesgo(palabras, act, dur)
    if sesgo["aplicado"]:
        s = sesgo["sesgo_s"]
        for w in palabras:
            w.setdefault("inicio_whisper", w["inicio"])
            w.setdefault("fin_whisper", w["fin"])
            w["inicio"] = min(max(w["inicio"] + s, 0.0), dur)
            w["fin"] = min(max(w["fin"] + s, 0.0), dur)
    m_abs = act["mask"]
    L = act["db"]
    hop = act["hop_s"]
    n = len(m_abs)
    m = m_abs

    def fr(t):
        return int(min(max(t / hop, 0), n - 1))

    movidos = 0
    sin_energia = 0
    deltas = []
    prev_fin = 0.0
    for k, w in enumerate(palabras):
        w.setdefault("inicio_whisper", w["inicio"])
        w.setdefault("fin_whisper", w["fin"])
        ini, fin = w["inicio"], w["fin"]
        sig_ini = palabras[k + 1]["inicio"] if k + 1 < len(palabras) else dur
        lo = max(prev_fin, 0.0)
        hi = min(sig_ini, dur)
        i0, i1 = fr(ini), fr(fin)
        nuevo_ini, nuevo_fin = ini, fin
        if i1 <= i0:
            i1 = i0 + 1
        tramo = m[i0:i1]
        esperada = 0.06 * len(w.get("norm") or normalizar(w["texto"])) + 0.05
        if tramo.any() and fin - ini > max(0.35, 2.5 * esperada):
            # Palabra demasiado larga para su texto ("es" de 0,57 s) con un hueco adentro
            # (≥ 60 ms bajo el pico − 18 dB: la cola de la sala cuenta como hueco). Pasa tras
            # muletillas largas ("mmm… es"): Whisper le pega a la palabra la cola de la
            # anterior. Lo que está del lado continuo con la palabra vecina es de la vecina.
            pico_w = float(L[i0:i1].max())
            silen = ~(m[i0:i1] & (L[i0:i1] >= pico_w - 18.0))
            gi, gl = dsp.corridas(silen)
            internos = [(g0, gln) for g0, gln in zip(gi, gl)
                        if gln >= int(0.06 / hop) and g0 > 0 and g0 + gln < i1 - i0]
            if internos:
                g0, gln = max(internos, key=lambda q: q[1])
                pegada_prev = (k > 0 and palabras[k - 1]["fin"] >= ini - 0.03 and
                               m[max(0, i0 - int(0.05 / hop)) : i0 + g0].all())
                pegada_sig = (k + 1 < len(palabras) and sig_ini <= fin + 0.03 and
                              m[i0 + g0 + gln : min(n, i1 + int(0.05 / hop))].all())
                if pegada_prev:
                    palabras[k - 1]["fin"] = round((i0 + g0) * hop + 0.02, 3)
                    prev_fin = palabras[k - 1]["fin"]
                    ini = (i0 + g0 + gln) * hop - 0.010
                    lo = max(prev_fin, 0.0)
                    w["corregida"] = "hueco interno: cola de la palabra anterior"
                    # si quedó cortísima y la siguiente arranca pegada, su audio está al
                    # comienzo del tramo de la siguiente ("un ‖ día" → "un día")
                    if fin - ini < 0.5 * esperada and k + 1 < len(palabras) and sig_ini <= fin + 0.03:
                        nxt = palabras[k + 1]
                        fin = ini + min(esperada, 0.45 * max(nxt["fin"] - ini, 0.0))
                        nxt["inicio"] = round(max(nxt["inicio"], fin), 3)
                        sig_ini = nxt["inicio"]
                        hi = min(sig_ini, dur)
                elif pegada_sig:
                    fin = (i0 + g0) * hop + 0.02
                    w["corregida"] = "hueco interno: ataque de la palabra siguiente"
                i0, i1 = fr(ini), max(fr(fin), fr(ini) + 1)
                nuevo_ini, nuevo_fin = ini, fin
                tramo = m[i0:i1]
        if not tramo.any():
            # palabra sin energía propia: buscar voz cercana no reclamada
            sin_energia += 1
            w["sin_energia"] = True
        else:
            # inicio
            if not m[i0]:  # Whisper arrancó en silencio: avanzar hasta la voz
                j = i0 + int(np.argmax(m[i0:i1]))
                nuevo_ini = j * hop - 0.015
            else:  # arrancó con voz: ¿el ataque real está un poco antes?
                j = i0
                lim = max(fr(lo), fr(ini - max_atras))
                while j > lim and m[j - 1]:
                    j -= 1
                if j == 0 or not m[j - 1]:  # hay silencio antes: ataque encontrado
                    nuevo_ini = j * hop - 0.010
                # si no, la voz viene pegada de la palabra anterior: se respeta Whisper
            # fin (con umbral relativo al pico de la palabra: sin cola de reverb)
            pico = float(L[i0:i1].max())
            mf = m & (L >= pico - caida_db)
            if not mf[i1 - 1]:  # terminó en silencio o en la cola: retroceder hasta la voz
                tramo_f = mf[i0:i1]
                if tramo_f.any():
                    j = i1 - 1 - int(np.argmax(tramo_f[::-1]))
                    nuevo_fin = (j + 1) * hop + 0.025
            else:  # terminó con voz: ¿la caída real está un poco después?
                j = i1 - 1
                lim = min(fr(hi) - 1, fr(fin + max_adelante))
                while j < lim and mf[j + 1]:
                    j += 1
                if j == n - 1 or not mf[j + 1]:
                    nuevo_fin = (j + 1) * hop + 0.020
        nuevo_ini = max(nuevo_ini, lo, 0.0)
        nuevo_fin = min(max(nuevo_fin, nuevo_ini + 0.04), max(hi, nuevo_ini + 0.04), dur)
        if abs(nuevo_ini - ini) > 0.005 or abs(nuevo_fin - fin) > 0.005:
            movidos += 1
        deltas.append((nuevo_ini - ini, nuevo_fin - fin))
        w["inicio"] = round(nuevo_ini, 3)
        w["fin"] = round(nuevo_fin, 3)
        prev_fin = w["fin"]
    reubicadas = _reubicar_palabras_en_cola(palabras, act, dur)
    d = np.array(deltas) if deltas else np.zeros((0, 2))
    return {
        "sesgo_whisper": sesgo,
        "palabras_reubicadas": reubicadas,
        "palabras_ajustadas": movidos,
        "palabras_sin_energia": sin_energia,
        "delta_inicio_medio_ms": round(float(np.mean(np.abs(d[:, 0]))) * 1000, 1) if len(d) else 0,
        "delta_fin_medio_ms": round(float(np.mean(np.abs(d[:, 1]))) * 1000, 1) if len(d) else 0,
    }


def _reubicar_palabras_en_cola(palabras: list, act: dict, dur: float) -> int:
    """Whisper a veces pega la primera palabra de una frase al final de la anterior (cae en
    la cola de la sala, después de una pausa larga: "increíble. Las ‖ 1,4 s ‖ raíces").
    Señal: la palabra empieza donde terminó la anterior y su energía solo decae (no tiene
    ataque propio), mientras que justo antes de la palabra siguiente, pasada una pausa, hay
    voz que nadie reclama. La palabra se lleva ahí."""
    m, L, hop = act["mask"], act["db"], act["hop_s"]
    n = len(m)

    def fr(t):
        return int(min(max(t / hop, 0), n - 1))

    movidas = 0
    for k in range(1, len(palabras) - 1):
        w, prev, nxt = palabras[k], palabras[k - 1], palabras[k + 1]
        if w["inicio"] - prev["fin"] > 0.05 or nxt["inicio"] - w["fin"] < 0.4:
            continue
        i0, i1 = fr(w["inicio"]), fr(w["fin"])
        if i1 - i0 < 4:
            continue
        seg = L[i0:i1]
        subida = float(np.max(seg[2:] - seg[:-2]))
        if subida >= 6.0 or seg[-3:].mean() > seg[:3].mean() - 10.0:
            continue  # tiene ataque propio o no decae: es una palabra real
        p0, p1 = fr(prev["inicio"]), max(fr(prev["fin"]), fr(prev["inicio"]) + 1)
        pico_prev = float(L[p0:p1].max())
        # toda la palabra queda muy por debajo de la anterior (≥ 10 dB) y no tiene ningún
        # núcleo silábico (máximo local): es la cola de la sala, no una palabra
        if float(seg.max()) > pico_prev - 10.0:
            continue
        sm = np.convolve(seg, np.ones(5) / 5, mode="same")
        nucleos = int(np.sum((sm[1:-1] > sm[:-2]) & (sm[1:-1] >= sm[2:]) & (sm[1:-1] > sm.max() - 12)))
        if nucleos > 0:
            continue
        jn = fr(nxt["inicio"])
        # último ataque (silencio ≥ 0,2 s → voz) antes del inicio de la siguiente palabra
        j = jn
        while j > i1 and m[j - 1]:
            j -= 1
        hueco = j
        while hueco > i1 and not m[hueco - 1]:
            hueco -= 1
        if (j - hueco) * hop >= 0.2 and (jn - j) * hop >= 0.06 and j > i1:
            # hay voz sin dueño justo antes de la siguiente: es esta palabra
            w["inicio"] = round(j * hop - 0.01, 3)
            w["fin"] = round(max(w["inicio"] + 0.04, nxt["inicio"]), 3)
        else:
            # la siguiente se quedó con su audio ("Las raíces" dicho de corrido): esta palabra
            # va al comienzo del tramo de la siguiente, con su duración esperable
            esperada = 0.06 * len(w.get("norm") or normalizar(w["texto"])) + 0.05
            d = min(esperada, 0.45 * (nxt["fin"] - nxt["inicio"]))
            if d < 0.05:
                continue
            w["inicio"] = round(nxt["inicio"], 3)
            w["fin"] = round(nxt["inicio"] + d, 3)
            nxt["inicio"] = w["fin"]
        w["corregida"] = "reubicada: estaba en la cola de la palabra anterior"
        movidas += 1
    return movidas


def texto_plano(tr: dict) -> str:
    lineas = []
    for s in tr["segmentos"]:
        marca = " [¿alucinación?]" if s.get("sospecha_alucinacion") else ""
        lineas.append(f"[{util.fmt_t(s['inicio'])} → {util.fmt_t(s['fin'])}] {s['texto']}{marca}")
    return "\n".join(lineas) + "\n"
