"""«Aurora» — canción 5: clímax y cierre del video. Luz plena, expansión, resolución.

Re mayor (jónico: el Sol natural cierra la puerta que el Sol# de «Umbral» dejó
abierta), 112 bpm, 4/4, 84 compases + 12 s de cola ≈ 3:13.

Forma (compases):
   1–8   alba           antes del sol (Bm9 → A): el pad se abre desde lo oscuro, nube de
                        violines y el motivo de Aurora en la celesta (Re–Mi–Fa#–La: sube como el sol)
   9–16  luz            sale el sol en Re: arpegio de piano en corcheas, pad, sub         [bajo voz]
  17–24  ascenso        el bajo sube por grados (Mi → Re), los chelos suben una 8va,
                        batería a medio tiempo                                            [bajo voz]
  25–32  impulso        groove pleno, sub en corcheas, arpegio 3+3+2 en semicorcheas;
                        el bajo baja por grados y los violines sostienen un La            [bajo voz]
  33–40  cumbre         IV–V–iii–vi: los violines cantan alto, contracanto de chelos,
                        destellos de glock y celesta
  41–48  respiro        pedal de Re (D – G/D) y la cita transformada de «Umbral»          [bajo voz]
  49–56  retorno        vuelve la subida por grados (chelos y violas en décimas)          [bajo voz]
  57–64  cumbre 2       la más llena del set: tema arriba, violas a la 8va, todo abierto
  65–72  plenitud       la luz se queda: banda completa, violines y chelos en décimas     [bajo voz]
  73–80  resolución     el tema vuelve en voz baja; la batería se apaga                   [bajo voz]
  81–84  último acorde  G/D → Dsus4 → Dadd9: el Sol baja a Fa# y el acorde queda sonando  [bajo voz]

Lugar para la voz (60 de 84 compases): melodías escasas en la octava 5 o más grave (notas
largas de cuerdas en legato, ecos de una celesta sin martillo), el glock solo en las cumbres,
arpegio de fieltro a velocidad baja; el motor suma su hueco de 3 dB en 2,4 kHz. La energía
sube bajo la voz sin agregar melodía ni brillo (batería, sub, chelos, contrabajo); los pads se
abren de verdad en las cumbres y bajo la voz respiran cerrados (≤ 2,3 kHz).
"""
from motor import (Cancion, Piano, Glock, Celesta, Pad, Sub, Violines, Violas, Chelos,
                   Contrabajo, Bateria, Textura, swell, nube, nube_de_banco, nube_acordes,
                   EQ, Ducking, Compresor, Saturacion, Ancho, Auto)

# =============================================================== 1. DATOS ==
BPM = 112
SEMILLA = 2605

SECCIONES = [
    # nombre          compases energía emoción                                   bajo voz  loop
    ("alba",            8, 0.18, "antes del sol: el cielo se aclara",          False, (5, 9)),
    ("luz",             8, 0.32, "sale el sol: calma clara",                   True,  (9, 17)),
    ("ascenso",         8, 0.45, "subida serena, expectativa",                 True,  (17, 25)),
    ("impulso",         8, 0.60, "impulso luminoso: todo empuja",              True,  (25, 33)),
    ("cumbre",          8, 0.85, "plenitud: la luz se abre",                   False, (33, 41)),
    ("respiro",         8, 0.35, "respiro: gratitud, memoria",                 True,  (41, 49)),
    ("retorno",         8, 0.58, "vuelve la subida: certeza",                  True,  (49, 57)),
    ("cumbre_2",        8, 1.00, "la cumbre más alta: luz total",              False, (57, 65)),
    ("plenitud",        8, 0.80, "la luz se queda: plenitud serena",           True,  (65, 73)),
    ("resolucion",      8, 0.48, "resolución: todo se acomoda",                True,  (73, 81)),
    ("ultimo_acorde",   4, 0.20, "reposo final: el acorde queda sonando",     True,  (81, 85)),
]

# Un acorde por compás ("Asus4 A" divide el compás en dos).
ARMONIA = {
    1:  "Bm9 | Bm9 | Gmaj9 | Gmaj9 | Em9 | Em9 | Asus4 | A",                  # antes del sol
    9:  "Dadd9 | Dadd9/F# | Gmaj9 | Gmaj9 | Bm7 | Aadd9/C# | Gmaj9 | Asus4",  # sale el sol
    17: "Em9 | F#m7 | Gmaj9 | A6 | Bm9 | A/C# | Dadd9 | Gmaj9/A",             # bajo que sube
    25: "Dmaj9 | A/C# | Bm9 | F#m7/A | Gmaj9 | D/F# | Em9 | Asus4 A",         # bajo que baja
    33: "Gmaj9 | A6 | F#m7 | Bm9 | Gmaj9 | Asus4 A | Bm9 | Em9 A7sus4",       # IV–V–iii–vi
    41: "Dmaj9 | Gmaj9/D | Dmaj9 | Gmaj9/D | Bm11 | Gmaj9 | Em11 | Asus4",    # pedal de Re
    49: "Em9 | F#m7 | Gmaj9 | A6 | Bm9 | C#m7b5 | Dadd9 | Asus4 A",           # sube otra vez
    57: "Gmaj9 | A6 | F#m7 | Bm9 | Gmaj9 | Asus4 A | F#m7 Bm9 | Em9 A7sus4",  # cumbre 2
    65: "Dmaj9 | A/C# | Bm9 | F#m7/A | Gmaj9 | D/F# | Em9 | Asus4 A",         # plenitud
    73: "Gmaj9 | A6 | F#m7 | Bm9 | Gmaj9 | A7sus4 | Bm9 | Gmaj9/A",          # el tema se va
    81: "Gmaj9/D | Dsus4 | Dadd9 | Dadd9",                                    # plagal + 4–3
}

