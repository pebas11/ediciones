"""«Marea» — canción 3: reflexión y emoción. Cálida, melancólica pero esperanzada.

Si menor que gira a Re mayor en la segunda mitad (la esperanza). 6/8 a ♩ = 72
(negra con puntillo = 48: un compás de 2,5 s, el vaivén lento de una ola).
68 compases + ritardando + 10 s de cola ≈ 3:01.

Forma (compases):
   1–6   bajamar    neblina granular de chelo, el motivo en el piano de fieltro;
                    el vibráfono con arco toma las notas altas
   7–14  orilla     la figura de ola del piano (6 corcheas que suben y bajan),
                    entra el contrabajo                                     [bajo voz]
  15–22  ola        el chelo canta el tema A (Si menor); violas en olas     [bajo voz]
  23–30  resaca     tema A' con retardos 4–3 sobre Fa#7; mecedora del piano;
                    asoman los violines                                     [bajo voz]
  31–34  giro       oleada de cuerdas: Sol – Mi – La sus4 → La (el giro)
  35–42  claridad   subito piano: Re mayor, tema B en el chelo, el vibráfono brilla [bajo voz]
  43–50  crecida    bajo que sube por grados, pizzicato del contrabajo,
                    violines en notas largas                                [bajo voz]
  51–58  pleamar    tutti: tema B en violines y chelos a la octava, pulso grave muy suave
  59–68  reflujo    la marea se retira sobre un pedal de Re; cierre en D6/9 [bajo voz]

Respiración: la velocidad del piano, la expresión de las cuerdas y la neblina se
mueven en olas de 4 compases (cresta en el 3.º); las secciones dibujan la marea.

Lugar para la voz: en las secciones [bajo voz] la melodía es el chelo en notas
largas (Fa#3–Si4, fundamentales < 500 Hz), el vibráfono con arco no tiene ataque
y el piano va con fieltro y velocidades bajas.

Instrumentos propios de esta canción (definidos abajo, sin tocar el motor):
  * VibArco: vibráfono con arco (banco `vibrafono_arco`), nivelado por muestra.
  * ChelosN, ViolasN, ViolinesN, ContrabajoN, PianoN, PizzN: los mismos muestreos
    del motor con una tabla de corrección de nivel por muestra (capa, altura, rr),
    medida sobre el tramo estable (K-ponderado; en el pizzicato, el primer segundo).
    En `chelos` y `violas` la capa suave quedaba 12 y 7 dB más fuerte que la fuerte
    (un crescendo no subía de volumen) y `vibrafono_arco` no estaba nivelado.
"""
import numpy as np

from motor import (Cancion, Muestreador, Cuerdas, Piano, Pizzicato, Bateria, Textura,
                   swell, nube_de_banco, EQ, Filtro, Auto, acorde)
from motor.nucleo import desde_db, nota

# =============================================================== 1. DATOS ==
BPM = 72
SEMILLA = 1903
TPC = 3.0                      # tiempos (negras) por compás de 6/8

SECCIONES = [
    # nombre      compases energía emoción                                       voz    loop
    ("bajamar",    6, 0.15, "quietud: el mar en calma, todavía de noche",       False, (3, 7),
     "motivo en el piano (c3–6); neblina de chelo; vibráfono con arco"),
    ("orilla",     8, 0.26, "calma que respira",                                True,  (7, 15),
     "figura de ola del piano + contrabajo; sin melodía"),
    ("ola",        8, 0.36, "nostalgia que avanza",                             True,  (15, 23),
     "chelo: tema A en notas largas (Fa#3–Sol4); violas en olas"),
    ("resaca",     8, 0.46, "melancolía que crece, una pregunta",               True,  (23, 31),
     "tema A' y retardos sobre Fa#7; violines desde c27; cadencia rota hacia el giro"),
    ("giro",       4, 0.62, "el giro: algo se ilumina",                         False, (31, 35),
     "oleada de cuerdas (crescendo) que desemboca en Re mayor; transición"),
    ("claridad",   8, 0.40, "esperanza que amanece",                            True,  (35, 43),
     "subito piano en Re mayor; chelo: tema B; vibráfono más presente"),
    ("crecida",    8, 0.54, "la esperanza toma fuerza",                         True,  (43, 51),
     "pizzicato del contrabajo; violines en notas largas; crece hacia la pleamar"),
    ("pleamar",    8, 0.90, "plenitud, gratitud",                               False, (51, 59),
     "tutti: tema B en violines y chelos a la octava; pulso grave muy suave"),
    ("reflujo",   10, 0.22, "serenidad: la marea se retira",                    True,  (59, 67),
     "colas de cuerdas, pedal de Re, último motivo del chelo; final en c67–68"),
]

# Un acorde por compás ("Asus4 A6" parte el compás de 6/8 en dos negras con puntillo).
ARMONIA = {
    1:  "Bm(add9) | Bm(add9) | Bm(add9) | Gmaj7 | Em9 | Asus4 A6",
    # tema A: el bajo baja como el agua que se retira (Si La Sol Fa# Mi) y vuelve a subir
    7:  "Bm(add9) | Bm7/A | Gmaj7 | F#m7 | Em9 | D/F# | Gmaj9#11 | Asus4 A6",
    15: "Bm(add9) | Bm7/A | Gmaj7 | F#m7 | Em9 | D/F# | Gmaj9#11 | Asus4 A6",
    # resaca: la dominante con sensible (La#) y su retardo 4–3; cadencia rota al Sol del giro
    23: "Bm(add9) | Em9 | Gmaj7 | F#7sus4 F#7 | Bm(add9) | Bm7/A | Gmaj9#11 | F#7sus4 F#7",
    31: "Gmaj9#11 | Em9 | Asus4 | A",
    # Re mayor: el mismo bajo que baja, ahora luminoso
    35: "Dmaj9 | A/C# | Bm(add9) | Bm7/A | Gmaj9#11 | D/F# | Em9 | Asus4 A",
    # crecida: el bajo sube por grados dos veces (Fa# Sol La Si · Mi Fa# Sol La)
    43: "D/F# | Gmaj7 | A6 | Bm(add9) | Em9 | F#m7 | Gmaj9#11 | Asus4 A",
    51: "Dmaj9 | A/C# | Bm(add9) | Bm7/A | Gmaj9#11 | D/F# | Em9 | Asus4 A",
    # reflujo: pedal de Re, y la última ola
    59: "Dmaj9 | Em9/D | Gmaj7/D | Dmaj9 | Bm(add9) | Gmaj9#11 | Asus4 | A6 | D6/9 | D6/9",
}

