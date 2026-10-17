"""QA sin oídos: integridad, loudness, balance espectral, clicks e imágenes."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pyloudnorm as pyln
from scipy.signal import welch, stft, sosfilt

from .nucleo import SR, nombre_nota, hz_a_midi
from .efectos import pico_real, biquad
from .secuencia import STEMS

BANDAS = [("sub", 20, 60), ("graves", 60, 200), ("barro", 200, 400), ("medios_bajos", 400, 1000),
          ("medios", 1000, 2000), ("presencia", 2000, 5000), ("brillo", 5000, 10000),
          ("aire", 10000, 20000)]


# Ponderación K de BS.1770 a 48 kHz (coeficientes del estándar)
_K_SOS = np.array([[1.53512485958697, -2.69169618940638, 1.19839281085285,
                    1.0, -1.69065929318241, 0.73248077421585],
                   [1.0, -2.0, 1.0, 1.0, -1.99004745483398, 0.99007225036621]])


def _potencia_k(x: np.ndarray) -> np.ndarray:
    """Potencia ponderada K por muestra, sumada en canales."""
    y = sosfilt(_K_SOS, x.astype(np.float64) + 1e-18, axis=0)
    return (y ** 2).sum(axis=1) if y.ndim == 2 else y ** 2


def lufs(x: np.ndarray):
    """Loudness integrada BS.1770-4 (bloques de 400 ms al 75 %, compuertas −70 y −10).
    Igual que pyloudnorm pero vectorizada (mucho más rápida en señales largas)."""
    if len(x) < int(0.4 * SR):
        return None
    p = _potencia_k(x)
    b, h = int(0.4 * SR), int(0.1 * SR)
    cs = np.concatenate([[0.0], np.cumsum(p)])
    ini = np.arange(0, len(p) - b + 1, h)
    z = (cs[ini + b] - cs[ini]) / b
    lk = -0.691 + 10 * np.log10(z + 1e-30)
    z = z[lk > -70]
    if len(z) == 0:
        return None
    rel = -0.691 + 10 * np.log10(z.mean()) - 10
    z2 = z[-0.691 + 10 * np.log10(z) > rel]
    return float(-0.691 + 10 * np.log10(z2.mean())) if len(z2) else None


def _lufs(medidor, x):
    try:
        v = lufs(x)
        return v if v is not None and np.isfinite(v) else None
    except Exception:
        return None


def corto_plazo(x: np.ndarray, ventana=3.0, salto=0.5):
    """Loudness de corto plazo (LUFS-S, ventana de 3 s) cada `salto` s."""
    p = _potencia_k(x)
    n, h = int(ventana * SR), int(salto * SR)
    cs = np.concatenate([[0.0], np.cumsum(p)])
    ini = np.arange(0, max(1, len(p) - n), h)
    z = (cs[np.minimum(ini + n, len(p))] - cs[ini]) / n
    v = -0.691 + 10 * np.log10(z + 1e-30)
    return (ini + n / 2) / SR, np.maximum(v, -70.0)


def detectar_clicks(x: np.ndarray, umbral: float = 14.0, piso: float = 4e-4, ataques=None,
                    ventana=(0.004, 0.04), impulso: float = 6.0):
    """Discontinuidades: picos de la 2ª diferencia muy por encima de su entorno (20 ms).

    ataques: inicios de notas y clips (s) del mismo audio. Un pico dentro de la ventana de
    ataque de una nota (de −4 a +40 ms) solo cuenta si es impulsivo: |d2| ≥ `impulso` × la
    RMS de d2 en ±1 ms (sin las ±2 muestras del pico). Un ataque (martillo, púa, baqueta,
    ruido filtrado) reparte su 2ª diferencia en muchas muestras; un empalme roto, un escalón
    o un corte seco la concentran en una o dos. Fuera de las ventanas, igual que siempre.
    Sin `ataques` se comporta exactamente como antes (lo usa también el mezclador)."""
    m = x.astype(np.float64).mean(axis=1)
    d = np.abs(np.diff(m, 2))
    k = int(0.02 * SR)
    cs = np.concatenate([[0.0], np.cumsum(d)])
    med = (cs[k:] - cs[:-k]) / k                      # media móvil centrada de 20 ms
    base = np.empty_like(d)
    a = k // 2
    base[a:a + len(med)] = med[: len(d) - a]
    base[:a] = med[0]
    base[a + len(med):] = med[-1]
    r = d / (base + 1e-6)
    idx = np.nonzero((r > umbral) & (d > piso))[0]
    if ataques is not None and len(ataques) and len(idx):
        ons = np.sort(np.asarray(ataques, dtype=np.float64))
        t = (idx + 1) / SR
        j = np.searchsorted(ons, t - ventana[1], side="left")
        en_ataque = (j < len(ons)) & (ons[np.minimum(j, len(ons) - 1)] <= t + ventana[0])
        w = int(0.001 * SR)
        quedan = []
        for i, dentro in zip(idx, en_ataque):
            if not dentro:
                quedan.append(i)
                continue
            vec = np.concatenate([d[max(0, i - w): max(0, i - 2)], d[i + 3: i + w + 1]])
            rms = np.sqrt(np.mean(vec ** 2)) if len(vec) else 0.0
            if d[i] >= impulso * (rms + 1e-12):
                quedan.append(i)
        idx = np.asarray(quedan, dtype=np.int64)
    eventos = []
    ult = -10 ** 9
    for i in idx:
        if i - ult > int(0.01 * SR):
            eventos.append(round((i + 1) / SR, 4))
        ult = i
    return eventos


def onsets_por_stem(C, n: int, t0_s: float = 0.0) -> dict:
    """Inicios de notas (s) por stem, para no confundir ataques musicales con clicks.
    `t0_s`: segundo de la canción donde empieza el audio analizado (render con --desde)."""
    out = {k: [] for k in STEMS}
    for p in C.pistas.values():
        for nt in p.notas_humanizadas():
            out[p.stem].append(float(C.tempo.seg(nt.t)) - t0_s)
        for c in p.clips:
            if c["pos"] is not None:
                out[p.stem].append(float(C.tempo.seg(c["pos"])) - t0_s)
            if c["fin"] is not None:
                out[p.stem].append(float(C.tempo.seg(c["fin"])) - t0_s)
    return {k: np.array(sorted(v)) for k, v in out.items()}


def fuera_de_onsets(eventos, onsets, antes=0.006, despues=0.03):
    if len(onsets) == 0:
        return list(eventos)
    ev = []
    for t in eventos:
        i = np.searchsorted(onsets, t)
        cerca = False
        for j in (i - 1, i):
            if 0 <= j < len(onsets) and -antes <= t - onsets[j] <= despues:
                cerca = True
        if not cerca:
            ev.append(t)
    return ev


def saltos_agudos(x: np.ndarray, salto_db: float = 30.0, piso_db: float = -66.0):
    """Ráfagas súbitas de energía >9 kHz (1 ms) frente a los 40 ms previos."""
    m = x.astype(np.float64).mean(axis=1)
    hp = sosfilt(np.vstack([biquad("pa", 9000.0), biquad("pa", 9000.0)]), m + 1e-18)
    f = int(0.001 * SR)
    nfr = len(hp) // f
    e = (hp[: nfr * f].reshape(nfr, f) ** 2).mean(axis=1) + 1e-14
    edb = 10 * np.log10(e)
    # mediana de los 40 ms previos (filtro de mediana desplazado para que sea causal)
    from scipy.ndimage import median_filter
    med = median_filter(edb, size=40, mode="nearest", origin=19)
    cand = np.nonzero((edb > piso_db) & (edb - np.roll(med, 1) > salto_db))[0]
    out = []
    for i in cand:
        if i < 40:
            continue
        if not out or i / 1000 - out[-1] > 0.02:
            out.append(round(i / 1000, 3))
    return out


def bandas(x: np.ndarray):
    mid = x.astype(np.float64).mean(axis=1)
    f, p = welch(mid, SR, nperseg=8192, noverlap=0)
    tot = p[(f >= 20) & (f <= 20000)].sum()
    out = {}
    for nom, a, b in BANDAS:
        e = p[(f >= a) & (f < b)].sum()
        out[nom] = round(float(10 * np.log10(e / tot + 1e-20)), 2)
    return out, f, p


def densidad_octava(b: dict) -> dict:
    """Energía por octava de cada banda (dB), para comparar bandas de distinto ancho."""
    return {nom: b[nom] - 10 * np.log10(np.log2(hi / lo)) for nom, lo, hi in BANDAS}


def resonancias(f, p, umbral_db=12.0):
    """Picos angostos del espectro de largo plazo sobre su suavizado de 1/3 de octava."""
    pdb = 10 * np.log10(p + 1e-20)
    lf = np.log2(np.maximum(f, 1))
    out = []
    sel = np.nonzero((f > 50) & (f < 12000))[0]
    suave = np.empty_like(pdb)
    for i in sel:
        m = np.abs(lf - lf[i]) < 1 / 6
        suave[i] = np.mean(pdb[m])
    for i in sel[1:-1]:
        d = pdb[i] - suave[i]
        if d > umbral_db and pdb[i] >= pdb[i - 1] and pdb[i] >= pdb[i + 1]:
            out.append({"hz": round(float(f[i]), 1), "exceso_db": round(float(d), 1),
                        "nota": nombre_nota(round(float(hz_a_midi(f[i]))))})
    return sorted(out, key=lambda z: -z["exceso_db"])[:12]


def analizar(C, res, imagenes=True) -> dict:
    carpeta: Path = res["carpeta"]
    carpeta.mkdir(parents=True, exist_ok=True)
    m = res["master"]
    stems = res["stems"]
    pre = res["premaster"]
    med = pyln.Meter(SR)
    q = {}
    # ---------------------------------------------------------- integridad
    q["pico_real_dbtp"] = round(pico_real(m), 2)
    q["pico_muestra_dbfs"] = round(float(20 * np.log10(np.abs(m).max() + 1e-12)), 2)
    q["dc_dbfs"] = [round(float(20 * np.log10(abs(m[:, c].mean()) + 1e-12)), 1) for c in range(2)]
    q["lufs_integrado"] = round(float(med.integrated_loudness(m.astype(np.float64))), 2)
    q["lufs_integrado_rapido"] = round(lufs(m), 2)
    q["lufs_premaster"] = round(_lufs(med, pre), 2)
    ts, st = corto_plazo(m)
    vivos = st[st > -60]
    q["lra_lu"] = round(float(np.percentile(vivos, 95) - np.percentile(vivos, 10)), 1) if len(vivos) else 0
    t0 = float(res.get("t0_s", 0.0))          # render con --desde: el audio empieza en t0
    fin_musica = float(res.get("fin_musica_s", C.tempo.seg(C.tiempos_total))) - t0
    L, R = m[:, 0].astype(np.float64), m[:, 1].astype(np.float64)
    q["correlacion_estereo"] = round(float(np.corrcoef(L, R)[0, 1]), 3)
    w = SR
    cs = []
    for a in range(0, len(L) - w, w):
        if a / SR >= fin_musica:      # la cola (reverb que se apaga + hiss) no cuenta
            break
        l, r = L[a:a + w], R[a:a + w]
        if np.sqrt(0.5 * np.mean(l ** 2 + r ** 2)) > 10 ** (-50 / 20):   # sin tramos de solo hiss
            cs.append(np.corrcoef(l, r)[0, 1])
    q["correlacion_1s_min"] = round(float(np.min(cs)), 3) if cs else None
    q["correlacion_1s_mediana"] = round(float(np.median(cs)), 3) if cs else None
    mono = (L + R) / 2
    q["mono_menos_estereo_lu"] = round(_lufs(med, np.stack([mono, mono], 1)) - q["lufs_integrado"], 2)
    suma = sum(stems.values())
    err = np.sqrt(np.mean((suma - pre) ** 2)) / (np.sqrt(np.mean(pre ** 2)) + 1e-12)
    q["suma_stems_vs_premaster_db"] = round(float(20 * np.log10(err + 1e-12)), 1)
    q["largos_iguales"] = len({len(s) for s in stems.values()} | {len(m)}) == 1
    q["inicio_rms_dbfs"] = round(float(20 * np.log10(np.sqrt(np.mean(m[: int(0.01 * SR)] ** 2)) + 1e-12)), 1)
    q["fin_rms_dbfs"] = round(float(20 * np.log10(np.sqrt(np.mean(m[-int(0.1 * SR):] ** 2)) + 1e-12)), 1)
    clicks = {}
    agudos = {}
    ons = onsets_por_stem(C, len(m), t0)
    for k, s in stems.items():
        if np.abs(s).max() < 1e-6:
            continue
        if k == "bateria":  # los golpes son transitorios a propósito: solo lo que cae lejos de ellos
            clicks[k] = fuera_de_onsets(detectar_clicks(s, umbral=40.0), ons[k], 0.006, 0.25)
        else:               # en los ataques de las notas solo cuenta lo impulsivo (ver detectar_clicks)
            clicks[k] = detectar_clicks(s, umbral=14.0, ataques=ons[k])
        # ráfagas >9 kHz que NO coinciden con el ataque de una nota o un clip
        agudos[k] = fuera_de_onsets(saltos_agudos(s), ons[k]) if k != "bateria" else []
    todos = np.sort(np.concatenate([ons[k] for k in ons]))
    clicks["master"] = fuera_de_onsets(detectar_clicks(m, umbral=40.0), todos, 0.006, 0.25)
    q["clicks"] = {k: {"n": len(v), "t": [float(x) for x in v[:12]]} for k, v in clicks.items()}
    q["rafagas_agudas"] = {k: {"n": len(v), "t": [float(x) for x in v[:12]]} for k, v in agudos.items()}
    # ---------------------------------------------------------- balance
    secs = []
    for s in C.secciones:
        a = float(C.tempo.seg(C.tempo.pos(s.compas_ini))) - t0
        b = float(C.tempo.seg(C.tempo.pos(s.compas_fin))) - t0
        v = _lufs(med, m[max(0, int(a * SR)): max(0, int(b * SR))]) if b > 0 else None
        secs.append({"nombre": s.nombre, "inicio_s": round(a + t0, 1), "fin_s": round(b + t0, 1),
                     "energia": s.energia, "lufs": None if v is None else round(v, 1)})
    q["secciones"] = secs
    e = np.array([s["energia"] for s in secs if s["lufs"] is not None])
    lv = np.array([s["lufs"] for s in secs if s["lufs"] is not None])
    q["corr_energia_lufs"] = round(float(np.corrcoef(e, lv)[0, 1]), 3) if len(e) > 2 else None
    b_m, f, p = bandas(m)
    q["bandas_db_rel"] = b_m
    dens = densidad_octava(b_m)
    q["barro_vs_vecinas_db"] = round(dens["barro"] - 0.5 * (dens["graves"] + dens["medios_bajos"]), 2)
    q["presencia_vs_vecinas_db"] = round(dens["presencia"] - 0.5 * (dens["medios"] + dens["brillo"]), 2)
    q["resonancias"] = resonancias(f, p)
    esp_stems = {k: bandas(s) for k, s in stems.items() if np.abs(s).max() > 1e-6}
    q["bandas_stems"] = {k: v[0] for k, v in esp_stems.items()}
    q["segundos_render"] = round(res.get("segundos_render", 0), 1)
    grave = revisar_grave(C)
    q["clusters_grave"] = {"n": len(grave), "ejemplos": grave[:10]}
    (carpeta / "qa.json").write_text(json.dumps(q, indent=2, ensure_ascii=False))
    if imagenes:
        graficar(C, res, ts, st, f, p, carpeta, esp_stems)
    imprimir(q)
    return q


def imprimir(q):
    print("\n=== QA ===")
    print(f"LUFS {q['lufs_integrado']} (premaster {q['lufs_premaster']}) · pico real {q['pico_real_dbtp']} dBTP"
          f" · LRA {q['lra_lu']} LU · DC {q['dc_dbfs']} dBFS")
    print(f"correlación {q['correlacion_estereo']} (1 s: mín {q['correlacion_1s_min']}, mediana "
          f"{q['correlacion_1s_mediana']}) · mono−estéreo {q['mono_menos_estereo_lu']} LU")
    print(f"suma stems vs premaster {q['suma_stems_vs_premaster_db']} dB · largos iguales {q['largos_iguales']}"
          f" · inicio {q['inicio_rms_dbfs']} dBFS · fin {q['fin_rms_dbfs']} dBFS")
    print("clicks:", {k: v["n"] for k, v in q["clicks"].items()},
          "· ráfagas agudas:", {k: v["n"] for k, v in q["rafagas_agudas"].items()})
    print("secciones:", " | ".join(f"{s['nombre']} {s['lufs']} (e={s['energia']})" for s in q["secciones"]),
          f"· corr energía-LUFS {q['corr_energia_lufs']}")
    print("bandas (dB rel. al total):", q["bandas_db_rel"])
    print(f"barro vs vecinas {q['barro_vs_vecinas_db']} dB · presencia vs vecinas {q['presencia_vs_vecinas_db']} dB")
    print("resonancias >12 dB:", [(r["hz"], r["nota"], r["exceso_db"]) for r in q["resonancias"][:6]])
    print(f"clusters en el grave (regla de 5ª bajo ~Mi3): {q['clusters_grave']['n']}",
          q["clusters_grave"]["ejemplos"][:4])


# ================================================================ gráficos ==
def graficar(C, res, ts, st, f, p, carpeta: Path, esp_stems=None):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    m = res["master"]
    dur = len(m) / SR
    t0 = float(res.get("t0_s", 0.0))
    secs = [(s.nombre, float(C.tempo.seg(C.tempo.pos(s.compas_ini))) - t0,
             float(C.tempo.seg(C.tempo.pos(s.compas_fin))) - t0, s.energia, s.voz) for s in C.secciones]
    secs = [z for z in secs if z[2] > 0 and z[1] < dur]

    def marcar(ax, texto=True, y=None):
        for (nom, a, b, e, voz) in secs:
            ax.axvline(a, color="w" if y is None else "0.3", lw=0.6, alpha=0.7)
            if texto:
                ax.text(a + 0.5, ax.get_ylim()[1] if y is None else y, nom + (" ·voz" if voz else ""),
                        va="top", fontsize=8, color="w" if y is None else "0.15")

    # 1) espectrograma (frecuencia logarítmica)
    mid = m.mean(axis=1).astype(np.float64)
    ff, tt, Z = stft(mid, SR, nperseg=4096, noverlap=4096 - 2048)
    S = 20 * np.log10(np.abs(Z) + 1e-9)
    flog = np.geomspace(30, 16000, 360)
    Slog = np.stack([np.interp(flog, ff, S[:, j]) for j in range(S.shape[1])], axis=1)
    fig, ax = plt.subplots(figsize=(16, 6), dpi=100)
    ax.imshow(Slog, origin="lower", aspect="auto", cmap="magma", vmin=S.max() - 90, vmax=S.max(),
              extent=[tt[0], tt[-1], 0, len(flog)])
    marcas_f = [50, 100, 200, 500, 1000, 2000, 5000, 10000]
    ax.set_yticks([np.searchsorted(flog, v) for v in marcas_f])
    ax.set_yticklabels([f"{v // 1000}k" if v >= 1000 else str(v) for v in marcas_f])
    ax.set_xlabel("s")
    ax.set_ylabel("Hz")
    ax.set_title(f"{C.titulo} — espectrograma")
    marcar(ax)
    fig.tight_layout()
    fig.savefig(carpeta / "espectrograma.png")
    plt.close(fig)

    # 2) forma de onda + loudness
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(16, 7), dpi=100, sharex=True)
    h = int(0.05 * SR)
    nb = len(m) // h
    blk = m[: nb * h].reshape(nb, h, 2)
    tb = (np.arange(nb) + 0.5) * h / SR
    pk = np.abs(blk).max(axis=1)
    rms = np.sqrt((blk.astype(np.float64) ** 2).mean(axis=1))
    a1.fill_between(tb, -pk[:, 0], pk[:, 1], color="#c9b79c", lw=0)
    a1.fill_between(tb, -rms[:, 0], rms[:, 1], color="#6b4f2a", lw=0)
    a1.set_ylim(-1, 1)
    a1.set_ylabel("pico / RMS (L abajo, R arriba)")
    a1.set_title(f"{C.titulo} — forma de onda y loudness")
    marcar(a1, y=0.98)
    a2.plot(ts, st, color="#2c5d8a", lw=1.5, label="LUFS corto plazo (3 s)")
    lufs_obj = res["info_master"]["lufs"]
    for (nom, a, b, e, voz) in secs:
        a2.hlines(lufs_obj - 14 + 16 * e, a, b, color="#c0603a", lw=2, alpha=0.8)
    a2.plot([], [], color="#c0603a", label="energía pedida (escalada)")
    a2.set_ylim(-45, -6)
    a2.set_ylabel("LUFS")
    a2.set_xlabel("s")
    a2.legend(loc="lower right", fontsize=8)
    marcar(a2, texto=False)
    a2.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(carpeta / "forma_de_onda.png")
    plt.close(fig)

    # 3) espectro de largo plazo por stem
    fig, ax = plt.subplots(figsize=(12, 5), dpi=100)
    ax.semilogx(f, 10 * np.log10(p + 1e-20), color="k", lw=1.4, label="master")
    for k, (_b, fs, ps) in (esp_stems or {}).items():
        ax.semilogx(fs, 10 * np.log10(ps + 1e-20), lw=0.9, label=k, alpha=0.8)
    ax.axvspan(200, 400, color="#c0603a", alpha=0.08)
    ax.axvspan(2000, 5000, color="#2c5d8a", alpha=0.08)
    ax.set_xlim(20, 20000)
    ax.set_ylim(np.percentile(10 * np.log10(p + 1e-20), 5) - 20, 10 * np.log10(p.max()) + 5)
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.3, which="both")
    ax.set_title(f"{C.titulo} — espectro promedio (sombreado: barro 200–400, presencia 2–5 k)")
    fig.tight_layout()
    fig.savefig(carpeta / "espectro.png")
    plt.close(fig)

    pianola(C, carpeta / "pianola.png", None if t0 else dur)


def pianola(C, ruta, dur=None):
    """Imagen del arreglo: un carril por pista (altura relativa dentro del carril; en la
    batería, un sub-carril por golpe), secciones sombreadas y cifrado arriba."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.collections import LineCollection

    pistas = [p for p in C.pistas.values() if p.notas or p.clips]
    dur = dur or C.duracion_s
    fig, ax = plt.subplots(figsize=(18, 0.75 * len(pistas) + 2.2), dpi=100)
    colores = {"bateria": "#7a5c3e", "bajo": "#3e4f7a", "armonia": "#5a7a3e", "melodia": "#a0462d",
               "textura": "#6d6d6d"}
    golpes_orden = ["bombo", "aro", "escobilla", "caja", "barrido", "shaker", "hat", "hat_abierto",
                    "tic", "tac"]
    for k, p in enumerate(pistas):
        y0 = len(pistas) - 1 - k
        segs, alfas = [], []
        if p.stem == "bateria":
            for n in p.notas:
                g = n.x.get("golpe", "bombo")
                j = golpes_orden.index(g) if g in golpes_orden else 0
                yy = y0 + 0.08 + 0.84 * j / (len(golpes_orden) - 1)
                a = float(C.tempo.seg(n.t))
                segs.append([(a, yy), (a + 0.06, yy)])
                alfas.append(0.3 + 0.7 * n.vel)
        else:
            alturas = [n.midi for n in p.notas] or [60]
            lo, hi = min(alturas), max(alturas)
            rng_ = max(12, hi - lo)
            for n in p.notas:
                a = float(C.tempo.seg(n.t))
                b = float(C.tempo.seg(n.t + n.dur))
                yy = y0 + 0.08 + 0.84 * (n.midi - lo) / rng_
                segs.append([(a, yy), (max(b, a + 0.05), yy)])
                alfas.append(0.35 + 0.65 * n.vel)
        if segs:
            base = matplotlib.colors.to_rgb(colores[p.stem])
            cols = [(*base, al) for al in alfas]
            ax.add_collection(LineCollection(segs, colors=cols, linewidths=1.6, capstyle="butt"))
        for c in p.clips:
            if c["pos"] is not None:
                ta = float(C.tempo.seg(c["pos"]))
                tb = ta + 8
            else:
                tb = float(C.tempo.seg(c["fin"]))
                ta = tb - 4
            ax.add_patch(plt.Rectangle((ta, y0 + 0.15), tb - ta, 0.7, color=colores[p.stem], alpha=0.25))
        ax.text(-1, y0 + 0.5, f"{p.nombre} [{p.stem}]", ha="right", va="center", fontsize=9)
    for s in C.secciones:
        a = float(C.tempo.seg(C.tempo.pos(s.compas_ini)))
        b = float(C.tempo.seg(C.tempo.pos(s.compas_fin)))
        ax.axvspan(a, b, color="#2c5d8a" if s.voz else "#c0603a", alpha=0.05)
        ax.axvline(a, color="0.4", lw=0.7)
        ax.text(a + 0.3, len(pistas) + 0.55, f"{s.nombre} (c{s.compas_ini}) e={s.energia}", fontsize=8)
    for (t0, t1, sim) in C.armonia:
        ax.text(float(C.tempo.seg(t0)) + 0.1, len(pistas) + 0.12, sim, fontsize=5.5, color="0.25")
    ax.set_xlim(-0.5, dur)
    ax.set_ylim(-0.2, len(pistas) + 1.1)
    ax.set_yticks([])
    ax.set_xlabel("s")
    ax.set_title(f"{C.titulo} — pianola del arreglo (azul = bajo voz)")
    fig.tight_layout()
    fig.savefig(ruta)
    plt.close(fig)