# ---- Motivo de Aurora: sube por la pentatónica (Re–Mi–Fa#–La) y se posa en el Si.
MOTIVO = "D5/0.5 E5/0.5 F#5/0.5 A5/2.5 | B5/1 A5/1 F#5/2"         # sobre Gmaj9
RESPUESTA = "E5/0.5 F#5/0.5 G5/0.5 B5/2.5 | A5/1 G5/1 E5/2"       # sobre Em9 (4–3 en el 2)
LLEGADA = "A5/1 B5/1 D6/2 | C#6/4"                               # Asus4 → A: 4–3
# ---- Cita transformada de «Umbral»: allá el motivo subía al Sol# (la #4) y lo cruzaba;
# acá el Sol es natural y baja a Fa# (mismo ritmo, una 8va abajo: va bajo la voz).
CITA = "A4/0.5 E5/0.5 D5/0.5 G4/1.5 F#4/1 | D4/3 r/1"
CITA_FINAL = "r/1.5 A4/0.5 E5/0.5 D5/0.5 G4/1 | F#4/4"            # el Sol cae en el Dadd9

# ---- Tema de las cumbres (violines, legato). Arranca con el motivo y canta en la 8va 5–6.
TEMA = ("D5/0.5 E5/0.5_ F#5/0.5_ A5/2.5_ | B5/1_ C#6/2_ B5/1_ | A5/2_ E5/1_ F#5/1_ | D5/3 r/1 | "
        "E5/0.5 F#5/0.5_ A5/0.5_ B5/2.5_ | D6/2_ C#6/1.5_ B5/0.5_ | C#6/1.5_ B5/0.5_ A5/2_ | "
        "B5/2_ A5/2")
TEMA_2 = ("D5/0.5 E5/0.5_ F#5/0.5_ A5/0.5_ B5/2_ | C#6/3_ B5/0.5_ C#6/0.5_ | A5/2_ C#6/2_ | "
          "D6/3_ C#6/1_ | B5/1.5_ A5/0.5_ B5/2_ | D6/2_ C#6/1_ B5/1_ | C#6/2_ D6/2_ | B5/2_ A5/2")
TEMA_2B = "B5/1.5 A5/0.5 B5/2 | D6/2 C#6/1 B5/1 | C#6/2 D6/2 | B5/2 A5/2"   # celesta, 8va arriba
# ---- Contracantos de chelos (siempre desde Mi3: el grave queda limpio).
CONTRA = ("G3/2 A3/2_ | C#4/2_ B3/2_ | C#4/2_ A3/2_ | F#3/2_ A3/1_ B3/1_ | B3/2 D4/2_ | E3/4 | "
          "D4/2_ C#4/2_ | B3/2_ G3/2")
CONTRA_2 = ("G3/2 B3/2_ | A3/2_ E4/2_ | C#4/2_ A3/2_ | B3/1_ C#4/1_ D4/2_ | D4/2_ B3/2_ | A3/4 | "
            "A3/2_ F#3/2_ | G3/2_ E3/2")

# ---- Ecos de celesta bajo la voz: 2–3 notas, octava 4–5.
ECOS = {12: "r/2 D5/0.5 E5/0.5 F#5/1", 16: "r/1 A4/1 B4/1 A4/1",
        20: "r/2.5 C#5/0.5 E5/1", 24: "r/2 D5/0.5 E5/0.5 F#5/1",
        68: "r/2 C#5/0.5 E5/0.5 A5/1", 72: "r/2.5 C#5/0.5 E5/1"}
# ---- Destellos (solo fuera de la voz).
# (el glock vive en la octava 6: brilla igual y deja libre la franja de 2–5 kHz)
DESTELLOS_ALBA = {2: "r/2 F#6/2", 4: "r/2 A6/2", 6: "r/2 B6/2", 8: "r/2 A6/1 E6/1"}
GLOCK_1 = {33: "r/3 A6/0.5 B6/0.5", 35: "r/3 A6/1", 37: "r/3 F#6/0.5 B6/0.5",
           39: "r/2.5 F#6/0.5 B6/1"}
CELESTA_1 = {36: "r/2.5 D6/0.5 E6/0.5 F#6/0.5", 40: "r/2 A5/0.5 B5/0.5 D6/1"}
GLOCK_2 = {57: "r/3 F#6/0.5 B6/0.5", 58: "r/3 E6/0.5 A6/0.5", 60: "r/3 F#6/0.5 D6/0.5",
           62: "r/3 A6/0.5 E6/0.5", 64: "r/2.5 E6/0.5 D6/0.5 A6/0.5"}

# ---- Arpegios del piano (índices en el voicing de 4 voces; ≥ 4 sube una 8va).
P_LUZ = "0 2 1 3 2 4 3 5"                          # corcheas: zigzag que sube
P_ASC = "0 3 1 4 2 5 3 6"                          # corcheas: zigzag más abierto
P_IMP = "0 2 4 1 3 5 2 4 0 2 4 1 3 5 6 4"          # semicorcheas en grupos 3+3+2
P_CUM = "1 3 5 2 4 6 3 5 1 3 5 2 4 6 7 5"          # ídem, un escalón más arriba
P_CUM2 = "2 4 6 3 5 7 4 6 2 4 6 3 5 7 8 6"         # ídem, el más alto
P_PLE = "0 2 4 1 3 5 2 4 1 3 5 2 4 6 5 3"
P_RES = "0 . 2 3 . 4 . 2"                          # corcheas con aire
A_332 = [1.15, 0.78, 0.86, 1.05, 0.78, 0.86, 1.0, 0.8]
A_8 = [1.12, 0.85, 0.95, 0.85]

