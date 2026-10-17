"""«Umbral» — canción 1: apertura y gancho. Misterio y asombro.

Re lidio (Sol# = la #4 que da la luz), con préstamos de Re mayor (Sol natural
en Gmaj13#11 / Em9) y un iv menor (Gm6) para las dos cadencias grandes.
88 bpm, 4/4, 64 compases + 9 s de cola ≈ 3:03.

Forma (compases):
   1–8   umbral      dron, swell invertido y el motivo de celesta con la #4
   9–16  despertar   entra el piano de fieltro con acordes extendidos      [bajo voz]
  17–24  arpa        arpegios de arpa; los chelos asoman al final           [bajo voz]
  25–32  pulso       groove suave (bombo, aro, shaker), sub, Rhodes; el pad abre [bajo voz]
  33–40  apertura    escobillas y hats, vuelve el piano, crecen las cuerdas [bajo voz]
  41–48  cumbre      cuerdas con la melodía grande + contracanto de celesta
  49–56  cumbre 2    variación más alta, cadencia plagal menor (Gm6 → D)
  57–64  cierre      vuelve el motivo y se deshace en una nube granular; cola larga

Lugar para la voz: en las secciones [bajo voz] la melodía es escasa (ecos de
2–3 notas en la octava 5, velocidad baja), el piano respira y el motor le
aplica un hueco suave de 3 dB alrededor de 2,4 kHz a armonía, melodía y textura.
"""
from motor import (Cancion, Piano, Arpa, Glock, Celesta, Rhodes, Pad, Dron, Sub,
                   Violines, Violas, Chelos, Contrabajo, Bateria, Textura, swell, nube,
                   nube_de_banco, EQ, Ducking, Compresor, Saturacion, acorde)

# =============================================================== 1. DATOS ==
BPM = 88
SEMILLA = 1701

SECCIONES = [
    # nombre       compases energía emoción                                   bajo voz  loop
    ("umbral",      8, 0.15, "misterio: algo está por abrirse",             False, (5, 9)),
    ("despertar",   8, 0.30, "asombro contenido",                           True,  (9, 17)),
    ("arpa",        8, 0.42, "curiosidad que avanza",                       True,  (17, 25)),
    ("pulso",       8, 0.55, "movimiento sereno",                           True,  (25, 33)),
    ("apertura",    8, 0.68, "expectativa luminosa",                        True,  (33, 41)),
    ("cumbre",      8, 0.88, "asombro pleno",                               False, (41, 49)),
    ("cumbre_2",    8, 0.95, "elevación, gratitud",                         False, (49, 57)),
    ("cierre",      8, 0.25, "suspensión: el umbral queda abierto",         False, (57, 61)),
]

# Un acorde por compás ("Asus4 A" divide el compás en dos).
ARMONIA = {
    1:  "D5 | D5 | D5 | D5 | Dmaj9 | Dmaj9 | E/D | E/D",
    9:  "Dmaj9 | E/D | Bm11 | Gmaj13#11 | Dmaj9 | E/D | Bm11 | Gmaj13#11",
    17: "Dmaj9 | E/D | F#m11 | Gmaj13#11 | Bm11 | E/G# | Asus4 | A",
    25: "Bm9 | Gmaj9#11 | Dmaj9/F# | E/G# | Bm9 | Gmaj9#11 | Dmaj9/F# | E/G#",
    33: "Gmaj9#11 | Asus4 A | F#m11 | Bm11 | Gmaj13#11 | E/G# | Asus4 | Gm6",
    41: "Dmaj9 | E/D | Bm11 | Gmaj13#11 | Dmaj9/F# | E/G# | Asus4 A | Bm9",
    49: "Gmaj9#11 | Dmaj9/F# | Em9 | Asus4 A | Bm11 | E/G# | Gmaj13#11 | Gm6",
    57: "Dmaj9 | E/D | Bm11 | Gmaj13#11 | Dmaj9 | E/D | Dmaj9#11 | Dmaj9#11",
}