# ---- Motivo: la ola sube desde la 5ª (Fa#–Si–Do#–Re), rompe y se retira por grados.
MOTIVO = "F#4/1.5 B4/1 C#5/0.5 | D5/3 | B4/1.5 G4/1 F#4/0.5 | D4/1.5 C#4/1.5"

# ---- Tema A (chelo, Si menor): apoyatura Do#→Si sobre Gmaj7 y retardos 4–3.
TEMA_A = ("F#3/1.5_ B3/1_ C#4/0.5_ | D4/3 | C#4/1.5_ B3/1.5_ | A3/3 | "
          "B3/1.5_ E4/1_ F#4/0.5_ | G4/1.5_ F#4/1.5 | E4/1.5_ D4/1_ C#4/0.5_ | D4/1.5_ C#4/1.5")
# ---- Tema A' (resaca): sube a Sol4 y cae sobre el retardo Si→La# de Fa#7.
TEMA_A2 = ("F#3/1.5_ B3/1_ D4/0.5_ | G4/3 | F#4/1.5_ E4/1_ D4/0.5 | B3/1.5_ A#3/1.5 | "
           "C#4/1.5_ D4/1_ F#4/0.5_ | G4/1.5_ F#4/1.5 | E4/1.5_ D4/1_ C#4/0.5 | B3/1.5_ A#3/1.5")
# ---- Tema B (Re mayor): el mismo gesto, ahora con retardos 6–5 que se abren.
TEMA_B = ("A3/1.5_ D4/1_ E4/0.5_ | F#4/1.5_ E4/1.5 | D4/1.5_ C#4/1.5_ | B3/3 | "
          "D4/1.5_ G4/1_ A4/0.5_ | B4/1.5_ A4/1.5 | G4/1.5_ F#4/1_ E4/0.5_ | D4/1.5_ C#4/1.5")
# ---- Tema B' (crecida): las crestas suben Fa#4 → Sol4 → La4 → Si4.
TEMA_B2 = ("A3/1.5_ D4/1_ E4/0.5_ | F#4/3 | B3/1.5_ E4/1_ F#4/0.5_ | G4/1.5_ F#4/1.5 | "
           "G3/1.5_ B3/1_ E4/0.5_ | A4/3 | B4/1.5_ A4/1_ F#4/0.5_ | E4/1_ D4/0.5_ C#4/1.5")

# ---- Giro: violines (la oleada) y chelo por debajo.
GIRO_VLN = "B4/1.5_ D5/1_ E5/0.5_ | F#5/3_ | E5/1.5_ D5/1.5_ | C#5/3"
GIRO_CHELO = "D4/1.5_ B3/1.5_ | G3/3 | A3/1.5_ D4/1.5_ | E4/3"

# ---- Vibráfono con arco: notas largas que coronan los acordes (brillo sin ataque).
#      (compás, altura, duración en tiempos, vel)
VIB = [
    # bajamar: toma las crestas del motivo
    (1.5, "B4", 4.5, 0.30), (4, "D5", 4.5, 0.36), (6.5, "C#5", 1.5, 0.32),
    # orilla: un destello al final de cada ola
    (10, "C#5", 5.0, 0.30), (14, "E5", 4.5, 0.32),
    # ola
    (16, "F#5", 5.0, 0.30), (18.5, "E5", 4.0, 0.28), (20, "A5", 4.5, 0.30), (22, "E5", 3.5, 0.30),
    # resaca (el La# se apaga antes del acorde siguiente: Si menor / Sol)
    (24, "F#5", 5.0, 0.32), (26, "B4", 1.5, 0.30), (26.5, "A#4", 1.3, 0.30, {"soltar": 0.7}),
    (28, "C#5", 5.0, 0.32), (30, "B4", 1.5, 0.32), (30.5, "A#4", 1.3, 0.32, {"soltar": 0.7}),
    # giro: sube con la oleada
    (31, "F#5", 6.0, 0.40), (33, "E5", 3.0, 0.44), (34, "E5", 3.0, 0.42),
    # claridad: más presente
    (35, "A5", 5.5, 0.44), (37, "F#5", 5.5, 0.40), (39, "F#5", 3.0, 0.42), (40, "A5", 3.0, 0.40),
    (41, "B5", 3.0, 0.40), (42, "E5", 3.0, 0.42),
    # crecida
    (44, "F#5", 5.0, 0.38), (46, "F#5", 4.5, 0.36), (48, "A5", 4.5, 0.38), (50, "E5", 3.0, 0.42),
    # pleamar: arriba de todo
    (51, "A5", 6.0, 0.50), (53, "F#5", 6.0, 0.48), (55, "C#6", 6.0, 0.50), (57, "B5", 3.0, 0.48),
    (58, "E6", 3.0, 0.44),
    # reflujo: la novena queda sonando
    (59, "F#5", 6.0, 0.3), (63, "F#5", 6.0, 0.22), (65, "E5", 6.0, 0.22), (67, "E5", 6.0, 0.22),
]

# ---- Filtro del piano (Hz): la marea entera y, adentro, olas de 4 compases (cresta al 40 %).
CORTE_PIANO = [
    (1, 3000), (7, 3600, "suave"),
    (8.6, 5000, "suave"), (11, 3000, "suave"), (12.6, 5200, "suave"), (15, 3200, "suave"),     # orilla
    (16.6, 5800, "suave"), (19, 3400, "suave"), (20.6, 6000, "suave"), (23, 3600, "suave"),    # ola
    (24.6, 6800, "suave"), (27, 3800, "suave"), (28.6, 7200, "suave"), (31, 4500, "suave"),    # resaca
    (33.5, 14000, "exp"), (35, 6500, "exp"),                                                    # giro
    (36.6, 8500, "suave"), (39, 5000, "suave"), (40.6, 8500, "suave"), (43, 5000, "suave"),    # claridad
    (44.6, 9000, "suave"), (47, 6000, "suave"), (48.6, 11000, "suave"), (51, 14000, "exp"),    # crecida
    (59, 14000), (61, 7000, "exp"), (64, 4500, "exp"), (69, 2600, "exp"),                       # reflujo
]

