"""Secuencia: canción, secciones, armonía, pistas, notas, patrones y humanización.

Posiciones: un número es un compás (1 = comienzo, 9.5 = mitad del compás 9) o
"compás:tiempo" ("9:3" = tercer tiempo del compás 9). Duraciones en tiempos
(negras): R=4 redonda, B=2 blanca, N=1 negra, C=0.5 corchea, S=0.25 semicorchea.
"""
from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field

import numpy as np

from .nucleo import Auto, Tempo, nota, nombre_nota, rng, SR
from .teoria import acorde, conducir, bajos

R, B, N, C, S = 4.0, 2.0, 1.0, 0.5, 0.25
STEMS = ("bateria", "bajo", "armonia", "melodia", "textura")


@dataclass
class Nota:
    t: float            # inicio en tiempos (negras) desde el comienzo de la canción
    dur: float          # duración en tiempos
    midi: float         # altura MIDI (60 = Do4)
    vel: float = 0.7    # 0..1
    x: dict = field(default_factory=dict)  # extras: legato, vel_fin, golpe, pan, ...

    def __repr__(self):
        return f"Nota({self.t:.2f}, {self.dur:.2f}, {nombre_nota(self.midi)}, v={self.vel:.2f})"


@dataclass
class Seccion:
    nombre: str
    compas_ini: int       # primer compás (1-indexado)
    compases: int
    energia: float
    emocion: str
    voz: bool             # True = sección pensada para ir bajo la voz en off
    loop: tuple | None    # (compás_ini, compás_fin_exclusivo) recomendado para loopear
    notas: str = ""

    @property
    def compas_fin(self) -> int:   # exclusivo
        return self.compas_ini + self.compases


# ------------------------------------------------------- notación textual --
_RE_TOKEN = re.compile(r"^(?P<alt>\[[^\]]+\]|[A-Ga-g][#b]?-?\d|[rR\-])"
                       r"(?:/(?P<dur>[0-9.+]+))?(?P<mod>[!?_]*)(?:@(?P<vel>[0-9.]+))?$")
# un acorde entre corchetes (con espacios adentro) es un solo token: "[D4 F#4 A4]/2!@0.6"
_RE_PARTIR = re.compile(r"\[[^\[\]]*\]\S*|\S+")


def tokens_melodia(texto: str) -> list[str]:
    """Parte la mini-notación en tokens sin romper los acordes entre corchetes."""
    toks = _RE_PARTIR.findall(texto)
    for tok in toks:
        if tok.startswith("[") and "]" not in tok:
            raise ValueError(f"acorde sin cerrar en la melodía: {tok!r} ('{texto[:40]}…')")
    return toks


def melodia(texto: str, vel: float = 0.7, compas_t: float | None = None):
    """Mini-notación → lista de (t_relativo, dur, midi, vel, extras).

        "A5/0.5 E6 D6 G#5/1.5 A5/1 | F#5/3 r/1"

    * nota/duración (en tiempos); si se omite la duración se repite la anterior
    * r o - = silencio; [D4 F#4 A4]/2 = acorde (las notas a la vez; el acorde lleva los
      mismos sufijos que una nota: "[D4 F#4]/2!" o "[A3 E4]_")
    * sufijos: ! acento (×1.25), ? suave (×0.7), _ ligado a la siguiente (legato)
    * @0.8 velocidad explícita; "4+2" suma duraciones
    * | barra de compás: verifica que lo acumulado cierre el compás (si compas_t)
    """
    out = []
    t = 0.0
    dur = 1.0
    ligar = False
    for tok in tokens_melodia(texto):
        if tok == "|":
            if compas_t and abs((t / compas_t) - round(t / compas_t)) > 1e-6:
                raise ValueError(f"la barra no cierra el compás en t={t} ('{texto[:40]}…')")
            continue
        m = _RE_TOKEN.match(tok)
        if not m:
            raise ValueError(f"token de melodía inválido: {tok!r}")
        if m.group("dur"):
            dur = sum(float(p) for p in m.group("dur").split("+"))
        mod = m.group("mod") or ""
        v = float(m.group("vel")) if m.group("vel") else vel
        if "!" in mod:
            v = min(1.0, v * 1.25)
        if "?" in mod:
            v *= 0.7
        alt = m.group("alt")
        if alt in ("r", "R", "-"):
            t += dur
            ligar = False
            continue
        alturas = [nota(a) for a in alt.strip("[]").split()] if alt.startswith("[") else [nota(alt)]
        extras = {"legato": True} if ligar else {}
        for a in alturas:
            out.append((t, dur, a, v, dict(extras)))
        ligar = "_" in mod
        t += dur
    return out, t