# ---- Batería (semicorcheas; x normal, X acento, o fantasma, dígito = vel/9).
GROOVE = {
    "medio": {"bombo": "x... .... .... .... x... .... ..x. ....",
              "aro": ".... .... x... ....",
              "shaker": "4.3. 4.3. 4.3. 4.5."},
    "medio_esc": {"bombo": "x... .... .... .... x... .... ..x. ....",
                  "escobilla": ".... .... x... ....",
                  "esc_f": "..o. .... .... .o.o",
                  "shaker": "4232 4232 4232 4252"},
    "pleno": {"bombo": "x... ..x. x... .... x... ..x. x.x. ....",
              "escobilla": ".... x... .... x...",
              "esc_f": "..o. ...o .o.. ..o.",
              "hat": "x.x. x.x. x.x. x.x.",
              "shaker": "3253 3253 3253 3263"},
    "cumbre": {"bombo": "x... ..x. x.x. .... x... ..x. x... ..x.",
               "caja": ".... x... .... x...",
               "esc_f": "..o. ...o ..o. .o.o",
               "hat": "6263 6263 6263 6264",
               "shaker": "3253 3253 3253 3263"},
    "cumbre2": {"bombo": "x... ..x. x.x. ..x. x... ..x. x... x.x.",
                "caja": ".... X... .... x...",
                "esc_f": "..o. ..o. ..o. .o.o",
                "hat": "7374 7374 7374 7375",
                "shaker": "4364 4364 4364 4374"},
    "plenitud": {"bombo": "x... ..x. x... .... x... ..x. x.x. ....",
                 "escobilla": ".... x... .... x...",
                 "esc_f": "..o. ...o ..o. .o..",
                 "hat": "x.x. x.x. x.x. x.x.",
                 "shaker": "3253 3253 3253 3263"},
    "plenitud_b": {"bombo": "x... ..x. x... ..x. x... ..x. x.x. ....",
                   "escobilla": ".... x... .... x...",
                   "esc_f": ".o.. ..o. ...o .o.o",
                   "hat": "6.3. 6.34 6.3. 6.3.",
                   "shaker": "3253 3253 3253 3263"},
    "latido": {"bombo": "x... .... .... ....", "shaker": "3.2. 3.2. 3.2. 3.3."},
}
VEL_GOLPE = {"bombo": 0.8, "aro": 0.55, "escobilla": 0.6, "esc_f": 0.6, "caja": 0.56,
             "hat": 0.46, "shaker": 0.6}


# ============================================================ 2. AYUDAS ===
def pedal_acordes(p, C, desde, hasta, hueco=0.06):
    """Pedal de resonancia que se renueva en cada cambio de acorde (también a mitad de
    compás): el arpegio nunca arrastra el acorde anterior."""
    a0, b0 = C.tempo.pos(desde), C.tempo.pos(hasta)
    for t0, t1, _s in C.acordes(desde, hasta):
        a, b = max(t0, a0), min(t1, b0)
        if b - a > 0.25:
            p.pedal(C.c(a + 0.02), C.c(b - hueco))


def arpegio_piano(p, C, desde, hasta, patron, paso=0.25, vel=0.3, rango=("F#3", "C#5"),
                  acentos=None, bajo=False):
    """El motor de Aurora: arpegio de fieltro sobre voicings conducidos, pedal por acorde.
    `bajo` agrega la mano izquierda en A1–G#2 (solo donde no toca el sub)."""
    vs = C.voicings(desde, hasta, voces=4, rango=rango)
    if bajo:
        for t0, t1, _s, b in bajos_unidos(C, desde, hasta):
            p.nota(C.c(t0), b, t1 - t0, vel=vel + 0.08)
    p.arpegio(desde, hasta, Cancion.voicing_en(vs), patron=patron, paso=paso, vel=vel,
              acentos=acentos)
    pedal_acordes(p, C, desde, hasta)


def bajos_unidos(C, desde, hasta, rango=("A1", "G#2")):
    """Bajos por acorde, uniendo los consecutivos de igual altura (sin re-ataques)."""
    out = []
    for t0, t1, s, b in C.bajos(desde, hasta, rango=rango):
        if out and out[-1][3] == b and abs(out[-1][1] - t0) < 1e-6:
            out[-1] = (out[-1][0], t1, out[-1][2], b)
        else:
            out.append((t0, t1, s, b))
    return out


def sub_corcheas(p, C, desde, hasta, vel=0.72):
    """Sub firme en corcheas (el pulso de Aurora), con acento en los tiempos."""
    acentos = (1.0, 0.78, 0.9, 0.8, 0.96, 0.78, 0.9, 0.84)
    for t0, t1, _s, b in C.bajos(desde, hasta, rango=("A1", "G#2")):
        k, t = 0, t0
        while t < t1 - 1e-6:
            p.nota(C.c(t), b, 0.38, vel=vel * acentos[k % 8])
            t += 0.5
            k += 1


def sub_punteado(p, C, desde, hasta, vel=0.7):
    """Bajo 3+3+2: corchea con puntillo, corchea con puntillo, negra."""
    for t0, t1, _s, b in C.bajos(desde, hasta, rango=("A1", "G#2")):
        d = t1 - t0
        p.nota(C.c(t0), b, 1.35, vel=vel)
        if d >= 4:
            p.nota(C.c(t0 + 1.5), b, 1.35, vel=vel * 0.85)
            p.nota(C.c(t0 + 3.0), b, 0.9, vel=vel * 0.9)
        elif d > 1.6:
            p.nota(C.c(t0 + 1.5), b, d - 1.6, vel=vel * 0.85)