# ---- Pulso grave (solo en la pleamar): negras con puntillo, como un latido lejano.
PULSO = "x..... x....."            # 12 semicorcheas = un compás de 6/8


# ============================================ 2. INSTRUMENTOS NIVELADOS ===
# Corrección de nivel (dB) por muestra: (capa, midi de la muestra, rr). Medida sobre el
# tramo estable K-ponderado de cada muestra (con el ajuste del banco) y refinada con el
# render de cada capa pura: el instrumento queda parejo (±1 dB) entre alturas y la
# velocidad vuelve a mandar en el volumen (en chelos la capa suave sonaba 12 dB más).
CORR = {
    "vibrafono_arco": {(0, 57, 1): 12, (0, 64, 1): 2, (0, 67, 1): 3.5, (0, 74, 1): -4,
                       (0, 81, 1): -2, (0, 88, 1): -8.5},
    "chelos": {(0, 36, 1): -9.5, (0, 40, 1): -3, (0, 40, 2): -6.5, (0, 43, 1): -10.5,
               (0, 47, 1): -10, (0, 50, 1): -8.5, (0, 53, 1): -6.5, (0, 57, 1): -6.5,
               (0, 60, 1): -3.5, (0, 64, 1): -0.5, (0, 67, 1): -2, (0, 71, 1): -2,
               (0, 74, 1): -5, (0, 77, 1): -6, (1, 36, 1): 0.5, (1, 40, 1): 3.5,
               (1, 43, 1): 7, (1, 47, 1): 6.5, (1, 50, 1): 9.5, (1, 53, 1): 5, (1, 57, 1): 6,
               (1, 60, 1): 10, (1, 64, 1): 6, (1, 67, 1): 8.5, (1, 71, 1): 4.5, (1, 74, 1): 5,
               (1, 77, 1): 6},
    "contrabajo": {(0, 28, 1): 5.5, (0, 30, 1): 3.5, (0, 31, 1): 9, (0, 34, 1): -0.5,
                   (0, 36, 1): 3, (0, 38, 1): 9, (0, 40, 1): 6, (0, 42, 1): 1.5,
                   (0, 44, 1): -8.5, (0, 45, 1): -9.5, (0, 49, 1): 1, (0, 52, 1): 0.5,
                   (0, 56, 1): -4, (0, 59, 1): -3, (1, 28, 1): 1.5, (1, 30, 1): 2.5,
                   (1, 31, 1): 6.5, (1, 34, 1): -4.5, (1, 36, 1): -1, (1, 38, 1): 0,
                   (1, 40, 1): 2.5, (1, 42, 1): -3, (1, 44, 1): -4, (1, 45, 1): -1.5,
                   (1, 49, 1): 1, (1, 52, 1): 1, (1, 56, 1): 1, (1, 59, 1): -9},
    "violas": {(0, 48, 1): -4, (0, 50, 1): -5, (0, 52, 1): -4.5, (0, 55, 1): -5,
               (0, 59, 1): -1.5, (0, 62, 1): -3, (0, 65, 1): -4, (0, 69, 1): -5,
               (0, 72, 1): -7.5, (0, 76, 1): -4, (0, 79, 1): -11.5, (0, 83, 1): -1,
               (0, 86, 1): -4.5, (1, 48, 1): -0.5, (1, 50, 1): 3.5, (1, 52, 1): 5,
               (1, 55, 1): 8.5, (1, 59, 1): 5.5, (1, 62, 1): 2, (1, 65, 1): 7.5, (1, 69, 1): 5,
               (1, 72, 1): 6.5, (1, 76, 1): 3.5, (1, 79, 1): 7, (1, 83, 1): 4, (1, 86, 1): -5},
    "violines": {(0, 55, 1): 2.5, (0, 57, 1): 1, (0, 59, 1): 3, (0, 62, 1): 2, (0, 66, 1): -1,
                 (0, 69, 1): -1.5, (0, 72, 1): -4, (0, 76, 1): 1, (0, 79, 1): -1, (0, 83, 1): 1,
                 (0, 86, 1): -2.5, (1, 55, 1): 0.5, (1, 57, 1): -0.5, (1, 59, 1): -0.5,
                 (1, 62, 1): -1, (1, 66, 1): -2, (1, 69, 1): 3, (1, 72, 1): 1.5, (1, 76, 1): -1,
                 (1, 79, 1): -6, (1, 83, 1): -1.5, (1, 86, 1): -8},
    # pizzicato: nivel de los primeros ~1,2 s desde el pico de cada muestra
    "contrabajo_pizz": {(0, 28, 1): -3.5, (0, 28, 2): -4, (0, 30, 1): 5, (0, 30, 2): 5.5,
                        (0, 31, 1): 3.5, (0, 31, 2): 3, (0, 34, 1): -2, (0, 34, 2): 0,
                        (0, 36, 1): 4.5, (0, 36, 2): 3, (0, 38, 1): -8, (0, 38, 2): -8,
                        (0, 40, 1): 1.5, (0, 40, 2): 1, (0, 42, 1): -3.5, (0, 42, 2): -3.5,
                        (0, 44, 1): 3.5, (0, 44, 2): 5, (0, 45, 1): 1, (0, 45, 2): -0.5,
                        (0, 49, 1): 0.5, (0, 49, 2): 2, (0, 52, 1): -1.5, (0, 52, 2): -2.5,
                        (0, 56, 1): 1, (0, 56, 2): -0.5, (0, 59, 1): -4, (0, 59, 2): -4,
                        (1, 28, 1): -3, (1, 28, 2): -3, (1, 30, 1): 0, (1, 30, 2): -1.5,
                        (1, 31, 1): -2, (1, 31, 2): -1.5, (1, 34, 1): -0.5, (1, 34, 2): 1.5,
                        (1, 36, 1): 3, (1, 36, 2): 3.5, (1, 40, 1): 1, (1, 40, 2): 2.5},
    # piano: solo los saltos entre muestras vecinas (residuo sobre una recta: conserva la
    # caída natural hacia el agudo)
    "piano": {(0, 33, 1): -1, (0, 35, 1): 0, (0, 37, 1): 2.5, (0, 39, 1): 2.5, (0, 41, 1): -1,
              (0, 43, 1): 1, (0, 45, 1): -2.5, (0, 47, 1): 0, (0, 49, 1): 1.5, (0, 51, 1): 2.5,
              (0, 53, 1): 0, (0, 55, 1): -0.5, (0, 57, 1): -1, (0, 59, 1): 2, (0, 61, 1): -2,
              (0, 63, 1): -2, (0, 65, 1): 1, (0, 67, 1): -0.5, (0, 69, 1): -0.5, (0, 71, 1): -1,
              (0, 73, 1): 1.5, (0, 75, 1): -1, (0, 77, 1): 2.5, (0, 79, 1): -1, (0, 81, 1): -1,
              (0, 83, 1): -1.5, (0, 85, 1): -5, (0, 87, 1): -4,
              (1, 33, 1): -2, (1, 35, 1): 1, (1, 37, 1): 2.5, (1, 39, 1): 2.5, (1, 41, 1): -0.5,
              (1, 43, 1): 1.5, (1, 45, 1): -1.5, (1, 47, 1): 0.5, (1, 49, 1): 1.5,
              (1, 51, 1): 1.5, (1, 53, 1): 0, (1, 55, 1): -1, (1, 57, 1): -1, (1, 59, 1): 0,
              (1, 61, 1): -0.5, (1, 63, 1): -0.5, (1, 65, 1): 0.5, (1, 67, 1): -1,
              (1, 69, 1): -1, (1, 71, 1): -0.5, (1, 73, 1): 2, (1, 75, 1): -2, (1, 77, 1): 2.5,
              (1, 79, 1): -3, (1, 81, 1): -2.5, (1, 83, 1): -3, (1, 85, 1): -5.5, (1, 87, 1): -2},
}


