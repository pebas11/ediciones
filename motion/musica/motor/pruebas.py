"""Pruebas del motor.

Demos cortas por instrumento (pocos segundos cada una):

    cd motion/musica && python3 -m motor.pruebas            # todas
    cd motion/musica && python3 -m motor.pruebas piano arpa # algunas

Escriben salida/_pruebas/instrumentos/<nombre>.wav (sin master, 24 bit) y una
hoja de espectrogramas `hoja.png`. Imprimen pico, RMS, clicks y tiempo de render.

Pruebas con criterio (OK/MAL, código de salida ≠ 0 si alguna falla):

    cd motion/musica && python3 -m motor.pruebas tests              # todas (~4 min)
    cd motion/musica && python3 -m motor.pruebas tests --rapido     # nivelación de 5 bancos (~1 min)
    cd motion/musica && python3 -m motor.pruebas tests clicks glide # algunas

* nivelacion : monotonía por velocidad, suavidad entre muestras vecinas (±1,5 dB) y
               calibración (vel 0,6 = −26 LUFS ± 1) de cada banco muestreado
* parser     : acordes de la mini-notación ("[D4 F#4 A4]/2")
* clicks     : sin falsos positivos en los ataques (celesta grave, vibráfono); detecta un
               empalme roto, un escalón en un ataque y un corte seco
* glide      : Sub desliza solo entre notas ligadas y conserva la dinámica
* vibrafono  : domado del parcial 4·f0 (arco) y del 3er modo (láminas graves)
* desde      : render con --desde igual al render entero en ese tramo
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


# ============================================================ pruebas con criterio ==
class Chequeo:
    def __init__(self):
        self.filas = []

    def __call__(self, prueba, criterio, ok, valor=""):
        self.filas.append((prueba, criterio, bool(ok), valor))
        print(f"  [{'OK ' if ok else 'MAL'}] {prueba}: {criterio}  {valor}", flush=True)

    def resumen(self) -> bool:
        malos = [f for f in self.filas if not f[2]]
        print(f"\n{len(self.filas) - len(malos)}/{len(self.filas)} criterios OK")
        for f in malos:
            print(f"  MAL {f[0]}: {f[1]}  {f[3]}")
        return not malos


def _cancion_vacia(bpm=60, compas=(4, 4), compases=8):
    C = Cancion("prueba", "_prueba", bpm, compas=compas, semilla=3, cola_s=2.0)
    C.seccion("x", compases, 0.5, "x")
    return C


def _ctx(C, seg):
    from .mezcla import Contexto
    return Contexto(C, int(seg * SR), C.semilla, None)


BANCOS = {   # banco → (fábrica, tipo, ventana corta de la nivelación)
    "piano": (lambda: Piano(), "percusivo", 0.4), "arpa": (lambda: Arpa(), "percusivo", 0.4),
    "glock": (lambda: Glock(), "percusivo", 0.4), "vibrafono": (lambda: Vibrafono(), "percusivo", 0.4),
    "vibrafono_arco": (lambda: VibrafonoArco(), "arco", 0.4),
    "violines": (lambda: Violines(), "sostenido", 0), "violas": (lambda: Violas(), "sostenido", 0),
    "chelos": (lambda: Chelos(), "sostenido", 0), "contrabajo": (lambda: Contrabajo(), "sostenido", 0),
    "violines_trem": (lambda: CuerdasTrem("violines"), "sostenido", 0),
    "violas_trem": (lambda: CuerdasTrem("violas"), "sostenido", 0),
    "chelos_trem": (lambda: CuerdasTrem("chelos"), "sostenido", 0),
    "violines_pizz": (lambda: Pizzicato("violines"), "percusivo", 0.3),
    "chelos_pizz": (lambda: Pizzicato("chelos"), "percusivo", 0.3),
    "contrabajo_pizz": (lambda: Pizzicato("contrabajo"), "percusivo", 0.3),
}


def nivel_nota(inst, midi, vel, tipo, corta=0.4):
    """(lufs, energia, nivel) de una nota aislada, con la convención de NIVELES.md:
    sostenidos = nota de 8 s medida en 3–7 s (arco: 10 s en 3–8 s); percusivos = primeros 2 s
    (lufs con compuerta, energía K sin compuerta y la métrica de la nivelación)."""
    from .analisis import lufs, _potencia_k
    from .secuencia import Nota
    dur, (a, b) = {"sostenido": (8.0, (3.0, 7.0)), "arco": (10.0, (3.0, 8.0))}.get(tipo, (2.0, (0.0, 2.0)))
    C = _cancion_vacia()
    y = inst.render([Nota(0.0, dur, float(midi), float(vel), {})], _ctx(C, dur + 4.0), None)
    seg = y[int(a * SR): int(b * SR)]
    v = lufs(seg)
    if tipo != "percusivo":
        return v, v, v
    p = _potencia_k(y[: 2 * SR])
    h = int(0.005 * SR)
    e = p[: (SR // 2 // h) * h].reshape(-1, h).mean(axis=1)
    k = int(np.nonzero(e >= e.max() * 0.01)[0][0]) * h
    lk = lambda q: -0.691 + 10 * np.log10(q.mean() + 1e-30)  # noqa: E731
    return v, lk(p), 0.5 * (lk(p[k:k + int(corta * SR)]) + v)


def _residuos(ms, vs):
    out = []
    for k in range(len(ms)):
        if k == 0:
            ref = vs[1]
        elif k == len(ms) - 1:
            ref = vs[-2]
        else:
            f = (ms[k] - ms[k - 1]) / (ms[k + 1] - ms[k - 1])
            ref = vs[k - 1] + f * (vs[k + 1] - vs[k - 1])
        out.append(vs[k] - ref)
    return np.array(out)


def t_nivelacion(ch, rapido=False):
    sel = ["chelos", "violas", "piano", "vibrafono", "contrabajo_pizz"] if rapido else list(BANCOS)
    vels = (0.1, 0.3, 0.45, 0.6, 0.75, 0.85, 1.0)
    for nombre in sel:
        fab, tipo, corta = BANCOS[nombre]
        inst = fab()
        b = Banco.de(nombre)
        ms = sorted({int(round(m)) for i, m in enumerate(b.midi) if b.usable[i]})
        tabla = {m: {v: nivel_nota(inst, m, v, tipo, corta) for v in vels} for m in ms}
        # monotonía (energía: la compuerta de BS.1770 no es monótona si una capa trae más cola)
        peor = min((tabla[m][v2][1] - tabla[m][v1][1], m, v1, v2) for m in ms
                   for v1, v2 in zip(vels[:-1], vels[1:]))
        ch(nombre, "monotonía por velocidad (nunca baja más de 0,2 dB)", peor[0] > -0.2,
           f"peor {peor[0]:+.2f} dB en {peor[1]} ({peor[2]}→{peor[3]})")
        # suavidad entre muestras vecinas, en la métrica de la nivelación
        peor_r = max((abs(r), m, v) for v in (0.3, 0.6, 0.85)
                     for r, m in zip(_residuos(ms, [tabla[m][v][2] for m in ms]), ms))
        ch(nombre, "residuo entre muestras vecinas ≤ 1,5 dB", peor_r[0] <= 1.5,
           f"máx {peor_r[0]:.2f} dB en {peor_r[1]} a vel {peor_r[2]}")
        cal = float(np.median([tabla[m][0.6][0] for m in ms]))
        ch(nombre, "calibración: vel 0,6 = −26 LUFS (±1)", abs(cal + 26.0) <= 1.0, f"{cal:.2f} LUFS")
        # capas: la suave suena menos que la fuerte (a igual velocidad)
        if b.n_capas > 1:
            inst_c = fab()
            d = []
            for m in ms[:: max(1, len(ms) // 4)]:
                lv = []
                for capas_vel in ((2.0, 3.0), (-3.0, -2.0)):     # solo la capa suave / solo la fuerte
                    inst_c.capas_vel = capas_vel
                    lv.append(nivel_nota(inst_c, m, 0.6, tipo, corta)[1])
                d.append(lv[1] - lv[0])
            ch(nombre, "capa suave < fuerte (diferencia 5–12 dB)", all(5.0 <= x <= 12.0 for x in d),
               " ".join(f"{x:.1f}" for x in d) + " dB")


def t_parser(ch):
    from .secuencia import melodia
    n, largo = melodia("[D4 F#4 A4]/2 E5/1 [C#4 E4]/0.5! r/0.5 | [A3 E4]_ B4/4", 0.6, 4.0)
    ch("parser", "acorde de 3 notas a la vez", [(x[0], x[1], x[2]) for x in n[:3]] ==
       [(0.0, 2.0, 62), (0.0, 2.0, 66), (0.0, 2.0, 69)], [(x[0], x[1], x[2]) for x in n[:3]])
    ch("parser", "sufijos y barra en acordes (! y _)", abs(n[4][3] - 0.75) < 1e-9 and n[-1][4] == {"legato": True}
       and largo == 8.5, f"vel {n[4][3]}, ligado {n[-1][4]}, largo {largo}")
    try:
        melodia("[D4 F#4 A4/2")
        ch("parser", "acorde sin cerrar da un error claro", False, "no dio error")
    except ValueError as e:
        ch("parser", "acorde sin cerrar da un error claro", "sin cerrar" in str(e), str(e)[:60])
    C = _cancion_vacia(bpm=90)
    y = nube(Piano(), "[D3 A3 E4]/2 [D4 F#4 A4]/2", dur_s=4.0, estirar=4.0)(_ctx(C, 30))
    ch("parser", "nube() con acordes suena", float(np.abs(y).max()) > 1e-3, f"pico {float(np.abs(y).max()):.3f}")


def _render_stem(instrumento, notas_fn, seg=6.0, bpm=60):
    C = _cancion_vacia(bpm=bpm)
    p = C.pista("x", instrumento, "melodia")
    notas_fn(p)
    ns = p.notas_humanizadas()
    y = instrumento.render(ns, _ctx(C, seg), p)
    ons = np.array(sorted(float(C.tempo.seg(n.t)) for n in ns))
    return y, ons


def t_clicks(ch):
    from .analisis import detectar_clicks
    # falsos positivos: celesta con martillo, grave, sobre silencio; vibráfono con baquetas
    def cel(p):
        for k, m in enumerate(("C4", "E4", "D4", "G4", "C4", "A4")):
            p.nota(1 + k * 0.25, m, 0.5, vel=0.6)
    y, ons = _render_stem(Celesta(golpe=0.4), cel, 8.0)

    def vib(p):
        for k, m in enumerate(("A3", "C#4", "E4", "G#3", "B3", "A4")):
            p.nota(1 + k * 0.25, m, 0.4, vel=0.7)
    y2, ons2 = _render_stem(Vibrafono(), vib, 8.0)
    sin = len(detectar_clicks(y)) + len(detectar_clicks(y2))
    con = len(detectar_clicks(y, ataques=ons)) + len(detectar_clicks(y2, ataques=ons2))
    ch("clicks", "sin falsos positivos en ataques (celesta grave, vibráfono)", con == 0,
       f"{con} con la lista de notas (sin ella: {sin})")
    # verdaderos: empalme roto en una nota sostenida, lejos de los ataques
    def sost(p):
        p.nota(1, "A3", 4, vel=0.6).nota(1, "E4", 4, vel=0.5)
    z, ons3 = _render_stem(Chelos(), sost, 7.0)
    i = int(2.7 * SR)
    roto = z.copy()
    roto[i:] = z[i - 211: len(z) - 211]           # el empalme salta 211 muestras de la fuente
    ev = detectar_clicks(roto, ataques=ons3)
    ch("clicks", "detecta un empalme roto en un sostenido", any(abs(t - i / SR) < 0.005 for t in ev),
       f"eventos {ev[:4]}")
    # verdaderos: escalón justo en un ataque (muestra que arranca sin fundido) y corte seco
    esc = y2.copy()
    j = int(ons2[2] * SR) + 40
    esc[j:] += np.float32(0.02)
    ev = detectar_clicks(esc, ataques=ons2)
    ch("clicks", "detecta un escalón dentro de una ventana de ataque", any(abs(t - j / SR) < 0.005 for t in ev),
       f"eventos {ev[:4]}")
    corte = z.copy()
    k = int(3.3 * SR)
    k += int(np.argmax(np.abs(z[k:k + int(0.01 * SR)]).max(axis=1)))   # un corte donde hay señal
    corte[k:k + int(0.3 * SR)] = 0.0
    ev = detectar_clicks(corte, ataques=ons3)
    ch("clicks", "detecta un corte seco", any(abs(t - k / SR) < 0.005 for t in ev), f"eventos {ev[:4]}")


def _ciclos(y, t0, n=3):
    seg = y[int(t0 * SR): int((t0 + 0.25) * SR), 0]
    z = np.nonzero((seg[:-1] < 0) & (seg[1:] >= 0))[0]
    return [SR / d for d in np.diff(z)[:n]]


def t_glide(ch):
    from .secuencia import Nota
    C = _cancion_vacia()
    sep = [Nota(1.0, 0.9, 38.0, 0.7, {}), Nota(2.0, 0.9, 45.0, 0.7, {})]
    lig = [Nota(5.0, 1.0, 38.0, 0.7, {}), Nota(6.0, 1.0, 45.0, 0.7, {"legato": True})]
    y = Sub(glide_ms=40).render(sep + lig, _ctx(C, 9), None)
    f_sep, f_lig = _ciclos(y, 2.0), _ciclos(y, 6.0)
    ch("glide", "nota no ligada: llega a su altura en el acto (≥ 95 % en el 1er ciclo)",
       f_sep[0] >= 0.95 * 110.0, f"{[round(f, 1) for f in f_sep]} Hz (destino 110)")
    ch("glide", "nota ligada: desliza desde la anterior (1er ciclo < 85 %)",
       f_lig[0] < 0.85 * 110.0 and f_lig[-1] > f_lig[0], f"{[round(f, 1) for f in f_lig]} Hz (sale de 73,4)")
    def rms(v):
        z = Sub().render([Nota(1.0, 2.0, 38.0, v, {})], _ctx(C, 4), None)
        return 20 * np.log10(np.sqrt(np.mean(z[int(1.5 * SR): int(2.5 * SR)] ** 2)))
    d = rms(0.78) - rms(0.5)
    ch("glide", "Sub conserva la dinámica (vel 0,5 → 0,78 ≈ +3,9 dB)", 2.9 <= d <= 4.9, f"{d:+.2f} dB")


def _parcial_db(y, f0, razon, t0, t1):
    seg = y[int(t0 * SR): int(t1 * SR)].mean(axis=1)
    nfft = 1 << 17
    mag = 20 * np.log10(np.abs(np.fft.rfft(seg * np.hanning(len(seg)), nfft)) + 1e-12)
    f = np.fft.rfftfreq(nfft, 1 / SR)
    pico = lambda fc: mag[(f > fc * 0.97) & (f < fc * 1.03)].max()  # noqa: E731
    return pico(razon * f0) - pico(f0)


def t_vibrafono(ch):
    from .secuencia import Nota
    C = _cancion_vacia()
    f0 = 440 * 2 ** ((74 - 69) / 12)
    crudo = VibrafonoArco(domar=0).render([Nota(0, 6, 74.0, 0.6, {})], _ctx(C, 9), None)
    domado = VibrafonoArco().render([Nota(0, 6, 74.0, 0.6, {})], _ctx(C, 9), None)
    d4 = _parcial_db(crudo, f0, 4, 2, 5) - _parcial_db(domado, f0, 4, 2, 5)
    ch("vibrafono", "arco: el parcial 4·f0 (Re5 → 2,35 kHz) baja ≥ 9 dB", d4 >= 9.0, f"−{d4:.1f} dB")
    b = Banco.de("vibrafono")
    i = b.elegir(57, 1)
    razon = b.muestras[i]["modos"]["m3"]["razon"]
    f0 = 220.0
    n = [Nota(0, 2, 57.0, 0.9, {})]
    m_crudo = _parcial_db(Vibrafono(motor_hz=0, domar=0).render(n, _ctx(C, 4), None), f0, razon, 0.01, 0.3)
    m_dom = _parcial_db(Vibrafono(motor_hz=0).render(n, _ctx(C, 4), None), f0, razon, 0.01, 0.3)
    ch("vibrafono", "La3: el 3er modo (10,7·f0 = 2,36 kHz) queda ≤ −25 dB de la fundamental",
       m_dom <= -25.0, f"{m_crudo:+.1f} → {m_dom:+.1f} dB")
    ch("vibrafono", "La3 de vibrafono_arco excluida (no se elige nunca)",
       all(int(round(Banco.de("vibrafono_arco").midi[Banco.de("vibrafono_arco").elegir(m, 0)])) != 57
           for m in range(50, 62)), "")


def t_desde(ch):
    C = _cancion_vacia(bpm=90, compases=8)
    C.progresion(1, "Dmaj9 | E/D | Bm11 | Gmaj13#11 | Dmaj9 | E/D | Bm11 | Gmaj13#11")
    pi = C.pista("piano", Piano(), "armonia", envios={"reverb": 0.3})
    pad = C.pista("pad", Pad(), "armonia", envios={"reverb": 0.2})
    for t0, t1, _s, v in C.voicings(1, 9, voces=4, rango=("E3", "B4")):
        pi.acorde(C.c(t0), v, t1 - t0, vel=0.45, rasgueo=0.02)
    pi.pedal_por_compas(1, 9)
    pad.acordes_ligados(C.voicings(1, 9, voces=4, rango=("E3", "E5")), vel=0.5)
    sub = C.pista("sub", Sub(glide_ms=30), "bajo")      # oscilador continuo: fase de nota en nota
    for t0, t1, _s, b in C.bajos(1, 9, rango=("A1", "G#2")):
        sub.nota(C.c(t0), b, t1 - t0 - 0.3, vel=0.7)
    entero = render_cancion(C, escribir=False, qa=False, niveles=False)
    tramo = render_cancion(C, escribir=False, qa=False, niveles=False, desde_compas=5, preroll_s=8.0)
    i0 = int(round(C.tempo.seg(C.tempo.pos(5)) * SR))
    for st in ("armonia", "bajo"):
        a = entero["stems"][st][i0 + int(0.05 * SR):]
        b = tramo["stems"][st][int(0.05 * SR):]
        n = min(len(a), len(b)) - int(1.6 * SR)       # sin el fundido final
        # sin la ganancia de margen común (sale del pico de lo renderizado: difiere en un tramo)
        a = a[:n].astype(np.float64) / 10 ** (entero["ganancia_db"] / 20)
        b = b[:n].astype(np.float64) / 10 ** (tramo["ganancia_db"] / 20)
        err = 20 * np.log10(np.sqrt(np.mean((a - b) ** 2)) / np.sqrt(np.mean(a ** 2)))
        ch("desde", f"--desde 5 igual al render entero en ese tramo ({st}: error < −40 dB)", err < -40.0,
           f"{err:.1f} dB (margen: {entero['ganancia_db'] - tramo['ganancia_db']:+.2f} dB)")


TESTS = {"nivelacion": t_nivelacion, "parser": t_parser, "clicks": t_clicks, "glide": t_glide,
         "vibrafono": t_vibrafono, "desde": t_desde}


def tests(nombres, rapido=False) -> bool:
    ch = Chequeo()
    for nm in (nombres or list(TESTS)):
        t0 = time.time()
        print(f"\n== {nm}", flush=True)
        if nm == "nivelacion":
            TESTS[nm](ch, rapido=rapido)
        else:
            TESTS[nm](ch)
        print(f"   ({time.time() - t0:.0f} s)")
    return ch.resumen()


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "tests":
        rap = "--rapido" in args
        sys.exit(0 if tests([a for a in args[1:] if not a.startswith("--")], rapido=rap) else 1)
    main(args)
