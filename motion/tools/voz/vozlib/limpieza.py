"""Cadena de limpieza natural, en el orden pedido:

    0. DC y de-clip LSAR (solo si el análisis encontró clipping)
    1. Pasa-altos ~75 Hz
    2. Reducción de zumbido (notches causales en la frecuencia exacta de la red y armónicos)
    3. Reducción de ruido con límite de atenuación (DeepFilterNet3 → deep-filter → RNNoise →
       noisereduce). Los clics se reparan justo antes: la red los desparrama.
    4. Clics residuales y plosivas
    5. De-esser dinámico 5–9 kHz
    6. EQ correctiva suave (barro 200–400 Hz si sobra; presencia y aire leves)
    7. Compresión moderada (nivelador lento + compresor)
    8. Normalización en dos pasadas a −16 LUFS y −1,5 dBTP

Todo es determinista y en float32/float64; los parámetros salen del análisis.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import signal
from scipy.ndimage import median_filter

from . import analisis, dsp, ruido, util

DEFAULTS = {
    "pasa_altos_hz": 75.0,
    "zumbido_ancho_hz": 1.5,
    "ruido_backend": "auto",
    "ruido_atenuacion_db": None,  # None = según SNR (12/15/18 dB)
    "deesser_banda": (5000.0, 9000.0),
    "deesser_max_db": 6.0,
    "eq_max_barro_db": 3.0,
    "eq_presencia_db": 1.0,
    "eq_aire_db": 1.5,
    "comp_ratio": 2.5,
    "comp_ataque_ms": 5.0,
    "comp_liberacion_ms": 90.0,
    "comp_max_db": 9.0,
    "nivelador_max_db": 6.0,
    "lufs": -16.0,
    "true_peak": -1.5,
}


# ----------------------------------------------------------------------------
# 0. De-clip
# ----------------------------------------------------------------------------


def _ar_cov(segmentos: list[np.ndarray], p: int, lam: float = 1e-3) -> np.ndarray | None:
    """Coeficientes AR (método de covarianza) usando solo tramos de muestras sanas."""
    filas, obj = [], []
    for s in segmentos:
        if len(s) <= p + 4:
            continue
        M = np.lib.stride_tricks.sliding_window_view(s.astype(np.float64), p + 1)
        filas.append(M[:, :-1][:, ::-1])
        obj.append(M[:, -1])
    if not filas:
        return None
    X, y = np.vstack(filas), np.concatenate(obj)
    R = X.T @ X
    R += lam * np.trace(R) / p * np.eye(p)
    return -np.linalg.solve(R, X.T @ y)


def _lsar(w: np.ndarray, desconocidas: np.ndarray, p: int, cota: np.ndarray, iters: int = 6) -> np.ndarray:
    """Interpolación AR por mínimos cuadrados (Janssen) con la restricción de recorte:
    lo reconstruido nunca puede quedar por debajo del techo, con el signo de la meseta."""
    N = len(w)
    idx = np.flatnonzero(~desconocidas)
    if len(idx) < 2 * p:
        return w
    cortes = np.flatnonzero(np.diff(idx) > 1)
    ini = np.r_[idx[0], idx[cortes + 1]]
    fin = np.r_[idx[cortes], idx[-1]] + 1
    a = _ar_cov([w[i:j] for i, j in zip(ini, fin)], p)
    if a is None:
        return w
    coef = np.r_[1.0, a]
    A = np.zeros((N - p, N))
    filas = np.arange(N - p)
    for k in range(p + 1):
        A[filas, np.arange(p, N) - k] = coef[k]
    x = w.astype(np.float64).copy()
    u = desconocidas.copy()
    signo = np.sign(w)
    for _ in range(iters):
        ui, ki = np.flatnonzero(u), np.flatnonzero(~u)
        if not len(ui):
            break
        Au = A[:, ui]
        G = Au.T @ Au + 1e-9 * np.eye(len(ui))
        x[ui] = -np.linalg.solve(G, Au.T @ (A[:, ki] @ x[ki]))
        viola = u & desconocidas & (signo * x < cota - 1e-9)
        if not viola.any():
            break
        x[viola] = signo[viola] * cota[viola]
        u &= ~viola
    return x


def declip(x: np.ndarray, sr: int, clip_info: dict, p: int = 32) -> tuple[np.ndarray, dict]:
    """De-clip por interpolación AR (LSAR, orden 32) sobre cada meseta detectada. Medido con
    el grito seco recortado en PCM: +3 a +5 dB de SNR respecto del recortado (como el
    `adeclip` de ffmpeg). Después del AAC la mejora es chica: el códec ya borró la forma."""
    y = x.astype(np.float64).copy()
    n = len(x)
    regiones = clip_info.get("regiones_muestras", [])
    techo = clip_info.get("techo")
    reparadas = 0
    for s, e in regiones:
        L = e - s
        if L > 400:  # > 8 ms recortados: no hay contexto suficiente, se deja
            continue
        C = max(4 * p, 2 * L)
        a, b = max(0, s - C), min(n, e + C)
        w = y[a:b].copy()
        desc = np.zeros(len(w), dtype=bool)
        desc[s - a : e - a] = True
        cota = np.abs(x[a:b]).astype(np.float64)
        if techo:
            cota[desc] = np.maximum(cota[desc], 0.98 * techo)
        rec = _lsar(w, desc, p, cota)
        # nunca más de +6 dB sobre el techo (protección ante un AR inestable)
        lim = 2.0 * float(np.max(np.abs(x[s:e])))
        y[a:b] = np.clip(rec, -lim, lim)
        reparadas += L
    return y.astype(np.float32), {"muestras_reparadas": int(reparadas), "metodo": f"LSAR p={p}"}


def regiones_clipping(x: np.ndarray, sr: int) -> list[tuple[int, int]]:
    return analisis.regiones_clipping_muestras(x, sr)


# ----------------------------------------------------------------------------
# 1–2. Pasa-altos y zumbido
# ----------------------------------------------------------------------------


def pasa_altos(x: np.ndarray, sr: int, fc: float) -> np.ndarray:
    sos = signal.butter(4, fc, btype="highpass", fs=sr, output="sos")
    return signal.sosfilt(sos, x).astype(np.float32)


def quitar_zumbido(x: np.ndarray, sr: int, f0: float, armonicos: list[int],
                   ancho_hz: float = 1.5, deriva_hz: float = 0.0, ventana_s: float = 4.0) -> tuple[np.ndarray, dict]:
    """Resta del zumbido: se estima cada armónico como un fasor (amplitud y fase) en bloques
    de 10 períodos, solo en los bloques sin voz, con mediana en ±4 s; se sintetiza y se resta.

    Por qué no notches: un notch de 1,5 Hz "suena" ~0,5 s. Con fase cero el sonido aparece
    antes de cada ataque (pre-eco); causal, aparece después de cada frase cuando un armónico
    de la voz pasa por un múltiplo de 50 Hz (medido en voz masculina real: la pausa que sigue
    a la frase subía a −10 dB respecto de la voz). La resta no toca la voz: la voz no está en
    fase con la red."""
    if not armonicos:
        return x, {"metodo": "ninguno"}
    n = len(x)
    B = int(round(10 * sr / f0))  # 10 períodos: los otros armónicos caen en ceros
    nb = n // B
    if nb < 10:
        return x, {"metodo": "ninguno", "motivo": "audio muy corto"}
    X = x[: nb * B].astype(np.float64).reshape(nb, B)
    nivel = dsp.db(np.mean(X ** 2, axis=1))
    piso = float(np.percentile(nivel, 10))
    quietos = nivel < piso + 6.0
    iq = np.flatnonzero(quietos)
    M = max(2, int(round(ventana_s * sr / B)))
    ti = np.arange(B) / sr
    centros = (np.arange(nb) * B + B / 2) / sr
    y = x.astype(np.float64).copy()
    estimados = 0
    for k in armonicos:
        fk = f0 * k
        if fk >= sr / 2 - 100:
            continue
        w = 2 * np.pi * fk
        c = (2.0 / B) * (X @ np.exp(-1j * w * ti)) * np.exp(-1j * w * (np.arange(nb) * B) / sr)
        cs = np.zeros(nb, dtype=np.complex128)
        for b in range(nb):
            lo = np.searchsorted(iq, b - M)
            hi = np.searchsorted(iq, b + M, side="right")
            if hi - lo >= 3:
                sel = c[iq[lo:hi]]
                cs[b] = np.median(sel.real) + 1j * np.median(sel.imag)
        if not np.any(cs):
            continue
        estimados += 1
        # síntesis por tramos (memoria acotada), fasor interpolado entre centros de bloque
        paso = sr * 10
        for a in range(0, n, paso):
            t = np.arange(a, min(n, a + paso)) / sr
            cr = np.interp(t, centros, cs.real)
            ci = np.interp(t, centros, cs.imag)
            y[a : a + len(t)] -= cr * np.cos(w * t) - ci * np.sin(w * t)
    return y.astype(np.float32), {"metodo": "resta de fasores", "armonicos_restados": estimados,
                                   "bloques_sin_voz": int(quietos.sum()), "bloques": int(nb)}


def quitar_zumbido_notch(x: np.ndarray, sr: int, f0: float, armonicos: list[int],
                         ancho_hz: float, deriva_hz: float = 0.0) -> np.ndarray:
    """Versión con notches (no se usa: suena después de cada frase; queda para comparar)."""
    if not armonicos:
        return x
    secs = []
    for k in armonicos:
        f = f0 * k
        if f >= sr / 2 - 100:
            continue
        # la deriva de la red se multiplica en los armónicos
        bw = max(ancho_hz, 0.25 * k, 4.0 * k * deriva_hz)
        secs.append(dsp.notch(f, f / bw, sr))
    sos = np.vstack(secs)
    # Causal a propósito: un notch tan angosto "suena" ~0,5 s. Con filtfilt (fase cero) ese
    # sonido aparece ANTES de cada ataque (pre-eco medido de −37 dBFS a 70 ms del ataque, y
    # Whisper adelantaba las palabras ~100 ms). Causal, queda detrás de la voz y lo tapa la
    # cola de la propia sala. El retardo de fase afecta solo a bandas de ±1 Hz.
    return signal.sosfilt(sos, x).astype(np.float32)


# ----------------------------------------------------------------------------
# 4. De-click y plosivas
# ----------------------------------------------------------------------------


def declick(x: np.ndarray, sr: int, umbral_db: float = 20.0, max_ms: float = 2.0) -> tuple[np.ndarray, dict]:
    """Clics de boca: impulsos de ≤ 2 ms en la banda alta, 20 dB sobre su vecindad.
    Se resta solo la componente > 3 kHz del clic con una ventana suave."""
    sos = signal.butter(4, 3000, btype="highpass", fs=sr, output="sos")
    hp = signal.sosfiltfilt(sos, x.astype(np.float64))
    blk = int(sr * 0.001)
    m = len(x) // blk
    if m < 30:
        return x, {"clics": 0}
    e = np.sqrt(np.mean(hp[: m * blk].reshape(m, blk) ** 2, axis=1) + 1e-20)
    ref = median_filter(e, size=21, mode="nearest")
    piso = np.percentile(e, 20)
    cand = (dsp.db_amp(e / np.maximum(ref, piso)) > umbral_db) & (e > piso * 10)
    # banda media (100–3000 Hz) para saber si el candidato está pegado a una sílaba
    sos_m = signal.butter(2, [100, 3000], btype="bandpass", fs=sr, output="sos")
    xm = signal.sosfiltfilt(sos_m, x.astype(np.float64))
    em = dsp.db_amp(np.sqrt(np.mean(xm[: m * blk].reshape(m, blk) ** 2, axis=1) + 1e-20))
    em_piso, em_alto = np.percentile(em, 15), np.percentile(em, 97)
    umbral_voz = em_piso + max(12.0, 0.3 * (em_alto - em_piso))
    del xm
    ini, lar = dsp.corridas(cand)
    y = x.astype(np.float64).copy()
    n_clics = 0
    descartados = 0
    for i, l in zip(ini, lar):
        if l > max_ms:
            continue
        # Un clic es un impulso: antes y después la banda alta vuelve enseguida al fondo.
        # El ataque de una oclusiva (t, k, p) o de una fricativa sigue con energía: no se toca
        # (en voz real la mayoría de los candidatos eran eso: medido en LibriVox).
        pico = float(e[i : i + l].max())
        despues = float(e[i + l : i + l + 6].mean()) if i + l + 6 <= m else pico
        antes = float(e[max(0, i - 6) : i].mean()) if i > 0 else pico
        if despues > pico * 10 ** (-15 / 20) or antes > pico * 10 ** (-15 / 20):
            descartados += 1
            continue
        # Dentro de la voz, casi todo lo que parece un clic es la explosión de una oclusiva
        # ("p", "t", "k": centroide 0,7–4 kHz, medido en LibriVox). Ahí solo se tocan los clics
        # muy brillantes (centroide ≥ 4,5 kHz, típicos de la boca). En las pausas, todos.
        if em[max(0, i - 2) : min(m, i + l + 2)].max() > umbral_voz:
            a0, b0 = max(0, (i - 1) * blk), min(len(x), (i + l + 1) * blk)
            seg = x[a0:b0].astype(np.float64)
            S = np.abs(np.fft.rfft(seg * np.hanning(len(seg)))) ** 2
            f = np.fft.rfftfreq(len(seg), 1 / sr)
            if float(np.sum(f * S) / (np.sum(S) + 1e-30)) < 4500:
                descartados += 1
                continue
        a = max(0, (i - 1) * blk)
        b = min(len(x), (i + l + 1) * blk)
        w = signal.windows.tukey(b - a, alpha=0.5)
        y[a:b] -= hp[a:b] * w
        n_clics += 1
    return y.astype(np.float32), {"clics": n_clics, "candidatos_descartados": descartados}


def plosivas(x: np.ndarray, sr: int, max_red_db: float = 12.0) -> tuple[np.ndarray, dict]:
    """Golpes de aire (p, b): ráfagas < 150 Hz que dominan el espectro. Se atenúa solo esa
    banda, dinámicamente (compresor de graves que actúa nada más que en el golpe)."""
    sos = signal.butter(4, 150, btype="lowpass", fs=sr, output="sos")
    lp = signal.sosfiltfilt(sos, x.astype(np.float64))
    hp = x.astype(np.float64) - lp
    hop = int(sr * 0.001)
    _, p_lp = dsp.potencia_centrada(lp, sr, 0.008, hop)
    _, p_all = dsp.potencia_centrada(x, sr, 0.008, hop)
    _, p_hp = dsp.potencia_centrada(hp, sr, 0.008, hop)
    L_lp = dsp.db(p_lp)
    act = L_lp > np.percentile(L_lp, 50)
    ref = np.percentile(L_lp[act], 90) if np.any(act) else np.max(L_lp)
    dominio = dsp.db(p_lp / np.maximum(p_hp, 1e-20))  # graves sobre el resto
    exceso = np.where((dominio > 6.0) & (L_lp > ref), np.minimum(L_lp - ref + 6.0, max_red_db), 0.0)
    golpes = int(np.sum(np.diff(np.concatenate([[0], (exceso > 0).astype(int)])) == 1))
    if golpes == 0:
        return x, {"golpes": 0}
    g_db = dsp.suavizar_ganancia(-exceso, 0.001, 0.04, sr / hop)
    g = dsp.a_tasa_audio(10 ** (g_db / 20), hop, len(x))
    y = hp + lp * g
    return y.astype(np.float32), {"golpes": golpes, "max_reduccion_db": round(float(-g_db.min()), 1)}


# ----------------------------------------------------------------------------
# 5. De-esser dinámico
# ----------------------------------------------------------------------------


def deesser(x: np.ndarray, sr: int, banda=(5000.0, 9000.0), max_db: float = 6.0,
            ratio: float = 3.0, percentil: float = 75.0) -> tuple[np.ndarray, dict]:
    """Compresor solo de la banda 5–9 kHz, solo en cuadros sibilantes (la banda tiene casi
    toda la energía) y solo por encima del percentil `percentil` de esas sibilantes."""
    hi = min(banda[1], sr / 2 * 0.95)
    sos = signal.butter(3, [banda[0], hi], btype="bandpass", fs=sr, output="sos")
    b = signal.sosfiltfilt(sos, x.astype(np.float64))
    resto = x.astype(np.float64) - b
    hop = int(sr * 0.001)
    _, pb = dsp.potencia_centrada(b, sr, 0.005, hop)
    _, pt = dsp.potencia_centrada(x, sr, 0.005, hop)
    Lb = dsp.db(pb)
    rel = Lb - dsp.db(pt)  # cuánto de la energía está en la banda sibilante
    sib = rel > -6.0  # espectro de "s"/"sh"/"z"
    activos = Lb > np.percentile(Lb, 60)
    cand = sib & activos
    if cand.sum() < 20:
        return x, {"activo": False, "motivo": "pocas sibilantes"}
    umbral = float(np.percentile(Lb[cand], percentil))  # solo las sibilantes más fuertes
    exceso = np.where(cand, np.maximum(Lb - umbral, 0.0), 0.0)
    red = np.minimum(exceso * (1 - 1 / ratio), max_db)
    g_db = dsp.suavizar_ganancia(-red, 0.001, 0.05, sr / hop)
    g = dsp.a_tasa_audio(10 ** (g_db / 20), hop, len(x))
    y = resto + b * g
    return y.astype(np.float32), {
        "activo": True,
        "percentil": percentil,
        "umbral_banda_dbfs": round(umbral, 1),
        "reduccion_max_db": round(float(-g_db.min()), 1),
        "porcentaje_tiempo_actuando": round(100 * float(np.mean(g_db < -1.0)), 2),
    }


# ----------------------------------------------------------------------------
# 6. EQ correctiva
# ----------------------------------------------------------------------------


def plan_eq(esp: dict, cfg: dict) -> list[dict]:
    filtros = []
    exceso = esp["barro_200_400_db"] - analisis.REF_BARRO
    if exceso > 2.0:
        g = -min(cfg["eq_max_barro_db"], 1.0 + 0.5 * (exceso - 2.0))
        filtros.append({"tipo": "peaking", "f_hz": 300.0, "q": 1.0, "ganancia_db": round(g, 1),
                        "motivo": f"barro +{exceso:.1f} dB sobre la referencia"})
    dif_pres = esp["presencia_2k5_5k_db"] - analisis.REF_PRESENCIA
    if dif_pres < 3.0:  # no realzar una voz que ya es brillante
        g = cfg["eq_presencia_db"] + (min(1.0, 0.25 * (-dif_pres - 2.0)) if dif_pres < -2.0 else 0.0)
        filtros.append({"tipo": "peaking", "f_hz": 3800.0, "q": 0.9, "ganancia_db": round(g, 1),
                        "motivo": f"presencia {dif_pres:+.1f} dB vs referencia"})
    ancho = esp.get("ancho_banda_util_hz") or 0
    dif_aire = esp["aire_10k_12k5_db"] - analisis.REF_AIRE
    if ancho >= 12500 and dif_aire < 3.0:
        filtros.append({"tipo": "high_shelf", "f_hz": 10000.0, "ganancia_db": cfg["eq_aire_db"],
                        "motivo": f"aire {dif_aire:+.1f} dB vs referencia"})
    return filtros


def aplicar_eq(x: np.ndarray, sr: int, filtros: list[dict]) -> np.ndarray:
    if not filtros:
        return x
    secs = []
    for f in filtros:
        if f["tipo"] == "peaking":
            secs.append(dsp.peaking(f["f_hz"], f["q"], f["ganancia_db"], sr))
        elif f["tipo"] == "high_shelf":
            secs.append(dsp.high_shelf(f["f_hz"], f["ganancia_db"], sr))
        elif f["tipo"] == "low_shelf":
            secs.append(dsp.low_shelf(f["f_hz"], f["ganancia_db"], sr))
    return signal.sosfilt(np.vstack(secs), x).astype(np.float32)


# ----------------------------------------------------------------------------
# 7. Compresión: nivelador lento + compresor moderado
# ----------------------------------------------------------------------------


def nivelador(x: np.ndarray, sr: int, max_db: float = 6.0, tau_s: float = 1.0) -> tuple[np.ndarray, dict]:
    """Empareja frases que quedaron más bajas/altas (el youtuber se aleja del teléfono).
    Corrige el 60 % de la diferencia con la mediana, ±max_db, y se congela en las pausas."""
    hop = int(sr * 0.01)
    _, p = dsp.potencia_centrada(x, sr, 0.4, hop)
    L = dsp.db(p)
    act = analisis.actividad(x, sr)
    umbral = act["umbral"]
    voz = L > umbral + 3
    if voz.sum() < 100:
        return x, {"activo": False}
    objetivo = float(np.median(L[voz]))
    corr = np.clip((objetivo - L) * 0.6, -max_db, max_db)
    g = np.empty_like(corr)
    c = math.exp(-1.0 / (tau_s * 100))
    gi = 0.0
    for i in range(len(corr)):
        if voz[i]:
            gi = c * gi + (1 - c) * corr[i]
        g[i] = gi
    gg = dsp.a_tasa_audio(10 ** (g / 20), hop, len(x))
    return (x * gg).astype(np.float32), {"activo": True, "rango_db": [round(float(g.min()), 1),
                                                                     round(float(g.max()), 1)]}


def compresor(x: np.ndarray, sr: int, ratio: float = 2.5, ataque_ms: float = 5.0,
              liberacion_ms: float = 90.0, max_db: float = 9.0, rodilla_db: float = 6.0,
              percentil: float = 70.0) -> tuple[np.ndarray, dict]:
    hop = int(sr * 0.001)
    _, p = dsp.potencia_centrada(x, sr, 0.010, hop)
    L = dsp.db(p)
    act = analisis.actividad(x, sr)
    voz = L > act["umbral"]
    if voz.sum() < 100:
        return x, {"activo": False}
    T = float(np.percentile(L[voz], percentil))
    over = L - T
    gr = np.where(over <= -rodilla_db / 2, 0.0,
                  np.where(over >= rodilla_db / 2, over * (1 - 1 / ratio),
                           (1 - 1 / ratio) * (over + rodilla_db / 2) ** 2 / (2 * rodilla_db)))
    gr = np.minimum(gr, max_db)
    g_db = dsp.suavizar_ganancia(-gr, ataque_ms / 1000, liberacion_ms / 1000, sr / hop)
    g = dsp.a_tasa_audio(10 ** (g_db / 20), hop, len(x))
    gv = g_db[voz]
    return (x * g).astype(np.float32), {
        "activo": True, "umbral_dbfs": round(T, 1), "ratio": ratio,
        "reduccion_media_en_voz_db": round(float(-gv.mean()), 2),
        "reduccion_p95_db": round(float(-np.percentile(gv, 5)), 2),
    }


# ----------------------------------------------------------------------------
# 8. Normalización (dos pasadas) + limitador de pico verdadero
# ----------------------------------------------------------------------------


def limitador_tp(x: np.ndarray, sr: int, techo_db: float, anticipo_ms: float = 2.0,
                 liberacion_ms: float = 60.0) -> np.ndarray:
    hop = int(sr * 0.001)
    env = dsp.envolvente_pico_os(x, hop)
    techo = 10 ** (techo_db / 20)
    req = dsp.db_amp(np.minimum(1.0, techo / np.maximum(env, 1e-9)))
    if req.min() >= -0.01:
        return x
    la = max(1, int(math.ceil(anticipo_ms / 1000 * sr / hop)))
    req = dsp.minimo_movil(req, 2 * la + 1)
    g_db = dsp.suavizar_ganancia(req, anticipo_ms / 3000, liberacion_ms / 1000, sr / hop)
    g_db = np.minimum(g_db, req)
    g_db = dsp.minimo_movil(g_db, 3)
    g = dsp.a_tasa_audio(10 ** (g_db / 20), hop, len(x))
    return (x * g).astype(np.float32)


def normalizar(x: np.ndarray, sr: int, lufs: float = -16.0, tp: float = -1.5) -> tuple[np.ndarray, dict]:
    """Dos pasadas: (1) medir el loudness integrado; (2) aplicar la ganancia y el limitador
    de pico verdadero. Como el limitador baja un poco el loudness, se re-mide y se corrige la
    ganancia (partiendo siempre de la señal sin limitar) hasta quedar a ±0,1 LU."""
    x = x.astype(np.float32)
    techo = 10 ** (tp / 20)
    L0 = analisis.loudness(x, sr)
    g = lufs - L0
    medidas = []
    y = x
    for it in range(4):
        y = (x * 10 ** (g / 20)).astype(np.float32)
        y = limitador_tp(y, sr, tp - 0.15)
        L = analisis.loudness(y, sr)
        medidas.append({"pasada": it + 1, "ganancia_db": round(g, 2), "lufs_resultante": round(L, 2)})
        if abs(L - lufs) <= 0.1:
            break
        g += lufs - L
    pk = dsp.true_peak(y)
    if pk > techo:  # seguridad final
        y = limitador_tp(y, sr, tp - 0.3)
        pk = dsp.true_peak(y)
    return y, {"lufs_medido_original": round(L0, 2), "pasadas": medidas,
               "lufs_final": round(analisis.loudness(y, sr), 2),
               "tp_final_dbtp": round(float(dsp.db_amp(pk)), 2)}


def ajustar_loudness_final(x: np.ndarray, sr: int, lufs: float = -16.0, tp: float = -1.5,
                           tolerancia: float = 0.15) -> tuple[np.ndarray, dict]:
    """Retoque tras los cortes: los silencios casi no pesan en LUFS (compuerta), así que
    alcanza con una ganancia chica y, si hace falta, el mismo limitador."""
    L = analisis.loudness(x, sr)
    if abs(L - lufs) <= tolerancia and dsp.true_peak(x) <= 10 ** (tp / 20):
        return x, {"ajuste_db": 0.0, "lufs": round(L, 2),
                   "tp_dbtp": round(float(dsp.db_amp(dsp.true_peak(x))), 2)}
    y, info = normalizar(x, sr, lufs, tp)
    info["ajuste_db"] = round(lufs - L, 2)
    return y, info


# ----------------------------------------------------------------------------
# Cadena completa
# ----------------------------------------------------------------------------


def atenuacion_por_snr(snr_db: float) -> float:
    if snr_db >= 45:
        return 12.0
    if snr_db >= 30:
        return 15.0
    return 18.0


def limpiar(x: np.ndarray, sr: int, an: dict, cfg: dict | None = None,
            crono: util.Cronometro | None = None, hilos: int = 2, modelos=None) -> tuple[np.ndarray, dict]:
    cfg = {**DEFAULTS, **(cfg or {})}
    crono = crono or util.Cronometro(len(x) / sr)
    pasos: dict = {}
    y = x.astype(np.float32)

    with crono.etapa("limpieza 0: DC y de-clip"):
        dc = float(np.mean(y))
        y = (y - dc).astype(np.float32)
        pasos["dc"] = {"restado": round(dc, 6)}
        if an["clipping"]["hay"]:
            info_c, regs = analisis._clipping(y, sr)
            y, info = declip(y, sr, {"regiones_muestras": regs, "techo": info_c.get("techo_estimado")})
            pasos["declip"] = {"aplicado": True, "regiones": len(regs), **info}
        else:
            pasos["declip"] = {"aplicado": False}

    with crono.etapa("limpieza 1: pasa-altos"):
        y = pasa_altos(y, sr, cfg["pasa_altos_hz"])
        pasos["pasa_altos"] = {"fc_hz": cfg["pasa_altos_hz"], "orden": 4}

    with crono.etapa("limpieza 2: zumbido"):
        z = an.get("zumbido", {})
        if z.get("hay"):
            arm = z["armonicos_a_filtrar"]
            y, info = quitar_zumbido(y, sr, z["f0_estimada_hz"], arm)
            pasos["zumbido"] = {"aplicado": True, "f0_hz": z["f0_estimada_hz"], "armonicos": arm,
                                "deriva_hz": z.get("deriva_hz", 0.0), **info}
        else:
            pasos["zumbido"] = {"aplicado": False}

    with crono.etapa("limpieza 3: reducción de ruido"):
        # Los clics se detectan y reparan ANTES de la red: DeepFilterNet los conserva pero los
        # desparrama ~20 ms (su ventana STFT) y después ya no se pueden aislar. Medido en el
        # fixture: clic tras DFN→declick queda ~10 dB sobre el fondo; con declick→DFN, < 3 dB.
        y, ic = declick(y, sr)
        pasos["declick"] = ic
        aten = cfg["ruido_atenuacion_db"] or atenuacion_por_snr(an["ruido"]["snr_estimada_db"])
        y, info = ruido.reducir_ruido(y, sr, cfg["ruido_backend"], aten, hilos, modelos)
        pasos["ruido"] = info

    with crono.etapa("limpieza 4: clics residuales y plosivas"):
        y, ic2 = declick(y, sr)
        y, ip = plosivas(y, sr)
        pasos["declick"]["clics_residuales"] = ic2["clics"]
        pasos["plosivas"] = ip

    with crono.etapa("limpieza 5: de-esser"):
        # más sibilante que la voz de referencia → actúa sobre más "eses"; menos → casi nada
        exceso = an.get("espectro", {}).get("sibilancia_5k_8k_db", analisis.REF_SIBILANCIA) \
            - analisis.REF_SIBILANCIA
        pct = 60.0 if exceso >= 3 else 75.0 if exceso >= 0 else 90.0
        y, info = deesser(y, sr, cfg["deesser_banda"], cfg["deesser_max_db"], percentil=pct)
        info["sibilancia_vs_referencia_db"] = round(exceso, 1)
        pasos["deesser"] = info

    with crono.etapa("limpieza 6: EQ"):
        act = analisis.actividad(y, sr)
        esp = analisis.espectro_largo(y, sr, act)
        filtros = plan_eq(esp, cfg)
        y = aplicar_eq(y, sr, filtros)
        pasos["eq"] = {"filtros": filtros,
                       "medido": {k: esp[k] for k in ("barro_200_400_db", "presencia_2k5_5k_db",
                                                      "sibilancia_5k_8k_db", "aire_10k_12k5_db",
                                                      "ancho_banda_util_hz")}}

    with crono.etapa("limpieza 7: compresión"):
        y, iniv = nivelador(y, sr, cfg["nivelador_max_db"])
        y, icomp = compresor(y, sr, cfg["comp_ratio"], cfg["comp_ataque_ms"],
                             cfg["comp_liberacion_ms"], cfg["comp_max_db"])
        pasos["nivelador"] = iniv
        pasos["compresor"] = icomp

    with crono.etapa("limpieza 8: normalización"):
        y, info = normalizar(y, sr, cfg["lufs"], cfg["true_peak"])
        pasos["normalizacion"] = info

    return y, pasos
