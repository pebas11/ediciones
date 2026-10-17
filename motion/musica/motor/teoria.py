"""Teoría: escalas, cifrado americano y conducción de voces.

    acorde("Gmaj13#11").pcs        → {7, 11, 2, 6, 9, 1, 4}
    conducir(["Dmaj9", "E/D", "Bm11", "Gmaj13#11"], voces=4, rango=("D3", "A4"))
        → [[57, 61, 64, 66], [56, 59, 64, 66], ...]  (movimiento mínimo)

Reglas que aplica `conducir` (pedido del proyecto):
  * Grave limpio: si la nota de abajo está por debajo de Mi3 (MIDI 52), el
    intervalo con la siguiente voz es de 5ª justa o más. Entre Mi3 y La3, al
    menos una 3ª menor. Segundas solo desde Do4 hacia arriba.
  * Sin novenas menores entre voces (salvo que el acorde tenga b9).
  * Sin duplicar 3ª, 7ª ni tensiones; se omite primero la 5ª y después la raíz
    (el bajo ya la toca), nunca la 3ª, la 7ª/6ª ni las alteraciones.
"""
from __future__ import annotations

import itertools
import re
from dataclasses import dataclass, field

import numpy as np

from .nucleo import nota

PC = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

MODOS = {
    "jonico": [0, 2, 4, 5, 7, 9, 11], "mayor": [0, 2, 4, 5, 7, 9, 11],
    "dorico": [0, 2, 3, 5, 7, 9, 10], "frigio": [0, 1, 3, 5, 7, 8, 10],
    "lidio": [0, 2, 4, 6, 7, 9, 11], "mixolidio": [0, 2, 4, 5, 7, 9, 10],
    "eolico": [0, 2, 3, 5, 7, 8, 10], "menor": [0, 2, 3, 5, 7, 8, 10],
    "locrio": [0, 1, 3, 5, 6, 8, 10],
    "menor_armonica": [0, 2, 3, 5, 7, 8, 11], "menor_melodica": [0, 2, 3, 5, 7, 9, 11],
    "penta_mayor": [0, 2, 4, 7, 9], "penta_menor": [0, 3, 5, 7, 10],
}


def pc_de(nombre: str) -> int:
    nombre = nombre.strip()
    base = PC[nombre[0].upper()]
    for c in nombre[1:]:
        base += 1 if c == "#" else -1 if c == "b" else 0
    return base % 12


def escala(tonica: str, modo: str = "mayor") -> list[int]:
    """Clases de altura de la escala: escala("D", "lidio") → [2, 4, 6, 8, 9, 11, 1]."""
    t = pc_de(tonica)
    return [(t + i) % 12 for i in MODOS[modo]]


def en_escala(esc: list[int], grado: int, octava: int = 4) -> int:
    """Grado (1 = tónica, admite negativos y >7) → MIDI, con la tónica en `octava`."""
    n = len(esc)
    g = grado - 1
    o, i = divmod(g, n)
    t = esc[0]
    base = 12 * (octava + 1) + t
    return base + ((esc[i] - t) % 12) + 12 * o


# ------------------------------------------------------------------ acordes --
ROL_ORDEN = {"tercera": 0, "septima": 1, "alterada": 2, "color": 3, "raiz": 4, "quinta": 5}


@dataclass
class Acorde:
    simbolo: str
    raiz: int
    bajo: int
    intervalos: dict = field(default_factory=dict)  # semitonos desde la raíz → rol

    @property
    def pcs(self) -> set:
        return {(self.raiz + i) % 12 for i in self.intervalos}

    def pcs_por_rol(self, *roles) -> set:
        return {(self.raiz + i) % 12 for i, r in self.intervalos.items() if r in roles}

    def tiene(self, intervalo: int) -> bool:
        return intervalo % 12 in {i % 12 for i in self.intervalos}

    def __repr__(self):
        nom = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        notas = " ".join(nom[(self.raiz + i) % 12] for i in sorted(self.intervalos))
        return f"Acorde({self.simbolo}: {notas} / bajo {nom[self.bajo]})"


