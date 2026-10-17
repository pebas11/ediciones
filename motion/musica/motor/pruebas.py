"""Pruebas cortas por instrumento (pocos segundos cada una).

    cd motion/musica && python3 -m motor.pruebas            # todas
    cd motion/musica && python3 -m motor.pruebas piano arpa # algunas

Escribe salida/_pruebas/instrumentos/<nombre>.wav (sin master, 24 bit) y una
hoja de espectrogramas `hoja.png`. Imprime pico, RMS, clicks y tiempo de render.
"""
from __future__ import annotations

import sys
import time

import numpy as np
import soundfile as sf

from . import *  # noqa: F401,F403
from .nucleo import SR
from .mezcla import render_cancion, DIR_SALIDA
from .analisis import detectar_clicks, saltos_agudos, onsets_por_stem, fuera_de_onsets

DIR = DIR_SALIDA / "_pruebas" / "instrumentos"
PROG = "Dmaj9 | E/D | Bm11 | Gmaj13#11"


def demo(nombre, instrumento, armar, compases=4, bpm=88, stem="armonia", envios=None,
         efectos=None, cola=3.0):
    C = Cancion(f"prueba {nombre}", f"_prueba_{nombre}", bpm, semilla=3, cola_s=cola)
    C.seccion("prueba", compases, 0.5, "prueba")
    prog = [x.strip() for x in PROG.split("|")]
    C.progresion(1, " | ".join(prog[i % 4] for i in range(compases)))
    p = C.pista(nombre, instrumento, stem, envios=envios or {"reverb": 0.25}, efectos=efectos or [])
    armar(C, p)
    t0 = time.time()
    res = render_cancion(C, salida=DIR / nombre, escribir=False, qa=False)
    dt = time.time() - t0
    x = res["premaster"]
    DIR.mkdir(parents=True, exist_ok=True)
    sf.write(DIR / f"{nombre}.wav", x, SR, subtype="PCM_24")
    seco = res["stems"][stem]
    ons = onsets_por_stem(C, len(seco))[stem]
    if stem == "bateria":   # igual que el QA: los golpes son transitorios a propósito
        ck = fuera_de_onsets(detectar_clicks(seco, umbral=40.0), ons, 0.006, 0.25)
        ag = []
    else:
        ck = detectar_clicks(seco)
        ag = fuera_de_onsets(saltos_agudos(seco), ons)
    ck = [round(float(t), 3) for t in ck]
    ag = [round(float(t), 3) for t in ag]
    pk = 20 * np.log10(np.abs(x).max() + 1e-12)
    rms = 20 * np.log10(np.sqrt(np.mean(x ** 2)) + 1e-12)
    print(f"  {nombre:14s} {dt:5.1f}s  pico {pk:6.1f} dBFS  rms {rms:6.1f}  clicks {len(ck)} {ck[:4]}  "
          f"ráfagas {len(ag)} {ag[:4]}")
    return nombre, x


def voicings(C, desde=1, hasta=5, voces=4, rango=("D3", "A4")):
    return C.voicings(desde, hasta, voces=voces, rango=rango)


def a_piano(C, p):
    for t0, t1, s, v in voicings(C):
        p.acorde(1 + t0 / 4, v, (t1 - t0), vel=0.45, rasgueo=0.012)
    for t0, t1, s, b in C.bajos(1, 5):
        p.nota(1 + t0 / 4, b, t1 - t0, vel=0.5)
    p.melodia(1, "r/2 A4/1 F#4/1 | G#4/3 B4/1 | C#5/2 A4/2 | F#4/4", vel=0.5)
    p.pedal_por_compas(1, 5)


def a_arpa(C, p):
    vs = voicings(C, voces=4, rango=("D3", "D5"))
    p.arpegio(1, 5, Cancion.voicing_en(vs), patron="0 1 2 3 4 3 2 1", paso=0.5, vel=0.55,
              acentos=[1.1, 0.8, 0.9, 0.8])


def a_glock(C, p):
    p.melodia(1, "A6/0.5 E7 D7 G#6/1.5 A6/1 | r/4 | F#6/1 C#7/1 E7/2 | r/4", vel=0.5)


def a_vibes(C, p):
    for t0, t1, s, v in voicings(C, rango=("F3", "C5")):
        p.acorde(1 + t0 / 4, v, (t1 - t0) * 0.9, vel=0.5, rasgueo=0.02)
    p.pedal_por_compas(1, 5)


def a_celesta(C, p):
    p.melodia(1, "A5/0.5 E6 D6 G#5/1.5 A5/1 | F#5/3 r/1 | A5/0.5 E6 D6 C#6/1.5 B5/0.5 G#5/0.5 | A5/4",
              vel=0.6)


def a_cuerdas_largas(C, p):
    m = {"violines": "A4", "violas": "F#4", "chelos": "D3", "contrabajo": "D2"}
    alt = m.get(p.instrumento.banco_nombre.split("_")[0], "D3")
    p.nota(1, alt, 12, vel=0.15, vel_fin=0.95)
    p.nota(4, alt, 4, vel=0.6)


def a_violines_legato(C, p):
    p.melodia(1, "A4/2_ E5/1_ D5/1_ | G#4/3_ A4/1 | B4/2_ C#5/2_ | A4/4", vel=0.55)


def a_rhodes(C, p):
    for t0, t1, s, v in voicings(C, rango=("D3", "B4")):
        p.acorde(1 + t0 / 4, v, 1.5, vel=0.6, rasgueo=0.008)
        p.acorde(1 + (t0 + 2.5) / 4, v, 1.0, vel=0.45)