# ------------------------------------------------------------------ pista --
class Pista:
    """Una pista = un instrumento + sus notas, automatizaciones, efectos y envíos."""

    def __init__(self, cancion: "Cancion", nombre: str, instrumento, stem: str,
                 vol: float = 0.0, pan: float = 0.0, envios: dict | None = None,
                 efectos: list | None = None, humano: dict | None = None):
        if stem not in STEMS:
            raise ValueError(f"stem '{stem}' inválido; usar uno de {STEMS}")
        self.cancion = cancion
        self.nombre = nombre
        self.instrumento = instrumento
        self.stem = stem
        self.vol = vol                    # dB
        self.pan = pan                    # −1..1
        self.envios = dict(envios or {})  # {"reverb": 0.3, "sala": 0.1, "eco": 0.2} (lineal, post-fader)
        self.efectos = list(efectos or [])
        self.humano = {"tiempo_ms": 0.0, "vel": 0.0, "swing": 0.5, "swing_div": 0.5,
                       "desfase_ms": 0.0}
        if humano:
            self.humano.update(humano)
        self.notas: list[Nota] = []
        self.autos: dict[str, Auto] = {}
        self.pedales: list[tuple[float, float]] = []   # (bajar, subir) en tiempos
        self.clips: list[dict] = []                     # audio libre (texturas)
        self.silencios: list[tuple[float, float]] = []  # (desde, hasta) en tiempos: mute

    # ---------------------------------------------------------- utilidades
    @property
    def tempo(self) -> Tempo:
        return self.cancion.tempo

    def _t(self, pos) -> float:
        return self.tempo.pos(pos)

    # ---------------------------------------------------------- notas
    def nota(self, pos, altura, dur: float, vel: float = 0.7, **x):
        """Agrega una nota. pos = compás o "compás:tiempo"; dur en tiempos."""
        self.notas.append(Nota(self._t(pos), float(dur), float(nota(altura)), float(vel), dict(x)))
        return self

    def acorde(self, pos, alturas, dur: float, vel: float = 0.6, rasgueo: float = 0.0,
               arriba: bool = True, **x):
        """Notas simultáneas; rasgueo = segundos entre notas (arpegiado leve)."""
        al = sorted(nota(a) for a in alturas)
        if not arriba:
            al = al[::-1]
        t0 = self._t(pos)
        for i, a in enumerate(al):
            dt_beats = i * rasgueo * self.tempo.bpm_en(t0) / 60.0
            self.notas.append(Nota(t0 + dt_beats, float(dur) - dt_beats, float(a), float(vel), dict(x)))
        return self

    def melodia(self, pos, texto: str, vel: float = 0.7, transponer: int = 0, **x):
        """Mini-notación (ver `melodia`). Devuelve la posición final (en compases)."""
        notas, largo = melodia(texto, vel, self.tempo.tpc)
        t0 = self._t(pos)
        for (t, d, a, v, ex) in notas:
            e = dict(x)
            e.update(ex)
            self.notas.append(Nota(t0 + t, d, float(a + transponer), v, e))
        return 1 + (t0 + largo) / self.tempo.tpc

    def arpegio(self, desde, hasta, voicing_de, patron="0 1 2 3", paso: float = C,
                dur: float | None = None, vel: float = 0.6, acentos=None,
                ligadura: float = 1.0, **x):
        """Arpegia los voicings entre dos compases.

        * voicing_de : función t_tiempos → lista MIDI, o lista fija
        * patron     : índices en el voicing ordenado (negativos desde arriba,
                       ≥ len sube octava); "." = silencio
        * paso       : duración de cada paso en tiempos (C = corcheas)
        * dur        : duración de cada nota (por defecto paso × ligadura)
        * acentos    : lista de multiplicadores de velocidad que se repite
        """
        pasos = patron.split() if isinstance(patron, str) else list(patron)
        t, t_fin = self._t(desde), self._t(hasta)
        k = 0
        while t < t_fin - 1e-9:
            p = pasos[k % len(pasos)]
            if p not in (".", "-"):
                v = voicing_de(t) if callable(voicing_de) else voicing_de
                v = sorted(v)
                i = int(p)
                if i < 0:
                    alt = v[i]
                else:
                    alt = v[i % len(v)] + 12 * (i // len(v))
                ac = acentos[k % len(acentos)] if acentos else 1.0
                d = dur if dur is not None else paso * ligadura
                self.notas.append(Nota(t, min(d, t_fin - t + 2), float(alt), float(min(1, vel * ac)), dict(x)))
            t += paso
            k += 1
        return self

    def patron(self, golpe: str, texto: str, desde, hasta, vel: float = 0.7,
               prob: float = 1.0, altura: int = 60, escala: float = 1.0, **x):
        """Patrón de batería por semicorcheas (16 pasos por compás en 4/4).

        x normal · X acento · o/g fantasma (×0.35) · 1–9 velocidad/9 · . silencio.
        Espacios y | se ignoran. Si el texto dura varios compases, se cicla.
        prob < 1 omite golpes al azar (determinista).
        `vel` es la velocidad de x/X/o; los dígitos son velocidades absolutas (dígito/9) y
        `vel` no los toca (así sonaban las canciones). `escala` multiplica TODAS las
        velocidades del patrón, dígitos incluidos (para subir o bajar un groove entero).
        """
        pasos = [c for c in texto if c not in " |"]
        paso = 0.25
        t, t_fin = self._t(desde), self._t(hasta)
        k = 0
        g = rng(self.cancion.semilla, self.nombre, golpe, "patron", round(t * 4))
        while t < t_fin - 1e-9:
            c = pasos[k % len(pasos)]
            v = None
            if c == "x":
                v = vel
            elif c == "X":
                v = min(1.0, vel * 1.3)
            elif c in "og":
                v = vel * 0.35
            elif c.isdigit() and c != "0":
                v = int(c) / 9.0
            if v is not None and escala != 1.0:
                v = min(1.0, v * escala)
            if v is not None and (prob >= 1 or g.random() < prob):
                e = dict(x)
                e["golpe"] = golpe
                self.notas.append(Nota(t, paso, float(altura), float(v), e))
            t += paso
            k += 1
        return self

    def acordes_ligados(self, voicings, vel: float = 0.6, desde_t=None, **x):
        """Toca voicings [(t0, t1, cifrado, [midi…])] (salida de C.voicings) ligando las
        notas comunes entre acordes seguidos: no se reatacan (ideal para pads y cuerdas)."""
        abiertas: dict = {}
        fin_prev = None
        for (t0, t1, _s, v) in voicings:
            if fin_prev is not None and t0 > fin_prev + 1e-6:
                for m, ta in abiertas.items():
                    self.notas.append(Nota(ta, fin_prev - ta, float(m), float(vel), dict(x)))
                abiertas = {}
            sig = set(int(m) for m in v)
            for m in list(abiertas):
                if m not in sig:
                    ta = abiertas.pop(m)
                    self.notas.append(Nota(ta, t0 - ta, float(m), float(vel), dict(x)))
            for m in sig:
                abiertas.setdefault(m, t0)
            fin_prev = t1
        for m, ta in abiertas.items():
            self.notas.append(Nota(ta, fin_prev - ta, float(m), float(vel), dict(x)))
        return self

    def golpe(self, pos, golpe: str, vel: float = 0.7, dur: float = 0.25, altura=60, **x):
        e = dict(x)
        e["golpe"] = golpe
        self.notas.append(Nota(self._t(pos), dur, float(nota(altura)), float(vel), e))
        return self

    # ---------------------------------------------------------- control
    def auto(self, param: str, puntos):
        """Automatiza un parámetro: 'vol' (dB relativos), 'pan', o los del instrumento."""
        self.autos[param] = puntos if isinstance(puntos, Auto) else Auto(puntos, param)
        return self

    def pedal(self, bajar, subir):
        self.pedales.append((self._t(bajar), self._t(subir)))
        return self

    def pedal_por_compas(self, desde, hasta, cada: int = 1, hueco: float = 0.06):
        """Pedal de resonancia que se renueva cada `cada` compases (sube un instante antes)."""
        c = float(desde)
        while c < float(hasta) - 1e-9:
            t0 = self._t(c)
            t1 = self._t(min(c + cada, float(hasta))) - hueco
            self.pedales.append((t0 + 0.02, t1))
            c += cada
        return self

    def silenciar(self, desde, hasta):
        self.silencios.append((self._t(desde), self._t(hasta)))
        return self

    def clip(self, generador, pos=None, fin=None, ganancia_db: float = 0.0, nombre: str = ""):
        """Audio libre (texturas): `generador(ctx)` → array (n,2) a 48 kHz.

        Se ubica empezando en `pos`, o terminando exactamente en `fin` (útil
        para swells invertidos que desembocan en un downbeat).
        """
        self.clips.append({"gen": generador, "pos": None if pos is None else self._t(pos),
                           "fin": None if fin is None else self._t(fin),
                           "db": ganancia_db, "nombre": nombre})
        return self

    # ---------------------------------------------------------- humanización
    def humanizar(self, tiempo_ms: float = 6.0, vel: float = 0.05, swing: float = 0.5,
                  swing_div: float = 0.5, desfase_ms: float = 0.0):
        """Microtiempos (σ en ms), variación de velocidad (σ relativa), swing estilo DAW
        (0.5 recto, 0.55–0.6 leve) sobre la subdivisión swing_div, y desfase fijo."""
        self.humano.update(tiempo_ms=tiempo_ms, vel=vel, swing=swing, swing_div=swing_div,
                           desfase_ms=desfase_ms)
        return self

    def notas_humanizadas(self) -> list[Nota]:
        h = self.humano
        out = []
        for n in self.notas:
            m = copy.copy(n)
            m.x = dict(n.x)
            t = n.t
            div = h["swing_div"]
            if h["swing"] != 0.5 and div > 0:
                k = t / div
                if abs(k - round(k)) < 1e-6 and int(round(k)) % 2 == 1:
                    t += (h["swing"] - 0.5) * 2 * div
            g = rng(self.cancion.semilla, self.nombre, round(n.t * 480), int(n.midi),
                    n.x.get("golpe", ""))
            dt_s = h["desfase_ms"] / 1000.0
            if h["tiempo_ms"] > 0 and not n.x.get("exacto"):
                dt_s += float(np.clip(g.normal(0, h["tiempo_ms"]), -2.5 * h["tiempo_ms"],
                                      2.5 * h["tiempo_ms"])) / 1000.0
            bpm = self.tempo.bpm_en(t)
            m.t = t + dt_s * bpm / 60.0
            if h["vel"] > 0:
                m.vel = float(np.clip(n.vel * (1 + g.normal(0, h["vel"])), 0.02, 1.0))
            # descontar silencios
            if any(a <= n.t < b for a, b in self.silencios):
                continue
            out.append(m)
        out.sort(key=lambda z: z.t)
        return out

    def pedal_abajo_en(self, t: float) -> tuple[bool, float]:
        """¿Está el pedal bajado en t (tiempos)? Devuelve (bajado, t_subida)."""
        for a, b in self.pedales:
            if a <= t < b:
                return True, b
        return False, t


# ---------------------------------------------------------------- canción --
class Cancion:
    """Declaración completa de una canción. Ver README.md."""

    def __init__(self, titulo: str, slug: str, bpm: float, compas=(4, 4),
                 tonalidad: str = "", semilla: int = 1, cola_s: float = 8.0):
        self.titulo = titulo
        self.slug = slug
        self.tempo = Tempo(bpm, compas)
        self.compas = compas
        self.tonalidad = tonalidad
        self.semilla = semilla
        self.cola_s = cola_s
        self.secciones: list[Seccion] = []
        self.pistas: dict[str, Pista] = {}
        self.armonia: list[tuple[float, float, str]] = []   # (t0, t1, cifrado)
        self.marcas: list[tuple[float, str]] = []
        # Espacio común (ver efectos.py y mezcla.py). Se pueden ajustar por canción.
        self.fx = {
            "reverb": {"dur": 3.6, "predelay_ms": 28, "brillo": 0.45, "ancho": 1.0, "tipo": "sala_grande"},
            "sala": {"dur": 0.9, "predelay_ms": 6, "brillo": 0.6, "ancho": 0.8, "tipo": "sala"},
            "eco": {"division": 0.75, "realim": 0.38, "corte": 3200.0, "graves": 250.0,
                    "pingpong": True, "a_reverb": 0.35},
            "cinta": {"wow": 0.0012, "flutter": 0.0004, "saturacion": 0.25, "hiss_db": -72.0,
                      "brillo": 15000.0},
            "hueco_voz": {"frecuencia": 2400.0, "q": 0.8, "profundidad_db": 3.0,
                          "stems": ("armonia", "melodia", "textura")},
            "master": {"lufs": -14.0, "techo_dbtp": -1.0, "glue": 0.5, "aire_db": 1.0},
        }

    # ------------------------------------------------------------ estructura
    def seccion(self, nombre: str, compases: int, energia: float, emocion: str,
                voz: bool = False, loop=None, notas: str = "") -> Seccion:
        ini = self.secciones[-1].compas_fin if self.secciones else 1
        if loop is None:
            largo = 8 if compases >= 8 else 4 if compases >= 4 else compases
            loop = (ini + compases - largo, ini + compases)
        s = Seccion(nombre, ini, compases, energia, emocion, voz, loop, notas)
        self.secciones.append(s)
        return s

    def sec(self, nombre: str) -> Seccion:
        for s in self.secciones:
            if s.nombre == nombre:
                return s
        raise KeyError(nombre)

    @property
    def compases_total(self) -> int:
        return self.secciones[-1].compas_fin - 1 if self.secciones else 0

    @property
    def tiempos_total(self) -> float:
        return self.compases_total * self.tempo.tpc

    @property
    def duracion_s(self) -> float:
        return float(self.tempo.seg(self.tiempos_total)) + self.cola_s

    def ritardando(self, desde, hasta, bpm_final: float):
        self.tempo.ritardando(self.tempo.pos(desde), self.tempo.pos(hasta), bpm_final)

    # ------------------------------------------------------------ armonía
    def progresion(self, desde, texto: str):
        """Registra la armonía: "Dmaj9 | E/D | Bm11 | Asus4 A" (un compás por barra;
        varios acordes en un compás lo dividen en partes iguales)."""
        t = self.tempo.pos(desde)
        tpc = self.tempo.tpc
        for compas_txt in texto.split("|"):
            sims = compas_txt.split()
            if not sims:
                t += tpc
                continue
            d = tpc / len(sims)
            for s in sims:
                if s in ("%", "-"):
                    if self.armonia:
                        t0, _, prev = self.armonia[-1]
                        self.armonia[-1] = (t0, t + d, prev)
                else:
                    acorde(s)  # valida
                    self.armonia.append((t, t + d, s))
                t += d
        self.armonia.sort()
        return self

    def acordes(self, desde=None, hasta=None):
        """[(t0, t1, cifrado)] que se solapan con el rango de compases dado."""
        a = self.tempo.pos(desde) if desde is not None else -1e9
        b = self.tempo.pos(hasta) if hasta is not None else 1e9
        return [(t0, t1, s) for (t0, t1, s) in self.armonia if t1 > a + 1e-9 and t0 < b - 1e-9]

    def acorde_en(self, t: float) -> str | None:
        for t0, t1, s in self.armonia:
            if t0 - 1e-9 <= t < t1 - 1e-9:
                return s
        return None

    def voicings(self, desde, hasta, voces=4, rango=("D3", "A4"), inicio=None, tope=None,
                 con_raiz=False):
        """Voicings conducidos para la armonía registrada entre dos compases.
        Devuelve [(t0, t1, cifrado, [midi...])]."""
        segs = self.acordes(desde, hasta)
        vs = conducir([s for _, _, s in segs], voces=voces, rango=rango, inicio=inicio,
                      tope=tope, con_raiz=con_raiz)
        return [(t0, t1, s, v) for (t0, t1, s), v in zip(segs, vs)]

    def bajos(self, desde, hasta, rango=("C2", "B2")):
        segs = self.acordes(desde, hasta)
        bs = bajos([s for _, _, s in segs], rango)
        return [(t0, t1, s, b) for (t0, t1, s), b in zip(segs, bs)]

    @staticmethod
    def voicing_en(lista):
        """Convierte la salida de `voicings` en función t → voicing (para arpegios)."""
        def f(t):
            for t0, t1, _, v in lista:
                if t0 - 1e-9 <= t < t1 - 1e-9:
                    return v
            return lista[-1][3]
        return f

    # ------------------------------------------------------------ pistas
    def pista(self, nombre: str, instrumento, stem: str, **kw) -> Pista:
        if nombre in self.pistas:
            raise ValueError(f"pista repetida: {nombre}")
        p = Pista(self, nombre, instrumento, stem, **kw)
        self.pistas[nombre] = p
        return p

    def c(self, t: float) -> float:
        """Tiempos (negras desde el inicio) → posición en compases (para nota/acorde/melodia)."""
        return 1.0 + t / self.tempo.tpc

    def marca(self, pos, texto: str):
        self.marcas.append((self.tempo.pos(pos), texto))

    # ------------------------------------------------------------ render
    def render(self, salida=None, **kw):
        from .mezcla import render_cancion
        return render_cancion(self, salida=salida, **kw)

    def muestra_de(self, pos) -> int:
        return int(round(self.tempo.seg(self.tempo.pos(pos)) * SR))
