"""«Espiral» — canción 4: tensión e intriga. Un problema, una pregunta, algo que no cierra.

Fa# menor con color frigio de Do# (el Re natural sobre el Do#), 96 bpm, 4/4,
72 compases + cola ≈ 3:10.

La idea es una cuña: el bajo baja por semitonos (lamento: Fa#–Fa–Mi–Re#–Re–Do#)
mientras un ostinato de piano apagado sube en secuencia. El ostinato es una célula
de 7 corcheas sobre compases de 8: nunca cierra con el compás, cada compás empieza
en otro punto del giro. Cada vuelta de 8 compases arranca un escalón más arriba y
suma una capa. Debajo late un Do# en corcheas (pizzicato, acentos 3+3+2): es la
pregunta. Todos los acordes de la canción contienen ese Do#; al final, cuando la
armonía se abre a La mayor (la relativa), el mismo Do# pasa a ser la tercera del
acorde, el Re que colgaba toda la canción baja por fin a Do#, y la célula del
ostinato se vuelve de 8 pasos: la espiral cierra.

Forma (compases):
   1–8   pregunta   mecánica del piano (3+3+2), trémolo grave, pulso de Do#, vibráfono con arco
   9–16  vuelta 1   entra la espiral (La3–La4); bajo cromático en pizzicato        [bajo voz]
  17–24  vuelta 2   la espiral sube un escalón; sub en pulsos, tic-tac de hats y aro [bajo voz]
  25–32  vuelta 3   ciclo de Si menor (la célula transpuesta a la 4ª); bombo, pad  [bajo voz]
  33–40  grieta     pedal de Do#: la espiral se rompe en fragmentos y se rearma     [bajo voz]
  41–48  vuelta 4   ciclo A una octava arriba, con canon de pizzicato             [bajo voz]
  49–56  vuelta 5   ciclo B; los violines estiran la pregunta en notas largas       [bajo voz]
  57–64  vórtice    todo gira: melodía de violines, lamento de chelos, caja suave
  65–72  claro      cadencia rota a Re y apertura a La mayor; el pulso se frena

Recursos que nacieron en esta canción y hoy están en el motor: Mecanica (la mecánica del
piano como percusión), VibrafonoArco (vibráfono con arco, nivelado), espiral()/columna()
(el ostinato por índices sobre columnas de alturas) y nube_acordes (la espiral que se deshace).

Mezcla rehecha para la nivelación nueva del motor (NIVELES.md): las capas suaves ya no están
subidas, así que las pistas que tocan a velocidad baja (pulso, trémolos, pizzicatos, cuerdas
bajo voz, vibráfonos) llevan su compensación en `vol` o en automatizaciones de volumen.
"""
from __future__ import annotations

from motor import (Cancion, Piano, Vibrafono, VibrafonoArco, Glock, Pad, Dron, Sub, Violines,
                   Chelos, Contrabajo, CuerdasTrem, Pizzicato, Bateria, Mecanica, Textura, swell,
                   nube_acordes, espiral, columna, EQ, Ducking, Compresor, Saturacion, Ancho)
from motor.figuras import pasos_espiral

# =============================================================== 1. DATOS ==
BPM = 96
SEMILLA = 4404

SECCIONES = [
    # nombre      compases energía emoción                                       bajo voz loop
    ("pregunta",   8, 0.16, "intriga: algo no cierra",                         False, (5, 9)),
    ("vuelta_1",   8, 0.28, "la pregunta insiste",                             True,  (9, 17)),
    ("vuelta_2",   8, 0.38, "se enrosca: aparecen más dudas",                  True,  (17, 25)),
    ("vuelta_3",   8, 0.48, "el problema crece",                               True,  (25, 33)),
    ("grieta",     8, 0.32, "suspenso: el piso se abre",                       True,  (33, 37)),
    ("vuelta_4",   8, 0.58, "todo vuelve a girar, más arriba",                 True,  (41, 49)),
    ("vuelta_5",   8, 0.68, "urgencia contenida",                              True,  (49, 57)),
    ("vortice",    8, 0.86, "vértigo: la espiral en su punto más alto",        False, (57, 65)),
    ("claro",      8, 0.30, "se resuelve: la pregunta encuentra su respuesta", False, (69, 73)),
]

# Un acorde por compás. El Do# está en todos (es el pulso).
ARMONIA = {
    1:  "F#m(add9) | F#m(add9) | F#m(add9) | F#m(add9) | Dmaj7#11 | Dmaj7#11 | C#7sus4 | C#7sus4b9",
    9:  "F#m(add9) | F#mmaj9/F | F#m9/E | D#ø7 | Dmaj7#11 | Dmaj7#11 | C#7sus4 | C#7sus4b9",
    17: "F#m(add9) | F#mmaj9/F | F#m9/E | D#ø7 | Dmaj7#11 | Bm9/D | C#7sus4 | C#7sus4b9",
    25: "Bm9 | Bmmaj9/A# | Bm9/A | G#ø7 | Gmaj7#11 | Gmaj7#11 | C#7sus4 | C#7sus4b9",
    33: "C#7sus4b9 | Dmaj7#11/C# | C#7sus4b9 | Dmaj7#11/C# | C#7sus4b9 | Dmaj7#11/C# | Bm9/C# | C#7sus4b9",
    41: "F#m(add9) | F#mmaj9/F | F#m9/E | D#ø7 | Dmaj7#11 | Bm9/D | C#7sus4 | C#7sus4b9",
    49: "Bm9 | Bmmaj9/A# | Bm9/A | G#ø7 | Gmaj7#11 | Gmaj7#11 | C#7sus4 | C#7sus4b9",
    57: "F#m(add9) | F#mmaj9/F | F#m9/E | D#ø7 | Dmaj7#11 | Gmaj7#11 | C#7sus4 | C#7b9",
    65: "Dmaj9 | Bm11 | E7sus4 | E7 | Amaj9 | Amaj9 | Dmaj9/A | A6/9",
}

