"""«Deriva» — canción 2: la cama principal de las explicaciones.
Movimiento constante y curiosidad luminosa: fluida, nunca quieta, nunca invasiva.

La mayor / Fa# menor, 104 bpm, 4/4, 80 compases (ritardando en los 4 últimos) + 9 s de
cola ≈ 3:14. El 70 % (c9–56 y c65–72) va bajo voz.

Todo "rueda" en grupos de 3 contra el 4/4:
  * el arpegio en semicorcheas acentúa cada 3 (polirritmo 3:4); cada frase de
    4 compases cierra con un grupo de 4 (o de 2) y vuelve a empezar acentuada;
  * el sub camina en tresillo (3+3+2 corcheas) y el Rhodes comparte ese tresillo;
  * el trémolo del Rhodes late en tresillos de corchea, el motor del vibráfono en
    corcheas, y el eco de la banda repite a la corchea con puntillo (= 3 semicorcheas).
El arpegio pasa de mano en mano: vibráfono → arpa con pizzicatos → piano de
fieltro → vibráfono en aumentación (corcheas) → arpa y piano en movimiento contrario.

Forma (compases):
   1–8   orilla      el arpegio solo (vibráfono); el filtro se abre
   9–16  corriente   entran el Rhodes con trémolo y el sub                 [bajo voz]
  17–24  deriva      batería en medio tiempo; el sub camina en tresillo    [bajo voz]
  25–32  cardumen    Fa# menor; el arpegio pasa al arpa, pizzicatos en los  [bajo voz]
                     acentos, aro en 2 y 4, entra el pad
  33–40  altamar     piano de fieltro rodando, arpa en los acentos,       [bajo voz]
                     contracanto de chelos, escobillas
  41–48  respiro     puente sin batería: IV → bVI (Fmaj9#11) → I/5 → bVII  [bajo voz]
                     (G6/9) → V sus; arpegio en corcheas, cuerdas que respiran
  49–56  regreso     el groove vuelve por capas                            [bajo voz]
  57–64  plenitud    el tema (vibráfono + violas a la 8ª baja), todo junto
  65–72  estela      meseta después de la cumbre                           [bajo voz]
  73–80  bruma       el arpegio se desarma nota a nota; el tema se apaga sobre
                     el bVI (Do natural) y vuelve la tercera mayor; nube granular

Lugar para la voz: en las secciones [bajo voz] la melodía son ecos de 2–3 notas
(la cabeza del motivo) en la octava 5, a velocidad baja; el arpegio rueda suave
y el motor les aplica el hueco de 3 dB en 2,4 kHz. La batería lleva un valle
fijo en 3 kHz (transitorios suaves en 1–4 kHz).

Prueba de una parte sin tocar render.py:
    DERIVA_SECCIONES=respiro,regreso python3 motion/musica/render.py 02 --hasta 17
arma solo esas secciones, una tras otra, desde el compás 1.
"""
import os

from motor import (Cancion, Piano, Arpa, Vibrafono, Rhodes, Pad, Sub, Chelos, Violas,
                   Violines, Pizzicato, Bateria, Textura, swell, nube, nube_de_banco,
                   EQ, Filtro, Tremolo, Ducking, Compresor, Saturacion, Ancho, Auto, acorde,
                   escala, rng, nota)
from motor.teoria import bajo_de

# =============================================================== 1. DATOS ==
BPM = 104
SEMILLA = 2610
TPC = 4.0
MOTOR_CORCHEAS = BPM / 60.0 * 2      # Hz: el motor del vibráfono late en corcheas

SECCIONES = [
    # nombre      comp energía emoción                                  voz    loop (relativo)  notas
    ("orilla",      8, 0.18, "curiosidad: algo empieza a moverse",     False, (4, 8),
     "solo el arpegio de vibráfono; el filtro se abre"),
    ("corriente",   8, 0.32, "avance sereno",                          True,  None,
     "entran el Rhodes con trémolo y el sub; shaker desde el c13"),
    ("deriva",      8, 0.44, "movimiento fluido, atención despierta",  True,  None,
     "batería en medio tiempo; el sub camina en tresillo"),
    ("cardumen",    8, 0.50, "curiosidad juguetona",                   True,  None,
     "Fa# menor; arpa rodando con pizzicatos; aro en 2 y 4; pad"),
    ("altamar",     8, 0.56, "amplitud, el horizonte se abre",         True,  None,
     "piano de fieltro rodando; contracanto de chelos; escobillas"),
    ("respiro",     8, 0.30, "pausa luminosa, suspensión",             True,  None,
     "puente sin batería; préstamos bVI y bVII; cuerdas"),
    ("regreso",     8, 0.50, "reanudar con ganas",                     True,  None,
     "el groove vuelve por capas"),
    ("plenitud",    8, 0.80, "claridad plena: todo encaja",            False, None,
     "el tema en vibráfono y violas; arpa y piano en contrario"),
    ("estela",      8, 0.55, "satisfacción en movimiento",             True,  None,
     "meseta después de la cumbre; se va aligerando"),
    ("bruma",       8, 0.18, "se deshace en la luz",                   False, (0, 4),
     "el arpegio se desarma; nube granular; ritardando final"),
]

# Un acorde por compás ("E6sus4 E" divide el compás en dos).
ARMONIA = {
    "orilla":    "Amaj9 | Amaj9 | F#m11 | F#m11 | Dmaj9 | Dmaj9 | E6sus4 | E6sus4",
    "corriente": "Amaj9 | C#m7 | F#m11 | Dmaj9 | Amaj9/C# | Dmaj9 | Bm9 | E6sus4",
    "deriva":    "Amaj9 | C#m7 | F#m11 | Dmaj9 | Bm9 | C#m7 | Dmaj9 | E6sus4",
    "cardumen":  "F#m11 | Dmaj9 | Amaj9/C# | Bm9 | F#m11 | Dmaj9 | Bm9 | C#m7",
    "altamar":   "Dmaj9 | E6sus4 | C#m7 | F#m11 | Bm9 | Amaj9/C# | Dmaj9 | E6sus4 E",
    "respiro":   "Dmaj9 | Dmaj9 | Fmaj9#11 | Fmaj9#11 | Amaj9/E | Amaj9/E | G6/9 | E6sus4",
    "regreso":   "Amaj9 | C#m7 | F#m11 | Dmaj9 | Amaj9/C# | Dmaj9 | Bm9 | E6sus4",
    "plenitud":  "Amaj9 | C#m7 | F#m11 | Dmaj9 | Amaj9/C# | Dmaj9 | Bm9 | E6sus4 E",
    "estela":    "F#m11 | Dmaj9 | Amaj9/C# | Bm9 | F#m11 | Dmaj9 | G6/9 | E6sus4",
    "bruma":     "Amaj9 | Amaj9 | Dmaj9/A | Dmaj9/A | Fmaj7#11/A | Fmaj7#11/A | Amaj9 | Amaj9",
}

