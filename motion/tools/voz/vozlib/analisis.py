"""Análisis del audio: piso de ruido, LUFS, picos/clipping, DC, zumbido, espectro y reverb."""

from __future__ import annotations

import numpy as np
import pyloudnorm
from scipy import signal

from . import dsp

# Diferencias de referencia de un espectro de voz "sano" (LTASS, Byrne et al. 1994),
# en dB respecto del promedio 1–2 kHz, medidas en bandas de 1/3 de octava.
REF_BARRO = 9.0  # (200–400 Hz) − (1–2 kHz)
REF_PRESENCIA = -5.5  # (2,5–5 kHz) − (1–2 kHz)
REF_AIRE = -13.0  # (10–14 kHz) − (1–2 kHz)
REF_SIBILANCIA = -9.0  # (5–9 kHz) − (1–2 kHz)


def actividad(x: np.ndarray, sr: int, win_s: float = 0.02, hop_s: float = 0.01) -> dict:
    """Cuadros de 20 ms: nivel en dB, piso de ruido, nivel de voz y máscara de voz."""
    t, pot = dsp.rms_frames(x, sr, win_s, hop_s)
    L = dsp.db(pot)
    L = np.maximum(L, -120.0)
    piso = float(np.percentile(L, 10))
    voz = float(np.percentile(L, 95))
    rango = max(voz - piso, 1.0)
    umbral = piso + max(8.0, 0.35 * rango)
    return {"t": t, "db": L, "piso": piso, "voz": voz, "umbral": umbral, "mask": L > umbral,
            "hop_s": hop_s}


def detectar_clipping(x: np.ndarray, sr: int) -> dict:
    return _clipping(x, sr)[0]


def regiones_clipping_muestras(x: np.ndarray, sr: int) -> list[tuple[int, int]]:
    """Todas las regiones recortadas, en muestras exactas [inicio, fin)."""
    return _clipping(x, sr)[1]


def _clipping(x: np.ndarray, sr: int) -> tuple[dict, list[tuple[int, int]]]:
    a = np.abs(x)
    pk = float(a.max()) if len(a) else 0.0
    res = {"pico_muestra": pk, "pico_dbfs": float(dsp.db_amp(pk)), "hay": False,
           "regiones": [], "muestras_afectadas": 0}
    if pk < 0.1:
        return res, []
    regiones = []
    # 1) mesetas exactas (PCM recortado): muestras consecutivas iguales cerca del pico
    cerca = a >= 0.9 * pk
    iguales = np.concatenate([[False], np.abs(np.diff(x)) < 1e-7]) & cerca
    ini, lar = dsp.corridas(iguales)
    for i, l in zip(ini, lar):
        if l >= 2:
            regiones.append((int(i) - 1, int(i + l)))
    # 2) Tras el AAC la meseta queda ondulada (y ~5 % más baja) y ya no hay muestras iguales,
    #    pero el histograma de amplitudes delata el techo: en la voz sana la cantidad de
    #    muestras baja siempre hacia el pico (cociente ≤ 0,4 medido); con recorte aparece una
    #    joroba cerca del techo (cociente 1,2–76 medido, PCM y AAC).
    alto = a[a > 0.6 * pk]
    if len(alto) >= 200:
        h, ed = np.histogram(alto, bins=80, range=(0.6 * pk, pk))
        c = (ed[:-1] + ed[1:]) / 2
        bajo = float(h[c < 0.75 * pk].mean()) if np.any(c < 0.75 * pk) else 0.0
        sel = c >= 0.84 * pk
        k = int(np.argmax(h[sel]))
        cociente = float(h[sel][k]) / max(bajo, 1.0)
        techo = float(c[sel][k])
        res["joroba_histograma"] = round(cociente, 2)
        if cociente >= 1.0 and h[sel][k] >= 30:
            res["techo_estimado"] = round(techo, 4)
            ini, lar = dsp.corridas(a >= 0.94 * techo)
            for i, l in zip(ini, lar):
                if l >= 3:
                    regiones.append((int(i), int(i + l)))
    if not regiones:
        return res, []
    regiones.sort()
    fusion = [list(regiones[0])]
    for s, e in regiones[1:]:
        if s <= fusion[-1][1] + 8:
            fusion[-1][1] = max(fusion[-1][1], e)
        else:
            fusion.append([s, e])
    afectadas = int(sum(e - s for s, e in fusion))
    res.update({
        "hay": afectadas >= 3,
        "muestras_afectadas": afectadas,
        "n_regiones": len(fusion),
        "regiones": [{"inicio_s": round(s / sr, 5), "fin_s": round(e / sr, 5), "muestras": e - s}
                     for s, e in fusion[:20]],
    })
    return res, [(int(s), int(e)) for s, e in fusion]