# ---- Columnas del ostinato: alturas (desde La3) entre las que gira la espiral.
# A = {Fa#, Sol#, La, Do#} sirve a TODO el ciclo A (el bajo cromático cambia debajo);
# B es la misma figura una 4ª arriba (secuencia real) y trae el semitono frigio Do#–Re.
COLUMNAS = {
    "A": ("F#", "G#", "A", "C#"),     # F#m(add9) · /F · /E · D#ø · Dmaj7#11 · C#7sus4(b13)
    "B": ("B", "C#", "D", "F#"),      # Bm9 · Bmmaj9/A# · G#ø7(11) · Gmaj7#11 · C#7sus4b9
    "P": ("C#", "D", "F#", "A"),      # pedal de Do#: Dmaj7 sobre Do#
    "D": ("B", "D", "E#", "G#"),      # C#7b9: el disminuido, máxima tensión
    "R": ("C#", "E", "F#", "A"),      # claro: Dmaj9 · Bm11 · E7sus4
    "R5": ("B", "D", "E", "G#"),      # E7
    "RA": ("A", "B", "C#", "E"),      # Amaj9 / A6/9
}
COL_COMPAS = {}
for _c in range(1, 25):
    COL_COMPAS[_c] = "A"
for _c in range(25, 33):
    COL_COMPAS[_c] = "B"
for _c in range(33, 41):
    COL_COMPAS[_c] = "P"
for _c in range(41, 49):
    COL_COMPAS[_c] = "A"
for _c in range(49, 57):
    COL_COMPAS[_c] = "B"
for _c in range(57, 62):
    COL_COMPAS[_c] = "A"
COL_COMPAS.update({62: "B", 63: "B", 64: "D", 65: "R", 66: "R", 67: "R", 68: "R5",
                   69: "RA", 70: "RA", 71: "R", 72: "RA"})

# Célula de la espiral: zigzag que sube (2 arriba, 1 abajo) en 7 pasos de corchea.
P7 = "0 2 1 3 2 4 3"
# En el claro se vuelve de 8 pasos, baja, y coincide con el compás: cierra.
P8_CIERRA = "6 4 5 3 4 2 3 1"

# ---- La pregunta (vibráfono): sube y queda colgada en el Re (b9 sobre Do#).
PREGUNTA = "r/2 G#4/0.5 A4/0.5 C#5/1 | D5/3 r/1"
PREGUNTA_2 = "r/2 A4/0.5 C#5/0.5 F#5/1 | D5/3 r/1"
PREGUNTA_3 = "r/2 F#4/0.5 G#4/0.5 C#5/1 | D5/2 r/2"
# ---- La respuesta (claro): el mismo gesto; el Re baja a Do# sobre La mayor.
RESPUESTA = "r/2 G#4/0.5 A4/0.5 C#5/1 | D5/4 | C#5/4"

# ---- Violines: la pregunta estirada (vuelta 5, bajo voz: notas largas en la octava 5).
VL_V5 = "C#5/8_ D5/8_ F#5/8_ G#5/4_ D5/4"
# ---- Vórtice: secuencia que sube (nota larga + dos corcheas) y cae a Mi# (3ª del V).
VL_VORTICE = ("C#5/3_ D5/0.5_ E5/0.5_ | F#5/3_ G#5/0.5_ A5/0.5_ | G#5/3_ A5/0.5_ B5/0.5_ | "
              "C#6/3_ B5/0.5_ A5/0.5_ | C#6/2_ G#5/2_ | B5/2_ D6/2_ | C#6/2_ B5/1_ G#5/1_ | "
              "E#5/3_ D5/0.5_ E#5/0.5")
# ---- Chelos: el lamento cromático cantado (vórtice).
VC_VORTICE = "F#3/4_ | F3/4_ | E3/4_ | D#3/4_ | D3/4_ | B2/4_ | C#3/4_ | C#3/4"
# ---- Claro: el Re de la pregunta resuelve en Do# (violines) sobre una línea cálida de chelos.
VL_CLARO = "F#5/4_ | F#5/2_ E5/2_ | E5/2_ D5/2_ | D5/4_ | C#5/4_ | C#5/4_ | B4/2_ C#5/2_ | C#5/4"
VC_CLARO = "A3/4_ | D4/2_ C#4/2_ | B3/4_ | G#3/4_ | A3/4_ | E4/2_ C#4/2_ | D4/4_ | E4/4"