# Escaleras del arpegio: el acorde abierto, de grave a agudo (índice 0 = abajo).
# Terceras y cuartas, sin segundas abajo; los colores (9ª, 11ª, #11) arriba.
ESCALERAS = {
    "Amaj9":      "A3 C#4 E4 G#4 B4 E5 G#5",
    "Amaj9/C#":   "G#3 C#4 E4 A4 B4 E5 G#5",
    "Amaj9/E":    "G#3 B3 E4 A4 C#5 E5 G#5",
    "C#m7":       "G#3 C#4 E4 G#4 B4 E5 G#5",
    "F#m11":      "F#3 A3 C#4 F#4 B4 E5 A5",       # arriba, cuartas apiladas (C# F# B E A)
    "Dmaj9":      "A3 D4 F#4 A4 C#5 E5 A5",
    "Dmaj9/A":    "A3 D4 F#4 A4 C#5 E5 A5",
    "Bm9":        "B3 D4 F#4 A4 C#5 F#5 A5",
    "E6sus4":     "B3 E4 A4 C#5 E5 A5 B5",
    "E":          "B3 E4 G#4 B4 E5 G#5 B5",
    "Fmaj9#11":   "A3 C4 E4 G4 B4 E5 G5",          # Fa lidio sin la raíz (la da el bajo)
    "G6/9":       "G3 B3 E4 A4 D5 G5 B5",          # cuartas puras (B E A D G)
    "Fmaj7#11/A": "A3 C4 F4 A4 B4 E5 A5",
}

# Celdas: grupos de 3 pasos (índices en la escalera). El primero de cada grupo va
# acentuado, así los acentos dibujan una línea propia que deriva contra el compás.
# Ningún grupo empieza con la nota con la que terminó el anterior (nada de repiques).
CELDAS = {
    "ola":      "012 123 234 123",      # olas que suben y vuelven
    "remolino": "021 243 132 354",      # grave-agudo-medio, en zigzag
    "abierta":  "024 135 246 135",      # saltos de 5ª/6ª: más aire
    "alta":     "354 243 465 354",      # la mitad aguda de la escalera
    "espejo":   "432 321 210 321",      # olas que bajan (contrario de "ola")
}

# ---- Motivo: sube una 4ª y sigue por grados (la ola), cae en arpegio.
# Ritmo de 3: corchea con puntillo, corchea con puntillo, corchea (= 3+3+2).
MOTIVO = "E5/0.75 A5/0.75 B5/0.5 C#6/1.5 B5/0.5 | G#5/1.5 E5/1.5 B4/1"
RESPUESTA = "C#5/0.75 F#5/0.75 G#5/0.5 A5/1.5 G#5/0.5 | E5/1.5 C#5/1.5 A4/1"
# Tema completo (plenitud), con ligaduras para las violas.
TEMA = ("E5/0.75_ A5/0.75_ B5/0.5_ C#6/1.5_ B5/0.5_ | G#5/1.5_ E5/1.5_ B4/1 | "
        "C#5/0.75_ F#5/0.75_ G#5/0.5_ A5/1.5_ G#5/0.5_ | E5/1.5_ C#5/1.5_ A4/1 | "
        "E5/0.75_ A5/0.75_ B5/0.5_ E6/1.5_ D6/0.5_ | C#6/1.5_ A5/1.5_ F#5/1 | "
        "D6/0.75_ C#6/0.75_ B5/0.5_ A5/1_ F#5/1 | E5/0.75_ F#5/0.75_ A5/0.5_ B5/2")
# Contracantos de chelos (registro de tenor: nunca debajo de Mi3).
CONTRA_ALTAMAR = ("C#4/3_ B3/1 | A3/4 | G#3/3_ B3/1 | A3/2_ C#4/2 | D4/3_ C#4/1 | "
                  "B3/2_ G#3/2 | A3/4 | A3/2_ G#3/2")
CONTRA_PLENITUD = ("G#3/4 | G#3/2_ B3/2 | A3/4 | A3/2_ F#3/2 | E3/2_ G#3/2 | F#3/2_ A3/2 | "
                   "D4/2_ C#4/2 | A3/2_ G#3/2")

# ---- Batería (semicorcheas; dígito = velocidad/9, x normal, o fantasma).
SH = "2324 2325 2324 2326"            # shaker en semicorcheas (con swing leve)
GROOVE = {
    "deriva": {       # medio tiempo: bombo en el 1 y en el "y" del 2, aro en el 3
        "bombo":  "7... ..6. .... .... 7... ..6. ..5. ....",
        "aro":    ".... .... 5... .... .... .... 5... ....",
        "aro_f":  "...2 .... ...2 ..2. .... ..2. ...2 .2.2",
        "shaker": SH,
    },
    "cardumen": {     # tiempo entero: aro en 2 y 4
        "bombo":  "7... ..6. .... .... 7... ..6. ..5. ....",
        "aro":    ".... 5... .... 5...",
        "aro_f":  "..2. ...2 .2.. ..2. ..2. .... .2.. .2.2",
        "hat":    "..3. ..4. ..3. ..4.",
        "shaker": ".2.2 .2.3 .2.2 .2.3",
    },
    "altamar": {      # escobillas en 2 y 4 (cambio de color)
        "bombo":  "7... ..6. ..5. .... 7... ..6. .... ..5.",
        "escobilla": ".... 5... .... 5...",
        "esc_f":  "..2. ...2 ..2. .2.. ..2. ...2 .2.. ..22",
        "hat":    "..3. ..3. ..3. ..4.",
        "shaker": SH,
    },
    "plenitud": {     # lo más lleno: caja suave en 2 y 4, hats en corcheas
        "bombo":  "8... ..7. ..6. .... 8... ..7. .... ..6.",
        "caja":   ".... 5... .... 5...",
        "esc_f":  "..2. ...2 ..2. .2.2",
        "hat":    "4.3. 5.3. 4.3. 5.3.",
        "shaker": SH,
    },
    "estela": {
        "bombo":  "7... ..6. .... .... 7... ..6. ..5. ....",
        "aro":    ".... 4... .... 4...",
        "aro_f":  "...2 .... ..2. ...2",
        "shaker": SH,
    },
}