class Nivelado:
    """Mezcla: aplica CORR[banco] a cada muestra leída (antes del cruce de capas)."""

    def leer(self, midi, capa, n_total, offset, clave, sostenida=False, semilla=0):
        y = super().leer(midi, capa, n_total, offset, clave, sostenida, semilla)
        b = self.banco
        i = b.elegir(midi, capa, clave)
        g = CORR.get(self.banco_nombre, {}).get(
            (int(b.capa[i]), int(round(b.midi[i])), int(b.rr[i])), 0.0)
        return y * np.float32(desde_db(g)) if g else y


class CuerdasN(Nivelado, Cuerdas):
    pass


def ChelosN(**kw):
    kw.setdefault("ganancia_db", 3.5)        # vuelve a la calibración del motor (−26 a vel 0,6)
    return CuerdasN("chelos", **kw)


def ViolasN(**kw):
    kw.setdefault("ganancia_db", 1.0)
    return CuerdasN("violas", **kw)


def ViolinesN(**kw):
    return CuerdasN("violines", **kw)


def ContrabajoN(**kw):
    kw.setdefault("rango_db", 20.0)
    kw.setdefault("ganancia_db", 2.0)
    return CuerdasN("contrabajo", **kw)


class PianoN(Nivelado, Piano):
    pass


class PizzN(Nivelado, Pizzicato):
    pass


class VibArco(Nivelado, Muestreador):
    """Vibráfono con arco (VCSL, bowed): el arco entra en ~0,5 s, sostiene unos 5 s y la
    lámina sigue sonando al soltar. Sin ataque percusivo: brillo que no pisa la voz."""

    def __init__(self, rango_db=18.0, soltar=2.8, **kw):
        kw.setdefault("tope_hz", 9000.0)
        kw.setdefault("capas_vel", (0.3, 0.85))
        kw.setdefault("ganancia_db", -11.0)   # banco sin calibrar: −26 LUFS a vel 0,6
        kw.setdefault("abrir", 0.2)
        super().__init__("vibrafono_arco", rango_db=rango_db, soltar=soltar, **kw)
        self.nombre = "vibrafono_arco"


# ============================================================ 3. AYUDAS ===
def grave_ok(lo, hi):
    """Regla del grave del proyecto (la misma que revisar_grave)."""
    d = hi - lo
    return not ((lo < 50 and 0 < d < 7) or (50 <= lo < 52 and 0 < d < 3))


def escalera(sim, bajo, sup, quinta=True, octava=False, medio=True, techo_medio=None):
    """Notas de la figura, de abajo hacia arriba: mano izquierda abierta (bajo, su 5ª o su
    8ª y la 10ª, todo debajo de La3) y el voicing agudo `sup` de la mano derecha. Entre las
    dos queda un hueco en 200–400 Hz: ahí canta el chelo. Respeta la regla del grave."""
    ac = acorde(sim)
    pcs = ac.pcs
    techo_medio = techo_medio or (62 if octava else 57)
    out = [bajo]
    if octava:
        out.append(bajo + 12)
    elif quinta and (bajo + 7) % 12 in pcs:
        out.append(bajo + 7)
    elif quinta:   # sin 5ª propia (acorde invertido): la nota del acorde más cercana que quepa
        for m in range(bajo + 7, bajo + 13):
            if m % 12 in pcs and grave_ok(bajo, m):
                out.append(m)
                break
    if medio:
        # 10ª: la 3ª del acorde (o la nota suspendida); si la 3ª ya está en el bajo, la 5ª;
        # si no entra, la 7ª menor o la 6ª (una 7ª mayor en el registro medio-grave empasta
        # y roza con la raíz cuando la canta el chelo)
        tercera = ac.pcs_por_rol("tercera")
        septima = {pc for pc in ac.pcs_por_rol("septima") if (pc - ac.raiz) % 12 != 11}
        quinta_raiz = ac.pcs_por_rol("quinta") | {ac.raiz}
        for pcs_m in (quinta_raiz if ac.bajo in tercera else tercera, septima, quinta_raiz):
            cands = [m for m in range(out[-1] + 3, techo_medio + 1)
                     if m % 12 in pcs_m and grave_ok(out[-1], m)]
            if cands:
                out.append(cands[0])
                break
        else:
            out.append(out[-1])        # la figura conserva su forma (índice 2 = mano izquierda)
    for m in sorted(set(sup)):
        if m > out[-1] and grave_ok(out[-1], m):
            out.append(m)
    return out