# ---- Motivo (celesta): sube al umbral (Sol#, la #4) y lo cruza (La).
MOTIVO = "A5/0.5 E6 D6 G#5/1.5 A5/1 | F#5/3 r/1"         # sobre D
RESPUESTA = "A5/0.5 E6 D6 C#6/1.5 B5/1 | A5/3 r/1"       # baja por la 7ª mayor
EXTENSION = "B5/0.5 F#6 E6 C#6/1.5 B5/1 | G#5/3 r/1"     # sobre E/D: queda en el Sol#
VARIANTE_B = "F#5/0.5 C#6 B5 E5/1.5 F#5/1 | C#6/3 r/1"   # sobre Bm11 → Gmaj13#11
VARIANTE_A = "E6/0.5 A5 B5 D6/1.5 C#6/1 | B5/3 r/1"      # sobre Asus4 A → Bm9

# Ecos bajo la voz: 2–3 notas, octava 5 (fundamentales < 1,1 kHz).
ECOS = {10: "r/2.5 G#5/0.5 A5/1", 12: "r/2 C#6/2", 14: "r/2.5 G#5/0.5 A5/1",
        16: "r/1 C#6/1 B5/2"}

# ---- Melodía grande (violines, legato) y contracanto (chelos).
TEMA = ("A4/2_ E5/1_ D5/1_ | G#4/3_ B4/1_ | D5/2_ C#5/1_ B4/1_ | C#5/3_ B4/1_ | "
        "A4/2_ F#4/2_ | G#4/2_ B4/2_ | D5/2_ C#5/2 | B4/4")
TEMA_2 = ("D5/1_ E5/1_ F#5/2_ | A5/3_ F#5/1_ | G5/2_ F#5/1_ E5/1_ | D5/2_ C#5/2 | "
          "F#5/2_ E5/1_ D5/1_ | G#5/2_ E5/2_ | F#5/2_ C#5/2_ | D5/4")
CONTRA = ("D4/2 C#4/2 | B3/4 | B3/2 A3/2 | G3/2 F#3/1 E3/1 | F#3/2 A3/2 | B3/2 G#3/2 | "
          "A3/4 | B3/2 D4/2")
CONTRA_2 = ("B3/1 C#4/1 D4/2 | C#4/2 A3/2 | B3/2 G3/2 | E3/4 | D4/2 C#4/1 B3/1 | B3/2 G#3/2 | "
            "A3/2 B3/2 | Bb3/4")   # el Si bemol del Gm6 baja a La en el cierre

# ---- Destellos de glockenspiel (cumbres): dos notas en el tiempo 4.
GLOCK = {42: "r/3 B6/0.5 G#6/0.5", 44: "r/3 C#7/0.5 B6/0.5", 46: "r/3 B6/0.5 G#6/0.5",
         48: "r/3 D7/0.5 B6/0.5", 50: "r/3 A6/0.5 F#6/0.5", 52: "r/3 E7/0.5 C#7/0.5",
         54: "r/3 B6/0.5 G#6/0.5", 56: "r/2 D7/1 E7/1"}

# ---- Batería (semicorcheas; x normal, X acento, o fantasma, dígito = vel/9).
GROOVE = {
    "pulso": {"bombo": "x... .... x.x. ....", "shaker": "4.6. 4.6. 4.6. 4.7.",
              "aro": ".... x... .... x...", "aro_f": "...o .... ..o. ...o"},
    "apertura": {"bombo": "x... ..x. x.x. ....", "escobilla": ".... x... .... x...",
                 "esc_f": "..o. ...o ..o. .o..", "shaker": "3264 3264 3264 3274",
                 "hat": "..x. ..x. ..x. ..x."},
    "cumbre": {"bombo": "x... ..x. x.x. ..x.", "caja": ".... x... .... x...",
               "esc_f": "..o. ...o ..o. .o.o", "shaker": "3264 3264 3264 3274",
               "hat": "x.x. x.x. x.x. x.x."},
}


# ============================================================ 2. AYUDAS ===
def bajo_seguro(b, voicing, piso=33):
    """La octava más aguda del bajo que queda a una 5ª o más debajo del voicing
    (regla del grave limpio). None si no hay ninguna."""
    for cand in (b + 24, b + 12, b):
        if cand >= piso and min(voicing) - cand >= 7:
            return cand
    return None