def sub_largo(p, C, desde, hasta, vel=0.55, figura=None):
    """Notas largas (redondas, o la figura dada en tiempos) con un respiro antes del cambio."""
    for t0, t1, _s, b in bajos_unidos(C, desde, hasta):
        t = t0
        paso = figura or (t1 - t0)
        while t < t1 - 1e-6:
            p.nota(C.c(t), b, min(paso, t1 - t) - 0.15, vel=vel)
            t += paso


def groove(bat, nombre, desde, hasta, solo=None, sin=(), escala=1.0):
    """Patrones de GROOVE[nombre]; `escala` sube o baja el groove entero (dígitos incluidos)."""
    for k, patron in GROOVE[nombre].items():
        if (solo and k not in solo) or k in sin:
            continue
        golpe = {"esc_f": "escobilla"}.get(k, k)
        bat.patron(golpe, patron, desde, hasta, vel=VEL_GOLPE[k], escala=escala)


def ganancia_por_seccion(p, C, valores, rampa=0.1):
    """`vol` de la pista por sección ({nombre: dB}, las que falten repiten la anterior), con
    rampas de `rampa` compases antes de cada borde: los cambios nunca son escalones."""
    pts, prev = [], None
    for s in C.secciones:
        v = valores.get(s.nombre, prev)
        if v is None:
            continue
        if prev is None:
            pts.append((1, v))
        elif v != prev:
            pts += [(s.compas_ini - rampa, prev), (s.compas_ini, v)]
        prev = v
    p.auto("vol", pts)


def linea_ligada(p, desde, alturas, vel, vel_fin=None, dur=4.0):
    """Notas largas ligadas (una por compás por defecto): sin golpe de arco entre ellas."""
    for k, alt in enumerate(alturas):
        v = vel if vel_fin is None else vel + (vel_fin - vel) * k / max(1, len(alturas) - 1)
        p.nota(desde + k * dur / 4.0, alt, dur, vel=v, legato=k > 0)


