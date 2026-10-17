"""mezcla.png: la mezcla sobre la línea de tiempo, para revisar sin oídos.

Paneles (eje x compartido, un solo eje y por panel):
  1. voz: envolvente RMS (dBFS) y frases detectadas
  2. ganancia de cada stem (dB): bloques + fundidos + ducking + realce
  3. sonoridad de corto plazo (3 s): voz, cama y mezcla final, con la franja objetivo de la cama
  4. reducción del limitador del master (dB)
  5. arreglo: tramos, secciones, empalmes (↺ loop, ⇢ salto), transiciones, anclas y downbeats
"""
from __future__ import annotations

import numpy as np

from . import SR, STEMS

# paleta de referencia (validada: categórica de 5 en orden fijo, superficie clara)
SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_2 = "#52514e"
TENUE = "#898781"
GRILLA = "#e1e0d9"
EJE = "#c3c2b7"
COLOR_STEM = {"bateria": "#2a78d6", "bajo": "#eb6834", "armonia": "#1baf7a",
              "melodia": "#eda100", "textura": "#e87ba4"}
CAMA = "#6250d6"


def _mmss(x, _pos=None):
    x = max(0.0, x)
    return f"{int(x // 60)}:{int(x % 60):02d}"


def dibujar(ruta, voz, R, ctrl, edl, plan, st, gr, resumen: dict):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FuncFormatter, MultipleLocator

    dur = edl.n_total / SR
    ancho = float(np.clip(10 + dur / 12, 16, 34))
    fig, ax = plt.subplots(5, 1, figsize=(ancho, 13.5), dpi=100, sharex=True,
                           gridspec_kw={"height_ratios": [1.3, 2.6, 2.1, 0.9, 1.9]})
    fig.patch.set_facecolor(SUPERFICIE)
    for a in ax:
        a.set_facecolor(SUPERFICIE)
        a.grid(True, color=GRILLA, lw=0.6)
        a.set_axisbelow(True)
        for lado in ("top", "right"):
            a.spines[lado].set_visible(False)
        for lado in ("left", "bottom"):
            a.spines[lado].set_color(EJE)
        a.tick_params(colors=TENUE, labelsize=8)
        a.yaxis.label.set_color(TINTA_2)
    t = np.arange(0, dur, 0.02)

    def frases_fondo(a):
        for (x0, x1) in voz.frases:
            a.axvspan(x0, x1, color=GRILLA, alpha=0.55, lw=0)

    # 1) voz
    a = ax[0]
    frases_fondo(a)
    if voz.nivel_db is not None:
        tv = (np.arange(len(voz.nivel_db)) + 0.5) * 0.01
        a.fill_between(tv, -80, np.maximum(voz.nivel_db, -80), color=TINTA_2, alpha=0.75, lw=0)
    if voz.umbral_db is not None:
        a.axhline(voz.umbral_db, color=TENUE, lw=0.8)
        a.text(0.2, voz.umbral_db + 1.5, "umbral de habla", fontsize=7, color=TENUE)
    a.set_ylim(-75, 0)
    a.set_ylabel("voz (dBFS)")
    a.set_title("Voz: envolvente RMS (banda 100 Hz–6 kHz) y frases detectadas", loc="left",
                fontsize=10, color=TINTA)

    # 2) ganancia por stem
    a = ax[1]
    frases_fondo(a)
    # batería/bajo y armonía/textura comparten profundidad por defecto: las gruesas van debajo y
    # las finas encima, así se ven las dos identidades aunque coincidan
    anchos = {"bateria": 3.4, "armonia": 3.4, "bajo": 1.2, "textura": 1.2, "melodia": 1.5}
    finales = []
    for s in ("bateria", "armonia", "bajo", "textura", "melodia"):
        g = R.ganancia_stem_db(s, t)
        a.plot(t, g, color=COLOR_STEM[s], lw=anchos[s], label=s, solid_capstyle="butt",
               zorder=2 if anchos[s] > 2 else 3)
        vivos = np.nonzero(g > -59)[0]
        if len(vivos):
            finales.append([float(g[vivos[-1]]), s])
    # etiquetas directas a la derecha, escalonadas (alivio de contraste: la identidad no queda
    # solo en el color)
    finales.sort()
    sep, y_min, y_max = 3.6, -40.0, 12.0
    for i in range(1, len(finales)):
        finales[i][0] = max(finales[i][0], finales[i - 1][0] + sep)
    if finales:                              # la pila no se sale del panel
        exceso = finales[-1][0] - y_max
        if exceso > 0:
            for f in finales:
                f[0] -= exceso
        falta = y_min - finales[0][0]
        if falta > 0:
            for f in finales:
                f[0] += falta
    for y, s in finales:
        a.text(1.004, y, s, transform=a.get_yaxis_transform(), fontsize=7.5, color=TINTA_2,
               va="center", clip_on=False)
    a.set_ylim(-42, 14)
    a.yaxis.set_major_locator(MultipleLocator(6))
    a.set_ylabel("ganancia (dB)")
    h, l = a.get_legend_handles_labels()
    orden = [l.index(s) for s in STEMS if s in l]
    a.legend([h[i] for i in orden], [l[i] for i in orden], loc="lower left", fontsize=8, ncol=5,
             frameon=False, labelcolor=TINTA_2, handlelength=2.5)
    a.set_title("Ganancia de cada stem: nivel del bloque, fundidos, ducking guiado por la voz y realce",
                loc="left", fontsize=10, color=TINTA)

    # 3) sonoridad de corto plazo (escala de la mezcla final)
    a = ax[2]
    tt, lc, lv, lm = st
    techos = resumen.get("techos") or {}
    obj, w = techos.get("bajo_voz", (plan.parametros["niveles"]["musica_bajo_voz_lu"],
                                     plan.parametros["niveles"]["ventana_lu"]))
    habla = voz.mascara(tt) if len(tt) else np.zeros(0, bool)
    lo = np.where(habla, lv + obj - w, np.nan)
    hi = np.where(habla, lv + obj + w, np.nan)
    a.fill_between(tt, lo, hi, color=GRILLA, alpha=0.9, lw=0,
                   label=f"objetivo música bajo la voz ({obj:+g} ± {w:g} LU)")
    a.plot(tt, np.where(lv > -60, lv, np.nan), color=TINTA_2, lw=1.2, label="voz")
    a.plot(tt, np.where(lc > -70, lc, np.nan), color=CAMA, lw=1.4, label="música (cama)")
    a.plot(tt, np.where(lm > -70, lm, np.nan), color=TINTA, lw=0.9, label="mezcla final")
    # techos sin voz: pausas (voz − 10 LU) e intro/final (tope absoluto)
    if voz.frases:
        regiones = [("pausa", b0, b1) for (_, b0), (b1, _) in zip(voz.frases[:-1], voz.frases[1:])
                    if b1 - b0 >= 0.6]
        regiones.insert(0, ("intro", 0.0, voz.frases[0][0]))
        regiones.append(("final", voz.frases[-1][1], dur))
    else:
        regiones = [("intro", 0.0, dur)]
    for (tipo, x0, x1) in regiones:
        y = techos.get("pausas") if tipo == "pausa" else techos.get("sin_voz")
        if y is None or x1 - x0 < 0.3:
            continue
        a.plot([x0, x1], [y, y], color=TINTA_2, lw=1.0, solid_capstyle="butt")
    if techos.get("sin_voz") is not None:
        a.text(0.3, techos["sin_voz"] + 0.6, f"tope sin voz {techos['sin_voz']:g} LUFS-S", fontsize=7, color=TINTA_2)
    if techos.get("pausas") is not None and len(regiones) > 2:
        x0 = regiones[1][1]
        a.text(x0, techos["pausas"] + 0.6, "techo pausas (voz − 10 LU)", fontsize=7, color=TINTA_2)
    a.set_ylim(-60, -6)
    a.yaxis.set_major_locator(MultipleLocator(6))
    a.set_ylabel("LUFS (3 s)")
    a.legend(loc="lower left", fontsize=8, ncol=4, frameon=False, labelcolor=TINTA_2)
    a.set_title("Sonoridad de corto plazo, en la escala de la mezcla final", loc="left", fontsize=10, color=TINTA)

    # 4) limitador
    a = ax[3]
    if gr is not None and len(gr):
        h = int(0.02 * SR)
        nb = len(gr) // h
        g2 = gr[: nb * h].reshape(nb, h).max(axis=1)
        a.plot((np.arange(nb) + 0.5) * 0.02, g2, color=TINTA, lw=0.9)
        a.set_ylim(0, max(1.5, float(g2.max()) * 1.2))
    a.set_ylabel("reducción (dB)")
    a.set_title("Limitador del master (pico real ≤ techo)", loc="left", fontsize=10, color=TINTA)

    # 5) arreglo
    a = ax[4]
    a.set_ylim(0, 4)
    a.set_yticks([])
    for k, tre in enumerate(edl.tramos):
        x0, x1 = tre.t_entrada, tre.t_fin_musica
        a.add_patch(plt.Rectangle((x0, 2.2), x1 - x0, 1.3, color=GRILLA if k % 2 == 0 else "#efeee9", lw=0))
        a.text(x0 + 0.3, 3.25, f"{tre.tramo.id}", fontsize=8.5, color=TINTA, va="center", clip_on=True)
        a.text(x0 + 0.3, 2.8, f"{tre.tramo.cancion.slug} · c. {tre.ruta_txt()}", fontsize=7,
               color=TINTA_2, va="center", clip_on=True)
        a.text(x0 + 0.3, 2.42, f"nivel {tre.tramo.nivel_db:+g} dB", fontsize=6.5, color=TENUE,
               va="center", clip_on=True)
        # secciones (cambios dentro del tramo)
        prev = None
        for cr in tre.corridas:
            for c in range(cr.c0, cr.c1 + 1):
                sec = cr.cancion.seccion_de(c).nombre
                if sec != prev:
                    tx = cr.tl(c)
                    a.plot([tx, tx], [1.45, 2.2], color=TENUE, lw=0.7)
                    a.text(tx + 0.2, 1.8, sec, fontsize=6.5, color=TINTA_2, va="center", clip_on=True)
                    prev = sec
        if tre.tramo.ancla is not None and tre.ancla_t is not None:
            for b in ax:
                b.axvline(tre.ancla_t, color=TINTA, lw=0.9)
            a.text(tre.ancla_t + 0.2, 0.25, f"ancla: {tre.tramo.ancla.texto()} (error {tre.ancla_error_ms:+.1f} ms)",
                   fontsize=7, color=TINTA, va="bottom")
    for e in edl.empalmes:
        if e.tipo == "continuo":
            continue
        a.text(e.t, 1.2, "↺" if e.tipo == "loop" else "⇢", fontsize=10, color=TINTA, ha="center", va="center")
    for tr in edl.transiciones:
        x0, x1 = tr.ventana
        a.add_patch(plt.Rectangle((x0, 0.75), max(0.05, x1 - x0), 0.3, color=TINTA_2, alpha=0.6, lw=0))
        a.text(x0, 0.6, tr.tipo, fontsize=7, color=TINTA, va="top", clip_on=True)
    from .envolventes import pulsos_efectivos
    downs, _ = pulsos_efectivos(edl)
    for x in downs:
        a.plot([x, x], [0.0, 0.18], color=TENUE, lw=0.5)
    a.set_title("Arreglo: tramos, secciones, empalmes (↺ loop · ⇢ salto), transiciones, anclas y downbeats",
                loc="left", fontsize=10, color=TINTA)

    ax[-1].xaxis.set_major_formatter(FuncFormatter(_mmss))
    paso = 5 if dur <= 200 else 10 if dur <= 420 else 30
    ax[-1].xaxis.set_major_locator(MultipleLocator(paso))
    ax[-1].set_xlim(0, dur)
    ax[-1].set_xlabel("tiempo (m:ss)", color=TINTA_2)
    fig.suptitle(resumen.get("titulo", "Mezcla"), x=0.01, ha="left", fontsize=12, color=TINTA)
    fig.text(0.01, 0.955, resumen.get("subtitulo", ""), fontsize=9, color=TINTA_2, ha="left")
    fig.subplots_adjust(left=0.045, right=0.955, top=0.92, bottom=0.05, hspace=0.42)
    fig.savefig(ruta, facecolor=SUPERFICIE)
    plt.close(fig)