CRESTA = 0.4      # la ola crece durante el 40 % de su período y se retira en el resto


def ola(c, desde, periodo=4.0, prof=0.15, cresta=CRESTA):
    """Factor de dinámica en olas: valle al empezar cada ola, cresta al `cresta` del período
    (las frases del chelo llegan a su nota alta en el 2.º compás de cada cuatro)."""
    f = ((c - desde) / periodo) % 1.0
    y = -np.cos(np.pi * f / cresta) if f < cresta else np.cos(np.pi * (f - cresta) / (1 - cresta))
    return 1.0 + prof * y


def olas_auto(desde, hasta, lo, hi, periodo=4.0, fin=None, cresta=CRESTA, curva="suave"):
    """Puntos de automatización en olas (valle–cresta–valle) entre dos compases."""
    pts = [(desde, lo)]
    c = desde
    while c + periodo <= hasta + 1e-9:
        pts.append((c + periodo * cresta, hi, curva))
        pts.append((c + periodo, lo, curva))
        c += periodo
    if fin is not None:
        pts.append((hasta, fin, curva))
    return pts


def roza(m, t0, t1, melodicas, min_solape=0.5):
    """¿La altura m forma 2ª menor o 9ª menor con alguna nota melódica que suene al menos
    `min_solape` tiempos dentro de [t0, t1)?"""
    return any(min(n.t + n.dur, t1) - max(n.t, t0) >= min_solape
               and abs(int(n.midi) - m) in (1, 13, 25)
               for p in melodicas for n in p.notas if n.t < t1 and n.t + n.dur > t0)


def sin_roces(voicings, melodicas, rango, min_solape=0.5):
    """Contrapunto: si una nota del voicing forma 2ª menor o 9ª menor con una nota de la
    melodía que suena encima (un retardo, una apoyatura), se cambia por la nota del acorde
    más cercana que no roce. Así el retardo no suena contra su propia resolución."""
    lo, hi = nota(rango[0]), nota(rango[1])
    out = []
    for (t0, t1, sim, v) in voicings:
        pcs = acorde(sim).pcs
        nuevo = []
        for m in v:
            if not roza(m, t0, t1, melodicas, min_solape):
                nuevo.append(m)
                continue
            resto = nuevo + [z for z in v if z != m]
            cands = sorted((x for x in range(lo, hi + 1) if x % 12 in pcs and x not in v
                            and x not in nuevo and not roza(x, t0, t1, melodicas, min_solape)
                            and all(abs(x - y) not in (1, 13) for y in resto)),
                           key=lambda x: (abs(x - m), x))
            if cands:
                nuevo.append(cands[0])
        out.append((t0, t1, sim, sorted(nuevo)))
    return out


def pedal_por_acorde(p, C, desde, hasta, hueco=0.06):
    """Pedal que se renueva con cada acorde (los retardos de medio compás no se empastan)."""
    for t0, t1, _s in C.acordes(desde, hasta):
        a, b = max(t0, C.tempo.pos(desde)), min(t1, C.tempo.pos(hasta))
        p.pedales.append((a + 0.02, b - hueco))


def figura(p, C, desde, hasta, pasos, vel, rango=("A4", "A5"), voces=3, quinta=True,
           octava=False, acentos=(1.12, 0.78, 0.86, 1.0, 0.8, 0.86), periodo=4.0, prof=0.15,
           dur=1.5, tope=None, rasgueo=0.012, forma=None, melodicas=()):
    """Figura de piano en 6/8: `pasos` = 6 elementos por compás (uno por corchea), cada uno
    un índice de la escalera (0 = bajo), una tupla de índices (acorde) o None (silencio).
    La velocidad respira en olas de `periodo` compases; `forma(c)` la escala (crescendos)."""
    vs = C.voicings(desde, hasta, voces=voces, rango=rango, tope=tope)
    if melodicas:
        vs = sin_roces(vs, melodicas, rango)
    bs = C.bajos(desde, hasta, rango=("A1", "G#2"))
    t_ini = C.tempo.pos(desde)
    for (t0, t1, sim, v), (_, _, _, b) in zip(vs, bs):
        esc = escalera(sim, b, v, quinta, octava)
        if melodicas and len(esc) > 2 and roza(esc[2], t0, t1, melodicas):
            esc[2] = esc[1]           # la nota media no se pone debajo de un retardo
        t = t0
        while t < t1 - 1e-6:
            k = int(round(((t - t_ini) % TPC) / 0.5)) % 6
            paso = pasos[k]
            if paso is not None:
                c = C.c(t)
                f = ola(c, desde, periodo, prof) * acentos[k] * (forma(c) if forma else 1.0)
                idx = paso if isinstance(paso, tuple) else (paso,)
                alts = sorted({esc[min(i, len(esc) - 1)] for i in idx})
                d = min(dur, t1 - t - 0.01)       # la tecla se suelta antes del acorde nuevo
                if len(alts) > 1:
                    p.acorde(c, alts, d, vel=vel * f, rasgueo=rasgueo)
                else:
                    p.nota(c, alts[0], d, vel=vel * f)
            t += 0.5
    pedal_por_acorde(p, C, desde, hasta)


def bajo_largo(p, C, desde, hasta, vel=0.4, rango=("A1", "G#2"), legato=False, recorte=0.1,
               periodo=4.0, prof=0.12, arco=0.04):
    """Contrabajo (o chelos en 8va): una nota por acorde; la dinámica sigue la ola de
    `periodo` compases y cada nota crece apenas (`arco`) como un arco que se apoya."""
    for t0, t1, _s, b in C.bajos(desde, hasta, rango=rango):
        v = vel * ola(C.c(t0), desde, periodo, prof)
        x = {"legato": True} if legato else {}
        p.nota(C.c(t0), b, t1 - t0 - recorte, vel=v, vel_fin=v + arco, **x)