TRESILLO = (0.0, 1.5, 3.0)           # 3+3+2 en corcheas: el ADN rítmico de la canción
ACENTOS_332 = (1.25, 0.8, 0.85, 1.15, 0.8, 0.85, 1.1, 0.82)

# ---- Batería (semicorcheas): tic (hat cerrado en el contratiempo) y tac (aro en 2 y 4).
GROOVE = {
    "tic":     {"hat": "..x. ..x. ..x. ..x."},
    "tictac":  {"hat": "..x. ..x. ..x. ..x.", "aro": ".... x... .... x...",
                "shaker": "3121 3121 3121 3131"},
    "v3":      {"bombo": "x.....x.....x...", "hat": "..x. ..x. ..x. ..x.",
                "aro": ".... x... .... x..o", "shaker": "4231 4231 4231 4232"},
    "v4":      {"bombo": "x.....x.....x...", "hat": "x.x. x.x. x.x. x.x.",
                "aro": ".... x... .... x...", "aro_f": "..o. ...o .o.. ..o.",
                "shaker": "4232 4232 4232 4233"},
    "v5":      {"bombo": "x.....x.....x.x.", "hat": "4252 4252 4252 4262",
                "aro": ".... x... .... x...", "esc_f": "..o. ...o ..o. .o..",
                "shaker": "4232 4232 4232 4233"},
    "vortice": {"bombo": "x.....x.....x...", "caja": ".... x... .... x...",
                "hat": "5.4. 5.4. 5.4. 5.5.", "esc_f": "..o. ...o ..o. .o.o",
                "shaker": "5454 5454 5454 5464"},
}


# ================================================================ 2. AYUDAS ===
def cols(compas: int) -> list[int]:
    """Columna de alturas (desde La3) entre las que gira la espiral en ese compás."""
    return columna(COLUMNAS[COL_COMPAS[compas]])


def notas_espiral(C, desde, hasta, desplaz=0, vel=0.45, dur=0.42):
    """Las notas del ostinato con tiempos relativos al compás `desde` (para nube_acordes)."""
    t0 = (desde - 1) * C.tempo.tpc
    return [(t - t0, dur, m, vel) for t, _c, _k, m in pasos_espiral(C.tempo, desde, hasta, cols,
                                                                     desplaz=desplaz)]


def pulso(p, desde, hasta, alturas=("C#4",), vel=0.3, figura=0.5, dur=0.36,
          acentos=ACENTOS_332, cresc=(1.0, 1.0), solo_acentos=False, **x):
    """El pulso insistente: Do# repetido (pizzicato apagado), acentos 3+3+2."""
    t, t_fin = (desde - 1) * 4.0, (hasta - 1) * 4.0
    t_a = t
    k = 0
    while t < t_fin - 1e-9:
        ac = acentos[k % len(acentos)]
        if not solo_acentos or ac > 1.0:
            f = (t - t_a) / max(1e-9, t_fin - t_a)
            v = vel * ac * (cresc[0] + (cresc[1] - cresc[0]) * f)
            for a in alturas:
                p.nota(1 + t / 4.0, a, dur, vel=min(1.0, v), apagar=True, **x)
        t += figura
        k += 1


def bajo_332(p, C, desde, hasta, rango=("G1", "F#2"), vel=0.7, durs=(1.25, 1.25, 0.85),
             golpes=TRESILLO, octava=0, **x):
    """Sub (o pizzicato) en pulsos 3+3+2 sobre el bajo de cada compás."""
    for t0, t1, _s, b in C.bajos(desde, hasta, rango=rango):
        for j, off in enumerate(golpes):
            if t0 + off < t1 - 1e-6:
                d = min(durs[j % len(durs)], t1 - (t0 + off) - 0.06)
                p.nota(C.c(t0 + off), b + octava, d, vel=vel * (1.0 if j == 0 else 0.86), **x)


def trem_linea(p, C, desde, hasta, octava=12, rango=("G1", "F#2"), v0=0.16, v1=0.36):
    """Trémolo de chelos sobre la línea del bajo (una 8va arriba): respira cada 2 compases."""
    for k, (t0, t1, _s, b) in enumerate(C.bajos(desde, hasta, rango=rango)):
        a, z = (v0, v1) if k % 2 == 0 else (v1, v0)
        p.nota(C.c(t0), b + octava, t1 - t0, vel=a, vel_fin=z, legato=k > 0)


def groove(bat, nombre, desde, hasta, solo=None, sin=(), escala=1.0):
    """Toca un groove de GROOVE; `escala` sube o baja el groove entero (dígitos incluidos)."""
    g = GROOVE[nombre]
    vel = {"bombo": 0.62, "aro": 0.44, "aro_f": 0.44, "escobilla": 0.5, "esc_f": 0.5,
           "caja": 0.5, "hat": 0.4, "shaker": 0.6}
    for k, patron in g.items():
        if (solo and k not in solo) or k in sin:
            continue
        golpe = {"aro_f": "aro", "esc_f": "escobilla"}.get(k, k)
        bat.patron(golpe, patron, desde, hasta, vel=vel[k], escala=escala)


