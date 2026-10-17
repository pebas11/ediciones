"""Plan musical (`plan.json`): esquema, carga y validación con mensajes claros.

Esquema (ver MEZCLA.md para el detalle y un ejemplo):

    {
      "version": 1,
      "parametros": { ...cambios sobre config.DEFECTOS... },        (opcional)
      "tramos": [
        {
          "id": "apertura",                      (opcional; para mensajes e informe)
          "cancion": "01-umbral",                slug, número ("01") o nombre ("umbral")
          "secciones": ["umbral", "despertar"],  o "seccion": "x", o "compases": [9, 24] (inclusivo)
          "inicio": 0.0, "fin": 48.0,            segundos sobre la línea de tiempo de la voz
          "nivel_db": 0,                         nivel relativo de la música en este tramo (±12)
          "transicion": {"tipo": "fundido", "tiempos": 4},   con el tramo siguiente
          "entrada": {"tipo": "golpe"},          (opcional) "golpe" o {"tipo": "fundido", "tiempos": N}
          "ancla": {"seccion": "cumbre", "en": 131.2},       (opcional) o {"compas": 41, "tiempo": 1, "en": ...}
          "repetir": "despertar",                (opcional) sección a loopear si falta material
          "acortar": "final",                    "final" (corta el final) o "inicio" (conserva el final)
          "stems": {"melodia": -4, "bateria": "silencio"},   (opcional) ganancias fijas por stem
          "ducking": {...} | false               (opcional) cambios de profundidad/EQ en este tramo
        }
      ]
    }

Transiciones: "fundido" {tiempos, alineacion: auto|antes|despues}, "cola" {segundos},
"pausa" {silencio_s}, "corte"; en el último tramo además "final" (deja terminar la canción).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from . import STEMS
from .canciones import Catalogo, Cancion, ErrorCancion
from .config import DEFECTOS, fusionar, validar_rangos, sugerir, _tipo

TIPOS = ("fundido", "cola", "pausa", "corte", "final")
CLAVES_PLAN = ("version", "parametros", "tramos", "notas", "canciones_dir")
CLAVES_TRAMO = ("id", "cancion", "secciones", "seccion", "compases", "inicio", "fin", "nivel_db",
                "transicion", "entrada", "ancla", "repetir", "acortar", "stems", "ducking", "notas")
CLAVES_TRANS = {"fundido": ("tipo", "tiempos", "alineacion"), "cola": ("tipo", "segundos"),
                "pausa": ("tipo", "silencio_s"), "corte": ("tipo",), "final": ("tipo",)}
CLAVES_ANCLA = ("seccion", "compas", "tiempo", "en", "repeticion")
CLAVES_ENTRADA = ("tipo", "tiempos")
CLAVES_DUCK_TRAMO = ("profundidad_db", "eq_db")


class ErrorPlan(ValueError):
    def __init__(self, errores: list[str]):
        self.errores = errores
        super().__init__("plan inválido:\n  - " + "\n  - ".join(errores))


@dataclass
class Transicion:
    tipo: str
    tiempos: float | None = None
    segundos: float | None = None
    silencio_s: float | None = None
    alineacion: str = "auto"


@dataclass
class Ancla:
    compas: int
    tiempo: float
    en: float
    repeticion: int = 1
    seccion: str | None = None

    def texto(self) -> str:
        quien = f"sección «{self.seccion}»" if self.seccion else f"compás {self.compas}"
        extra = f", tiempo {self.tiempo:g}" if self.tiempo != 1 else ""
        return f"{quien}{extra} en {self.en:.3f} s"


@dataclass
class Tramo:
    indice: int
    id: str
    cancion: Cancion
    piezas: list[tuple[int, int]]          # rangos de compases (inclusivos), en orden
    inicio: float
    fin: float
    nivel_db: float = 0.0
    transicion: Transicion = field(default_factory=lambda: Transicion("fundido"))
    entrada: dict | None = None            # {"tipo": "golpe"|"fundido", "tiempos": N}
    ancla: Ancla | None = None
    repetir: str | None = None
    acortar: str = "final"
    stems: dict = field(default_factory=dict)     # stem → dB (None = silencio)
    ducking: dict | bool | None = None
    secciones_txt: str = ""

    @property
    def nombre(self) -> str:
        if self.id == f"tramo {self.indice + 1}":
            return self.id
        return f"tramo {self.indice + 1} («{self.id}»)"

    def barras(self) -> list[int]:
        out = []
        for a, b in self.piezas:
            out.extend(range(a, b + 1))
        return out


@dataclass
class Plan:
    tramos: list[Tramo]
    parametros: dict
    avisos: list[str]
    ruta: str = ""
    datos: dict = field(default_factory=dict)


def _num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def cargar(ruta: str | Path, catalogo: Catalogo | None = None, extra_parametros: dict | None = None) -> Plan:
    ruta = Path(ruta)
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ErrorPlan([f"no existe el plan {ruta}"]) from None
    except json.JSONDecodeError as e:
        raise ErrorPlan([f"{ruta}: JSON inválido en la línea {e.lineno}, columna {e.colno}: {e.msg}"]) from None
    return validar(datos, catalogo, ruta=str(ruta), extra_parametros=extra_parametros)


def validar(datos, catalogo: Catalogo | None = None, ruta: str = "", extra_parametros: dict | None = None) -> Plan:
    errores: list[str] = []
    avisos: list[str] = []
    if isinstance(datos, list):          # atajo: una lista de tramos
        datos = {"tramos": datos}
    if not isinstance(datos, dict):
        raise ErrorPlan([f"el plan tiene que ser un objeto JSON con 'tramos' (llegó {_tipo(datos)})"])
    for k in datos:
        if k not in CLAVES_PLAN:
            errores.append(f"clave desconocida en el plan: '{k}'{sugerir(k, CLAVES_PLAN)}. "
                           f"Válidas: {', '.join(CLAVES_PLAN)}")
    if datos.get("version", 1) != 1:
        errores.append(f"version {datos.get('version')!r} no soportada (usar 1)")
    if catalogo is None:
        catalogo = Catalogo(Path(datos["canciones_dir"]) if datos.get("canciones_dir") else None)
    # parámetros
    params = DEFECTOS
    try:
        params = fusionar(DEFECTOS, datos.get("parametros", {}) or {}, "parametros", errores)
        if extra_parametros:
            params = fusionar(params, extra_parametros, "--param", errores)
        validar_rangos(params, errores)
    except Exception as e:      # noqa: BLE001
        errores.append(str(e))
    tramos_in = datos.get("tramos")
    if not isinstance(tramos_in, list) or not tramos_in:
        errores.append("'tramos' tiene que ser una lista no vacía")
        raise ErrorPlan(errores)
    tramos: list[Tramo] = []
    for i, t in enumerate(tramos_in):
        tr = _tramo(i, t, len(tramos_in), catalogo, params, errores, avisos)
        if tr is not None:
            tramos.append(tr)
    # relaciones entre tramos
    if len(tramos) == len(tramos_in):
        for a, b in zip(tramos[:-1], tramos[1:]):
            if b.inicio < a.inicio:
                errores.append(f"{b.nombre}: los tramos tienen que estar en orden de 'inicio' "
                               f"({b.inicio} < {a.inicio} de {a.nombre})")
            elif b.inicio < a.fin - 0.01:
                errores.append(f"{a.nombre} (fin {a.fin}) y {b.nombre} (inicio {b.inicio}) se superponen: "
                               "el 'fin' de un tramo tiene que ser ≤ el 'inicio' del siguiente")
            elif b.inicio > a.fin + 0.01 and a.transicion.tipo != "pausa":
                errores.append(f"entre {a.nombre} (fin {a.fin}) y {b.nombre} (inicio {b.inicio}) hay un hueco "
                               f"de {b.inicio - a.fin:.2f} s: usá \"transicion\": {{\"tipo\": \"pausa\"}} en "
                               f"{a.nombre} o hacé coincidir 'fin' e 'inicio'")
            if a.transicion.tipo == "final":
                errores.append(f"{a.nombre}: la transición 'final' solo vale en el último tramo")
            if a.transicion.tipo == "pausa" and b.inicio <= a.fin + 0.01:
                sil = a.transicion.silencio_s
                if sil is not None and sil > (b.inicio - a.inicio) * 0.8:
                    errores.append(f"{a.nombre}: silencio_s={sil} no entra en el tramo")
    if errores:
        raise ErrorPlan(errores)
    return Plan(tramos, params, avisos, ruta, datos)


def _tramo(i: int, t, total: int, cat: Catalogo, params: dict, errores: list, avisos: list) -> Tramo | None:
    pref = f"tramo {i + 1}"
    if not isinstance(t, dict):
        errores.append(f"{pref}: tiene que ser un objeto (llegó {_tipo(t)})")
        return None
    if isinstance(t.get("id"), str) and t["id"]:
        pref = f"tramo {i + 1} («{t['id']}»)"
    n_err = len(errores)
    for k in t:
        if k not in CLAVES_TRAMO:
            errores.append(f"{pref}: clave desconocida '{k}'{sugerir(k, CLAVES_TRAMO)}. "
                           f"Válidas: {', '.join(CLAVES_TRAMO)}")
    # canción
    if "cancion" not in t:
        errores.append(f"{pref}: falta 'cancion' (slug, número o nombre)")
        return None
    try:
        c = cat.cargar(t["cancion"])
    except ErrorCancion as e:
        errores.append(f"{pref}: {e}")
        return None
    # material
    piezas: list[tuple[int, int]] = []
    fuentes = [k for k in ("secciones", "seccion", "compases") if k in t]
    if not fuentes:
        errores.append(f"{pref}: falta el material: 'secciones' (lista), 'seccion' o 'compases' [a, b]. "
                       f"Secciones de {c.slug}: {', '.join(s.nombre for s in c.secciones)}")
    elif len(fuentes) > 1:
        errores.append(f"{pref}: usá solo una de {fuentes}")
    else:
        k = fuentes[0]
        v = t[k]
        if k in ("secciones", "seccion"):
            nombres = [v] if isinstance(v, str) else v
            if not isinstance(nombres, list) or not nombres or not all(isinstance(x, str) for x in nombres):
                errores.append(f"{pref}: '{k}' tiene que ser un texto o una lista de textos")
            else:
                for nom in nombres:
                    try:
                        s = c.seccion(nom)
                        piezas.append((s.c0, s.c1))
                    except KeyError:
                        noms = [s.nombre for s in c.secciones]
                        errores.append(f"{pref}: la sección '{nom}' no existe en {c.slug}"
                                       f"{sugerir(nom, noms)}. Secciones: {', '.join(noms)}")
        else:
            rng = v
            if isinstance(v, str) and "-" in v:
                try:
                    rng = [int(x) for x in v.split("-")]
                except ValueError:
                    rng = None
            if not (isinstance(rng, list) and len(rng) == 2 and all(isinstance(x, int) for x in rng)):
                errores.append(f"{pref}: 'compases' tiene que ser [primero, último] (inclusivo), p. ej. [9, 24]")
            elif not (1 <= rng[0] <= rng[1] <= c.n_compases):
                errores.append(f"{pref}: compases {rng} fuera de rango (1–{c.n_compases} en {c.slug})")
            else:
                piezas.append((rng[0], rng[1]))
    # tiempos
    ini, fin = t.get("inicio"), t.get("fin")
    if not _num(ini) or not _num(fin):
        errores.append(f"{pref}: 'inicio' y 'fin' son obligatorios y en segundos (números)")
        ini, fin = 0.0, 1.0
    elif ini < 0:
        errores.append(f"{pref}: 'inicio' no puede ser negativo ({ini})")
    elif fin <= ini:
        errores.append(f"{pref}: 'fin' ({fin}) tiene que ser mayor que 'inicio' ({ini})")
    elif fin - ini < 2.0:
        errores.append(f"{pref}: dura {fin - ini:.2f} s; el mínimo es 2 s (un tramo necesita al menos un compás)")
    nivel = t.get("nivel_db", 0.0)
    if not _num(nivel) or abs(nivel) > 12:
        errores.append(f"{pref}: 'nivel_db' tiene que ser un número entre −12 y 12 (llegó {nivel!r})")
        nivel = 0.0
    # transición
    ultimo = i == total - 1
    tr = _transicion(pref, t.get("transicion"), ultimo, params, errores)
    # entrada
    entrada = None
    if "entrada" in t:
        e = t["entrada"]
        if isinstance(e, str):
            e = {"tipo": e}
        if not isinstance(e, dict) or e.get("tipo") not in ("golpe", "fundido"):
            errores.append(f"{pref}: 'entrada' tiene que ser \"golpe\" o {{\"tipo\": \"fundido\", \"tiempos\": N}}")
        else:
            for k in e:
                if k not in CLAVES_ENTRADA:
                    errores.append(f"{pref}: clave desconocida en 'entrada': '{k}'")
            tiempos = e.get("tiempos", params["transiciones"]["fundido_tiempos"])
            if not _num(tiempos) or not (0.25 <= tiempos <= 64):
                errores.append(f"{pref}: entrada.tiempos tiene que estar entre 0,25 y 64")
            entrada = {"tipo": e["tipo"], "tiempos": float(tiempos) if _num(tiempos) else 4.0}
    # ancla
    ancla = None
    if "ancla" in t:
        ancla = _ancla(pref, t["ancla"], c, piezas, ini, fin, errores)
    # repetir
    repetir = t.get("repetir")
    if repetir is not None:
        if not isinstance(repetir, str):
            errores.append(f"{pref}: 'repetir' tiene que ser el nombre de una sección")
            repetir = None
        else:
            try:
                s = c.seccion(repetir)
                repetir = s.nombre
                if piezas and not any(a <= s.loop[0] and s.loop[1] <= b for a, b in piezas):
                    errores.append(f"{pref}: 'repetir' = '{repetir}', pero su loop (compases "
                                   f"{s.loop[0]}–{s.loop[1]}) no está dentro del material del tramo")
            except KeyError:
                noms = [s.nombre for s in c.secciones]
                errores.append(f"{pref}: 'repetir': la sección '{repetir}' no existe{sugerir(repetir, noms)}")
                repetir = None
    acortar = t.get("acortar", "final")
    if acortar not in ("final", "inicio"):
        errores.append(f"{pref}: 'acortar' tiene que ser \"final\" o \"inicio\" (llegó {acortar!r})")
        acortar = "final"
    # stems
    stems = {}
    if "stems" in t:
        st = t["stems"]
        if not isinstance(st, dict):
            errores.append(f"{pref}: 'stems' tiene que ser un objeto {{stem: dB | \"silencio\"}}")
        else:
            for s, v in st.items():
                if s not in STEMS:
                    errores.append(f"{pref}: stem desconocido '{s}'{sugerir(s, STEMS)}. Válidos: {', '.join(STEMS)}")
                elif v is None or v == "silencio":
                    stems[s] = None
                elif _num(v) and -60 <= v <= 12:
                    stems[s] = float(v)
                else:
                    errores.append(f"{pref}: stems.{s} tiene que ser dB entre −60 y 12, o \"silencio\" (llegó {v!r})")
            if piezas and stems and all(v is None for v in stems.values()) and len(stems) == len(STEMS):
                errores.append(f"{pref}: todos los stems en silencio")
    # ducking por tramo
    duck = None
    if "ducking" in t:
        d = t["ducking"]
        if d is False:
            duck = False
        elif isinstance(d, dict):
            duck = {}
            for k, v in d.items():
                if k not in CLAVES_DUCK_TRAMO:
                    errores.append(f"{pref}: ducking.{k} desconocido{sugerir(k, CLAVES_DUCK_TRAMO)}. "
                                   f"Válidos: {', '.join(CLAVES_DUCK_TRAMO)}")
                elif k == "profundidad_db":
                    if not isinstance(v, dict):
                        errores.append(f"{pref}: ducking.profundidad_db tiene que ser {{stem: dB}}")
                        continue
                    for s, x in v.items():
                        if s not in STEMS:
                            errores.append(f"{pref}: ducking.profundidad_db.{s}: stem desconocido")
                        elif not _num(x) or not (-40 <= x <= 0):
                            errores.append(f"{pref}: ducking.profundidad_db.{s} tiene que estar entre −40 y 0")
                    duck["profundidad_db"] = {s: float(x) for s, x in v.items() if s in STEMS and _num(x)}
                elif k == "eq_db":
                    if not _num(v) or not (-18 <= v <= 0):
                        errores.append(f"{pref}: ducking.eq_db tiene que estar entre −18 y 0")
                    else:
                        duck["eq_db"] = float(v)
        else:
            errores.append(f"{pref}: 'ducking' tiene que ser false o un objeto con profundidad_db / eq_db")
    if len(errores) > n_err:
        return None
    sec_txt = (", ".join(t["secciones"]) if isinstance(t.get("secciones"), list) else
               t.get("secciones") or t.get("seccion") or f"compases {piezas[0][0]}–{piezas[0][1]}")
    return Tramo(i, t.get("id") or f"tramo {i + 1}", c, piezas, float(ini), float(fin), float(nivel),
                 tr, entrada, ancla, repetir, acortar, stems, duck, sec_txt)


def _transicion(pref, v, ultimo, params, errores) -> Transicion:
    pt = params["transiciones"]
    if v is None:
        return Transicion("cola", segundos=pt["cola_s"]) if ultimo else \
            Transicion("fundido", tiempos=pt["fundido_tiempos"])
    if isinstance(v, str):
        v = {"tipo": v}
    if not isinstance(v, dict) or "tipo" not in v:
        errores.append(f"{pref}: 'transicion' tiene que ser un texto o un objeto con 'tipo' "
                       f"({', '.join(TIPOS)})")
        return Transicion("fundido", tiempos=pt["fundido_tiempos"])
    tipo = v["tipo"]
    if tipo not in TIPOS:
        errores.append(f"{pref}: transicion.tipo '{tipo}' no válido{sugerir(str(tipo), TIPOS)}; "
                       f"usá uno de: {', '.join(TIPOS)}")
        return Transicion("fundido", tiempos=pt["fundido_tiempos"])
    for k in v:
        if k not in CLAVES_TRANS[tipo]:
            errores.append(f"{pref}: transicion '{tipo}' no lleva '{k}' (claves: {', '.join(CLAVES_TRANS[tipo])})")
    tr = Transicion(tipo)
    if tipo == "fundido":
        n = v.get("tiempos", pt["final_fundido_tiempos"] if ultimo else pt["fundido_tiempos"])
        if not _num(n) or not (0.25 <= n <= 64):
            errores.append(f"{pref}: transicion.tiempos tiene que estar entre 0,25 y 64 (llegó {n!r})")
            n = 4.0
        tr.tiempos = float(n)
        al = v.get("alineacion", "auto")
        if al not in ("auto", "antes", "despues"):
            errores.append(f"{pref}: transicion.alineacion tiene que ser auto, antes o despues")
            al = "auto"
        tr.alineacion = al
    elif tipo == "cola":
        s = v.get("segundos", pt["cola_s"])
        if not _num(s) or not (0.5 <= s <= 12):
            errores.append(f"{pref}: transicion.segundos tiene que estar entre 0,5 y 12 (recomendado 2–4)")
            s = 3.0
        tr.segundos = float(s)
    elif tipo == "pausa":
        s = v.get("silencio_s")
        if s is not None and (not _num(s) or not (0 <= s <= 30)):
            errores.append(f"{pref}: transicion.silencio_s tiene que estar entre 0 y 30")
            s = None
        tr.silencio_s = None if s is None else float(s)
    elif tipo == "final" and not ultimo:
        pass   # se informa en las relaciones entre tramos
    return tr


def _ancla(pref, v, c: Cancion, piezas, ini, fin, errores) -> Ancla | None:
    if not isinstance(v, dict):
        errores.append(f"{pref}: 'ancla' tiene que ser un objeto: {{\"seccion\": \"x\", \"en\": s}} o "
                       "{\"compas\": n, \"en\": s}")
        return None
    for k in v:
        if k not in CLAVES_ANCLA:
            errores.append(f"{pref}: clave desconocida en 'ancla': '{k}'{sugerir(k, CLAVES_ANCLA)}")
    en = v.get("en")
    if not _num(en):
        errores.append(f"{pref}: ancla.en (segundos) es obligatorio")
        return None
    if _num(ini) and _num(fin) and not (ini <= en < fin):
        errores.append(f"{pref}: ancla.en = {en} tiene que caer dentro del tramo [{ini}, {fin})")
    sec = v.get("seccion")
    comp = v.get("compas")
    if (sec is None) == (comp is None):
        errores.append(f"{pref}: el ancla lleva 'seccion' o 'compas' (uno solo)")
        return None
    if sec is not None:
        try:
            s = c.seccion(sec)
            comp, sec = s.c0, s.nombre
        except KeyError:
            noms = [s.nombre for s in c.secciones]
            errores.append(f"{pref}: ancla: la sección '{sec}' no existe en {c.slug}{sugerir(str(sec), noms)}")
            return None
    if not isinstance(comp, int) or not (1 <= comp <= c.n_compases):
        errores.append(f"{pref}: ancla.compas tiene que ser un entero entre 1 y {c.n_compases}")
        return None
    if piezas and not any(a <= comp <= b for a, b in piezas):
        errores.append(f"{pref}: el ancla (compás {comp}) no está dentro del material del tramo "
                       f"({', '.join(f'{a}–{b}' for a, b in piezas)})")
    tiempo = v.get("tiempo", 1)
    if not _num(tiempo) or not (1 <= tiempo < c.pulsos + 1):
        errores.append(f"{pref}: ancla.tiempo tiene que estar entre 1 y {c.pulsos} (pulsos del compás)")
        tiempo = 1
    rep = v.get("repeticion", 1)
    if not isinstance(rep, int) or rep < 1:
        errores.append(f"{pref}: ancla.repeticion tiene que ser un entero ≥ 1")
        rep = 1
    return Ancla(int(comp), float(tiempo), float(en), rep, sec)