def respira(p, C, desde, hasta, vel=0.32, rango=("A4", "A5"), melodicas=()):
    """Piano que respira: bajo y acorde (apenas arpegiado) en el 1, una nota en el 4."""
    vs = C.voicings(desde, hasta, voces=3, rango=rango)
    if melodicas:
        vs = sin_roces(vs, melodicas, rango)
    bs = C.bajos(desde, hasta, rango=("A1", "G#2"))
    for (t0, t1, sim, v), (_, _, _, b) in zip(vs, bs):
        esc = escalera(sim, b, v)
        p.acorde(C.c(t0), esc[:2], t1 - t0 - 0.01, vel=vel + 0.04, rasgueo=0.02)
        # la mano derecha entra un instante después (y se suelta antes del acorde nuevo)
        p.acorde(C.c(t0 + 0.06), [m for m in esc[2:] if m not in esc[:2]], t1 - t0 - 0.08,
                 vel=vel * 0.9, rasgueo=0.03)
        if t1 - t0 >= TPC - 1e-6:
            p.nota(C.c(t0 + 1.5), esc[-1], 1.5, vel=vel * 0.72)
            p.nota(C.c(t0 + 2.5), esc[-2], 0.5, vel=vel * 0.6)
    pedal_por_acorde(p, C, desde, hasta)