# ============================================================ 3. CANCIÓN ==
def cancion() -> Cancion:
    C = Cancion("Espiral", slug="04-espiral", bpm=BPM, compas=(4, 4),
                tonalidad="Fa# menor (frigio de Do#)", semilla=SEMILLA, cola_s=9.0)
    for nom, comp, e, emo, voz, loop in SECCIONES:
        C.seccion(nom, comp, energia=e, emocion=emo, voz=voz, loop=loop)
    for c, prog in ARMONIA.items():
        C.progresion(c, prog)
    C.ritardando(71, 73, 84)           # el reloj se frena
    C.fx["reverb"].update(dur=3.6, predelay_ms=28, brillo=0.42)
    C.fx["eco"].update(division=0.75, realim=0.32, corte=2600.0)

    # ---------------------------------------------------------------- pistas
    mec = C.pista("mecanica", Mecanica(pb_hz=3000.0, pan=0.18), "bateria", vol=-8.0,
                  envios={"sala": 0.2, "reverb": 0.12},
                  efectos=[EQ(("pa", 36), ("campana", 280, -3.0, 1.0))])
    bat = C.pista("bateria", Bateria(color=0.4), "bateria", vol=0.0,
                  envios={"sala": 0.16, "reverb": 0.05},
                  efectos=[EQ(("campana", 2600, -2.5, 0.9)),
                           Compresor(umbral_db=-26, ratio=2.2, ataque_ms=12, relaj_ms=150, mezcla=0.4),
                           Saturacion(drive_db=2.5, mezcla=0.3)])
    sub = C.pista("sub", Sub(drive_db=6, octava=0.15), "bajo", vol=0.0,
                  efectos=[Ducking(prof_db=2.5, relaj_ms=170)])
    pizz_cb = C.pista("pizz_cb", Pizzicato("contrabajo"), "bajo", vol=-4.0,
                      envios={"reverb": 0.1}, efectos=[EQ(("pa", 35), ("pb", 2400))])
    cbajo = C.pista("contrabajo", Contrabajo(), "bajo", vol=-3.6, envios={"reverb": 0.14},
                    efectos=[EQ(("pa", 35), ("pb", 3000))])
    piano = C.pista("piano", Piano(fieltro=0.85, brillo=0.35, mecanica=0.6), "armonia", vol=2.0,
                    envios={"reverb": 0.18, "eco": 0.04},
                    efectos=[EQ(("pa", 80), ("campana", 300, -3.0, 0.9))])
    piano_ab = C.pista("piano_abierto", Piano(fieltro=0.55, mecanica=0.5), "armonia", vol=2.0,
                       envios={"reverb": 0.26, "eco": 0.04},
                       efectos=[EQ(("pa", 45), ("campana", 320, -2.0, 0.8))])
    pul = C.pista("pulso", Pizzicato("chelos"), "armonia", vol=2.4,
                  envios={"reverb": 0.12, "sala": 0.1},
                  efectos=[EQ(("pa", 160), ("campana", 290, -3.0, 1.1), ("pb", 3600))])
    pizz_vl = C.pista("pizz_vl", Pizzicato("violines"), "armonia", vol=4.6,
                      envios={"reverb": 0.2, "eco": 0.06},
                      efectos=[EQ(("pa", 180), ("campana", 2800, -2.0, 1.0), ("pb", 4200))])
    pizz_ac = C.pista("pizz_acentos", Pizzicato("violines"), "armonia", vol=2.8,
                      envios={"reverb": 0.2, "eco": 0.06},
                      efectos=[EQ(("pa", 180), ("campana", 2800, -2.0, 1.0), ("pb", 4200))])
    trem_vc = C.pista("trem_vc", CuerdasTrem("chelos"), "armonia", vol=6.0,
                      envios={"reverb": 0.22}, efectos=[EQ(("pa", 45), ("pb", 5000))])
    trem_va = C.pista("trem_va", CuerdasTrem("violas"), "armonia", vol=1.3,
                      envios={"reverb": 0.28}, efectos=[EQ(("pa", 150), ("pb", 6000))])
    violines = C.pista("violines", Violines(doble=True), "melodia", vol=7.0,
                       envios={"reverb": 0.34},
                       efectos=[EQ(("pa", 170), ("campana", 3200, -2.5, 0.9), ("pb", 11000))])
    chelos = C.pista("chelos", Chelos(), "armonia", vol=1.5, envios={"reverb": 0.28},
                     efectos=[EQ(("pa", 50))])
    vibes = C.pista("vibrafono", Vibrafono(motor_hz=2.2, motor_prof=0.25), "melodia", vol=0.5,
                    envios={"reverb": 0.36, "eco": 0.1},
                    efectos=[EQ(("pa", 120))])
    arco = C.pista("arco", VibrafonoArco(), "melodia", vol=-7.5, envios={"reverb": 0.32},
                   efectos=[EQ(("pa", 140), ("pb", 3600))])
    glock = C.pista("glock", Glock(), "melodia", vol=-0.5, envios={"reverb": 0.42, "eco": 0.15},
                    efectos=[EQ(("agudos", 7000, -3.0))])
    pad = C.pista("pad", Pad(voces=6, desafinar=12, sub=0.0, ataque=2.5, soltar=3.5, pa=150,
                             respira=0.3), "armonia", vol=-7.0, envios={"reverb": 0.18},
                  efectos=[EQ(("campana", 320, -2.0, 0.9)), Ducking(prof_db=2.0, relaj_ms=200)])
    dron = C.pista("dron", Dron(corte=520, aire=0.12), "textura", vol=-4.0, envios={"reverb": 0.2})
    tex = C.pista("textura", Textura(), "textura", vol=0.0, envios={"reverb": 0.12},
                  efectos=[Ancho(ancho=0.75)])

    # humanización (determinista)
    mec.humanizar(tiempo_ms=9, vel=0.14)
    bat.humanizar(tiempo_ms=6, vel=0.1, swing=0.53, swing_div=0.25)
    sub.humanizar(tiempo_ms=3, vel=0.04)
    pizz_cb.humanizar(tiempo_ms=6, vel=0.06)
    piano.humanizar(tiempo_ms=6, vel=0.06)
    piano_ab.humanizar(tiempo_ms=10, vel=0.06)
    pul.humanizar(tiempo_ms=5, vel=0.07)
    pizz_vl.humanizar(tiempo_ms=7, vel=0.07)
    pizz_ac.humanizar(tiempo_ms=7, vel=0.07)
    vibes.humanizar(tiempo_ms=6, vel=0.05)
    for p in (trem_vc, trem_va, violines, chelos, cbajo):
        p.humanizar(tiempo_ms=12, vel=0.04)
    glock.humanizar(tiempo_ms=5, vel=0.05)

    # ------------------------------------------------------- 1–8 pregunta
    # la mecánica del piano marca el 3+3+2 (el ADN rítmico) y el pedal late cada 2 compases
    mec.patron("apagador", "x.....x.....x...", 1, 5, vel=0.5, altura=73)
    mec.patron("apagador", "x.....x.....x..o", 5, 9, vel=0.55, altura=73)
    for c in (1, 3, 5, 7):
        mec.golpe(c, "pedal", 0.6)
    # trémolo grave en quintas vacías que respira
    trem_vc.nota(1, "F#2", 16, vel=0.1, vel_fin=0.28).nota(1, "C#3", 16, vel=0.08, vel_fin=0.25)
    trem_vc.nota(5, "D3", 8, vel=0.3, vel_fin=0.2, legato=True)
    trem_vc.nota(5, "A3", 8, vel=0.26, vel_fin=0.18, legato=True)
    trem_vc.nota(7, "C#3", 8, vel=0.2, vel_fin=0.31, legato=True)
    trem_vc.nota(7, "G#3", 8, vel=0.18, vel_fin=0.28, legato=True)
    # el pulso de Do# (la pregunta) aparece en el 3
    pulso(pul, 3, 9, vel=0.26, cresc=(0.85, 1.05))
    # vibráfono con arco: Do#5 que aparece... y se corre al Re (b9 sobre Do#)
    arco.nota(3, "C#5", 16, vel=0.5).nota(7, "D5", 8, vel=0.51)
    vibes.melodia(7, PREGUNTA, vel=0.35)
    vibes.pedal(7, 8.95)
    tex.clip(swell(Piano(fieltro=0.6), ["F#2", "C#3", "A3", "G#4", "C#5"], largo_tiempos=8,
                   vel=0.5), fin=9, ganancia_db=-18)

    # ------------------------------------------------------- 9–16 vuelta 1
    espiral(piano, 9, 17, cols, desplaz=0, vel=0.34)
    pulso(pul, 9, 17, vel=0.28)
    for t0, t1, _s, b in C.bajos(9, 17, rango=("G1", "F#2")):        # bajo cromático
        pizz_cb.nota(C.c(t0), b, 3.4, vel=0.5, apagar=True, soltar=0.35)
    trem_linea(trem_vc, C, 9, 17, v0=0.14, v1=0.3)
    mec.patron("apagador", "x.....x.....x...", 9, 13, vel=0.42, altura=73)
    mec.patron("apagador", "......x.......o.", 13, 17, vel=0.4, altura=73)
    groove(bat, "tictac", 13, 17, solo=("shaker",))
    vibes.melodia(15, PREGUNTA_3, vel=0.33)
    vibes.pedal(15, 16.95)

    # ------------------------------------------------------- 17–24 vuelta 2
    espiral(piano, 17, 25, cols, desplaz=1, vel=0.35)
    pulso(pul, 17, 25, vel=0.3)
    pulso(pizz_ac, 21, 25, alturas=("C#5",), vel=0.2, solo_acentos=True)
    bajo_332(sub, C, 17, 25, vel=0.5)
    bajo_332(pizz_cb, C, 17, 25, vel=0.46, golpes=(0.0, 1.5), durs=(1.3, 1.3), apagar=True)
    trem_linea(trem_vc, C, 17, 25, v0=0.18, v1=0.36)
    trem_va.acordes_ligados(C.voicings(21, 25, voces=2, rango=("A3", "E5")), vel=0.3)
    groove(bat, "tic", 17, 21)
    groove(bat, "tictac", 21, 25)
    vibes.melodia(23, PREGUNTA_2, vel=0.33)
    vibes.pedal(23, 24.95)

    # ------------------------------------------------------- 25–32 vuelta 3
    tex.clip(swell(Piano(fieltro=0.6), ["B2", "F#3", "D4", "C#5"], largo_tiempos=6, vel=0.5),
             fin=25, ganancia_db=-14)
    espiral(piano, 25, 33, cols, desplaz=2, vel=0.37)
    pulso(pul, 25, 33, vel=0.31)
    pulso(pizz_ac, 29, 33, alturas=("C#5",), vel=0.22, solo_acentos=True)   # a mitad de vuelta
    bajo_332(sub, C, 25, 33, vel=0.58)
    bajo_332(pizz_cb, C, 25, 33, vel=0.48, golpes=(0.0, 1.5), durs=(1.3, 1.3), apagar=True)
    trem_linea(trem_vc, C, 25, 33, v0=0.2, v1=0.38)
    trem_va.acordes_ligados(C.voicings(25, 33, voces=2, rango=("A3", "E5")), vel=0.32)
    pad.acordes_ligados(C.voicings(25, 33, voces=4, rango=("A3", "E5")), vel=0.5)
    groove(bat, "v3", 25, 33, escala=0.72)
    vibes.melodia(31, PREGUNTA, vel=0.34)
    vibes.pedal(31, 32.95)

    # ------------------------------------------------------- 33–40 grieta
    # el piso se abre: dron de Do#, la espiral en fragmentos, el arco sostiene el Re
    dron.nota(33, "C#2", 4 * 8, vel=0.75)
    dron.auto("vol", [(32, -30), (33, -4, "suave"), (38, -4), (41, -36, "suave")])  # loop 33–37 parejo
    trem_vc.nota(33, "C#3", 8, vel=0.14, vel_fin=0.3).nota(35, "C#3", 8, vel=0.3, vel_fin=0.16, legato=True)
    trem_vc.nota(37, "C#3", 8, vel=0.16, vel_fin=0.32, legato=True)
    trem_vc.nota(39, "C#3", 8, vel=0.3, vel_fin=0.4, legato=True)
    trem_va.acordes_ligados(C.voicings(33, 41, voces=2, rango=("C#4", "A4")), vel=0.26)
    pad.acordes_ligados(C.voicings(33, 41, voces=4, rango=("C#4", "F#5")), vel=0.45)
    arco.nota(33, "D5", 16, vel=0.55).nota(37, "C#5", 16, vel=0.5)
    espiral(piano, 33, 37, cols, desplaz=2, vel=0.3, filtro=lambda k, c: k % 3 == 0, cresc=(1.0, 1.0))
    espiral(piano, 37, 39, cols, desplaz=2, vel=0.32, filtro=lambda k, c: k % 2 == 0, cresc=(1.0, 1.0))
    espiral(piano, 39, 41, cols, desplaz=2, vel=0.34, cresc=(0.95, 1.1))
    tex.clip(nube_acordes(Piano(fieltro=0.8, mecanica=0.0), notas_espiral(C, 25, 29, desplaz=2),
                           dur_s=15.0, estirar=5.0, densidad=12, grano=(0.12, 0.34),
                           tonos=(0, 12, -12), pesos=(4, 1, 1), ataque=3, caida=6),
             pos=33, ganancia_db=-9)
    mec.patron("apagador", "x.......x.....x.", 33, 37, vel=0.4, altura=73, prob=0.7)
    mec.golpe(33, "pedal", 0.55).golpe(35, "pedal", 0.5)
    # se rearma: el pulso vuelve en negras (37) y en corcheas (39), el 3+3+2 en el 39
    pulso(pul, 37, 39, vel=0.26, figura=1.0, acentos=(1.2, 0.85, 1.0, 0.85))
    pulso(pul, 39, 41, vel=0.29, cresc=(0.9, 1.1))
    mec.patron("apagador", "x.....x.....x...", 39, 41, vel=0.45, altura=73)
    for t0, t1, _s, b in C.bajos(39, 41, rango=("G1", "F#2")):
        sub.nota(C.c(t0), b, 1.25, vel=0.5).nota(C.c(t0 + 1.5), b, 1.25, vel=0.44)
        sub.nota(C.c(t0 + 3.0), b, 0.85, vel=0.46)
    groove(bat, "tic", 39, 41, escala=0.85)
    bat.patron("escobilla", ".... ..o. .o.o oxxX", 40, 41, vel=0.45)
    bat.golpe(40, "barrido", 0.42, dur=4)
    tex.clip(swell(Piano(fieltro=0.55), ["F#2", "C#3", "G#3", "A3", "C#4", "G#4"], largo_tiempos=8,
                   vel=0.55, curva=2.0), fin=41, ganancia_db=-13)

    # ------------------------------------------------------- 41–48 vuelta 4
    espiral(piano, 41, 49, cols, desplaz=3, vel=0.38)
    espiral(pizz_vl, 41, 49, cols, desplaz=0, vel=0.32, dur=0.4, retraso=0.5,
            filtro=lambda k, c: k % 2 == 0, apagar=True)                   # canon
    pulso(pul, 41, 49, vel=0.32)
    bajo_332(sub, C, 41, 49, vel=0.62)
    bajo_332(pizz_cb, C, 41, 49, vel=0.5, golpes=(0.0, 1.5), durs=(1.3, 1.3), apagar=True)
    trem_linea(trem_vc, C, 41, 49, v0=0.22, v1=0.4)
    trem_va.acordes_ligados(C.voicings(41, 49, voces=2, rango=("A3", "E5")), vel=0.34)
    pad.acordes_ligados(C.voicings(41, 49, voces=4, rango=("A3", "E5")), vel=0.52)
    groove(bat, "v4", 41, 45, sin=("aro_f",), escala=0.86)
    groove(bat, "v4", 45, 49, escala=0.9)
    bat.golpe("48:4.5", "hat_abierto", 0.42)
    vibes.melodia(47, PREGUNTA_2, vel=0.34)
    vibes.pedal(47, 48.95)

    # ------------------------------------------------------- 49–56 vuelta 5
    espiral(piano, 49, 57, cols, desplaz=4, vel=0.4)
    espiral(pizz_vl, 49, 57, cols, desplaz=1, vel=0.33, dur=0.4, retraso=0.5,
            filtro=lambda k, c: k % 2 == 0, apagar=True)
    pulso(pul, 49, 57, vel=0.33)
    bajo_332(sub, C, 49, 57, vel=0.66)
    bajo_332(pizz_cb, C, 49, 57, vel=0.5, golpes=(0.0, 1.5), durs=(1.3, 1.3), apagar=True)
    trem_linea(trem_vc, C, 49, 57, v0=0.24, v1=0.42)
    trem_va.acordes_ligados(C.voicings(49, 57, voces=2, rango=("A3", "E5")), vel=0.36)
    pad.acordes_ligados(C.voicings(49, 57, voces=4, rango=("A3", "E5")), vel=0.55)
    violines.melodia(49, VL_V5, vel=0.4)
    violines.auto("expresion", [(49, 0.55), (52.9, 0.85, "suave"), (53, 0.8), (56.9, 1.0, "suave"),
                                (57, 0.9), (60.9, 1.0, "suave"), (61, 0.92), (64.9, 1.0, "suave"),
                                (65, 0.7), (73, 0.5)])
    groove(bat, "v5", 49, 56, escala=0.92)
    groove(bat, "v4", 56, 57, solo=("bombo", "shaker"))
    bat.patron("escobilla", ".... ..o. .o.o oxxX", 56, 57, vel=0.5)
    bat.golpe("56:4.5", "hat_abierto", 0.48)
    vibes.nota(55, "G#4", 1, vel=0.3).nota("55:3", "C#5", 1, vel=0.32)
    tex.clip(swell(CuerdasTrem("violas"), ["C#4", "F#4", "A4", "C#5"], largo_tiempos=8, vel=0.55,
                   curva=2.2), fin=57, ganancia_db=-10.5)

    # ------------------------------------------------------- 57–64 vórtice
    espiral(piano, 57, 65, cols, desplaz=5, vel=0.46, cresc=(0.95, 1.08))
    espiral(pizz_vl, 57, 65, cols, desplaz=1, vel=0.34, dur=0.4, retraso=0.5, apagar=True)
    pulso(pul, 57, 65, alturas=("C#4",), vel=0.36)
    pulso(pul, 57, 65, alturas=("C#5",), vel=0.3, solo_acentos=True)
    bajo_332(sub, C, 57, 65, vel=0.72)
    for t0, t1, _s, b in C.bajos(57, 65, rango=("G1", "F#2")):
        cbajo.nota(C.c(t0), b, t1 - t0, vel=0.55, legato=True)
    chelos.melodia(57, VC_VORTICE, vel=0.62)
    violines.melodia(57, VL_VORTICE, vel=0.56)
    trem_va.acordes_ligados(C.voicings(57, 65, voces=3, rango=("A3", "E5")), vel=0.42)
    pad.acordes_ligados(C.voicings(57, 65, voces=4, rango=("A3", "E5")), vel=0.6)
    groove(bat, "vortice", 57, 64)
    for c in (58, 60, 62):
        bat.golpe(f"{c}:4.5", "hat_abierto", 0.45)
    groove(bat, "vortice", 64, 65, solo=("bombo", "hat"))
    bat.patron("caja", ".... ..o. o.o. oxxX", 64, 65, vel=0.42)

    # ------------------------------------------------------- 65–72 claro
    # cadencia rota (C#7b9 → Dmaj9): se levanta el apagado, el piano suena abierto
    mec.golpe(65, "pedal", 0.45)
    espiral(piano_ab, 65, 67, cols, desplaz=0, vel=0.28, acento=1.1, cresc=(1.05, 0.9),
            patron=P8_CIERRA, dur=0.9)
    espiral(piano_ab, 67, 69, cols, desplaz=0, vel=0.26, acento=1.1, cresc=(1.0, 0.9),
            patron="5 3 4 2", paso=1.0, dur=1.6)
    espiral(piano_ab, 69, 71, cols, desplaz=2, vel=0.23, acento=1.0, cresc=(1.0, 0.85),
            patron="4 2", paso=2.0, dur=3.0)
    piano_ab.acorde(71, ["A2", "E3", "D4", "F#4", "C#5"], 4, vel=0.25, rasgueo=0.06)
    piano_ab.acorde(72, ["A2", "E3", "B3", "C#4", "F#4", "C#5"], 8, vel=0.25, rasgueo=0.07)
    piano_ab.pedal_por_compas(65, 71)
    piano_ab.pedal(71, 72.95)
    piano_ab.pedal(73, 74.9)
    pulso(pul, 65, 67, vel=0.28, figura=1.0, acentos=(1.15, 0.85, 1.0, 0.85))
    pulso(pul, 67, 69, vel=0.25, figura=2.0, acentos=(1.0, 0.85))
    pulso(pul, 69, 71, vel=0.22, figura=4.0, acentos=(1.0,), dur=1.0)
    violines.melodia(65, VL_CLARO, vel=0.3)
    chelos.melodia(65, VC_CLARO, vel=0.31)
    for t0, t1, _s, b in C.bajos(65, 73, rango=("G1", "F#2")):
        cbajo.nota(C.c(t0), b, t1 - t0, vel=0.34, legato=True)
        sub.nota(C.c(t0), b, t1 - t0 - 0.1, vel=0.3)
    pad.acordes_ligados(C.voicings(65, 73, voces=4, rango=("A3", "E5")), vel=0.55)
    arco.nota(68, "D5", 4, vel=0.45, soltar=1.2).nota(69, "C#5", 16, vel=0.43)
    vibes.melodia(67, RESPUESTA, vel=0.33)
    vibes.pedal(67, 70.95)
    glock.nota("69:3", "E6", 2, vel=0.26).nota(72, "C#7", 4, vel=0.22)
    tex.clip(nube_acordes(Vibrafono(motor_hz=0.0), [(0, 1, "D5", 0.5), (1, 3, "C#5", 0.55),
                                                    (4, 4, "A4", 0.45)],
                           dur_s=16.0, estirar=6.0, densidad=10, grano=(0.15, 0.4),
                           tonos=(0, 12), pesos=(4, 1), ataque=4, caida=8),
             pos=69, ganancia_db=-8)

    # ------------------------------------------------------- automatizaciones
    pad.auto("corte", [(25, 520), (33, 760, "exp"), (34, 480, "exp"), (41, 760, "exp"),
                       (49, 1150, "exp"), (57, 2200, "exp"), (64.9, 3400, "exp"), (65, 1500),
                       (73, 520, "exp")])
    pad.auto("vol", [(25, -10), (27, -3, "suave"), (33, -4), (41, -2), (57, 0), (65, -4), (74, -10)])
    trem_va.auto("expresion", [(21, 0.5), (24.9, 0.9, "suave"), (25, 0.8), (32.9, 1.0, "suave"),
                               (33, 0.55), (36.9, 0.8, "suave"), (40.9, 1.0, "suave"),
                               (41, 0.8), (48.9, 1.0, "suave"), (49, 0.85), (56.9, 1.0, "suave"),
                               (57, 0.85), (64.9, 1.0, "suave")])
    chelos.auto("expresion", [(57, 0.85), (60.9, 1.0, "suave"), (61, 0.92), (64.9, 1.0, "suave"),
                              (65, 0.75), (73, 0.4)])
    cbajo.auto("expresion", [(57, 0.8), (64.9, 1.0, "suave"), (65, 0.75), (73, 0.35)])
    sub.auto("vol", [(17, -0.7), (24.95, -0.7), (25, 0.0), (38.95, 0.0), (39, 1.0), (40.95, 1.0),
                     (41, 0.8), (56.95, 0.8), (57, 0.0), (64.95, 0.0), (65, 3.5),
                     (69, -0.5, "suave"), (72, -10.5, "suave")])
    # cuerdas: bajo voz y en el claro tocan suave (capa suave, que ahora suena a su nivel real)
    violines.auto("vol", [(49, 4.5), (56.95, 4.5), (57, 0.0), (64.95, 0.0), (65.05, 5.0)])
    chelos.auto("vol", [(57, 0.0), (64.95, 0.0), (65.05, 6.5)])
    cbajo.auto("vol", [(57, 0.0), (64.95, 0.0), (65.05, 5.6)])
    # el pulso y el trémolo de chelos, parejos sección por sección con la mezcla anterior
    pul.auto("vol", [(40.95, 0.0), (41, -0.5), (56.95, -0.5), (57, -1.1), (64.95, -1.1), (65, 0.0)])
    trem_vc.auto("vol", [(24.95, 0.0), (25, 1.1), (32.95, 1.1), (33, 1.6), (40.95, 1.6), (41, -0.5),
                         (48.95, -0.5), (49, 0.0)])
    # el piano suave suena menos que antes y el fuerte más (curva nueva): se compensa por sección
    piano.auto("vol", [(9, 0.2), (16.95, 1.7, "suave"), (17, 0.9), (24.95, 0.9), (25, 0.6),
                       (32.95, 0.6), (33, 0.9), (40.95, 0.9), (41, -1.1), (48.95, -1.1), (49, -0.1),
                       (56.95, -0.1), (57, -2.9)])
    return C