_RE_RAIZ = re.compile(r"^([A-G])(#|b)?")


def acorde(simbolo: str) -> Acorde:
    """Interpreta cifrado americano.

    Calidades: (vacío) mayor, m/min/-, maj/M/Δ (con 7/9/11/13), dim/°, ø (m7b5),
    aug/+, sus2, sus4/sus, 6, m6, 6/9 (o 69), add9/add11/add2/add4.
    Extensiones 7 9 11 13 y alteraciones b5 #5 b9 #9 #11 b13; omisiones no3 no5.
    Bajo con barra: "E/D", "Dmaj9/F#".
    """
    s = simbolo.strip().replace("(", "").replace(")", "").replace(" ", "")
    bajo_txt = None
    m69 = s.replace("6/9", "69")
    if "/" in m69:
        s, bajo_txt = m69.rsplit("/", 1)
    else:
        s = m69
    m = _RE_RAIZ.match(s)
    if not m:
        raise ValueError(f"acorde inválido: {simbolo}")
    raiz = pc_de(m.group(0))
    q = s[m.end():]
    iv: dict[int, str] = {0: "raiz"}
    tercera, quinta = 4, 7
    septima = None
    exts: list[int] = []
    sus = None

    def toma(prefijos):
        nonlocal q
        for p in prefijos:
            if q.startswith(p):
                q = q[len(p):]
                return p
        return None

    menor = False
    mayor7 = False
    if toma(["maj", "Maj", "M", "Δ"]):
        mayor7 = True
    elif toma(["min", "m", "-"]):
        menor = True
        if toma(["maj", "M", "Δ"]):
            mayor7 = True  # m(maj7)
    elif toma(["dim", "°", "o"]):
        tercera, quinta = 3, 6
        if toma(["7"]):
            septima = 9
    elif toma(["ø"]):
        tercera, quinta, septima = 3, 6, 10
    elif toma(["aug", "+"]):
        quinta = 8
    if menor:
        tercera = 3
    # número principal (6, 69, 7, 9, 11, 13)
    num = toma(["69", "13", "11", "9", "7", "6", "5"])
    if num == "5":
        tercera = None
    elif num == "6":
        exts.append(9)
    elif num == "69":
        exts += [9, 14]
    elif num in ("7", "9", "11", "13"):
        septima = 11 if mayor7 else (septima if septima is not None else 10)
        n = int(num)
        if n >= 9:
            exts.append(14)
        if n >= 11 and (menor or tercera == 3):
            exts.append(17)
        elif n >= 11 and not mayor7:
            exts.append(17)  # 11 dominante: suele ir sin 3ª (se resuelve abajo)
        if n >= 13:
            exts.append(21)
    elif mayor7 and num is None:
        pass  # "Dmaj" = tríada mayor
    # sufijos
    while q:
        p = toma(["sus2", "sus4", "sus", "add9", "add11", "add2", "add4", "add13",
                  "b5", "#5", "b9", "#9", "#11", "b13", "no3", "no5", "omit3", "omit5",
                  "m7b5", "7"])
        if p is None:
            raise ValueError(f"no entiendo '{q}' en {simbolo}")
        if p in ("sus2",):
            sus = 2
        elif p in ("sus4", "sus"):
            sus = 5
        elif p in ("add9", "add2"):
            exts.append(14)
        elif p in ("add11", "add4"):
            exts.append(17)
        elif p == "add13":
            exts.append(21)
        elif p == "b5":
            quinta = 6
        elif p == "#5":
            quinta = 8
        elif p == "b9":
            exts = [e for e in exts if e != 14] + [13]
        elif p == "#9":
            exts.append(15)
        elif p == "#11":
            exts = [e for e in exts if e != 17] + [18]
        elif p == "b13":
            exts = [e for e in exts if e != 21] + [20]
        elif p in ("no3", "omit3"):
            tercera = None
        elif p in ("no5", "omit5"):
            quinta = None
        elif p == "m7b5":
            tercera, quinta, septima = 3, 6, 10
        elif p == "7":
            septima = 10 if septima is None else septima
    # 11 natural sobre 3ª mayor choca: en dominantes se quita la 3ª (sonido sus)
    if 17 in exts and tercera == 4 and sus is None:
        if mayor7:
            exts.remove(17)
        else:
            tercera = None
    if sus is not None:
        tercera = None
        iv[sus] = "tercera"
    if tercera is not None:
        iv[tercera] = "tercera"
    if quinta is not None:
        iv[quinta] = "alterada" if quinta != 7 else "quinta"
    if septima is not None:
        iv[septima] = "septima"
    for e in exts:
        alter = e in (13, 15, 18, 20)
        if e == 9 and septima is None:
            iv[9] = "septima"  # la 6ª cumple el papel de la 7ª
        else:
            iv[e] = "alterada" if alter else "color"
    bajo = pc_de(bajo_txt) if bajo_txt else raiz
    return Acorde(simbolo, raiz, bajo, iv)