# ============================================================ revisión musical ==
def revisar_grave(C, limite: int = 50, paso: float = 0.5, min_intervalo: int = 7):
    """Busca 'clusters' en el grave en toda la partitura (todas las pistas con altura,
    con el pedal de resonancia y con lo que sigue sonando en los instrumentos que dejan
    sonar: arpa, pizzicato, glock): si la nota de abajo está bajo ~Mi3 (Re3, MIDI 50) la
    siguiente debe estar a una 5ª justa o más; entre Re3 y Mi3, nada de segundas.
    Devuelve [(compás, [notas], [pistas]), …]."""
    from .nucleo import nombre_nota
    eventos = []
    for p in C.pistas.values():
        if p.stem == "bateria" or p.instrumento.__class__.__name__ in ("Textura", "Bateria"):
            continue
        usa_pedal = getattr(p.instrumento, "usa_pedal", False)
        fin_sonoro = getattr(p.instrumento, "fin_sonoro", None)
        for n in p.notas:
            fin = n.t + n.dur
            if fin_sonoro is not None:
                try:
                    fin = max(fin, float(fin_sonoro(n, C.tempo)))
                except Exception:       # instrumentos de las canciones con otra interfaz
                    pass
            if usa_pedal and p.pedales:
                abajo, sube = p.pedal_abajo_en(n.t + n.dur - 1e-6)
                if abajo:
                    fin = max(fin, sube)
            eventos.append((n.t, fin, int(n.midi), p.nombre))
    if not eventos:
        return []
    t_fin = max(e[1] for e in eventos)
    problemas = []
    t = 0.0
    ultimo = None
    while t < t_fin:
        sonando = sorted({(m, nom) for (a, b, m, nom) in eventos if a <= t + 1e-6 < b})
        alturas = sorted({m for m, _ in sonando})
        for lo, hi in zip(alturas[:-1], alturas[1:]):
            d = hi - lo
            if (lo < limite and 0 < d < min_intervalo) or (limite <= lo < 52 and 0 < d < 3):
                clave = (lo, hi)
                if clave != ultimo:
                    pistas = sorted({nom for m, nom in sonando if m in (lo, hi)})
                    problemas.append((round(1 + t / C.tempo.tpc, 2),
                                      [nombre_nota(lo), nombre_nota(hi)], pistas))
                ultimo = clave
                break
        else:
            ultimo = None
        t += paso
    return problemas