# ============================================================ 4. CANCIÓN ==
def cancion() -> Cancion:
    C = Cancion("Marea", slug="03-marea", bpm=BPM, compas=(6, 8),
                tonalidad="Si menor → Re mayor", semilla=SEMILLA, cola_s=10.0)
    for nom, comp, e, emo, voz, loop, notas in SECCIONES:
        C.seccion(nom, comp, energia=e, emocion=emo, voz=voz, loop=loop, notas=notas)
    for c, prog in ARMONIA.items():
        C.progresion(c, prog)
    C.ritardando(65, 69, 58)          # la última ola se demora
    # mismo espacio que «Umbral» (sala grande, cinta); el eco va a la negra: contra el
    # 6/8 dibuja ondas que se cruzan
    C.fx["reverb"].update(dur=3.8, predelay_ms=32, brillo=0.46)
    C.fx["eco"].update(division=1.0, realim=0.3, corte=2600.0)

    # ---------------------------------------------------------------- pistas
    mar = C.pista("mar", Textura(), "textura", vol=3.0, envios={"reverb": 0.22},
                  efectos=[EQ(("pa", 140), ("campana", 290, -3.0, 0.8)),
                           Filtro("pasabajos", corte=Auto([(1, 1300)] + olas_auto(3, 59, 1100, 2600)[1:] +
                                                         [(63, 1200, "suave"), (69, 800, "suave")]),
                                  q=0.7, polos=2)])
    oleaje = C.pista("oleaje", Textura(), "textura", vol=0.0)
    piano = C.pista("piano", PianoN(fieltro=0.7, mecanica=0.5), "armonia", vol=0.5,
                    envios={"reverb": 0.24, "eco": 0.04},
                    efectos=[EQ(("pa", 38), ("campana", 300, -3.0, 0.8), ("agudos", 7000, 3.0)),
                             Filtro("pasabajos", corte=Auto(CORTE_PIANO), q=0.65, polos=2)])
    # el chelo que canta, apenas a la derecha: deja el centro exacto para la voz
    chelo = C.pista("chelo", ChelosN(pan=0.2), "melodia", vol=0.0, envios={"reverb": 0.26},
                    efectos=[EQ(("pa", 65), ("campana", 230, -1.5, 0.9), ("campana", 3000, -4.5, 0.8),
                                ("agudos", 7000, 4.5))])
    chelos2 = C.pista("chelos2", ChelosN(), "armonia", vol=-2.0, envios={"reverb": 0.3},
                      efectos=[EQ(("pa", 55), ("campana", 260, -2.0, 0.9))])
    violas = C.pista("violas", ViolasN(), "armonia", vol=-4.0, envios={"reverb": 0.32},
                     efectos=[EQ(("pa", 160), ("campana", 330, -3.0, 0.9), ("campana", 2800, -3.5, 0.8),
                              ("agudos", 7000, 3.0))])
    violines = C.pista("violines", ViolinesN(doble=True), "melodia", vol=0.0,
                       envios={"reverb": 0.36},
                       efectos=[EQ(("pa", 200), ("campana", 2800, -5.0, 0.7), ("agudos", 8500, 4.5))])
    cbajo = C.pista("contrabajo", ContrabajoN(), "bajo", vol=-2.5, envios={"reverb": 0.14},
                    efectos=[EQ(("pa", 36), ("pb", 3200))])
    pizz = C.pista("pizz", PizzN("contrabajo"), "bajo", vol=-3.0, envios={"reverb": 0.2},
                   efectos=[EQ(("pa", 40), ("pb", 2500))])
    vib = C.pista("vib", VibArco(tope_hz=12000.0), "melodia", vol=0.0,
                  envios={"reverb": 0.38, "eco": 0.08},
                  efectos=[EQ(("pa", 200), ("campana", 2500, -10.0, 0.6), ("agudos", 6500, 4.0))])
    pulso = C.pista("pulso", Bateria(color=0.2, tono=0.9), "bateria", vol=0.0,
                    envios={"sala": 0.15}, efectos=[EQ(("pb", 170, 0.7), ("pa", 30))])

    # humanización (determinista)
    piano.humanizar(tiempo_ms=10, vel=0.06)
    for p in (chelo, chelos2, violas, violines, cbajo):
        p.humanizar(tiempo_ms=13, vel=0.04)
    pizz.humanizar(tiempo_ms=8, vel=0.06)
    vib.humanizar(tiempo_ms=8, vel=0.05)
    pulso.humanizar(tiempo_ms=5, vel=0.05)

    # ---------------------------------------------------------------- textura: la neblina
    # Nubes granulares de las propias muestras de chelo, con las notas que caben en toda la
    # armonía de cada tramo: Si+Fa# (Si menor), solo Fa# en la resaca (Fa#7 tiene La#),
    # La+Mi en Re mayor. El volumen respira en olas de 4 compases.
    mar.clip(nube_de_banco("chelos", "B2", dur_s=58.0, estirar=16, densidad=9, grano=(0.25, 0.6),
                           tonos=(0, 7, 12), pesos=(3, 3, 1), pan=0.9, ataque=7, caida=6,
                           brillo_hz=1600), pos=1, ganancia_db=-6)
    mar.clip(nube_de_banco("chelos", "F#3", dur_s=34.0, estirar=14, densidad=9, grano=(0.25, 0.6),
                           tonos=(0, -12, 12), pesos=(3, 2, 1), pan=0.9, ataque=6, caida=6,
                           brillo_hz=1600), pos=21.5, ganancia_db=-7)
    mar.clip(nube_de_banco("chelos", "A3", dur_s=92.0, estirar=18, densidad=9, grano=(0.25, 0.6),
                           tonos=(0, -5, 7), pesos=(3, 2, 2), pan=0.9, ataque=6, caida=10,
                           brillo_hz=1700), pos=33, ganancia_db=-7)
    mar.auto("vol", [(1, 0.0)] + olas_auto(3, 59, -6.0, 0.0)[1:] +
             [(61, -5, "suave"), (64, -6, "suave"), (69, -10, "suave")])

    # ---------------------------------------------------------------- 1–6 bajamar
    figura(piano, C, 1, 3, [(0, 1), None, None, 2, None, None], vel=0.28,
           acentos=(1, 1, 1, 0.8, 1, 1), prof=0.0, dur=3.0)
    piano.melodia(3, MOTIVO, vel=0.46)
    figura(piano, C, 3, 7, [(0, 1), None, None, 2, None, None], vel=0.25,
           acentos=(1, 1, 1, 0.75, 1, 1), prof=0.0, dur=3.0)

    # ---------------------------------------------------------------- 7–14 orilla
    oleaje.clip(swell(PianoN(fieltro=0.6), ["B2", "F#3", "D4", "C#5"], largo_tiempos=4.5, vel=0.5),
                fin=7, ganancia_db=-17)
    figura(piano, C, 7, 15, [0, 1, 2, 3, 4, 3], vel=0.31)
    bajo_largo(cbajo, C, 7, 15, vel=0.34)
    # las violas asoman con una nota común (Fa#4 cabe en Em9, D/F#, Gmaj9#11) y bajan a Mi
    violas.nota(11, "F#4", 9.0, vel=0.22, vel_fin=0.34).nota(14, "E4", 3.0, vel=0.3, vel_fin=0.2)

    # ---------------------------------------------------------------- 15–22 ola
    chelo.melodia(15, TEMA_A, vel=0.48)
    figura(piano, C, 15, 23, [(0, 1), None, 2, (3, 5), None, 4], vel=0.3, melodicas=[chelo])
    bajo_largo(cbajo, C, 15, 23, vel=0.38)
    violas.acordes_ligados(sin_roces(C.voicings(15, 23, voces=2, rango=("E4", "C#5")), [chelo],
                                     ("E4", "D5")), vel=0.34)

    # ---------------------------------------------------------------- 23–30 resaca
    oleaje.clip(swell(VibArco(), ["F#4", "B4", "C#5"], largo_tiempos=3.0, vel=0.5),
                fin=23, ganancia_db=-12)
    chelo.melodia(23, TEMA_A2, vel=0.56)
    figura(piano, C, 23, 31, [(0, 1), 2, 3, (4, 5), 3, 2], vel=0.31, melodicas=[chelo])
    bajo_largo(cbajo, C, 23, 31, vel=0.44)
    violas.acordes_ligados(sin_roces(C.voicings(23, 31, voces=2, rango=("E4", "D5")),
                                     [chelo, violines], ("E4", "D5")), vel=0.4)
    violines.nota(27, "F#5", 6.0, vel=0.2, vel_fin=0.3).nota(29, "E5", 3.0, vel=0.3)
    violines.nota(30, "E5", 1.5, vel=0.32, legato=True).nota("30:2.5", "C#5", 1.5, vel=0.34,
                                                           legato=True)

    # ---------------------------------------------------------------- 31–34 giro
    oleaje.clip(swell(VibArco(), ["G4", "B4", "F#5"], largo_tiempos=4.5, vel=0.55),
                fin=31, ganancia_db=-11)
    violines.melodia(31, GIRO_VLN, vel=0.56)
    chelo.melodia(31, GIRO_CHELO, vel=0.56)
    bajo_largo(chelos2, C, 31, 35, vel=0.5, rango=("A2", "G#3"), prof=0.0)
    bajo_largo(cbajo, C, 31, 35, vel=0.52, prof=0.0, arco=0.08)
    violas.acordes_ligados(sin_roces(C.voicings(31, 35, voces=3, rango=("D4", "B4")),
                                     [chelo, violines], ("D4", "C#5")), vel=0.48)
    # sin la 5ª grave: los chelos tocan el bajo a la 8va (la regla del grave entre pistas)
    figura(piano, C, 31, 35, [0, 1, 2, 3, 4, 5], vel=0.34, voces=4, rango=("A4", "D6"),
           octava=True, prof=0.0, acentos=(1.1, 0.8, 0.85, 1.0, 0.9, 0.95),
           forma=lambda c: float(np.interp(c, [31, 33.5, 34.9], [0.95, 1.2, 0.9])),
           melodicas=[chelo, violines])
    # la oleada desemboca en Re mayor: el acorde nuevo se adelanta desde el reverso
    oleaje.clip(swell(VibArco(), ["D4", "A4", "E5", "F#5"], largo_tiempos=6.0, vel=0.6, curva=2.2),
                fin=35, ganancia_db=-9)

    # ---------------------------------------------------------------- 35–42 claridad
    chelo.melodia(35, TEMA_B, vel=0.53)
    figura(piano, C, 35, 43, [0, 1, 2, 4, 3, 2], vel=0.29, rango=("A4", "B5"), melodicas=[chelo])
    bajo_largo(cbajo, C, 35, 43, vel=0.36)
    violas.acordes_ligados(sin_roces(C.voicings(37, 43, voces=2, rango=("E4", "C#5")), [chelo],
                                     ("E4", "D5")), vel=0.34)

    # ---------------------------------------------------------------- 43–50 crecida
    chelo.melodia(43, TEMA_B2, vel=0.56)
    figura(piano, C, 43, 51, [(0, 1), 2, 3, (4, 5), 3, 2], vel=0.32, rango=("A4", "B5"),
           octava=True, melodicas=[chelo, violines])
    # pizzicato del contrabajo: fundamental en el 1 y su 8va en el 4 (el pulso de la marea)
    for t0, t1, _s, b in C.bajos(43, 51, rango=("A1", "G#2")):
        f = ola(C.c(t0), 43, 4.0, 0.12)
        pizz.nota(C.c(t0), b, 1.4, vel=0.5 * f)
        if t1 - t0 >= TPC - 1e-6:
            pizz.nota(C.c(t0 + 1.5), b + 12, 1.4, vel=0.4 * f)
    violines.acordes_ligados(sin_roces(C.voicings(43, 51, voces=2, rango=("C#5", "A5")), [chelo],
                                       ("C#5", "B5")), vel=0.3)
    violas.acordes_ligados(sin_roces(C.voicings(43, 51, voces=2, rango=("E4", "C#5")),
                                     [chelo, violines], ("E4", "D5")), vel=0.4)
    bajo_largo(cbajo, C, 47, 51, vel=0.4, prof=0.0, arco=0.12)
    oleaje.clip(swell(PianoN(fieltro=0.55), ["D2", "A2", "E3", "F#3", "C#4", "A4", "E5"],
                      largo_tiempos=7.5, vel=0.6, curva=2.2), fin=51, ganancia_db=-12)

    # ---------------------------------------------------------------- 51–58 pleamar
    chelo.melodia(51, TEMA_B, vel=0.74)
    violines.melodia(51, TEMA_B, vel=0.76, transponer=12)
    bajo_largo(chelos2, C, 51, 59, vel=0.64, rango=("A2", "G#3"), legato=True)
    bajo_largo(cbajo, C, 51, 59, vel=0.62)
    violas.acordes_ligados(sin_roces(C.voicings(51, 59, voces=3, rango=("D4", "B4")),
                                     [chelo, violines], ("D4", "C#5")), vel=0.6)
    figura(piano, C, 51, 59, [(0, 1), 2, 3, (4, 5), 3, 2], vel=0.36, voces=4,
           rango=("A4", "D6"), octava=True, prof=0.1, melodicas=[chelo, violines])
    pulso.patron("bombo", PULSO, 51, 59, vel=0.36)

    # ---------------------------------------------------------------- 59–68 reflujo
    violines.nota(59, "F#5", 5.0, vel=0.32, vel_fin=0.05, legato=True)
    violas.nota(59, "A4", 5.0, vel=0.3, vel_fin=0.05).nota(59, "D5", 5.0, vel=0.26, vel_fin=0.04)
    chelo.nota(59, "D4", 6.0, vel=0.38, vel_fin=0.14)
    cbajo.nota(59, "D2", 12.0, vel=0.36, vel_fin=0.2).nota(63, "B1", 3.0, vel=0.23)
    cbajo.nota(64, "G1", 3.0, vel=0.23).nota(65, "A1", 6.0, vel=0.23, vel_fin=0.26)
    cbajo.nota(67, "D2", 6.0, vel=0.25, vel_fin=0.07)
    respira(piano, C, 59, 67, vel=0.19, melodicas=[chelo, violines])
    chelo.melodia(63, "A3/1.5_ D4/1_ E4/0.5_ | F#4/3 | E4/1.5_ D4/1.5_ | C#4/3 | D4/6", vel=0.3)
    piano.acorde(67, ["D2", "A2", "E3", "F#3", "B3", "E4", "A4"], 6.0, vel=0.23, rasgueo=0.06)
    piano.pedal(67, 69.9)
    piano.melodia("68:2.5", "F#5/1.5", vel=0.26)

    # ---------------------------------------------------------------- vibráfono con arco
    for c, alt, d, v, *x in VIB:
        vib.nota(c, alt, d, vel=v, **(x[0] if x else {}))

    # ---------------------------------------------------------------- automatizaciones
    # (sin escalones: cada cambio es una rampa, para que no haya clicks)
    chelo.auto("expresion", olas_auto(15, 31, 0.8, 1.0) +
               [(33.5, 1.0, "suave"), (34.9, 0.8, "suave")] + olas_auto(35, 51, 0.8, 1.0)[1:] +
               [(52.4, 1.0, "suave"), (54.5, 0.9, "suave"), (56.2, 1.0, "suave"),
                (58.9, 0.95, "suave"), (60, 0.85, "suave")])
    violas.auto("expresion", [(11, 0.8), (15, 0.6)] + olas_auto(15, 31, 0.6, 0.95)[1:] +
                [(33.5, 1.0, "suave"), (34.9, 0.6, "suave"), (37, 0.55)] +
                olas_auto(37, 51, 0.55, 0.95, periodo=7.0)[1:] + [(52, 0.85, "suave"), (58.5, 1.0),
                                                     (60, 0.8, "suave")])
    violines.auto("expresion", [(27, 0.6), (31, 0.9, "suave"), (33.5, 1.0, "suave"),
                                (34.9, 0.55, "suave"), (43, 0.55)] +
                  olas_auto(43, 47, 0.55, 0.85)[1:] +
                  [(50.9, 0.92, "suave"), (52.4, 1.0, "suave"), (54.5, 0.9, "suave"),
                   (56.2, 1.0, "suave"), (58.9, 0.92, "suave"), (60, 0.8, "suave")])
    chelos2.auto("expresion", [(31, 0.6), (33.5, 1.0, "suave"), (34.9, 0.6, "suave"),
                               (51, 0.85), (59, 0.8)])
    cbajo.auto("expresion", [(7, 0.9), (31, 0.9), (33.5, 1.0, "suave"), (35, 0.85, "suave")])
    return C