# ----------------------------------------------------------- conducción ----
def _ok_espaciado(v, b9_permitida: bool) -> bool:
    for a, b in zip(v[:-1], v[1:]):
        d = b - a
        if d == 0:
            return False
        if a < 52 and d < 7:
            return False
        if a < 57 and d < 3:
            return False
        if a < 60 and d < 2:
            return False
    if not b9_permitida:
        for i in range(len(v)):
            for j in range(i + 1, len(v)):
                if v[j] - v[i] == 13:
                    return False
    return True


def _costo(v, prev, ac: Acorde, centro, tope_max, bonus_color):
    v = np.asarray(v)
    c = 0.0
    if prev is not None and len(prev) == len(v):
        mov = np.abs(v - np.asarray(prev))
        c += mov.sum() + 0.6 * (mov > 4).sum() * 2 + 0.3 * mov.max()
    elif prev is not None:
        c += sum(min(abs(x - p) for p in prev) for x in v)
    c += 0.25 * abs(v.mean() - centro)
    if tope_max is not None and v[-1] > tope_max:
        c += 3.0 * (v[-1] - tope_max)
    # segundas: color en el agudo, pero con moderación
    d = np.diff(v)
    c += 0.8 * (d <= 2).sum()
    # repartir: intervalos grandes abajo, chicos arriba
    if len(d) >= 2 and d[0] < d[-1]:
        c += 0.15 * (d[-1] - d[0])
    pcs = [(x % 12) for x in v]
    colores = ac.pcs_por_rol("color", "alterada")
    c -= bonus_color * len(set(pcs) & colores)
    return c


def _buscar(cand, voces, oblig, ac, pcs, prev, centro, tmax, bonus_color, estricto=True):
    mejor, mejor_c = None, 1e18
    b9 = ac.tiene(13)
    for comb in itertools.combinations(cand, voces):
        pcs_c = [m % 12 for m in comb]
        if not oblig <= set(pcs_c):
            continue
        vistos = set()
        dup_mala = False
        for p in pcs_c:  # duplicaciones: solo raíz o quinta
            if p in vistos and p not in ({ac.raiz} | ac.pcs_por_rol("quinta")):
                dup_mala = True
                break
            vistos.add(p)
        if dup_mala and estricto:
            continue
        if estricto and len(set(pcs_c)) < min(voces, len(pcs)) - (1 if voces >= 5 else 0):
            continue
        if voces <= 2 and comb[-1] - comb[0] > 12:
            continue
        if not _ok_espaciado(comb, b9):
            continue
        c = _costo(comb, prev, ac, centro, tmax, bonus_color)
        if c < mejor_c:
            mejor, mejor_c = list(comb), c
    return mejor