def a_pad(C, p):
    for t0, t1, s, v in voicings(C, voces=5, rango=("A2", "D5")):
        for m in v:
            p.nota(1 + t0 / 4, m, t1 - t0, vel=0.7)
    p.auto("corte", [(1, 300), (5, 3500, "exp")])


def a_dron(C, p):
    p.nota(1, "D2", 16, vel=0.8)
    p.nota(1, "A2", 16, vel=0.6)


def a_sub(C, p):
    for t0, t1, s, b in C.bajos(1, 5, rango=("A1", "G#2")):
        p.nota(1 + t0 / 4, b, 1.5, vel=0.8)
        p.nota(1 + (t0 + 2) / 4, b, 0.5, vel=0.6)
        p.nota(1 + (t0 + 3) / 4, b, 0.9, vel=0.7)


def a_bateria(C, p):
    p.patron("bombo", "x... .... x.x. .... x... ..x. x... ....", 1, 5, vel=0.85)
    p.patron("aro", ".... x... .... x... .... x... .... x..o", 1, 5, vel=0.7)
    p.patron("shaker", "xxxx xxxx xxxx xxxx", 1, 5, vel=0.55)
    p.patron("hat", "..x. ..x. ..x. ..x.", 3, 5, vel=0.5)
    p.patron("escobilla", ".... x... .... x...", 3, 5, vel=0.6)
    p.golpe("4:4", "hat_abierto", 0.5)
    p.golpe("2:1", "barrido", 0.6, dur=4)
    p.humanizar(tiempo_ms=6, vel=0.08, swing=0.56, swing_div=0.25)


def a_textura(C, p):
    p.clip(swell(Piano(), ["D3", "A3", "E4", "F#4", "C#5"], largo_tiempos=6), fin=3)
    p.clip(nube(Celesta(), "A5/0.5 E6 D6 G#5/1.5 A5/1 F#5/3", dur_s=9.0, estirar=6.0,
                tonos=(0, 12, -12), pesos=(3, 1, 1)), pos=3)


def a_trem(C, p):
    p.nota(1, "D3", 8, vel=0.3, vel_fin=0.8)
    p.nota(1, "A3", 8, vel=0.3, vel_fin=0.8)


def a_pizz(C, p):
    p.melodia(1, "D4/0.5 F#4 A4 C#5 E5/1 r/1 | G#4/0.5 B4 E5 G#5/1 r/2", vel=0.6)


PRUEBAS = {
    "piano": lambda: demo("piano", Piano(), a_piano),
    "arpa": lambda: demo("arpa", Arpa(), a_arpa),
    "glock": lambda: demo("glock", Glock(), a_glock, stem="melodia"),
    "vibrafono": lambda: demo("vibrafono", Vibrafono(), a_vibes),
    "celesta": lambda: demo("celesta", Celesta(), a_celesta, stem="melodia"),
    "violines": lambda: demo("violines", Violines(), a_cuerdas_largas, compases=5),
    "violines_leg": lambda: demo("violines_leg", Violines(doble=True), a_violines_legato, stem="melodia"),
    "violas": lambda: demo("violas", Violas(), a_cuerdas_largas, compases=5),
    "chelos": lambda: demo("chelos", Chelos(), a_cuerdas_largas, compases=5),
    "contrabajo": lambda: demo("contrabajo", Contrabajo(), a_cuerdas_largas, compases=5, stem="bajo"),
    "trem": lambda: demo("trem", CuerdasTrem("chelos"), a_trem, compases=2),
    "pizz": lambda: demo("pizz", Pizzicato("violines"), a_pizz, compases=2),
    "rhodes": lambda: demo("rhodes", Rhodes(), a_rhodes),
    "pad": lambda: demo("pad", Pad(), a_pad),
    "dron": lambda: demo("dron", Dron(), a_dron),
    "sub": lambda: demo("sub", Sub(), a_sub, stem="bajo", envios={}),
    "bateria": lambda: demo("bateria", Bateria(), a_bateria, stem="bateria", envios={"sala": 0.2}),
    "textura": lambda: demo("textura", Textura(), a_textura, stem="textura", envios={"reverb": 0.3}),
}


def hoja(resultados, ruta):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy.signal import stft
    n = len(resultados)
    fig, axs = plt.subplots(n, 1, figsize=(14, 2.0 * n), dpi=90)
    axs = np.atleast_1d(axs)
    for ax, (nom, x) in zip(axs, resultados):
        f, t, Z = stft(x.mean(axis=1), SR, nperseg=2048, noverlap=1536)
        S = 20 * np.log10(np.abs(Z) + 1e-9)
        sel = (f > 30) & (f < 16000)
        ax.pcolormesh(t, f[sel], S[sel], shading="auto", cmap="magma", vmin=S.max() - 85, vmax=S.max())
        ax.set_yscale("log")
        ax.set_ylim(30, 16000)
        ax.text(0.01, 0.85, nom, transform=ax.transAxes, color="w", fontsize=10)
    fig.tight_layout()
    fig.savefig(ruta)
    plt.close(fig)


def main(nombres):
    sel = nombres or list(PRUEBAS)
    res = []
    for nm in sel:
        res.append(PRUEBAS[nm]())
    hoja(res, DIR / "hoja.png")
    print(f"→ {DIR}")


if __name__ == "__main__":
    main(sys.argv[1:])