def piano_respira(p, C, desde, hasta, vel=0.36, rango=("E3", "B4")):
    """Felt piano: bajo + acorde apenas arpegiado en el 1 y tres notas que respiran."""
    vs = C.voicings(desde, hasta, voces=4, rango=rango)
    bs = C.bajos(desde, hasta, rango=("A1", "G#2"))
    for (t0, t1, sim, v), (_, _, _, b) in zip(vs, bs):
        d = t1 - t0
        p.nota(C.c(t0), b, d, vel=vel + 0.06)
        p.acorde(C.c(t0), v, d, vel=vel, rasgueo=0.02)
        if d >= 4:
            # la 5ª del bajo en el 3, solo si es del acorde y no ensucia el grave
            if (b + 7) % 12 in acorde(sim).pcs and v[0] - (b + 7) >= 7:
                p.nota(C.c(t0 + 2.0), b + 7, 2.0, vel=vel * 0.78)
            p.nota(C.c(t0 + 1.5), v[-1], 2.5, vel=vel * 0.8)
            p.nota(C.c(t0 + 2.5), v[-2], 1.5, vel=vel * 0.72)
            p.nota(C.c(t0 + 3.0), v[1], 1.0, vel=vel * 0.66)
    p.pedal_por_compas(desde, hasta)


def piano_blancas(p, C, desde, hasta, vel=0.34, rango=("E3", "B4"), con_sub=False):
    """Acordes en 1 y 3 con el bajo: sostén sin ocupar (con sub, el bajo sube de octava)."""
    vs = C.voicings(desde, hasta, voces=4, rango=rango)
    bs = C.bajos(desde, hasta, rango=("A1", "G#2"))
    for (t0, t1, _s, v), (_, _, _, b) in zip(vs, bs):
        d = t1 - t0
        bb = bajo_seguro(b, v, piso=40) if con_sub else b
        if bb is not None:
            p.nota(C.c(t0), bb, d, vel=vel + 0.05)
        p.acorde(C.c(t0), v, min(2, d), vel=vel, rasgueo=0.015)
        if d >= 4:
            p.acorde(C.c(t0 + 2), v[1:], 2, vel=vel * 0.8, rasgueo=0.012)
    p.pedal_por_compas(desde, hasta)


def piano_negras(p, C, desde, hasta, vel=0.33, rango=("E3", "C#5")):
    """Pulso de negras en la mano derecha y el bajo una 8va arriba (el grave es del sub)."""
    vs = C.voicings(desde, hasta, voces=3, rango=rango)
    bs = C.bajos(desde, hasta, rango=("A1", "G#2"))
    for (t0, t1, _s, v), (_, _, _, b) in zip(vs, bs):
        k = 0
        t = t0
        while t < t1 - 1e-6:
            acento = 1.12 if k % 2 == 0 else 0.88
            p.acorde(C.c(t), v, 0.9, vel=vel * acento, rasgueo=0.006)
            t += 1.0
            k += 1
        bb = bajo_seguro(b, v, piso=40)
        if bb is not None:
            p.nota(C.c(t0), bb, t1 - t0, vel=vel + 0.05)
    p.pedal_por_compas(desde, hasta)


def arpa_ondas(p, C, desde, hasta, patron="0 1 2 3 4 3 2 1", paso=0.5, vel=0.5,
               rango=("A3", "E5"), con_bajo=True):
    """Arpegio sobre el voicing; con_bajo agrega el bajo en el 1 de cada acorde,
    apagado al cambiar de acorde (el arpista lo apaga: el grave no se ensucia)."""
    vs = C.voicings(desde, hasta, voces=4, rango=rango)
    if con_bajo:
        for (t0, t1, _s, v), (_, _, _, b) in zip(vs, C.bajos(desde, hasta, rango=("G1", "F#2"))):
            p.nota(C.c(t0), b, t1 - t0, vel=vel * 1.1, apagar=True, soltar=0.3)
    p.arpegio(desde, hasta, Cancion.voicing_en(vs), patron=patron, paso=paso, vel=vel,
              acentos=[1.15, 0.8, 0.95, 0.8])


def rhodes_comp(p, C, desde, hasta, vel=0.42, rango=("E3", "C5")):
    """Comping sincopado (contratiempo del 1, el 3, y una corchea al final)."""
    for t0, t1, _s, v in C.voicings(desde, hasta, voces=4, rango=rango):
        d = t1 - t0
        if d >= 4:
            p.acorde(C.c(t0 + 0.5), v, 1.0, vel=vel, rasgueo=0.006)
            p.acorde(C.c(t0 + 2.0), v, 1.3, vel=vel * 0.86, rasgueo=0.006)
            p.acorde(C.c(t0 + 3.5), v[1:], 0.45, vel=vel * 0.7)
        else:
            p.acorde(C.c(t0 + 0.5), v, d - 0.7, vel=vel * 0.95, rasgueo=0.006)