ESCALA_LA = set(escala("A", "mayor"))
_ESC_CACHE = {}


# ============================================================ 2. AYUDAS ===
def P(c, tiempo=1.0):
    """Compás c, tiempo (1 = downbeat, 2.5 = "y" del 2) → posición en compases."""
    return c + (tiempo - 1.0) / TPC


def escalera(sim):
    """Escalera (MIDI, de grave a agudo) del acorde para el arpegio."""
    if sim not in _ESC_CACHE:
        if sim in ESCALERAS:
            _ESC_CACHE[sim] = [nota(x) for x in ESCALERAS[sim].split()]
        else:   # respaldo: voicing abierto de 6 voces
            from motor import conducir
            _ESC_CACHE[sim] = sorted(conducir([sim], voces=6, rango=("A3", "B5"))[0])
    return _ESC_CACHE[sim]


def rodar(p, C, desde, hasta, celdas="remolino", base=0, paso=0.25, vel=0.4,
          acentos=(1.0, 0.62, 0.74), dur=0.5, frase=4, transponer=0, prob=None,
          solo_acentos=False, recolectar=None, **x):
    """Arpegio que rueda en grupos de 3 sobre el 4/4 (polirritmo 3:4).

    * celdas: nombre en CELDAS o texto "021 132 243 132" (índices en la escalera
      del acorde vigente; cada grupo de 3 dígitos = 3 pasos, el 1º acentuado)
    * base: corre los índices (registro) · paso: 0.25 semicorcheas, 0.5 corcheas
    * frase: compases por frase; el resto de pasos se absorbe en un grupo de 4 (o
      forma uno de 2), así cada frase arranca acentuada en el downbeat
    * vel: número o función compás → velocidad · prob: función compás → probabilidad
      de que suene cada nota (para desarmarlo)
    * solo_acentos: solo la 1ª nota de cada grupo (pulso de corchea con puntillo)
    * recolectar: lista donde se agregan (t, midi) de los acentos (para doblarlos)
    """
    grupos = [[int(ch) for ch in g] for g in CELDAS.get(celdas, celdas).split()]
    t0, t1 = C.tempo.pos(desde), C.tempo.pos(hasta)
    g = rng(C.semilla, p.nombre, "rodar", round(t0 * 4))
    largo = frase * C.tempo.tpc
    tf = t0
    while tf < t1 - 1e-9:
        tf1 = min(tf + largo, t1)
        n = int(round((tf1 - tf) / paso))
        tam = [3] * (n // 3)
        resto = n % 3
        if resto == 1 and tam:
            tam[-1] = 4
        elif resto:
            tam.append(resto)
        k = 0
        for gi, tg in enumerate(tam):
            idx = grupos[gi % len(grupos)]
            for j in range(tg):
                t = tf + k * paso
                k += 1
                azar = g.random()
                if solo_acentos and j > 0:
                    continue
                pos = C.c(t)
                if prob is not None and azar > prob(pos):
                    continue
                esc = escalera(C.acorde_en(t + 1e-6))
                i = (idx[j] if j < 3 else idx[1]) + base
                alt = esc[i % len(esc)] + 12 * (i // len(esc)) + transponer
                ac = acentos[j] if j < 3 else acentos[1]
                v = vel(pos) if callable(vel) else vel
                p.nota(pos, alt, dur, vel=min(1.0, v * ac), **x)
                if recolectar is not None and j == 0:
                    recolectar.append((t, alt))
        tf = tf1


def fusionar(segs):
    """Une segmentos seguidos con el mismo bajo (o el mismo cifrado)."""
    out = []
    for seg in segs:
        t0, t1, s, b = seg
        if out and out[-1][3] == b and abs(out[-1][1] - t0) < 1e-6:
            out[-1] = (out[-1][0], t1, out[-1][2], b)
        else:
            out.append(seg)
    return out


def _salto(b, lo, hi):
    """El segundo golpe del tresillo: la 8ª si entra, si no la 5ª de abajo o de arriba."""
    for cand in (b + 12, b - 5, b + 7):
        if lo <= cand <= hi:
            return cand
    return b


def _vecina(obj, paso, pcs):
    m = obj + paso
    while m % 12 not in pcs:
        m += paso
    return m


def _aprox(obj, prev, b, pcs, lo, hi):
    """Nota de paso hacia `obj`: el grado vecino del lado de donde viene la línea
    (si repetiría una nota, el otro lado; si no, la cromática de abajo)."""
    lados = (1, -1) if prev > obj else (-1, 1)
    for lado in lados:
        m = _vecina(obj, lado, pcs)
        if lo <= m <= hi and m not in (prev, b):
            return m
    if lo <= obj - 1 <= hi and obj - 1 not in (prev, b):
        return obj - 1
    return _vecina(obj, lados[0], pcs)


def _paseo(b, obj, ac, pcs, lo, hi):
    """Caminata en negras: (2ª, 3ª, nota de paso) que lleva de `b` a `obj` por grados,
    con una nota del acorde en el tiempo 2 y sin repetir notas seguidas."""
    tonos = ac.pcs_por_rol("raiz", "tercera", "quinta", "septima") | {ac.bajo}
    escala_r = [m for m in range(lo, hi + 1) if m % 12 in pcs]
    aprox = {_vecina(obj, 1, pcs): 0.0, _vecina(obj, -1, pcs): 0.0}
    aprox.setdefault(obj - 1, 0.6)                      # cromática de abajo
    mejor, costo_min = (b, b, obj), 1e9
    for n2 in escala_r:
        for n3 in escala_r:
            for a, extra in aprox.items():
                if not (lo <= a <= hi):
                    continue
                saltos = (abs(n2 - b), abs(n3 - n2), abs(a - n3))
                if max(saltos) > 7 or n2 == b or n3 == n2 or a == n3:
                    continue
                c = sum(saltos) + extra
                c += 0.0 if n2 % 12 in tonos else 1.5
                c += 1.0 if n3 == obj else 0.0
                c += 0.8 if (n2 - b) * (n3 - n2) < 0 else 0.0     # cambio de dirección
                c += 1.5 if n3 == b else 0.0                       # vuelve a la raíz
                c += 1.0 if a == n2 else 0.0                       # va y viene
                if c < costo_min:
                    mejor, costo_min = (n2, n3, a), c
    return mejor


def sub_camina(p, C, desde, hasta, estilo="tresillo", vel=0.72, lo=32, hi=45):
    """Sub que camina. Estilos:
    * tresillo: raíz en el 1, 8ª (o 5ª) en el "y" del 2, nota de paso en el 4 (3+3+2)
    * negras: raíz, dos notas del acorde y la de paso hacia el próximo bajo
    * blancas: raíz y 8ª · largo: una nota por acorde (fusionando bajos iguales)
    La nota de paso apunta al bajo siguiente (también al de la sección que sigue)."""
    rango = ("G#1", "G#2")
    segs = fusionar(C.bajos(desde, hasta, rango=rango))
    sig = C.acordes(hasta, C.c(C.tempo.pos(hasta) + 0.25))
    nb_final = bajo_de(sig[0][2], rango, segs[-1][3]) if sig else segs[-1][3]
    for i, (t0, t1, s, b) in enumerate(segs):
        nb = segs[i + 1][3] if i + 1 < len(segs) else nb_final
        ac = acorde(s)
        pcs = ESCALA_LA if ac.pcs <= ESCALA_LA else ac.pcs
        d = t1 - t0
        if estilo == "largo" or d < TPC - 1e-6:
            p.nota(C.c(t0), b, d - 0.12, vel=vel)
            continue
        nbar = int(round(d / TPC))
        for k in range(nbar):
            tb = t0 + TPC * k
            obj = nb if k == nbar - 1 else b
            if estilo == "blancas":
                x = _salto(b, lo, hi)
                p.nota(C.c(tb), b, 1.9, vel=vel).nota(C.c(tb + 2), x, 1.9, vel=vel * 0.85)
            elif estilo == "tresillo":
                x = _salto(b, lo, hi)
                a = _aprox(obj, x, b, pcs, lo, hi)
                p.nota(C.c(tb), b, 1.4, vel=vel)
                p.nota(C.c(tb + 1.5), x, 1.4, vel=vel * 0.86)
                p.nota(C.c(tb + 3), a, 0.9, vel=vel * 0.8)
            elif estilo == "negras":
                c1, c2, a = _paseo(b, obj, ac, pcs, lo, hi)
                for kk, (m, f) in enumerate(((b, 1.0), (c1, 0.82), (c2, 0.86), (a, 0.8))):
                    p.nota(C.c(tb + kk), m, 0.9, vel=vel * f)


def rhodes_toca(p, C, desde, hasta, estilo="largo", vel=0.36, rango=("E3", "B4"), voces=4):
    """Rhodes: largo (un acorde por compás), respira (uno por acorde, aunque dure 2
    compases), tresillo (en el 1 y en el "y" del 2) o anticipa (cada acorde entra
    una corchea antes de la barra)."""
    vs = C.voicings(desde, hasta, voces=voces, rango=rango)
    if estilo == "respira":
        u = []
        for seg in vs:
            if u and u[-1][2] == seg[2] and abs(u[-1][1] - seg[0]) < 1e-6:
                u[-1] = (u[-1][0], seg[1], seg[2], u[-1][3])
            else:
                u.append(seg)
        vs = u
    for i, (t0, t1, _s, v) in enumerate(vs):
        d = t1 - t0
        if estilo in ("largo", "respira"):
            p.acorde(C.c(t0), v, d - 0.2, vel=vel, rasgueo=0.014)
        elif estilo == "tresillo":
            if d >= TPC - 1e-6:
                p.acorde(C.c(t0), v, 1.35, vel=vel, rasgueo=0.008)
                p.acorde(C.c(t0 + 1.5), v, 2.3, vel=vel * 0.8, rasgueo=0.006)
            else:
                p.acorde(C.c(t0), v, d - 0.15, vel=vel * 0.95, rasgueo=0.008)
        elif estilo == "anticipa":
            ini = t0 if i == 0 else t0 - 0.5
            fin = t1 - 0.6 if i < len(vs) - 1 else t1 - 0.15
            p.acorde(C.c(ini), v, fin - ini, vel=vel * (1.0 if i == 0 else 0.92), rasgueo=0.008)


def groove(bat, nombre, desde, hasta, solo=None, sin=()):
    for k, patron in GROOVE[nombre].items():
        if (solo and k not in solo) or k in sin:
            continue
        golpe = {"aro_f": "aro", "esc_f": "escobilla"}.get(k, k)
        bat.patron(golpe, patron, desde, hasta, vel=0.6)


def doblar_pizz(pz, C, acentos, desde, hasta, vel=0.3, prob=0.55, octava=0):
    """Pizzicatos sobre los acentos del arpegio (aparecen y desaparecen: cardumen)."""
    g = rng(C.semilla, "pizz", desde)
    a, b = C.tempo.pos(desde), C.tempo.pos(hasta)
    for t, m in acentos:
        if not (a - 1e-9 <= t < b - 1e-9) or g.random() > prob:
            continue
        m = m + 12 * octava
        while m < 55:
            m += 12
        pz.nota(C.c(t), m, 0.5, vel=vel)


class Arreglo:
    """Pistas + automatizaciones que cada sección va sumando (posiciones absolutas)."""

    def __init__(self, C):
        self.C = C
        self.puntos = {}

    def auto(self, pista, param, puntos):
        self.puntos.setdefault((pista, param), []).extend(puntos)

    def curva(self, pista, param, defecto):
        pts = self.puntos.get((pista, param))
        return Auto(sorted(pts, key=lambda q: q[0])) if pts else Auto([(1, defecto)])


# ======================================================== 3. SECCIONES ===
def s_orilla(A, c):
    C = A.C
    # el arpegio solo; deriva de verdad: la frase dura 8 compases (se realinea cada 3)
    rodar(A.vibra, C, c, c + 4, "ola", vel=lambda q: 0.36 + 0.02 * (q - c), frase=8)
    rodar(A.vibra, C, c + 4, c + 8, "remolino", vel=0.45, frase=4)
    A.auto("vibrafono", "vol", [(c, -18.0), (c + 2.5, 0.0, "suave")])
    # tibio mientras está solo; la luz se abre del todo cuando entran el Rhodes y el sub (c9)
    A.auto("vibrafono", "filtro", [(c, 650.0), (c + 3, 1800.0, "exp"), (c + 8, 3000.0, "exp"),
                                   (c + 9, 7500.0, "exp")])
    # agua: nube granular con notas que caben en los cuatro acordes (A B C# E)
    A.tex.clip(nube(Vibrafono(motor_hz=0), "A4/0.25 C#5 E5 B5 A5 E5 C#5 B4 A4 E5 C#6 B5 E5 A5 C#5 B4",
                    dur_s=16.0, estirar=6.0, densidad=11, grano=(0.08, 0.24), tonos=(0, 12),
                    pesos=(4, 1), ataque=5.0, caida=5.0), pos=c + 2, ganancia_db=-19)
    A.tex.clip(swell(Rhodes(trem_prof=0.25), ["A2", "E3", "G#3", "B3", "C#4"], largo_tiempos=6,
                     vel=0.5), fin=c + 8, ganancia_db=-17)


def s_corriente(A, c):
    C = A.C
    rodar(A.vibra, C, c, c + 8, "remolino", vel=0.38)
    rhodes_toca(A.rhodes, C, c, c + 8, "largo", vel=0.37)
    A.auto("rhodes", "trem", [(c, 0.45), (c + 8, 0.40)])
    sub_camina(A.sub, C, c, c + 4, "blancas", vel=0.66)
    sub_camina(A.sub, C, c + 4, c + 8, "tresillo", vel=0.70)
    A.bat.patron("shaker", SH, c + 4, c + 8)
    A.vibmel.melodia(P(c + 7, 3), "E5/0.75 A5/0.75 B5/0.5", vel=0.26)   # la cabeza del motivo


def s_deriva(A, c):
    C = A.C
    rodar(A.vibra, C, c, c + 8, "abierta", vel=0.35)
    groove(A.bat, "deriva", c, c + 8)
    A.bat.patron("hat", "..3. ..3. ..3. ..4.", c + 4, c + 8)
    A.bat.golpe(P(c + 7, 4.5), "hat_abierto", 0.36)
    sub_camina(A.sub, C, c, c + 8, "tresillo", vel=0.72)
    rhodes_toca(A.rhodes, C, c, c + 8, "tresillo", vel=0.37)
    A.auto("rhodes", "trem", [(c, 0.38), (c + 8, 0.36)])
    A.vibmel.melodia(P(c + 3, 3), "C#5/0.75 E5/0.75 F#5/0.5", vel=0.26)   # sobre Dmaj9
    A.vibmel.melodia(P(c + 7, 3), "E5/0.75 A5/0.75 B5/0.5", vel=0.26)     # sobre E6sus4
    A.tex.clip(swell(Arpa(), ["F#2", "C#3", "A3", "E4", "G#4"], largo_tiempos=4, vel=0.55),
               fin=c + 8, ganancia_db=-18)


def s_cardumen(A, c):
    C = A.C
    acentos = []
    rodar(A.arpa, C, c, c + 8, "alta", vel=0.33, dur=0.75, apagar=True, recolectar=acentos)
    A.auto("arpa", "vol", [(c, -9.0), (c + 2, 0.0, "suave")])
    rodar(A.vibra, C, c, c + 2, "abierta", vel=0.33)          # relevo: el vibráfono se va
    A.auto("vibrafono", "vol", [(c, 0.0), (c + 2, -14.0, "suave"), (c + 6, -14.0), (c + 7, 0.0, "suave")])
    doblar_pizz(A.pizz, C, acentos, c + 2, c + 8, vel=0.30, prob=0.55)
    rhodes_toca(A.rhodes, C, c, c + 8, "largo", vel=0.33)
    A.auto("rhodes", "trem", [(c, 0.34), (c + 8, 0.34)])
    A.pad.acordes_ligados(C.voicings(c, c + 8, voces=5, rango=("E3", "E5")), vel=0.44)
    A.auto("pad", "corte", [(c, 600.0), (c + 8, 1300.0, "exp")])
    A.auto("pad", "vol", [(c, -6.0), (c + 2, 0.0, "suave")])
    sub_camina(A.sub, C, c, c + 8, "negras", vel=0.70)
    groove(A.bat, "cardumen", c, c + 8)
    A.bat.golpe(P(c + 7, 4.5), "hat_abierto", 0.4)


def s_altamar(A, c):
    C = A.C
    rodar(A.piano, C, c, c + 8, "espejo", vel=0.28, dur=0.6)
    rodar(A.arpa, C, c, c + 8, "alta", vel=0.29, dur=1.5, apagar=True, solo_acentos=True)
    A.chelos.melodia(c, CONTRA_ALTAMAR, vel=0.35)
    A.auto("chelos", "expresion", [(c, 0.55), (c + 1.9, 0.9, "suave"), (c + 2, 0.7), (c + 3.9, 0.95, "suave"),
                                   (c + 4, 0.75), (c + 5.9, 1.0, "suave"), (c + 6, 0.8), (c + 7.9, 0.6, "suave")])
    rhodes_toca(A.rhodes, C, c, c + 8, "tresillo", vel=0.36)
    A.auto("rhodes", "trem", [(c, 0.36), (c + 8, 0.40)])
    A.pad.acordes_ligados(C.voicings(c, c + 8, voces=5, rango=("E3", "E5")), vel=0.40)
    A.auto("pad", "corte", [(c, 1300.0), (c + 8, 2100.0, "exp")])
    sub_camina(A.sub, C, c, c + 8, "tresillo", vel=0.74)
    groove(A.bat, "altamar", c, c + 8)
    A.bat.golpe(P(c + 7, 3), "barrido", 0.42, dur=2)      # la batería se retira hacia el puente


def s_respiro(A, c):
    C = A.C
    # el arpegio en aumentación: grupos de 3 corcheas (el 3:4 sigue, a la mitad de velocidad)
    rodar(A.vibra, C, c, c + 8, "ola", paso=0.5, vel=0.25, dur=1.0)
    rhodes_toca(A.rhodes, C, c, c + 8, "respira", vel=0.25)
    A.auto("rhodes", "trem", [(c, 0.40), (c + 1, 0.55, "suave"), (c + 7, 0.55), (c + 8, 0.36, "suave")])
    A.pad.acordes_ligados(C.voicings(c, c + 8, voces=5, rango=("E3", "F5")), vel=0.34)
    A.auto("pad", "corte", [(c, 1400.0), (c + 4, 2100.0, "exp"), (c + 8, 1500.0, "exp")])
    sub_camina(A.sub, C, c, c + 8, "largo", vel=0.36)
    for t0, t1, _s, b in fusionar(C.bajos(c, c + 8, rango=("G#1", "G#2"))):
        A.chelos.nota(C.c(t0), b, t1 - t0 - 0.12, vel=0.24, vel_fin=0.34)
    A.violas.acordes_ligados(C.voicings(c + 2, c + 8, voces=2, rango=("C#4", "A4")), vel=0.17)
    A.auto("violas", "vol", [(c, -4.0), (c + 8, -4.0), (c + 8.5, 0.0, "suave")])
    A.auto("chelos", "vol", [(c, 0.0), (c + 0.5, -3.0, "suave"), (c + 8, -3.0), (c + 8.5, 0.0, "suave")])
    A.auto("violas", "expresion", [(c, 0.5), (c + 3.5, 0.9, "suave"), (c + 4, 0.75), (c + 7.5, 0.95, "suave"),
                                   (c + 8, 0.6, "suave")])
    A.violines.melodia(c + 4, "C#5/4_ | E5/4_ | D5/4_ | C#5/4", vel=0.24)
    A.auto("violines", "expresion", [(c + 4, 0.45), (c + 6, 0.95, "suave"), (c + 8, 0.4, "suave")])
    # la cabeza del motivo, respirando sobre cada color del puente
    A.piano.melodia(P(c + 1, 3), "A4/0.75 D5/0.75 E5/0.5", vel=0.30)
    A.piano.melodia(P(c + 3, 3), "C5/0.75 F5/0.75 G5/0.5", vel=0.30)
    A.piano.melodia(P(c + 5, 3), "E5/0.75 A5/0.75 B5/0.5", vel=0.29)
    A.piano.melodia(P(c + 7, 2), "B4/1 C#5/2", vel=0.28)
    A.piano.pedal(P(c + 1, 3), P(c + 2, 4.9))
    A.piano.pedal(P(c + 3, 3), P(c + 4, 4.9))
    A.piano.pedal(P(c + 5, 3), P(c + 6, 4.9))
    A.piano.pedal(P(c + 7, 2), P(c + 8, 1))
    # aliento: nubes granulares de chelo (Re sobre IV y bVI, Mi sobre I/5, bVII y V)
    seg4 = C.tempo.seg(C.tempo.pos(c + 4)) - C.tempo.seg(C.tempo.pos(c))
    A.tex.clip(nube_de_banco("chelos", "D3", dur_s=seg4 + 1.0, estirar=10, densidad=9, grano=(0.18, 0.45),
                             tonos=(0, 12, 7), pesos=(4, 1, 1), ataque=2.5, caida=2.5), pos=c, ganancia_db=-25)
    A.tex.clip(nube_de_banco("chelos", "E3", dur_s=seg4 + 1.0, estirar=10, densidad=9, grano=(0.18, 0.45),
                             tonos=(0, 12, 7), pesos=(4, 1, 1), ataque=2.5, caida=2.5), pos=c + 4,
               ganancia_db=-25)
    A.tex.clip(swell(Piano(fieltro=0.45), ["A2", "E3", "B3", "C#4", "G#4", "E5"], largo_tiempos=8,
                     vel=0.6, curva=2.2), fin=c + 8, ganancia_db=-21)


def s_regreso(A, c):
    C = A.C
    rodar(A.vibra, C, c, c + 8, "remolino", vel=0.33)
    rodar(A.arpa, C, c + 4, c + 8, "alta", vel=0.29, dur=1.5, apagar=True, solo_acentos=True)
    acentos = []
    rodar(A.fantasma, C, c + 4, c + 8, "remolino", vel=0.0, recolectar=acentos)
    doblar_pizz(A.pizz, C, acentos, c + 4, c + 8, vel=0.28, prob=0.45)
    # el groove vuelve por capas: bombo y shaker, después el aro en el 3, después todo
    A.bat.patron("bombo", GROOVE["deriva"]["bombo"], c, c + 8)
    A.bat.patron("shaker", SH, c, c + 8)
    A.bat.patron("aro", GROOVE["deriva"]["aro"], c + 2, c + 4)
    A.bat.patron("aro", GROOVE["cardumen"]["aro"], c + 4, c + 8)
    A.bat.patron("aro", GROOVE["cardumen"]["aro_f"], c + 4, c + 8)
    A.bat.patron("hat", "..3. ..3. ..3. ..4.", c + 6, c + 8)
    A.bat.golpe(P(c + 7, 4.5), "hat_abierto", 0.42)
    sub_camina(A.sub, C, c, c + 8, "tresillo", vel=0.73)
    rhodes_toca(A.rhodes, C, c, c + 8, "anticipa", vel=0.36)
    A.auto("rhodes", "trem", [(c, 0.36), (c + 8, 0.36)])
    A.pad.acordes_ligados(C.voicings(c, c + 8, voces=5, rango=("E3", "E5")), vel=0.44)
    A.auto("pad", "corte", [(c, 1000.0), (c + 8, 2000.0, "exp")])
    A.vibmel.melodia(P(c + 1, 3), "B4/0.75 E5/0.75 G#5/0.5", vel=0.26)   # sobre C#m7
    A.vibmel.melodia(P(c + 5, 3), "C#5/0.75 F#5/0.75 A5/0.5", vel=0.26)  # sobre Dmaj9
    A.tex.clip(swell(Piano(fieltro=0.45), ["A2", "E3", "B3", "C#4", "G#4", "E5", "B5"], largo_tiempos=8,
                     vel=0.62, curva=2.2), fin=c + 8, ganancia_db=-17)


def s_plenitud(A, c):
    C = A.C
    A.vibmel.melodia(c, TEMA, vel=0.56)
    A.vibmel.pedal_por_compas(c, c + 8)
    A.violas.melodia(c, TEMA, vel=0.6, transponer=-12)
    A.auto("violas", "expresion", [(c, 0.8), (c + 1.9, 1.0, "suave"), (c + 2, 0.85), (c + 3.9, 1.0, "suave"),
                                   (c + 4, 0.88), (c + 5.9, 1.0, "suave"), (c + 6, 0.9), (c + 7.9, 1.0, "suave")])
    A.chelos.melodia(c, CONTRA_PLENITUD, vel=0.6)
    A.auto("chelos", "expresion", [(c, 0.8), (c + 7.9, 1.0, "suave")])
    acentos = []
    rodar(A.arpa, C, c, c + 8, "abierta", vel=0.44, dur=0.75, apagar=True, recolectar=acentos)
    rodar(A.piano, C, c, c + 8, "espejo", vel=0.30, dur=0.6)
    doblar_pizz(A.pizz, C, acentos, c, c + 8, vel=0.32, prob=0.4, octava=1)
    rhodes_toca(A.rhodes, C, c, c + 8, "tresillo", vel=0.38)
    A.auto("rhodes", "trem", [(c, 0.32), (c + 8, 0.32)])
    A.pad.acordes_ligados(C.voicings(c, c + 8, voces=5, rango=("E3", "E5")), vel=0.58)
    A.auto("pad", "corte", [(c, 2400.0), (c + 7, 3600.0, "exp")])
    sub_camina(A.sub, C, c, c + 8, "tresillo", vel=0.76)
    groove(A.bat, "plenitud", c, c + 8)
    A.auto("bateria", "vol", [(c - 0.5, 0.0), (c, 3.0, "suave"), (c + 7.5, 3.0), (c + 8, 0.0, "suave")])
    A.auto("sub", "vol", [(c - 0.5, 0.0), (c, 2.5, "suave"), (c + 7.5, 2.5), (c + 8, 0.0, "suave")])
    A.bat.golpe(P(c + 3, 4.5), "hat_abierto", 0.45)
    A.bat.patron("escobilla", ".... .... .... 2346", c + 7, c + 8)


def s_estela(A, c):
    C = A.C
    rodar(A.vibra, C, c, c + 4, "ola", vel=0.37)
    rodar(A.vibra, C, c + 4, c + 8, "remolino", vel=0.36)
    acentos = []
    rodar(A.fantasma, C, c, c + 4, "ola", vel=0.0, recolectar=acentos)
    doblar_pizz(A.pizz, C, acentos, c, c + 4, vel=0.28, prob=0.45)
    rhodes_toca(A.rhodes, C, c, c + 4, "largo", vel=0.35)
    rhodes_toca(A.rhodes, C, c + 4, c + 8, "tresillo", vel=0.35)
    A.auto("rhodes", "trem", [(c, 0.38), (c + 8, 0.42)])
    A.pad.acordes_ligados(C.voicings(c, c + 6, voces=5, rango=("E3", "E5")), vel=0.5)
    A.auto("pad", "corte", [(c, 2400.0), (c + 6, 800.0, "exp")])
    A.auto("pad", "vol", [(c, 0.0), (c + 6, -6.0, "suave"), (c + 8, -6.0)])
    for t0, t1, _s, v in C.voicings(c, c + 4, voces=1, rango=("E3", "B3")):
        A.chelos.nota(C.c(t0), v[0], t1 - t0 - 0.1, vel=0.28)
    A.auto("chelos", "expresion", [(c, 0.8), (c + 4, 0.3, "suave")])
    sub_camina(A.sub, C, c, c + 4, "negras", vel=0.70)
    sub_camina(A.sub, C, c + 4, c + 8, "tresillo", vel=0.70)
    groove(A.bat, "estela", c, c + 6)
    A.bat.patron("bombo", GROOVE["estela"]["bombo"], c + 6, c + 8)
    A.bat.patron("shaker", SH, c + 6, c + 8)
    A.vibmel.melodia(P(c + 7, 3), "E5/0.75 A5/0.75 B5/0.5", vel=0.26)     # sobre E6sus4


def s_bruma(A, c):
    C = A.C
    C.ritardando(c + 4, c + 8, 92)
    # el arpegio se desarma: cada vez suenan menos notas
    rodar(A.vibra, C, c, c + 8, "ola", vel=lambda q: 0.25 - 0.01 * (q - c), dur=0.75, frase=4,
          prob=lambda q: max(0.1, min(1.0, 1.0 - 0.13 * (q - c - 1))))
    A.vibra.pedal_por_compas(c + 4, c + 8)
    A.auto("vibrafono", "filtro", [(c + 3, 7500.0), (c + 8, 1300.0, "exp")])
    A.auto("vibrafono", "vol", [(c - 0.1, 0.0), (c + 1, -2.5, "suave")])
    A.auto("vib_melodia", "vol", [(c - 0.1, 0.0), (c + 0.2, -3.0, "suave")])
    # el tema, por última vez: se apaga sobre el bVI (Do natural) y vuelve la 3ª mayor (piano)
    A.vibmel.melodia(c, MOTIVO, vel=0.25)
    A.vibmel.melodia(c + 2, RESPUESTA, vel=0.23)
    A.vibmel.melodia(c + 4, "r/1 C5/1.5 B4/1.5 | A4/4", vel=0.21)
    A.vibmel.pedal_por_compas(c, c + 6)
    rhodes_toca(A.rhodes, C, c, c + 4, "largo", vel=0.22)
    A.auto("rhodes", "trem", [(c, 0.42), (c + 4, 0.5)])
    A.pad.acordes_ligados(C.voicings(c, c + 8, voces=5, rango=("E3", "E5")), vel=0.52)
    A.auto("pad", "corte", [(c, 1400.0), (c + 8, 520.0, "exp")])
    A.auto("pad", "vol", [(c, -6.0), (c + 1, -8.0, "suave"), (c + 8, -10.0)])
    A.sub.nota(c, "A1", 4 * 4 - 0.2, vel=0.36)
    A.auto("sub", "vol", [(c, 0.0), (c + 2, 0.0), (c + 4, -10.0, "suave")])
    A.bat.patron("shaker", "2323 2324 1212 1213", c, c + 2)
    A.tex.clip(nube(Vibrafono(motor_hz=MOTOR_CORCHEAS), "E5/0.5 A5 B5 E6 B5 A5 E5 B4 A4 E5 B5 A5",
                    dur_s=22.0, estirar=4.0, densidad=12, grano=(0.1, 0.3), tonos=(0, 12, -12),
                    pesos=(4, 1, 1), ataque=4.0, caida=10.0, pan=0.45), pos=c + 3, ganancia_db=-12)
    A.piano.acorde(c + 6, ["A2", "E3", "B3", "G#4", "C#5"], 8, vel=0.22, rasgueo=0.05)
    A.piano.pedal(c + 6, c + 8.9)


ARREGLO = {"orilla": s_orilla, "corriente": s_corriente, "deriva": s_deriva,
           "cardumen": s_cardumen, "altamar": s_altamar, "respiro": s_respiro,
           "regreso": s_regreso, "plenitud": s_plenitud, "estela": s_estela, "bruma": s_bruma}


# ============================================================ 4. CANCIÓN ==
def cancion() -> Cancion:
    C = Cancion("Deriva", slug="02-deriva", bpm=BPM, compas=(4, 4),
                tonalidad="La mayor / Fa# menor", semilla=SEMILLA, cola_s=9.0)
    C.fx["eco"].update(division=0.75, realim=0.34, corte=3000.0)

    sel = os.environ.get("DERIVA_SECCIONES")
    nombres = [n.strip() for n in sel.split(",")] if sel else [s[0] for s in SECCIONES]
    spec = {s[0]: s for s in SECCIONES}
    c = 1
    plan = []
    for nom in nombres:
        _, comp, e, emo, voz, loop, notas = spec[nom]
        lp = (c + loop[0], c + loop[1]) if loop else None
        C.seccion(nom, comp, energia=e, emocion=emo, voz=voz, loop=lp, notas=notas)
        C.progresion(c, ARMONIA[nom])
        plan.append((nom, c))
        c += comp

    A = Arreglo(C)
    # ---------------------------------------------------------------- pistas
    A.tex = C.pista("textura", Textura(), "textura", vol=0.0, envios={"reverb": 0.14})
    A.vibra = C.pista("vibrafono", Vibrafono(motor_hz=MOTOR_CORCHEAS, motor_prof=0.25, tope_hz=7000.0,
                                                abrir=0.3, ataque=0.003),
                      "armonia", vol=-3.0, envios={"reverb": 0.22, "eco": 0.12})
    A.arpa = C.pista("arpa", Arpa(largo_max=3.0, abrir=0.4), "armonia", vol=-12.0,
                     envios={"reverb": 0.28, "eco": 0.06}, efectos=[EQ(("pa", 110))])
    A.piano = C.pista("piano", Piano(fieltro=0.7, mecanica=0.3, abrir=0.3), "armonia", vol=-3.0,
                      envios={"reverb": 0.24, "eco": 0.04},
                      efectos=[EQ(("pa", 60), ("campana", 320, -2.0, 0.8))])
    A.rhodes = C.pista("rhodes", Rhodes(brillo=0.42, campana=0.3, trem_prof=0.0, drive=0.3, tope_hz=6000.0),
                       "armonia", vol=-6.5, envios={"reverb": 0.18, "eco": 0.08})
    A.pad = C.pista("pad", Pad(voces=6, desafinar=12, sub=0.0, ataque=2.0, soltar=3.0, pa=150, corte=900),
                    "armonia", vol=-11.0, envios={"reverb": 0.15},
                    efectos=[EQ(("campana", 300, -2.0, 0.9)), Ancho(1.2, mono_hz=250),
                             Ducking(prof_db=2.5, relaj_ms=200)])
    A.sub = C.pista("sub", Sub(drive_db=6, octava=0.15, glide_ms=22), "bajo", vol=-7.0,
                    efectos=[Ducking(prof_db=3.0, relaj_ms=170)])
    A.bat = C.pista("bateria", Bateria(color=0.4), "bateria", vol=-8.0,
                    envios={"sala": 0.18, "reverb": 0.05},
                    efectos=[Compresor(umbral_db=-24, ratio=2.5, ataque_ms=12, relaj_ms=140, mezcla=0.4),
                             Saturacion(drive_db=3, mezcla=0.3), EQ(("campana", 3000, -2.5, 0.8))])
    A.chelos = C.pista("chelos", Chelos(), "armonia", vol=-4.0, envios={"reverb": 0.3},
                       efectos=[EQ(("pa", 55))])
    A.violas = C.pista("violas", Violas(), "armonia", vol=-5.0, envios={"reverb": 0.32},
                       efectos=[EQ(("pa", 120), ("campana", 3000, -3.0, 0.9))])
    A.violines = C.pista("violines", Violines(), "armonia", vol=-2.0, envios={"reverb": 0.36},
                         efectos=[EQ(("pa", 180), ("campana", 3000, -3.0, 0.9))])
    A.pizz = C.pista("pizz", Pizzicato("violines"), "armonia", vol=-8.0,
                     envios={"reverb": 0.25, "sala": 0.1, "eco": 0.1},
                     efectos=[EQ(("pa", 160), ("campana", 3000, -2.0, 0.8))])
    A.vibmel = C.pista("vib_melodia", Vibrafono(motor_hz=MOTOR_CORCHEAS, motor_prof=0.3, tope_hz=4500.0,
                                                  ataque=0.010),
                       "melodia", vol=-1.0, envios={"reverb": 0.32, "eco": 0.18})

    class _Fantasma:     # pista muda: solo para calcular acentos de un arpegio
        nombre = "fantasma"

        def nota(self, *a, **k):
            return self
    A.fantasma = _Fantasma()

    # humanización (determinista)
    A.vibra.humanizar(tiempo_ms=6, vel=0.06, swing=0.53, swing_div=0.25)
    A.arpa.humanizar(tiempo_ms=7, vel=0.07, swing=0.53, swing_div=0.25)
    A.piano.humanizar(tiempo_ms=7, vel=0.06, swing=0.53, swing_div=0.25)
    A.rhodes.humanizar(tiempo_ms=8, vel=0.06)
    A.sub.humanizar(tiempo_ms=4, vel=0.04)
    A.bat.humanizar(tiempo_ms=7, vel=0.1, swing=0.55, swing_div=0.25)
    for p in (A.chelos, A.violas, A.violines):
        p.humanizar(tiempo_ms=12, vel=0.04)
    A.pizz.humanizar(tiempo_ms=8, vel=0.08)
    A.vibmel.humanizar(tiempo_ms=6, vel=0.05)

    # -------------------------------------------------------------- arreglo
    for nom, c0 in plan:
        ARREGLO[nom](A, c0)

    # ------------------------------------------------ automatizaciones finales
    for (pista, param), pts in A.puntos.items():
        if param in ("vol", "corte", "expresion"):
            C.pistas[pista].auto(param, sorted(pts, key=lambda q: q[0]))
    A.vibra.efectos.insert(0, Filtro("pasabajos", corte=A.curva("vibrafono", "filtro", 7500.0), q=0.7))
    # las láminas graves (Sol#3–Do#4) tienen el 3er modo en 10,7× (2,2–2,9 kHz): justo donde va la voz
    A.vibra.efectos.append(EQ(("pa", 150), ("campana", 290, -2.0, 1.0), ("campana", 2400, -9.0, 1.1),
                              ("campana", 4800, -4.0, 1.4)))
    A.rhodes.efectos[:0] = [EQ(("pa", 90), ("campana", 330, -2.5, 0.9)),
                            Tremolo(division=1 / 3, prof=A.curva("rhodes", "trem", 0.4), estereo=True),
                            Ducking(prof_db=1.5)]
    return C