def conducir(simbolos, voces: int = 4, rango=("C3", "G5"), inicio=None,
             tope=None, con_raiz: bool = False, bonus_color: float = 1.2):
    """Voicings con movimiento mínimo para una lista de acordes (sin el bajo).

    * simbolos : lista de cifrados (str) o Acorde
    * voces    : número de notas por voicing
    * rango    : (nota_baja, nota_alta) permitidas
    * inicio   : voicing previo para enlazar (lista de MIDI) o None
    * tope     : nota máxima preferida para la voz superior (lista por acorde o una)
    * con_raiz : True obliga a incluir la raíz arriba del bajo
    """
    lo, hi = nota(rango[0]), nota(rango[1])
    centro = (lo + hi) / 2
    prev = list(inicio) if inicio is not None else None
    out = []
    for k, sim in enumerate(simbolos):
        ac = sim if isinstance(sim, Acorde) else acorde(sim)
        tmax = tope[k] if isinstance(tope, (list, tuple)) else tope
        tmax = nota(tmax) if tmax is not None else None
        pcs = ac.pcs
        obligatorias = ac.pcs_por_rol("tercera", "septima", "alterada")
        if con_raiz:
            obligatorias |= {ac.raiz}
        if len(obligatorias) > voces:
            # pocas voces: 3ª y 7ª primero, después alteraciones
            orden = [ac.pcs_por_rol("tercera"), ac.pcs_por_rol("septima"), ac.pcs_por_rol("alterada")]
            sel = set()
            for grupo in orden:
                for pc in sorted(grupo):
                    if len(sel) < voces:
                        sel.add(pc)
            obligatorias = sel
        mejor = None
        # niveles de relajación si el rango es muy estrecho: (1) obligar solo las notas
        # que existen en el rango, (2) ampliar el rango 3 semitonos, (3) cualquier nota del acorde
        for nivel in range(4):
            lo_n, hi_n = (lo - 3, hi + 3) if nivel >= 2 else (lo, hi)
            cand = [m for m in range(lo_n, hi_n + 1) if m % 12 in pcs]
            oblig = obligatorias
            if nivel >= 1:
                oblig = {p for p in obligatorias if any(m % 12 == p for m in cand)}
            if nivel >= 3:
                oblig = set()
            mejor = _buscar(cand, voces, oblig, ac, pcs, prev, centro, tmax, bonus_color,
                            estricto=nivel < 3)
            if mejor is not None:
                break
        if mejor is None:
            raise ValueError(f"sin voicing válido para {ac.simbolo} en {rango} con {voces} voces")
        out.append(mejor)
        prev = mejor
    return out


def bajo_de(sim, rango=("C2", "B2"), prev=None) -> int:
    """Nota de bajo (la de la barra o la raíz) dentro del rango, cerca de la anterior."""
    ac = sim if isinstance(sim, Acorde) else acorde(sim)
    lo, hi = nota(rango[0]), nota(rango[1])
    cand = [m for m in range(lo, hi + 1) if m % 12 == ac.bajo]
    if not cand:
        raise ValueError(f"el bajo de {ac.simbolo} no entra en {rango}")
    if prev is None:
        return cand[0]
    return min(cand, key=lambda m: (abs(m - prev), m))


def bajos(simbolos, rango=("C2", "B2")) -> list[int]:
    out, prev = [], None
    for s in simbolos:
        prev = bajo_de(s, rango, prev)
        out.append(prev)
    return out


def voicing_abierto(sim, bajo_midi: int, voces: int = 5, techo="A5") -> list[int]:
    """Voicing amplio para pads: bajo + 5ª (o 10ª) + estructura superior."""
    ac = sim if isinstance(sim, Acorde) else acorde(sim)
    sup = conducir([ac], voces=voces - 1, rango=(bajo_midi + 7, nota(techo)))[0]
    return [bajo_midi] + sup