def picos_principales(x: np.ndarray, sr: int, n: int = 5) -> list:
    hop = int(0.01 * sr)
    m = len(x) // hop
    if m == 0:
        return []
    blk = np.abs(x[: m * hop]).reshape(m, hop).max(axis=1)
    orden = np.argsort(blk)[::-1]
    elegidos = []
    for k in orden:
        if all(abs(k - j) > 50 for j in elegidos):
            elegidos.append(int(k))
        if len(elegidos) >= n:
            break
    return [{"t_s": round(k * hop / sr, 3), "dbfs": round(float(dsp.db_amp(blk[k])), 2)}
            for k in elegidos]


def detectar_zumbido(x: np.ndarray, sr: int) -> dict:
    """Busca 50/60 Hz y armónicos con un Welch de alta resolución promediado por mediana
    (la mediana descarta la voz, que no es estacionaria, y deja el zumbido)."""
    fs = 8000
    y = signal.resample_poly(x.astype(np.float64), 1, sr // fs) if sr % fs == 0 else \
        dsp.resample(x, sr, fs).astype(np.float64)
    nper = 16384
    if len(y) < nper * 2:
        nper = max(2048, 2 ** int(np.log2(max(len(y) // 2, 2048))))
    f, P = signal.welch(y, fs=fs, nperseg=nper, noverlap=nper // 2, window="hann",
                        average="median", detrend=False)
    df = f[1] - f[0]
    mejor = None
    for base in (50.0, 60.0):
        arm = []
        for k in range(1, 21):
            fk = base * k
            if fk > fs / 2 - 30:
                break
            sel = (f >= fk - 1.6) & (f <= fk + 1.6)
            if not np.any(sel):
                continue
            ip = np.flatnonzero(sel)[np.argmax(P[sel])]
            vec = ((f >= fk - 15) & (f <= fk - 4)) | ((f >= fk + 4) & (f <= fk + 15))
            ref = float(np.median(P[vec]))
            prom = float(dsp.db(P[ip] / max(ref, 1e-30)))
            pot = max(float(np.sum(P[max(ip - 3, 0) : ip + 4]) - 7 * ref) * df, 1e-20)
            # interpolación parabólica de la frecuencia del pico
            if 0 < ip < len(P) - 1:
                a_, b_, c_ = np.log(P[ip - 1] + 1e-30), np.log(P[ip] + 1e-30), np.log(P[ip + 1] + 1e-30)
                den = a_ - 2 * b_ + c_
                delta = 0.5 * (a_ - c_) / den if den != 0 else 0.0
            else:
                delta = 0.0
            arm.append({"k": k, "f_hz": round(float(f[ip] + delta * df), 2),
                        "prominencia_db": round(prom, 1),
                        "nivel_dbfs": round(float(dsp.db(pot / 0.5)), 1)})
        score = sum(max(0.0, a["prominencia_db"] - 6.0) for a in arm)
        if mejor is None or score > mejor[0]:
            mejor = (score, base, arm)
    score, base, arm = mejor
    fuertes = [a for a in arm if a["prominencia_db"] >= 8.0]
    hay = any(a["prominencia_db"] >= 12.0 for a in arm[:4]) or len(fuertes) >= 2
    f0 = base
    if fuertes:
        pesos = np.array([a["prominencia_db"] for a in fuertes])
        f0 = float(np.average([a["f_hz"] / a["k"] for a in fuertes], weights=pesos))
    deriva = 0.0
    if hay:
        # Un notch de 1,5 Hz necesita la frecuencia exacta: 0,03 Hz de error deja pasar el
        # zumbido 30 dB más fuerte. Se refina con la suma coherente de los armónicos.
        ks = [a["k"] for a in fuertes][:6] or [1, 2, 3]
        f0, deriva = _refinar_f0(y, fs, f0, ks)
    # Un notch de 1,5 Hz no se oye. Si hay zumbido se filtran todos los armónicos hasta 1 kHz
    # (los que hoy quedan bajo el ruido aparecen después de la reducción de ruido) y los
    # superiores que se vean claramente (≥ 6 dB).
    filtrar = []
    if hay:
        filtrar = [a["k"] for a in arm if a["k"] * f0 <= 1000.0 or a["prominencia_db"] >= 6.0]
    return {
        "hay": bool(hay),
        "base_hz": base,
        "f0_estimada_hz": round(f0, 4),
        "deriva_hz": round(deriva, 4),
        "puntaje": round(score, 1),
        "armonicos": arm,
        "armonicos_a_filtrar": filtrar,
    }


def _refinar_f0(y: np.ndarray, fs: int, f0c: float, ks: list[int]) -> tuple[float, float]:
    """f0 exacta de la red: cada armónico se baja a banda base (mezcla compleja + promedio en
    bloques de 1/f0 s, cuyos ceros caen justo sobre los otros armónicos) y se busca el
    corrimiento δ que maximiza la potencia coherente Σ_k |Σ_n z_k[n]·e^{−j2πkδt_n}|².
    También estima la deriva (desvío de f0 entre ventanas de 60 s) para ensanchar notches."""
    n = len(y)
    t = np.arange(n) / fs
    blk = max(1, int(round(10 * fs / f0c)))  # 10 períodos (0,2 s): ceros cada 5 Hz
    nb = n // blk
    if nb < 50:
        return f0c, 0.0
    zs = []
    for k in ks:
        z = (y[: nb * blk] * np.exp(-2j * np.pi * k * f0c * t[: nb * blk])).reshape(nb, blk).mean(axis=1)
        zs.append((k, z))
    tb = (np.arange(nb) * blk + blk / 2) / fs

    def mejor_delta(sel, grilla):
        pot = np.zeros(len(grilla))
        for k, z in zs:
            rot = np.exp(-2j * np.pi * k * np.outer(grilla, tb[sel]))
            pot += np.abs(rot @ z[sel]) ** 2
        return float(grilla[int(np.argmax(pot))])

    todo = slice(None)
    d1 = mejor_delta(todo, np.linspace(-0.3, 0.3, 121))
    d2 = mejor_delta(todo, np.linspace(d1 - 0.006, d1 + 0.006, 25))
    f0 = f0c + d2
    # deriva: misma búsqueda por ventanas de 60 s
    porv = max(10, int(60 * fs / blk))
    locales = []
    for a in range(0, nb - porv // 2, porv):
        sel = slice(a, min(nb, a + porv))
        locales.append(mejor_delta(sel, np.linspace(d2 - 0.15, d2 + 0.15, 61)))
    deriva = float(np.std(locales)) if len(locales) >= 2 else 0.0
    return float(f0), deriva


def espectro_largo(x: np.ndarray, sr: int, act: dict) -> dict:
    """Espectro promedio (voz y ruido por separado) en tercios de octava."""
    nper = 4096
    hop = 2048
    acum_voz = np.zeros(nper // 2 + 1)
    acum_ruido = np.zeros(nper // 2 + 1)
    nv = nr = 0
    bloque = sr * 60
    f = np.fft.rfftfreq(nper, 1 / sr)
    win = signal.get_window("hann", nper)
    for a in range(0, max(len(x) - nper, 1), bloque):
        seg = x[a : a + bloque + nper].astype(np.float64)
        if len(seg) < nper:
            break
        _, tt, S = signal.stft(seg, fs=sr, window=win, nperseg=nper, noverlap=nper - hop,
                               boundary=None, padded=False)
        Pw = np.abs(S) ** 2
        tabs = a / sr + tt
        idx = np.clip(np.searchsorted(act["t"], tabs), 0, len(act["t"]) - 1)
        Lf = act["db"][idx]
        mv = Lf > act["umbral"] + 3
        mr = Lf < act["piso"] + 3
        if np.any(mv):
            acum_voz += Pw[:, mv].sum(axis=1)
            nv += int(mv.sum())
        if np.any(mr):
            acum_ruido += Pw[:, mr].sum(axis=1)
            nr += int(mr.sum())
    pv = acum_voz / max(nv, 1)
    pr = acum_ruido / max(nr, 1)
    bv = dsp.bandas_tercio(f, pv)
    br = dsp.bandas_tercio(f, pr)
    cent = dsp.TERCIOS

    def prom(lo, hi, b):
        sel = (cent >= lo) & (cent <= hi)
        return float(np.mean(b[sel]))

    ref = prom(1000, 2000, bv)
    barro = prom(200, 400, bv) - ref
    presencia = prom(2500, 5000, bv) - ref
    sibil = prom(5000, 8000, bv) - ref
    aire = prom(10000, 12500, bv) - ref
    # ancho de banda efectivo: última banda con voz 10 dB sobre el ruido y no muy por debajo
    snr_b = bv - br
    util = (snr_b > 10) & (bv > bv.max() - 60)
    ancho = float(cent[np.flatnonzero(util)[-1]]) if np.any(util) else float("nan")
    return {
        "bandas_hz": cent.tolist(),
        "voz_db": np.round(bv - ref, 1).tolist(),
        "ruido_db": np.round(br - ref, 1).tolist(),
        "snr_por_banda_db": np.round(snr_b, 1).tolist(),
        "barro_200_400_db": round(barro, 1),
        "presencia_2k5_5k_db": round(presencia, 1),
        "sibilancia_5k_8k_db": round(sibil, 1),
        "aire_10k_12k5_db": round(aire, 1),
        "referencia_ltass": {"barro": REF_BARRO, "presencia": REF_PRESENCIA,
                              "sibilancia": REF_SIBILANCIA, "aire": REF_AIRE},
        "ancho_banda_util_hz": ancho,
        "cuadros_voz": nv,
        "cuadros_ruido": nr,
    }


def estimar_reverb(x: np.ndarray, sr: int, act: dict) -> dict:
    """RT60 aparente a partir de las caídas libres de energía al final de las frases.

    Se toma el percentil 20 de las caídas medidas (las más rápidas): una caída de voz nunca
    es más rápida que la de la sala, así que las más rápidas acotan el RT60 de la sala.
    """
    hop_s = 0.005
    t, pot = dsp.rms_frames(x, sr, 0.01, hop_s)
    L = dsp.db(pot)
    piso = float(np.percentile(L, 10))
    voz = float(np.percentile(L, 95))
    rt = []
    i = 1
    n = len(L)
    maxlen = int(0.8 / hop_s)
    while i < n - 2:
        if L[i] >= voz - 12 and L[i] >= L[i - 1] and L[i] >= L[i + 1]:
            ini_lvl = L[i]
            minimo = ini_lvl
            j = i + 1
            while j < min(n, i + maxlen):
                if L[j] > minimo + 3.0:  # nuevo ataque: la caída se interrumpe
                    break
                minimo = min(minimo, L[j])
                if L[j] <= piso + 4:
                    break
                j += 1
            caida = ini_lvl - minimo
            if caida >= 20 and (j - i) >= 6:
                seg = L[i:j]
                tseg = np.arange(len(seg)) * hop_s
                a_ = ini_lvl - 5
                b_ = max(ini_lvl - 25, piso + 6)
                sel = (seg <= a_) & (seg >= b_)
                if sel.sum() >= 4:
                    pend, _ = np.polyfit(tseg[sel], seg[sel], 1)
                    if pend < -1:
                        rt.append(-60.0 / pend)
            i = max(j, i + 1)
        else:
            i += 1
    if len(rt) < 3:
        return {"rt60_aparente_s": None, "n_caidas": len(rt), "clase": "indeterminada"}
    rt = np.array(rt)
    est = float(np.percentile(rt, 20))
    clase = "seca" if est < 0.25 else ("algo de sala" if est < 0.5 else "reverberante")
    return {
        "rt60_aparente_s": round(est, 3),
        "rt60_mediana_caidas_s": round(float(np.median(rt)), 3),
        "n_caidas": int(len(rt)),
        "clase": clase,
    }


_K48 = (np.array([[1.53512485958697, -2.69169618940638, 1.19839281085285,
                    1.0, -1.69065929318241, 0.73248077421585],
                   [1.0, -2.0, 1.0, 1.0, -1.99004745483398, 0.99007225036621]]))


def loudness(x: np.ndarray, sr: int) -> float:
    """Loudness integrado ITU-R BS.1770-4 (compuerta absoluta −70 LUFS y relativa −10 LU).
    A 48 kHz se calcula vectorizado (≈ 10× más rápido que pyloudnorm, mismo resultado);
    a otras frecuencias se usa pyloudnorm."""
    if sr != 48000:
        meter = pyloudnorm.Meter(sr)
        with np.errstate(divide="ignore"):
            return float(meter.integrated_loudness(x.astype(np.float64)))
    y = signal.sosfilt(_K48, x.astype(np.float64))
    c = np.concatenate([[0.0], np.cumsum(y * y)])
    blk, paso = int(0.4 * sr), int(0.1 * sr)
    if len(y) < blk:
        return float("-inf")
    ini = np.arange(0, len(y) - blk + 1, paso)
    z = (c[ini + blk] - c[ini]) / blk
    with np.errstate(divide="ignore"):
        lb = -0.691 + 10 * np.log10(z)
    z1 = z[lb > -70.0]
    if not len(z1):
        return float("-inf")
    gr = -0.691 + 10 * np.log10(np.mean(z1)) - 10.0
    z2 = z[lb > max(gr, -70.0)]
    return float(-0.691 + 10 * np.log10(np.mean(z2))) if len(z2) else float("-inf")


def analizar(x: np.ndarray, sr: int, completo: bool = True) -> dict:
    dur = len(x) / sr
    act = actividad(x, sr)
    lufs = loudness(x, sr)
    tp = dsp.true_peak(x)
    dc = float(np.mean(x))
    rms = float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))
    res = {
        "duracion_s": round(dur, 3),
        "nivel": {
            "lufs_integrado": round(lufs, 2),
            "rms_dbfs": round(float(dsp.db_amp(rms)), 2),
            "true_peak_dbtp": round(float(dsp.db_amp(tp)), 2),
            "pico_muestra_dbfs": round(float(dsp.db_amp(np.max(np.abs(x)))), 2),
            "picos_principales": picos_principales(x, sr),
        },
        "ruido": {
            "piso_ruido_dbfs": round(act["piso"], 1),
            "nivel_voz_dbfs": round(act["voz"], 1),
            "snr_estimada_db": round(act["voz"] - act["piso"], 1),
            "porcentaje_voz": round(100 * float(np.mean(act["mask"])), 1),
        },
        "dc": {"offset": round(dc, 6), "offset_db_rel_rms": round(float(dsp.db_amp(dc / max(rms, 1e-9))), 1),
               "relevante": abs(dc) > 0.002},
        "clipping": detectar_clipping(x, sr),
    }
    if completo:
        res["zumbido"] = detectar_zumbido(x, sr)
        res["espectro"] = espectro_largo(x, sr, act)
        res["reverb"] = estimar_reverb(x, sr, act)
    return res


def resumen_corto(an: dict) -> str:
    z = an.get("zumbido", {})
    rv = an.get("reverb", {})
    partes = [
        f"{an['nivel']['lufs_integrado']:.1f} LUFS",
        f"TP {an['nivel']['true_peak_dbtp']:.1f} dBTP",
        f"piso {an['ruido']['piso_ruido_dbfs']:.0f} dBFS",
        f"SNR≈{an['ruido']['snr_estimada_db']:.0f} dB",
        "clipping" if an["clipping"]["hay"] else "sin clipping",
    ]
    if z:
        partes.append(f"zumbido {z['base_hz']:.0f} Hz" if z.get("hay") else "sin zumbido")
    if rv and rv.get("rt60_aparente_s"):
        partes.append(f"RT60≈{rv['rt60_aparente_s']:.2f} s ({rv['clase']})")
    return ", ".join(partes)