def sub_linea(p, C, desde, hasta, vel=0.75, rango=("A1", "G#2")):
    """Bajo: nota larga en el 1 y re-ataque en el 'y' del 3."""
    for t0, t1, _s, b in C.bajos(desde, hasta, rango=rango):
        d = t1 - t0
        if d >= 4:
            p.nota(C.c(t0), b, 2.4, vel=vel)
            p.nota(C.c(t0 + 2.5), b, 1.4, vel=vel * 0.85)
        else:
            p.nota(C.c(t0), b, d - 0.15, vel=vel * 0.95)


def groove(bat, nombre, desde, hasta, solo=None, sin=()):
    g = GROOVE[nombre]
    vel = {"bombo": 0.8, "aro": 0.6, "aro_f": 0.6, "escobilla": 0.62, "esc_f": 0.62,
           "caja": 0.55, "hat": 0.42, "shaker": 0.6}
    for k, patron in g.items():
        if (solo and k not in solo) or k in sin:
            continue
        golpe = {"aro_f": "aro", "esc_f": "escobilla"}.get(k, k)
        bat.patron(golpe, patron, desde, hasta, vel=vel[k])


# ============================================================ 3. CANCIÓN ==
def cancion() -> Cancion:
    C = Cancion("Umbral", slug="01-umbral", bpm=BPM, compas=(4, 4),
                tonalidad="Re lidio", semilla=SEMILLA, cola_s=9.0)
    for nom, comp, e, emo, voz, loop in SECCIONES:
        C.seccion(nom, comp, energia=e, emocion=emo, voz=voz, loop=loop)
    for c, prog in ARMONIA.items():
        C.progresion(c, prog)
    C.ritardando(61, 65, 80)          # el final se demora un poco
    C.fx["reverb"].update(dur=3.8, predelay_ms=32, brillo=0.42)
    C.fx["eco"].update(division=0.75, realim=0.36, corte=2800.0)

    # ---------------------------------------------------------------- pistas
    dron = C.pista("dron", Dron(corte=700, aire=0.18), "textura", vol=-3.5,
                   envios={"reverb": 0.25})
    tex = C.pista("textura", Textura(), "textura", vol=0.0, envios={"reverb": 0.12})
    celesta = C.pista("celesta", Celesta(brillo=0.5, golpe=0.45), "melodia", vol=0.0,
                      envios={"reverb": 0.38, "eco": 0.2})
    piano = C.pista("piano", Piano(fieltro=0.65, mecanica=0.5), "armonia", vol=5.3,
                    envios={"reverb": 0.22, "eco": 0.03},
                    efectos=[EQ(("pa", 40), ("campana", 320, -2.0, 0.8))])
    pad = C.pista("pad", Pad(voces=6, desafinar=13, sub=0.0, ataque=2.2, soltar=3.5, pa=140),
                  "armonia", vol=-5.0, envios={"reverb": 0.15},
                  efectos=[EQ(("campana", 300, -2.0, 0.9)), Ducking(prof_db=2.5, relaj_ms=200)])
    arpa = C.pista("arpa", Arpa(), "armonia", vol=0.0, envios={"reverb": 0.3, "eco": 0.06},
                   efectos=[EQ(("pa", 65))])
    rhodes = C.pista("rhodes", Rhodes(trem_prof=0.3), "armonia", vol=0.0,
                     envios={"reverb": 0.18, "eco": 0.1},
                     efectos=[EQ(("pa", 90), ("campana", 350, -2.0, 0.9)), Ducking(prof_db=1.5)])
    sub = C.pista("sub", Sub(drive_db=7, octava=0.12), "bajo", vol=0.0,
                  efectos=[Ducking(prof_db=3.0, relaj_ms=170)])
    bat = C.pista("bateria", Bateria(color=0.45), "bateria", vol=0.0,
                  envios={"sala": 0.18, "reverb": 0.05},
                  efectos=[Compresor(umbral_db=-24, ratio=2.5, ataque_ms=12, relaj_ms=140, mezcla=0.45),
                           Saturacion(drive_db=3, mezcla=0.3)])
    violines = C.pista("violines", Violines(doble=True), "melodia", vol=4.5,
                       envios={"reverb": 0.35}, efectos=[EQ(("pa", 170))])
    violas = C.pista("violas", Violas(), "armonia", vol=0.0, envios={"reverb": 0.32},
                     efectos=[EQ(("pa", 130))])
    chelos = C.pista("chelos", Chelos(), "armonia", vol=2.0, envios={"reverb": 0.3},
                     efectos=[EQ(("pa", 55))])
    cbajo = C.pista("contrabajo", Contrabajo(), "bajo", vol=0.0, envios={"reverb": 0.14},
                    efectos=[EQ(("pa", 40), ("pb", 3500))])
    glock = C.pista("glock", Glock(), "melodia", vol=-3.5, envios={"reverb": 0.4, "eco": 0.18},
                    efectos=[EQ(("agudos", 7000, -3.0))])

    # humanización (determinista)
    piano.humanizar(tiempo_ms=9, vel=0.07)
    celesta.humanizar(tiempo_ms=6, vel=0.06)
    arpa.humanizar(tiempo_ms=7, vel=0.08, swing=0.52)
    rhodes.humanizar(tiempo_ms=8, vel=0.07, swing=0.55)
    bat.humanizar(tiempo_ms=7, vel=0.1, swing=0.54, swing_div=0.25)
    sub.humanizar(tiempo_ms=4, vel=0.04)
    for p in (violines, violas, chelos, cbajo):
        p.humanizar(tiempo_ms=12, vel=0.04)
    glock.humanizar(tiempo_ms=5, vel=0.06)
    celesta.pedal_por_compas(1, 65)          # la celesta resuena dentro de cada compás

    # ------------------------------------------------------- 1–8 umbral
    # dron de Re (pedal): se retira cuando el piano abre la armonía (Bm11 en el 11)
    dron.nota(1, "D2", 4 * 10, vel=0.8).nota(1, "A2", 4 * 10, vel=0.6)
    dron.auto("vol", [(1, -30), (3, -2, "suave"), (9, -2), (11, -40, "suave"),
                      (61, -40), (62, -4, "suave"), (64, -4), (66, -12)])
    dron.nota(61, "D2", 4 * 4 + 6, vel=0.8).nota(61, "A2", 4 * 4 + 6, vel=0.55)
    tex.clip(nube_de_banco("vibrafono_arco", "A4", dur_s=24.0, estirar=14, densidad=10,
                           grano=(0.15, 0.4), tonos=(0, 12, -5), pesos=(4, 1, 1), ataque=6, caida=8),
             pos=1, ganancia_db=-17)
    tex.clip(swell(Piano(fieltro=0.5), ["D3", "A3", "E4", "F#4", "C#5"], largo_tiempos=6,
                   vel=0.5), fin=3, ganancia_db=-13.5)
    celesta.melodia(3, MOTIVO, vel=0.45)
    celesta.melodia(5, RESPUESTA, vel=0.43)
    celesta.melodia(7, EXTENSION, vel=0.47)
    pad.acordes_ligados(C.voicings(5, 9, voces=4, rango=("F#3", "E5")), vel=0.5)

    # ------------------------------------------------------- 9–16 despertar
    tex.clip(swell(Piano(fieltro=0.5), ["D2", "A2", "F#3", "C#4", "E4"], largo_tiempos=8,
                   vel=0.55), fin=9, ganancia_db=-10.5)
    piano_respira(piano, C, 9, 17, vel=0.42)
    for c, frase in ECOS.items():
        celesta.melodia(c, frase, vel=0.4)
    # el piano despierta solo (con el dron); el pad se suma recién en el 13
    pad.acordes_ligados(C.voicings(13, 17, voces=5, rango=("E3", "F5")), vel=0.5)

    # ------------------------------------------------------- 17–24 arpa
    arpa_ondas(arpa, C, 17, 25, vel=0.44)
    piano_blancas(piano, C, 17, 25, vel=0.33)
    pad.acordes_ligados(C.voicings(17, 25, voces=5, rango=("E3", "F5")), vel=0.55)
    # chelos asoman (divisi, registro medio: el grave queda para el piano y el arpa)
    chelos.nota(21, "F#3", 4, vel=0.52, vel_fin=0.64).nota(22, "G#3", 4, vel=0.55, vel_fin=0.66)
    chelos.nota(23, "A3", 8, vel=0.55, vel_fin=0.7).nota(23, "E3", 8, vel=0.48, vel_fin=0.64)

    # ------------------------------------------------------- 25–32 pulso
    tex.clip(swell(Piano(fieltro=0.5), ["B2", "F#3", "A3", "D4", "C#5"], largo_tiempos=4,
                   vel=0.5), fin=25, ganancia_db=-11)
    bat.auto("vol", [(25, 1.0), (33, 0.0)])                  # el groove entra con presencia
    groove(bat, "pulso", 25, 33, sin=("aro", "aro_f"))
    groove(bat, "pulso", 29, 33, solo=("aro", "aro_f"))     # el aro entra en el 29
    sub_linea(sub, C, 25, 33)
    rhodes_comp(rhodes, C, 25, 33)
    arpa_ondas(arpa, C, 29, 33, patron="1 . 3 . 2 4 . 3", vel=0.42, con_bajo=False)  # entra en el 29
    pad.acordes_ligados(C.voicings(25, 33, voces=5, rango=("E3", "F5")), vel=0.6)

    # ------------------------------------------------------- 33–40 apertura
    groove(bat, "apertura", 33, 41)
    bat.golpe(40, "barrido", 0.55, dur=4)
    bat.golpe("40:4.5", "hat_abierto", 0.5)
    sub_linea(sub, C, 33, 41)
    rhodes_comp(rhodes, C, 33, 41, vel=0.36)
    arpa_ondas(arpa, C, 33, 41, patron="1 2 3 4 5 4 3 2", vel=0.44, con_bajo=False)
    piano_blancas(piano, C, 33, 37, vel=0.34, con_sub=True)
    piano_negras(piano, C, 37, 41, vel=0.3)
    pad.acordes_ligados(C.voicings(33, 41, voces=5, rango=("E3", "F5")), vel=0.65)
    violas.acordes_ligados(C.voicings(37, 41, voces=2, rango=("C#4", "A4")), vel=0.62)
    for t0, t1, _s, b in C.bajos(37, 41, rango=("F#3", "F4")):       # chelos: el bajo en 8va
        chelos.nota(C.c(t0), b, t1 - t0, vel=0.65)
    for t0, t1, _s, b in C.bajos(37, 41, rango=("A1", "G#2")):
        cbajo.nota(C.c(t0), b, t1 - t0, vel=0.67)
    for p in (violas, chelos, cbajo):
        p.auto("expresion", [(37, 0.45), (40.9, 1.0, "suave"), (41, 0.92), (57, 0.92), (59, 0.25)])
    celesta.melodia(39, "r/2 A5/0.5 B5 C#6/1 | D6/2 E6/2", vel=0.45)   # transición: sube
    tex.clip(swell(Piano(fieltro=0.45), ["D2", "A2", "E3", "F#3", "C#4", "A4", "E5"],
                   largo_tiempos=8, vel=0.62, curva=2.2), fin=41, ganancia_db=-16)

    # ------------------------------------------------------- 41–56 cumbres
    for a, b in ((41, 49), (49, 56)):
        groove(bat, "cumbre", a, b)
    bat.patron("bombo", "x... .... .... ....", 56, 57, vel=0.8)   # respiro antes del cierre
    for c in (44, 48, 52):
        bat.golpe(f"{c}:4.5", "hat_abierto", 0.5)
    bat.patron("escobilla", ".... .... .... oxxX", 48, 49, vel=0.5)
    bat.patron("escobilla", ".... .... .... oxxX", 55, 56, vel=0.5)
    bat.golpe(57, "bombo", 0.55)
    sub_linea(sub, C, 41, 57)
    sub.nota(57, "D2", 8, vel=0.6)
    piano_negras(piano, C, 41, 57, vel=0.33)
    arpa_ondas(arpa, C, 41, 49, patron="1 2 3 4 5 4 3 2", paso=0.25, vel=0.38, con_bajo=False)
    arpa_ondas(arpa, C, 49, 56, patron="1 3 2 4 3 5 4 6", paso=0.25, vel=0.39, con_bajo=False)
    # gesto de arpa hacia el cierre: Gm6 en seisillos que desemboca en el 57
    # el arpista apaga el gesto con las palmas en el 57: el Sol2 y los Si bemol no
    # siguen sonando sobre el Re de la resolución (grave limpio, cadencia clara)
    gm6 = ["G2", "G3", "Bb3", "D4", "E4", "G4", "Bb4", "D5", "E5", "G5", "Bb5", "D6"]
    for k, alt in enumerate(gm6):
        ini = 3 + k / 6
        arpa.nota(f"56:{ini:.4f}", alt, 4.85 - ini, vel=0.38 + 0.025 * k, apagar=True)
    arpa.nota(57, "F#6", 3, vel=0.4).nota(57, "A5", 3, vel=0.37)
    pad.acordes_ligados(C.voicings(41, 57, voces=5, rango=("E3", "F5")), vel=0.7)
    violines.melodia(41, TEMA, vel=0.68)
    violines.melodia(49, TEMA_2, vel=0.83)        # la segunda cumbre, más arriba y más fuerte
    violines.nota(57, "C#5", 8, vel=0.63, vel_fin=0.08, legato=True)
    violines.auto("expresion", [(41, 0.86), (44.9, 1.0, "suave"), (45, 0.9), (48.9, 1.0, "suave"),
                                (49, 0.92), (52.9, 1.0, "suave"), (53, 0.94), (56.9, 1.0, "suave")])
    # violas: callan en la cumbre 1 (textura transparente) y en la 2 doblan el tema a la 8va baja
    violas.melodia(49, TEMA_2, vel=0.63, transponer=-12)
    violas.nota(57, "F#4", 8, vel=0.75, vel_fin=0.1).nota(57, "A4", 8, vel=0.7, vel_fin=0.1)
    chelos.melodia(41, CONTRA, vel=0.59)          # el contracanto canta sin tapar el tema
    chelos.melodia(49, CONTRA_2, vel=0.61)
    chelos.nota(57, "A3", 8, vel=0.62, vel_fin=0.06, legato=True)
    for t0, t1, _s, b in C.bajos(41, 57, rango=("A1", "G#2")):
        cbajo.nota(C.c(t0), b, t1 - t0, vel=0.63 if t0 < C.tempo.pos(49) else 0.7)
    cbajo.nota(57, "D2", 8, vel=0.6, vel_fin=0.06)
    celesta.melodia(41, MOTIVO, vel=0.55)
    celesta.melodia(43, VARIANTE_B, vel=0.52)
    celesta.melodia(45, MOTIVO, vel=0.55)
    celesta.melodia(47, VARIANTE_A, vel=0.53)
    celesta.melodia(49, RESPUESTA, vel=0.53)
    celesta.melodia(53, "F#5/0.5 C#6 B5 E5/1.5 F#5/1 | G#5/3 r/1", vel=0.52)
    for c, frase in GLOCK.items():
        glock.melodia(c, frase, vel=0.46 if c < 49 else 0.57)

    # ------------------------------------------------------- 57–64 cierre
    tex.clip(swell(Piano(fieltro=0.55), ["D3", "A3", "E4", "F#4", "G#4"], largo_tiempos=6,
                   vel=0.5), fin=57, ganancia_db=-13)
    celesta.melodia(57, MOTIVO, vel=0.52)
    celesta.melodia(59, RESPUESTA, vel=0.48)
    celesta.nota(63, "G#5", 4, vel=0.42, dejar_sonar=True)          # la #4 queda flotando
    piano_respira(piano, C, 59, 63, vel=0.3)
    piano.acorde(63, ["D2", "A2", "E3", "C#4", "F#4", "G#4"], 8, vel=0.32, rasgueo=0.05)
    piano.pedal(63, 65.9)
    pad.acordes_ligados(C.voicings(57, 65, voces=5, rango=("E3", "F5")), vel=0.6)
    tex.clip(nube(Celesta(brillo=0.4), MOTIVO + " " + RESPUESTA, dur_s=26.0, estirar=5.0,
                  densidad=14, grano=(0.09, 0.26), tonos=(0, 12, -12, 7), pesos=(5, 2, 1, 1),
                  ataque=5, caida=10), pos=59, ganancia_db=-3)

    # ------------------------------------------------------- automatizaciones
    pad.auto("corte", [(5, 380), (9, 600, "exp"), (17, 750, "exp"), (25, 1100, "exp"),
                       (33, 1900, "exp"), (41, 4200, "exp"), (56, 4800), (57, 2600, "exp"),
                       (65, 450, "exp")])
    pad.auto("vol", [(5, -10), (9, -4, "suave"), (13, -6), (15, 0, "suave"), (57, 0), (66, -6, "suave")])
    rhodes.auto("vol", [(25, -6), (27, 0, "suave"), (40, 0), (41, -40, "suave")])
    return C