# ============================================================ 3. CANCIÓN ==
def cancion() -> Cancion:
    C = Cancion("Aurora", slug="05-aurora", bpm=BPM, compas=(4, 4), tonalidad="Re mayor",
                semilla=SEMILLA, cola_s=12.0)
    for nom, comp, e, emo, voz, loop in SECCIONES:
        C.seccion(nom, comp, energia=e, emocion=emo, voz=voz, loop=loop)
    for c, prog in ARMONIA.items():
        C.progresion(c, prog)
    C.ritardando(79, 85, 96)          # el final se demora: 112 → 96 bpm
    C.fx["reverb"].update(dur=3.8, predelay_ms=30, brillo=0.46)
    C.fx["eco"].update(division=0.75, realim=0.34, corte=3000.0)
    C.marca(9, "sale el sol: primer acorde de Re")
    C.marca(33, "cumbre 1")
    C.marca(57, "cumbre 2: el punto más alto del set")
    C.marca(83, "acorde final (Dadd9): queda sonando")

    # ---------------------------------------------------------------- pistas
    tex = C.pista("textura", Textura(), "textura", vol=0.0, envios={"reverb": 0.14})
    pad = C.pista("pad", Pad(voces=8, desafinar=17, sub=0.0, ataque=2.6, soltar=4.0, q=0.9,
                             respira=0.3, respira_hz=0.05, chorus=0.4, ancho=1.0, pa=150),
                  "armonia", vol=-5.0, envios={"reverb": 0.16},
                  efectos=[EQ(("campana", 300, -2.5, 0.9), ("campana", 2500, -2.0, 0.8)),
                           Ancho(Auto([(1, 0.9), (33, 1.25, "suave"), (41, 0.95, "suave"),
                                       (57, 1.3, "suave"), (65, 1.15, "suave"), (81, 0.9, "suave"),
                                       (84, 0.75, "suave")]),
                                 mono_hz=180),
                           Ducking(prof_db=2.5, relaj_ms=200)])
    cielo = C.pista("cielo", Pad(voces=6, desafinar=11, sub=0.0, ataque=3.2, soltar=4.5, corte=3200,
                                 q=0.8, respira=0.4, respira_hz=0.07, chorus=0.55, ancho=1.0, pa=420),
                    "textura", vol=-7.0, envios={"reverb": 0.3},
                    efectos=[EQ(("campana", 2800, -4.0, 0.7)), Ducking(prof_db=2.0, relaj_ms=220)])
    piano = C.pista("piano", Piano(fieltro=0.6, brillo=0.5, mecanica=0.4), "armonia", vol=2.7,
                    envios={"reverb": 0.2, "eco": 0.04},
                    efectos=[EQ(("pa", 45), ("campana", 320, -2.0, 0.8), ("campana", 2600, -2.0, 0.9))])
    celesta = C.pista("celesta", Celesta(brillo=0.5, golpe=0.4), "melodia", vol=0.0, pan=0.12,
                      envios={"reverb": 0.38, "eco": 0.2})
    # celesta con macillo blando para lo que va bajo la voz: la nota redonda, sin el "tic"
    # de 2–3 kHz del martillo (es una elección de sonido: el QA ya no lo exige)
    celesta_voz = C.pista("celesta_voz", Celesta(brillo=0.42, golpe=0.15), "melodia", vol=0.0,
                          pan=-0.1, envios={"reverb": 0.4, "eco": 0.22})
    glock = C.pista("glock", Glock(), "melodia", vol=-3.5, pan=0.22,
                    envios={"reverb": 0.42, "eco": 0.2}, efectos=[EQ(("agudos", 7000, -3.0))])
    violines = C.pista("violines", Violines(doble=True), "melodia", vol=0.0, envios={"reverb": 0.36},
                       efectos=[EQ(("pa", 170), ("campana", 3000, -4.0, 0.8), ("agudos", 7500, -1.0))])
    violas = C.pista("violas", Violas(), "armonia", vol=0.0, envios={"reverb": 0.32},
                     efectos=[EQ(("pa", 130))])
    chelos = C.pista("chelos", Chelos(), "armonia", vol=9.5, envios={"reverb": 0.3},
                     efectos=[EQ(("pa", 60), ("campana", 280, -1.5, 1.0))])
    cbajo = C.pista("contrabajo", Contrabajo(), "bajo", vol=0.0, envios={"reverb": 0.12},
                    efectos=[EQ(("pa", 38), ("pb", 3000))])
    sub = C.pista("sub", Sub(drive_db=8.0, octava=0.16, ataque=0.008, soltar=0.09), "bajo",
                  vol=0.0, efectos=[Ducking(prof_db=3.0, relaj_ms=160)])
    bat = C.pista("bateria", Bateria(color=0.56), "bateria", vol=0.0,
                  envios={"sala": 0.16, "reverb": 0.06},
                  efectos=[Compresor(umbral_db=-24, ratio=2.5, ataque_ms=10, relaj_ms=130, mezcla=0.45),
                           Saturacion(drive_db=3, mezcla=0.3)])

    # humanización (determinista)
    piano.humanizar(tiempo_ms=6, vel=0.06)
    celesta.humanizar(tiempo_ms=6, vel=0.06)
    celesta_voz.humanizar(tiempo_ms=6, vel=0.06)
    glock.humanizar(tiempo_ms=5, vel=0.06)
    bat.humanizar(tiempo_ms=5, vel=0.08, swing=0.52, swing_div=0.25)
    sub.humanizar(tiempo_ms=3, vel=0.04)
    for p in (violines, violas, chelos, cbajo):
        p.humanizar(tiempo_ms=11, vel=0.04)
    celesta.pedal_por_compas(1, 85)
    celesta_voz.pedal_por_compas(1, 85)

    # el pad recorre toda la canción con conducción continua; se abre con el filtro
    pad.acordes_ligados(C.voicings(1, 85, voces=5, rango=("E3", "C#5")), vel=0.6)

    # ------------------------------------------------------- 1–8 alba
    tex.clip(nube_de_banco("violines", "F#5", dur_s=21.0, estirar=12, densidad=12,
                           grano=(0.12, 0.35), tonos=(0, 12, -12), pesos=(4, 1, 1),
                           ataque=7, caida=7, brillo_hz=7000), pos=1, ganancia_db=-23)
    celesta.melodia(3, MOTIVO, vel=0.4)
    celesta.melodia(5, RESPUESTA, vel=0.4)
    celesta.melodia(7, LLEGADA, vel=0.44)
    for c, frase in DESTELLOS_ALBA.items():
        glock.melodia(c, frase, vel=0.42)
    # primera luz en las cuerdas (pp, crescendo)
    chelos.nota(5, "B3", 8, vel=0.12, vel_fin=0.22).nota(7, "A3", 8, vel=0.22, vel_fin=0.28, legato=True)
    violas.nota(5, "G4", 8, vel=0.12, vel_fin=0.22).nota(7, "E4", 8, vel=0.22, vel_fin=0.28, legato=True)
    # el piano asoma: dos acordes arpegiados en la dominante
    for t0, t1, _s, v in C.voicings(7, 9, voces=4, rango=("E3", "C#5")):
        piano.acorde(C.c(t0), v, t1 - t0, vel=0.28, rasgueo=0.06)
    piano.nota(7, "A1", 8, vel=0.32)
    pedal_acordes(piano, C, 7, 9)
    tex.clip(swell(Piano(fieltro=0.5), ["D2", "A2", "F#3", "E4", "A4"], largo_tiempos=8,
                   vel=0.55), fin=9, ganancia_db=-14.6)

    # ------------------------------------------------------- 9–16 luz
    arpegio_piano(piano, C, 9, 17, P_LUZ, paso=0.5, vel=0.36, rango=("F#3", "D5"),
                  acentos=A_8, bajo=True)
    sub_largo(sub, C, 13, 17, vel=0.45)
    for c in (12, 16):
        celesta_voz.melodia(c, ECOS[c], vel=0.4)

    # ------------------------------------------------------- 17–24 ascenso
    arpegio_piano(piano, C, 17, 25, P_ASC, paso=0.5, vel=0.32, rango=("F#3", "C#5"), acentos=A_8)
    sub_punteado(sub, C, 17, 25, vel=0.58)
    groove(bat, "medio", 17, 21, solo=("bombo", "shaker"))
    groove(bat, "medio", 21, 25)
    # los chelos suben una 8va entera, de Mi3 a Mi4, con el bajo
    linea_ligada(chelos, 17, ["E3", "F#3", "G3", "A3", "B3", "C#4", "D4", "E4"], vel=0.25, vel_fin=0.44)
    violas.acordes_ligados(C.voicings(21, 25, voces=2, rango=("D4", "A4")), vel=0.26, legato=True)
    violines.nota(21, "F#5", 4, vel=0.2, vel_fin=0.3)
    violines.nota(22, "E5", 4, vel=0.3, legato=True)
    violines.nota(23, "F#5", 8, vel=0.3, vel_fin=0.42, legato=True)
    for c in (20, 24):
        celesta_voz.melodia(c, ECOS[c], vel=0.4)

    # ------------------------------------------------------- 25–32 impulso
    arpegio_piano(piano, C, 25, 33, P_IMP, paso=0.25, vel=0.27, rango=("E3", "B4"), acentos=A_332)
    sub_corcheas(sub, C, 25, 33, vel=0.68)
    groove(bat, "pleno", 25, 29, sin=("hat",))
    groove(bat, "pleno", 29, 32)
    groove(bat, "pleno", 32, 33, solo=("bombo", "hat", "shaker"))
    bat.patron("escobilla", ".... .... o.o. oxxX", 32, 33, vel=0.5)     # rulo hacia la cumbre
    bat.golpe("32:4.5", "hat_abierto", 0.45)
    # chelos: la escala que baja (el bajo a la 8va); violines: un La que no se mueve
    for t0, t1, _s, b in bajos_unidos(C, 25, 33, rango=("E3", "D#4")):
        chelos.nota(C.c(t0), b, t1 - t0, vel=0.4, legato=True)
    violas.acordes_ligados(C.voicings(25, 33, voces=2, rango=("F#4", "C#5")), vel=0.3, legato=True)
    violines.nota(25, "A4", 24, vel=0.2, vel_fin=0.3, legato=True)
    violines.melodia(31, "B4/4 | D5/2 C#5/2", vel=0.38, legato=True)
    tex.clip(swell(Piano(fieltro=0.45), ["G2", "D3", "A3", "B3", "F#4", "A4", "D5"], largo_tiempos=8,
                   vel=0.62, curva=2.2), fin=33, ganancia_db=-15.7)
    tex.clip(swell(Violines(), ["B4", "F#5", "A5"], largo_tiempos=6, vel=0.5), fin=33, ganancia_db=-9)

    # ------------------------------------------------------- 33–40 cumbre
    arpegio_piano(piano, C, 33, 41, P_CUM, paso=0.25, vel=0.3, rango=("F#3", "C#5"), acentos=A_332)
    sub_corcheas(sub, C, 33, 41, vel=0.79)
    groove(bat, "cumbre", 33, 41)
    for c in (34, 36, 38):
        bat.golpe(f"{c}:4.5", "hat_abierto", 0.42)
    bat.patron("escobilla", ".... .... .... oxxX", 40, 41, vel=0.5)
    cielo.acordes_ligados(C.voicings(33, 41, voces=3, rango=("A4", "E6")), vel=0.5)
    violines.melodia(33, TEMA, vel=0.64)
    violas.acordes_ligados(C.voicings(33, 41, voces=2, rango=("D4", "B4")), vel=0.4)
    chelos.melodia(33, CONTRA, vel=0.31)
    for t0, t1, _s, b in bajos_unidos(C, 33, 41):
        cbajo.nota(C.c(t0), b, t1 - t0, vel=0.5)
    for c, frase in GLOCK_1.items():
        glock.melodia(c, frase, vel=0.46)
    for c, frase in CELESTA_1.items():
        celesta.melodia(c, frase, vel=0.46)

    # ------------------------------------------------------- 41–48 respiro
    bat.golpe(41, "bombo", 0.62).golpe(41, "hat_abierto", 0.32)          # aterrizaje
    arpegio_piano(piano, C, 41, 45, P_RES, paso=0.5, vel=0.3, rango=("F#3", "D5"), bajo=True)
    arpegio_piano(piano, C, 45, 49, P_RES, paso=0.5, vel=0.3, rango=("F#3", "D5"))
    violas.acordes_ligados(C.voicings(41, 49, voces=2, rango=("D4", "A4")), vel=0.24, legato=True)
    for t0, t1, _s, b in bajos_unidos(C, 41, 49, rango=("E3", "D#4")):
        chelos.nota(C.c(t0), b, t1 - t0, vel=0.2, legato=True)
    celesta_voz.melodia(42, CITA, vel=0.36)
    tex.clip(nube(Piano(fieltro=0.6), MOTIVO, dur_s=16.0, estirar=4.0, densidad=10,
                  grano=(0.1, 0.3), tonos=(0, 12, -12), pesos=(4, 1, 1), ataque=4, caida=6),
             pos=41, ganancia_db=-12.7)
    sub_largo(sub, C, 45, 49, vel=0.45)
    groove(bat, "latido", 45, 49, solo=("bombo",), escala=0.75)     # latido suave, shaker igual
    groove(bat, "latido", 45, 49, solo=("shaker",))
    violines.nota(45, "F#5", 8, vel=0.22, vel_fin=0.3).nota(47, "E5", 8, vel=0.3, legato=True)

    # ------------------------------------------------------- 49–56 retorno
    arpegio_piano(piano, C, 49, 53, P_ASC, paso=0.5, vel=0.32, rango=("F#3", "C#5"), acentos=A_8)
    arpegio_piano(piano, C, 53, 57, P_IMP, paso=0.25, vel=0.28, rango=("E3", "B4"), acentos=A_332)
    sub_punteado(sub, C, 49, 53, vel=0.62)
    sub_corcheas(sub, C, 53, 57, vel=0.74)
    groove(bat, "medio_esc", 49, 53)
    groove(bat, "pleno", 53, 56)
    groove(bat, "pleno", 56, 57, solo=("bombo", "shaker"))
    bat.patron("caja", ".... .... o.o. oxxX", 56, 57, vel=0.5)          # rulo hacia la cumbre 2
    bat.golpe(56, "barrido", 0.5, dur=4)
    bat.golpe("56:4.5", "hat_abierto", 0.5)
    # chelos suben otra vez; violas en décimas encima
    linea_ligada(chelos, 49, ["E3", "F#3", "G3", "A3", "B3", "C#4", "D4", "A3"], vel=0.3, vel_fin=0.47)
    linea_ligada(violas, 49, ["G4", "A4", "B4", "C#5", "D5", "E5", "F#5", "E5"], vel=0.22, vel_fin=0.4)
    violines.melodia(56, "r/2 A4/0.5 B4/0.5 C#5/1", vel=0.46)           # anacrusa del tema
    for t0, t1, _s, b in bajos_unidos(C, 53, 57):
        cbajo.nota(C.c(t0), b, t1 - t0, vel=0.42)
    cielo.acordes_ligados(C.voicings(53, 73, voces=3, rango=("A4", "E6")), vel=0.55)
    tex.clip(swell(Piano(fieltro=0.45), ["G2", "D3", "B3", "F#4", "A4", "D5"], largo_tiempos=8,
                   vel=0.62, curva=2.2), fin=57, ganancia_db=-14.1)
    tex.clip(swell(Violines(), ["D5", "B5", "F#6"], largo_tiempos=8, vel=0.55), fin=57, ganancia_db=-10)

    # ------------------------------------------------------- 57–64 cumbre 2
    arpegio_piano(piano, C, 57, 65, P_CUM2, paso=0.25, vel=0.32, rango=("F#3", "C#5"), acentos=A_332)
    sub_corcheas(sub, C, 57, 65, vel=0.85)
    groove(bat, "cumbre2", 57, 65)
    for c in (58, 60, 62):
        bat.golpe(f"{c}:4.5", "hat_abierto", 0.45)
    bat.patron("caja", ".... .... .... oxxX", 64, 65, vel=0.45)
    violines.melodia(57, TEMA_2, vel=0.68)
    violas.melodia(57, TEMA_2, vel=0.42, transponer=-12)
    chelos.melodia(57, CONTRA_2, vel=0.29)
    for t0, t1, _s, b in bajos_unidos(C, 57, 65):
        cbajo.nota(C.c(t0), b, t1 - t0, vel=0.56)
    for c, frase in GLOCK_2.items():
        glock.melodia(c, frase, vel=0.46)
    celesta.melodia(59, "r/2 E6/0.5 F#6/0.5 A6/1", vel=0.46)
    celesta.melodia(61, TEMA_2B, vel=0.32, transponer=12)
    tex.clip(nube_de_banco("glock", "A6", dur_s=19.0, estirar=10, densidad=14, grano=(0.08, 0.22),
                           tonos=(0, 7, 12, -5), pesos=(4, 3, 1, 2), ataque=3, caida=5,
                           brillo_hz=8000), pos=57, ganancia_db=-20)

    # ------------------------------------------------------- 65–72 plenitud
    tex.clip(swell(Piano(fieltro=0.5), ["D2", "A2", "F#3", "C#4", "E4", "A4"], largo_tiempos=4,
                   vel=0.55), fin=65, ganancia_db=-15.7)
    arpegio_piano(piano, C, 65, 73, P_PLE, paso=0.25, vel=0.3, rango=("E3", "B4"), acentos=A_332)
    sub_corcheas(sub, C, 65, 73, vel=0.82)
    groove(bat, "plenitud", 65, 69, escala=1.08)
    groove(bat, "plenitud_b", 69, 72, escala=1.08)
    groove(bat, "plenitud", 72, 73, solo=("bombo", "shaker"))
    bat.patron("escobilla", ".... x... o.o. oxx.", 72, 73, vel=0.48)
    bat.golpe("72:4.5", "hat_abierto", 0.4)
    # violines y chelos en décimas paralelas que bajan (melodía escasa: una nota por compás)
    linea_ligada(violines, 65, ["F#5", "E5", "D5", "C#5", "B4", "A4", "G4", "A4"], vel=0.4, vel_fin=0.34)
    for t0, t1, _s, b in bajos_unidos(C, 65, 73, rango=("E3", "D#4")):
        chelos.nota(C.c(t0), b, t1 - t0, vel=0.39, legato=True)
    violas.acordes_ligados(C.voicings(65, 73, voces=2, rango=("C#4", "G#4")), vel=0.38, legato=True)
    for t0, t1, _s, b in bajos_unidos(C, 65, 73):
        cbajo.nota(C.c(t0), b, t1 - t0, vel=0.58)
    for c in (68, 72):
        celesta_voz.melodia(c, ECOS[c], vel=0.4)

    # ------------------------------------------------------- 73–80 resolución
    arpegio_piano(piano, C, 73, 77, P_LUZ, paso=0.5, vel=0.3, rango=("F#3", "D5"), acentos=A_8)
    arpegio_piano(piano, C, 77, 81, "0 2 4 3", paso=1.0, vel=0.3, rango=("F#3", "D5"))
    sub_largo(sub, C, 73, 77, vel=0.55, figura=2.0)
    sub_largo(sub, C, 77, 81, vel=0.48)
    groove(bat, "medio_esc", 73, 77)
    groove(bat, "latido", 77, 81)
    violines.melodia(73, "D5/0.5 E5/0.5_ F#5/0.5_ A5/2.5_ | B5/1_ A5/1_ F#5/2_ | E5/4_ | D5/4_ | "
                         "B4/4_ | D5/4_ | D5/2_ C#5/2_ | D5/2_ E5/2_", vel=0.36)
    violas.acordes_ligados(C.voicings(73, 81, voces=2, rango=("D4", "A4")), vel=0.28, legato=True)
    for t0, t1, _s, b in bajos_unidos(C, 73, 81, rango=("E3", "D#4")):
        chelos.nota(C.c(t0), b, t1 - t0, vel=0.32, legato=True)
    for t0, t1, _s, b in bajos_unidos(C, 73, 77):
        cbajo.nota(C.c(t0), b, t1 - t0, vel=0.4)

    # ------------------------------------------------------- 81–84 último acorde
    bat.golpe(81, "bombo", 0.42)
    piano.nota(81, "D2", 8, vel=0.3)
    piano.arpegio(81, 83, Cancion.voicing_en(C.voicings(81, 83, voces=4, rango=("F#3", "D5"))),
                  patron="0 2 4 3", paso=1.0, vel=0.25)
    pedal_acordes(piano, C, 81, 83)
    piano.acorde(83, ["D2", "A2", "F#3", "D4", "E4", "A4", "F#5"], 8, vel=0.3, rasgueo=0.08)
    piano.pedal(83, 96)       # deja sonar el último acorde: el pedal sube después del final
    sub.nota(81, "D2", 16, vel=0.42)
    cbajo.nota(81, "D2", 16, vel=0.38, vel_fin=0.05)
    chelos.nota(81, "D4", 16, vel=0.08, vel_fin=0.02, legato=True)
    violas.nota(81, "B4", 4, vel=0.26).nota(82, "A4", 12, vel=0.26, vel_fin=0.04, legato=True)
    violines.melodia(81, "F#5/4_ | G5/4_ | F#5/8", vel=0.28, legato=True)   # 4–3 arriba de todo
    celesta_voz.melodia(82, CITA_FINAL, vel=0.36)
    glock.nota("83:3", "A5", 2, vel=0.39)
    cielo.acordes_ligados(C.voicings(81, 85, voces=3, rango=("A4", "D6")), vel=0.4)
    tex.clip(nube_acordes(Piano(fieltro=0.55), [(0, 2, ["D3", "A3", "E4", "F#4", "A4"]),
                                                 (2, 2, ["D4", "F#4", "A4", "E5"])],
                          dur_s=18.0, estirar=6.0, densidad=12, grano=(0.1, 0.3),
                          tonos=(0, 12, -12), pesos=(5, 2, 1), ataque=4, caida=9, pan=0.5),
             pos=81, ganancia_db=-11.9)

    # ------------------------------------------------------- automatizaciones
    # el pad se abre de verdad en las cumbres (sin voz); bajo la voz respira cerrado
    pad.auto("corte", [(1, 260), (5, 520, "exp"), (9, 1100, "exp"), (17, 1250, "exp"),
                       (25, 1500, "exp"), (32, 2100, "exp"), (33.5, 4500, "exp"), (40, 4800),
                       (42, 1100, "exp"), (49, 1300), (56, 2100, "exp"), (57.5, 5200, "exp"),
                       (64, 6000), (66, 2300, "exp"), (73, 1800, "exp"), (81, 1200, "exp"),
                       (86, 450, "exp")])
    pad.auto("vol", [(1, -30), (3, -10, "suave"), (5, -7), (9, 0, "suave"), (41, 0), (42, -3, "suave"),
                     (49, -2), (57, 0, "suave"), (80, 0), (82, -3, "suave"), (87, -10, "suave")])
    cielo.auto("corte", [(33, 2400), (37, 3800, "exp"), (41, 2000, "exp"), (53, 1600),
                         (56.5, 1800), (57.5, 4200, "exp"), (64, 4200), (66, 2000, "exp"), (73, 1800),
                         (81, 1600), (86, 600, "exp")])
    cielo.auto("vol", [(33, -12), (37, 0, "suave"), (40, 0), (42, -30, "suave"), (53, -16),
                       (57, 0, "suave"), (64, 0), (66, -4, "suave"), (73, -8, "suave"), (81, -7),
                       (87, -14, "suave")])
    violines.auto("expresion", [(1, 1.0), (33, 0.86), (34.9, 1.0, "suave"), (35, 0.92),
                                (36.9, 1.0, "suave"), (37, 0.9), (38.9, 1.0, "suave"), (39, 0.94),
                                (40.9, 1.0, "suave"), (57, 0.9), (58.9, 1.0, "suave"), (59, 0.94),
                                (60.9, 1.0, "suave"), (61, 0.92), (62.9, 1.0, "suave"), (63, 0.96),
                                (64.9, 1.0, "suave"), (83, 1.0), (85.5, 0.3, "suave")])
    for p in (violas, chelos):
        p.auto("expresion", [(1, 1.0), (83, 1.0), (85.5, 0.3, "suave")])
    bat.auto("vol", [(17, -2.0), (25, 0.0), (73, 0.0), (77, -2.0), (81, -5.0)])
    # cuerdas: ganancia por sección. Con la nivelación nueva la capa suave suena de verdad
    # suave; para conservar el timbre de cada dinámica se compensa con vol (bajo la voz los
    # violines tocan pp cerca del micrófono, en las cumbres cantan con su timbre de mf–f)
    ganancia_por_seccion(violines, C, {"alba": 10.3, "ascenso": 10.3, "impulso": 11.9, "cumbre": 8.4,
                                       "respiro": 8.8, "cumbre_2": 9.5, "plenitud": 10.6,
                                       "resolucion": 11.1, "ultimo_acorde": 10.5})
    ganancia_por_seccion(violas, C, {"alba": 5.3, "ascenso": 9.3, "impulso": 10.0, "cumbre": 10.9,
                                     "respiro": 8.2, "retorno": 10.5, "cumbre_2": 10.0, "plenitud": 7.8,
                                     "resolucion": 8.9, "ultimo_acorde": 10.5})
    ganancia_por_seccion(cbajo, C, {"cumbre": 3.5, "retorno": -1.3, "cumbre_2": 2.1, "plenitud": -0.4,
                                    "resolucion": 5.4, "ultimo_acorde": 4.0})
    chelos.auto("vol", [(1, -4.0), (8, -4.0), (10, 0.0, "suave")])   # alba: lejos
    celesta.auto("vol", [(1, -3.0), (8.5, -3.0), (9.5, 0.0, "suave")])
    return C
