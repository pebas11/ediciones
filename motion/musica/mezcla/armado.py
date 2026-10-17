"""Armado musical: del plan a una EDL (lista de segmentos con fundidos) hecha como la haría un músico.

Reglas:
* Todo corte o empalme cae en un límite de compás (downbeats de cues.json). Los fundidos de
  empalme terminan `guarda_ms` antes del downbeat: así los ataques humanizados que se adelantan
  (hasta ~30 ms) quedan enteros en el lado que entra y no se cuelan del lado que sale.
* Fundidos de igual potencia adaptativos: con la correlación r de cada stem entre los dos
  lados, g_sale² + g_entra² + 2·r·g_sale·g_entra = 1 (r = 0 → igual potencia; r = 1 → igual
  ganancia). En empalmes de una misma canción se busca además un desfase de ±5 ms que maximice
  la correlación en graves (alineación de fase: sin cancelaciones del bajo ni del pad).
* Extender: se repite el loop recomendado de la sección (cues.json) tantas veces como haga falta;
  cada vuelta es un empalme de 1 tiempo. Acortar: se termina en un límite de compás (o se
  conserva el final con "acortar": "inicio").
* Anclas: el tramo se desplaza para que el downbeat pedido caiga exacto en el segundo pedido; la
  entrada queda en el límite de compás más cercano a 'inicio' (si falta material se repite el
  loop previo o se arranca antes en la canción).
* Entre canciones distintas, los stems rítmicos (batería y bajo) nunca se superponen: los del
  tramo que sale terminan antes del downbeat del que entra. Las colas de reverb no se cortan:
  en "cola" y "pausa" el sonido directo termina en el compás y una cola sintética (la misma
  familia de reverb de la banda, alimentada con los últimos tiempos) se apaga sola.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from . import SR, STEMS
from .canciones import Cancion
from .plan import Plan, Tramo

EPS = 1e-4


# ================================================================ estructuras ==
@dataclass
class Fundido:
    t0: float
    t1: float
    forma: str = "potencia"      # potencia (adaptativa con r) | coseno | lineal
    r: float = 0.0

    def entra(self, t: np.ndarray) -> np.ndarray:
        if self.t1 <= self.t0:
            return (t >= self.t0).astype(np.float32)
        x = np.clip((t - self.t0) / (self.t1 - self.t0), 0.0, 1.0)
        return curva(x, self.forma, self.r)

    def sale(self, t: np.ndarray) -> np.ndarray:
        if self.t1 <= self.t0:
            return (t < self.t0).astype(np.float32)
        x = np.clip((t - self.t0) / (self.t1 - self.t0), 0.0, 1.0)
        return curva(1.0 - x, self.forma, self.r)


def curva(x: np.ndarray, forma: str, r: float = 0.0) -> np.ndarray:
    """Ganancia 0→1 de un fundido de entrada; la de salida es curva(1 − x)."""
    if forma == "lineal":
        return x.astype(np.float32)
    if forma == "coseno":
        return (0.5 - 0.5 * np.cos(np.pi * x)).astype(np.float32)
    s, c = np.sin(0.5 * np.pi * x), np.cos(0.5 * np.pi * x)
    r = float(np.clip(r, 0.0, 1.0))
    return (s / np.sqrt(1.0 + 2.0 * r * s * c)).astype(np.float32)


@dataclass
class Corrida:
    """Compases c0..c1 (inclusivo) de una canción, contiguos, ubicados en la línea de tiempo."""
    tramo: int
    cancion: Cancion
    c0: int
    c1: int
    t0: float                      # downbeat de c0 en la línea de tiempo (nominal)
    lag: float = 0.0               # desfase de alineación (s)
    union: str = "inicio"          # inicio | loop | empalme | continuo

    @property
    def off(self) -> float:        # línea de tiempo = fuente + off
        return self.t0 - self.cancion.t(self.c0) + self.lag

    def tl(self, c: int, pulso: float = 1.0) -> float:
        return self.cancion.t(c, pulso) + self.off

    @property
    def t_fin(self) -> float:
        return self.tl(self.c1 + 1)

    def pulso(self, c: int | None = None) -> float:
        return self.cancion.pulso_s(self.c1 if c is None else c)


@dataclass
class Segmento:
    corrida: Corrida
    entra: dict                    # stem → Fundido
    sale: dict                     # stem → Fundido | None (None = sigue hasta s_fin)
    s_ini: float = 0.0             # tramo de fuente a leer (s)
    s_fin: float = 0.0
    natural: bool = False          # deja sonar la cola real de la canción (final de la canción)


@dataclass
class Cola:
    """Cola de reverb sintética: la reverb de la banda alimentada con los últimos tiempos."""
    corrida: Corrida
    t_entrada0: float              # comienzo de la ventana de entrada (línea de tiempo)
    t_corte: float                 # fin del sonido directo (= fin de la ventana)
    fundido: Fundido               # entrada de la cola (complementaria a la salida del directo)
    fin: float | None              # None: decae sola; si no, fundido coseno hasta `fin`
    stems: list
    nivel_db: float


@dataclass
class Empalme:
    tramo: int
    tipo: str                      # loop | empalme | continuo
    t: float                       # downbeat del lado que entra
    de: int                        # último compás que suena antes
    a: int                         # compás que entra
    ventana: tuple
    lag_ms: float = 0.0
    r: dict = field(default_factory=dict)
    cancion: str = ""


@dataclass
class TransicionReal:
    de: int
    a: int | None
    tipo: str
    t: float                       # downbeat de entrada del tramo siguiente (o fin de la música)
    ventana: tuple                 # región donde conviven / se apaga
    detalle: str = ""
    t_corte: float | None = None   # dónde termina el sonido directo del que sale


@dataclass
class TramoReal:
    tramo: Tramo
    barras: list
    corridas: list
    t_entrada: float
    t_fin_musica: float            # último límite de compás que suena
    avisos: list = field(default_factory=list)
    ancla_error_ms: float | None = None
    ancla_t: float | None = None

    def ruta_txt(self) -> str:
        partes = []
        for k, c in enumerate(self.corridas):
            et = {"loop": " ↺", "empalme": " ⇢", "continuo": ""}.get(c.union, "") if k else ""
            partes.append(f"{et}{c.c0}–{c.c1}" if c.c1 > c.c0 else f"{et}{c.c0}")
        return ", ".join(partes).replace(",  ↺", " ↺").replace(",  ⇢", " ⇢")


@dataclass
class EDL:
    segmentos: list
    colas: list
    empalmes: list
    transiciones: list
    tramos: list                   # TramoReal
    n_total: int
    avisos: list


# =================================================================== rutas ==
def _dur(c: Cancion, barras) -> float:
    return float(sum(c.dur(b) for b in barras))


def _ends(c: Cancion, barras, t0: float) -> np.ndarray:
    return t0 + np.cumsum([c.dur(b) for b in barras]) if barras else np.zeros(0)


def _loop_en(c: Cancion, barras: list[int], preferida: str | None) -> tuple[int, int] | None:
    """Loop a usar para extender `barras`: el de `preferida` si está entero en el material; si
    no, el de la última sección (recorriendo hacia atrás) cuyo loop esté entero."""
    def entero(loop):
        L0, L1 = loop
        seq = list(range(L0, L1 + 1))
        n = len(seq)
        return any(barras[i:i + n] == seq for i in range(len(barras) - n + 1))
    if preferida:
        s = c.seccion(preferida)
        if entero(s.loop):
            return s.loop
    vistas = []
    for b in reversed(barras):
        s = c.seccion_de(b)
        if s.nombre in vistas:
            continue
        vistas.append(s.nombre)
        if entero(s.loop):
            return s.loop
    return None


def _insertar_loop(barras: list[int], loop: tuple[int, int], veces: int) -> list[int]:
    L0, L1 = loop
    seq = list(range(L0, L1 + 1))
    n = len(seq)
    pos = max(i for i in range(len(barras) - n + 1) if barras[i:i + n] == seq) + n
    return barras[:pos] + seq * veces + barras[pos:]


def ajustar_adelante(c: Cancion, barras: list[int], t0: float, regla: str, X: float,
                     loop, avisos: list, nombre: str) -> list[int]:
    """Extiende con loops y recorta el final para cumplir la regla sobre el último límite de
    compás: 'primera>=' X, 'ultima<=' X o 'cercana' a X."""
    barras = list(barras)
    falta = X + (max(c.dur(b) for b in barras) if regla != "ultima<=" else 0.0) - (t0 + _dur(c, barras))
    if falta > 0:
        if loop is None:
            avisos.append(f"{nombre}: falta material ({falta:.1f} s) y no hay loop para repetir: "
                          "la música termina antes")
        else:
            d_loop = sum(c.dur(b) for b in range(loop[0], loop[1] + 1))
            veces = int(np.ceil(falta / d_loop))
            barras = _insertar_loop(barras, loop, veces)
    e = _ends(c, barras, t0)
    if regla == "primera>=":
        k = int(np.searchsorted(e, X - EPS))
        k = min(k, len(e) - 1)
    elif regla == "ultima<=":
        k = int(np.searchsorted(e, X + EPS, side="right")) - 1
        if k < 0:
            avisos.append(f"{nombre}: no entra ni un compás antes de {X:.2f} s; queda uno")
            k = 0
    else:
        k = int(np.argmin(np.abs(e - X)))
    return barras[:k + 1]


def ajustar_atras(c: Cancion, pre: list[int], x: int, R: float, loop_pre, avisos: list,
                  nombre: str) -> list[int]:
    """Barras previas al ancla (en orden) que duran lo más parecido posible a R."""
    pre = list(pre)
    if _dur(c, pre) < R - EPS:
        if pre and loop_pre is not None:
            d_loop = sum(c.dur(b) for b in range(loop_pre[0], loop_pre[1] + 1))
            veces = int(np.ceil((R - _dur(c, pre)) / d_loop)) + 1
            pre = _insertar_loop(pre, loop_pre, veces)
        else:
            b = (pre[0] if pre else x) - 1
            while b >= 1 and _dur(c, pre) < R - EPS:
                pre.insert(0, b)
                b -= 1
            if _dur(c, pre) < R - EPS:
                lp = _loop_en(c, pre, None) if pre else None
                if lp is not None:
                    d_loop = sum(c.dur(bb) for bb in range(lp[0], lp[1] + 1))
                    veces = int(np.ceil((R - _dur(c, pre)) / d_loop)) + 1
                    pre = _insertar_loop(pre, lp, veces)
        if _dur(c, pre) < R - c.dur(x) / 2:
            avisos.append(f"{nombre}: no hay material suficiente antes del ancla; el tramo empieza "
                          f"{R - _dur(c, pre):.2f} s tarde")
    # recortar desde el principio: la entrada más cercana a R
    durs = [c.dur(b) for b in pre]
    total = sum(durs)
    mejor, mejor_k = abs(total - R), 0
    acc = total
    for k in range(len(pre)):
        acc -= durs[k]
        if abs(acc - R) < mejor - EPS:
            mejor, mejor_k = abs(acc - R), k + 1
    return pre[mejor_k:]


def corridas_de(tramo: int, c: Cancion, barras: list[int], t0: float) -> list[Corrida]:
    out: list[Corrida] = []
    t = t0
    for b in barras:
        if out and b == out[-1].c1 + 1:
            out[-1].c1 = b
        else:
            if out:
                prev = out[-1]
                es_loop = any(s.loop == (b, prev.c1) for s in c.secciones) and b <= prev.c1
                union = "loop" if es_loop else "empalme"
            else:
                union = "inicio"
            out.append(Corrida(tramo, c, b, b, t, 0.0, union))
        t += c.dur(b)
    return out


# ================================================================== armado ==
class Armador:
    def __init__(self, plan: Plan, dur_voz: float, leer_audio: bool = True):
        self.plan = plan
        self.p = plan.parametros
        self.dur_voz = dur_voz
        self.leer_audio = leer_audio
        self.g = self.p["empalmes"]["guarda_ms"] / 1000.0
        self.e = self.p["empalmes"]["entrada_ms"] / 1000.0
        self.ritmicos = set(self.p["empalmes"]["stems_ritmicos"])
        self.avisos: list[str] = []

    # ---------------------------------------------------------------- entradas
    def _entradas(self):
        trs = self.plan.tramos
        n = len(trs)
        self.T_e = [0.0] * n
        self.pre = [None] * n          # barras previas al ancla
        self.post = [None] * n         # material desde el ancla / entrada
        self.t_ancla = [None] * n
        self.fijo = [None] * n         # rutas fijas (acortar inicio)
        for k in reversed(range(n)):
            tr = trs[k]
            c = tr.cancion
            barras = tr.barras()
            nombre = tr.nombre
            if tr.ancla is not None:
                an = tr.ancla
                occ = [i for i, b in enumerate(barras) if b == an.compas]
                if len(occ) < an.repeticion:
                    self.avisos.append(f"{nombre}: el ancla pide la repetición {an.repeticion} del compás "
                                       f"{an.compas} pero aparece {len(occ)} vez/veces; uso la última")
                ia = occ[min(an.repeticion, len(occ)) - 1]
                t_x = an.en - (an.tiempo - 1.0) * c.pulso_s(an.compas)
                R = t_x - tr.inicio
                pre_mat = barras[:ia]
                loop_pre = _loop_en(c, pre_mat, tr.repetir) if pre_mat else None
                pre = ajustar_atras(c, pre_mat, an.compas, R, loop_pre, self.avisos, nombre)
                self.pre[k], self.post[k] = pre, barras[ia:]
                self.t_ancla[k] = t_x
                self.T_e[k] = t_x - _dur(c, pre)
                if tr.acortar == "inicio":
                    self.avisos.append(f"{nombre}: con ancla, 'acortar' no se usa (manda el ancla)")
            elif tr.acortar == "inicio" or (k == n - 1 and tr.transicion.tipo == "final"
                                            and c.n_compases in barras):
                # alineado por el final: el material termina justo en el punto final (cadencia o
                # final real de la canción); si falta, se repite el loop; la entrada queda en el
                # límite de compás más cercano a 'inicio'
                X = self._punto_final(k)
                R = X - tr.inicio
                ruta = list(barras)
                if _dur(c, ruta) < R - EPS:
                    lp = _loop_en(c, ruta, tr.repetir)
                    if lp is not None:
                        d_loop = sum(c.dur(b) for b in range(lp[0], lp[1] + 1))
                        ruta = _insertar_loop(ruta, lp, int(np.ceil((R - _dur(c, ruta)) / d_loop)) + 1)
                    else:
                        self.avisos.append(f"{nombre}: falta material y no hay loop: entra tarde")
                durs = [c.dur(b) for b in ruta]
                total = sum(durs)
                mejor, mk, acc = abs(total - R), 0, total
                for j in range(len(ruta) - 1):
                    acc -= durs[j]
                    if abs(acc - R) < mejor - EPS:
                        mejor, mk = abs(acc - R), j + 1
                ruta = ruta[mk:]
                self.fijo[k] = ruta
                self.T_e[k] = X - _dur(c, ruta)
            else:
                self.T_e[k] = tr.inicio
        # Tramos seguidos de la misma canción con material contiguo (p. ej. para cambiar el nivel o
        # los stems): si el que sigue entra a menos de medio compás del final natural del anterior,
        # se lo pega a ese límite de compás y la música sigue sin empalme.
        self.pegado = [False] * n
        for k in range(n - 1):
            A, B = trs[k], trs[k + 1]
            if (A.cancion is not B.cancion or B.ancla is not None or self.fijo[k + 1] is not None
                    or self.fijo[k] is not None or A.transicion.tipo not in ("fundido", "corte")):
                continue
            mat = self.pre[k] + self.post[k] if self.pre[k] is not None else A.barras()
            if not mat or B.barras()[0] != mat[-1] + 1:
                continue
            t_nat = self.T_e[k] + _dur(A.cancion, mat)     # final natural del material
            if abs(t_nat - self.T_e[k + 1]) <= A.cancion.dur(mat[-1]) / 2:
                self.T_e[k + 1] = t_nat
                self.pegado[k + 1] = True

    def _punto_final(self, k: int) -> float:
        """Dónde conviene que termine el material del tramo k (para 'acortar': 'inicio')."""
        trs = self.plan.tramos
        tr = trs[k]
        if k == len(trs) - 1:
            return tr.fin
        T_B = self.T_e[k + 1]
        if tr.transicion.tipo == "pausa":
            if tr.fin < trs[k + 1].inicio - 0.01:
                return tr.fin
            sil = tr.transicion.silencio_s if tr.transicion.silencio_s is not None \
                else self.p["transiciones"]["pausa_silencio_s"]
            return T_B - sil
        return T_B

    # ---------------------------------------------------------------- requisitos de fin
    def _primera_barra(self, k: int) -> int:
        if self.pre[k]:
            return self.pre[k][0]
        if self.fijo[k]:
            return self.fijo[k][0]
        if self.post[k]:
            return self.post[k][0]
        return self.plan.tramos[k].barras()[0]

    def _alineacion(self, k: int) -> str:
        """auto: 'antes' si el tramo siguiente tiene material propio antes de su entrada."""
        tr = self.plan.tramos[k]
        al = tr.transicion.alineacion
        if al != "auto":
            return al
        B = self.plan.tramos[k + 1]
        cb = self._primera_barra(k + 1)
        W = tr.transicion.tiempos * B.cancion.pulso_s(cb)
        return "antes" if B.cancion.t(cb) >= W + self.g + 0.05 else "despues"

    def _requisito(self, k: int):
        trs = self.plan.tramos
        tr = trs[k]
        tipo = tr.transicion.tipo
        if k == len(trs) - 1:
            return "cercana", tr.fin, {}
        T_B = self.T_e[k + 1]
        g = self.g
        if tipo == "fundido":
            al = self._alineacion(k)
            B = trs[k + 1]
            W = tr.transicion.tiempos * B.cancion.pulso_s(self._primera_barra(k + 1))
            if al == "antes":
                return "primera>=", T_B - g, {"alineacion": al, "W": W}
            return "primera>=", T_B - g + W, {"alineacion": al, "W": W}
        if tipo == "corte":
            return "primera>=", T_B - g, {}
        if tipo == "cola":
            return "cola", T_B, {}
        if tipo == "pausa":
            if tr.fin < trs[k + 1].inicio - 0.01:
                X = tr.fin
            else:
                sil = tr.transicion.silencio_s if tr.transicion.silencio_s is not None \
                    else self.p["transiciones"]["pausa_silencio_s"]
                X = T_B - sil
            return "ultima<=", X + g, {"X": X}
        return "primera>=", T_B - g, {}

    # ---------------------------------------------------------------- rutas
    def _rutas(self):
        trs = self.plan.tramos
        self.reales: list[TramoReal] = []
        for k, tr in enumerate(trs):
            c = tr.cancion
            regla, X, info = self._requisito(k)
            nombre = tr.nombre
            av: list[str] = []
            if self.fijo[k] is not None:
                barras = list(self.fijo[k])
            elif self.pre[k] is not None:
                post_loop = _loop_en(c, self.post[k], tr.repetir)
                r = "primera>=" if regla == "cola" else regla
                post = ajustar_adelante(c, self.post[k], self.t_ancla[k], r, X, post_loop, av, nombre)
                barras = self.pre[k] + post
            else:
                mat = tr.barras()
                lp = _loop_en(c, mat, tr.repetir)
                r = "primera>=" if regla == "cola" else regla
                barras = ajustar_adelante(c, mat, self.T_e[k], r, X, lp, av, nombre)
            stop_medio = False
            if regla == "cola":
                # parar en el último límite de compás ≤ T_B (+¼ de tiempo de tolerancia) si queda a
                # ≤ medio compás; si no, el directo para justo en el downbeat del que entra (T_B)
                e = _ends(c, barras, self.T_e[k])
                tol = max(self.g, 0.25 * c.pulso_s(barras[-1]))
                j = int(np.searchsorted(e, X + tol + EPS, side="right")) - 1
                if j >= 0 and X - e[j] <= c.dur(barras[j]) / 2 + EPS:
                    barras = barras[:j + 1]
                else:
                    stop_medio = True
            corr = corridas_de(k, c, barras, self.T_e[k])
            tre = TramoReal(tr, barras, corr, self.T_e[k], corr[-1].t_fin, av)
            tre.info_req = (regla, X, info, stop_medio)
            tre.n_pre = len(self.pre[k]) if self.pre[k] is not None else None
            self.avisos.extend(av)
            self.reales.append(tre)

    def _medir_anclas(self):
        for tre in self.reales:
            tr = tre.tramo
            if tr.ancla is None or tre.n_pre is None:
                continue
            acc = 0
            for cc in tre.corridas:
                largo = cc.c1 - cc.c0 + 1
                if acc <= tre.n_pre < acc + largo:
                    t_real = cc.tl(cc.c0 + (tre.n_pre - acc), tr.ancla.tiempo)
                    tre.ancla_t = t_real
                    tre.ancla_error_ms = round((t_real - tr.ancla.en) * 1000.0, 2)
                    break
                acc += largo

    # ---------------------------------------------------------------- correlación y fase
    def _correlaciones(self, A: Corrida, B: Corrida, ventana, buscar_lag: bool):
        """r por stem entre los dos lados en la ventana (y el desfase de B que maximiza la
        correlación en graves, si se pide). Devuelve (lag_s, {stem: r})."""
        if not self.leer_audio:
            return 0.0, {s: 0.0 for s in STEMS}
        t0, t1 = ventana
        n = int(round((t1 - t0) * SR))
        if n < 64:
            return 0.0, {s: 0.0 for s in STEMS}
        a0 = int(round((t0 - A.off) * SR))
        max_lag = int(round(self.p["empalmes"]["alinear_fase_ms"] / 1000.0 * SR)) if buscar_lag else 0
        b0 = int(round((t0 - B.off) * SR))
        lag = 0
        if max_lag > 0:
            from scipy.signal import sosfilt
            from motor.efectos import biquad
            sos = np.vstack([biquad("pb", 400.0, 0.707), biquad("pb", 400.0, 0.707)])
            xa = A.cancion.leer_suma(a0 - 2048, a0 + n).mean(axis=1).astype(np.float64)
            xb = B.cancion.leer_suma(b0 - max_lag - 2048, b0 + n + max_lag).mean(axis=1).astype(np.float64)
            xa = sosfilt(sos, xa)[2048:]
            xb = sosfilt(sos, xb)[2048:]
            xa -= xa.mean()
            xb -= xb.mean()
            ea = float(np.dot(xa, xa))
            if ea > 1e-10:
                cor = np.correlate(xb, xa, mode="valid")          # índice j ↔ desfase j − max_lag
                cs = np.concatenate([[0.0], np.cumsum(xb * xb)])
                eb = cs[n:] - cs[:-n]
                rr = cor / np.sqrt(ea * np.maximum(eb[:len(cor)], 1e-12))
                j0 = max_lag
                j = int(np.argmax(rr))
                if rr[j] > 0.3 and rr[j] - rr[j0] > 0.05:
                    lag = j - max_lag
        # B se lee desde b0 + lag: equivale a mover B −lag muestras en la línea de tiempo
        lag_s = -lag / SR
        rs = {}
        piso = (1e-5 ** 2) * 2 * n          # −100 dBFS: por debajo es silencio (solo dither)
        for s in STEMS:
            xa = A.cancion.leer(s, a0, a0 + n).astype(np.float64)
            xb = B.cancion.leer(s, b0 + lag, b0 + lag + n).astype(np.float64)
            xa = (xa - xa.mean(axis=0)).ravel()
            xb = (xb - xb.mean(axis=0)).ravel()
            ea, eb = float(np.dot(xa, xa)), float(np.dot(xb, xb))
            rs[s] = float(np.clip(np.dot(xa, xb) / np.sqrt(ea * eb), 0.0, 1.0)) \
                if ea > piso and eb > piso else 0.0
        return lag_s, rs

    # ---------------------------------------------------------------- EDL
    def armar(self) -> EDL:
        self._entradas()
        self._rutas()
        p = self.p
        g, e = self.g, self.e
        segs: dict[int, Segmento] = {}
        orden: list[Corrida] = []
        for tre in self.reales:
            orden.extend(tre.corridas)
        for cr in orden:
            segs[id(cr)] = Segmento(cr, {}, {s: None for s in STEMS})
        empalmes: list[Empalme] = []
        transiciones: list[TransicionReal] = []
        colas: list[Cola] = []

        def todos(f):
            return {s: f for s in STEMS}

        def empalmes_internos(tre):
            """Loops y saltos dentro del tramo (en orden: cada desfase se mide contra el anterior real)."""
            cs = tre.corridas
            for A, B in zip(cs[:-1], cs[1:]):
                T = B.t0
                tiempos = p["empalmes"]["loop_tiempos"] if B.union == "loop" else p["empalmes"]["empalme_tiempos"]
                L = tiempos * 0.5 * (A.pulso(A.c1) + B.pulso(B.c0))
                ven = (T - g - L, T - g)
                lag, rs = self._correlaciones(A, B, ven, buscar_lag=True)
                B.lag = lag
                for s in STEMS:
                    f = Fundido(ven[0], ven[1], "potencia", rs[s])
                    segs[id(A)].sale[s] = f
                    segs[id(B)].entra[s] = f
                empalmes.append(Empalme(tre.tramo.indice, B.union, T + lag, A.c1, B.c0, ven,
                                        round(lag * 1000, 2), {s: round(v, 3) for s, v in rs.items()},
                                        A.cancion.slug))

        # ---- en orden temporal: entrada del tramo, sus empalmes internos y su salida
        n = len(self.reales)
        primero = self.reales[0]
        segs[id(primero.corridas[0])].entra.update(
            self._entrada(primero.corridas[0], primero.tramo.entrada or {"tipo": "golpe"}))
        empalmes_internos(primero)
        for k, tre in enumerate(self.reales):
            tr = tre.tramo
            A = tre.corridas[-1]
            regla, X, info, stop_medio = tre.info_req
            if k == n - 1:
                transiciones.append(self._final(tre, A, segs, colas))
                continue
            tre_b = self.reales[k + 1]
            B = tre_b.corridas[0]
            T_B = B.t0
            misma = A.cancion is B.cancion
            tipo = tr.transicion.tipo
            self._transicion(k, tre, tre_b, A, B, T_B, misma, tipo, info, stop_medio, segs,
                             empalmes, transiciones, colas, todos)
            if tre_b.tramo.entrada:
                segs[id(B)].entra.update(self._entrada(B, tre_b.tramo.entrada))
            empalmes_internos(tre_b)
        self._medir_anclas()

        # ---- rangos de lectura de cada segmento
        n_total = int(np.ceil(self.dur_voz * SR))
        for sg in segs.values():
            cr = sg.corrida
            t_ini = min(f.t0 for f in sg.entra.values() if f is not None) if sg.entra else cr.t0
            if sg.natural:
                t_fin = cr.cancion.n / SR + cr.off
            else:
                fins = [f.t1 for f in sg.sale.values() if f is not None]
                t_fin = max(fins) if len(fins) == len(STEMS) else cr.t_fin
            sg.s_ini = t_ini - cr.off - 0.002
            sg.s_fin = t_fin - cr.off + 0.002
            n_total = max(n_total, int(np.ceil((t_fin + 0.01) * SR)))
        for co in colas:
            dur_ir = self.p["transiciones"]["reverb"]["dur"] * 1.25 + 0.1
            fin = co.fin if co.fin is not None else co.t_corte + dur_ir
            n_total = max(n_total, int(np.ceil((fin + 0.05) * SR)))
        for tre in self.reales:
            tre.t_fin_musica = tre.corridas[-1].t_fin
        return EDL([segs[id(cr)] for cr in orden], colas, empalmes, transiciones, self.reales,
                   n_total, self.avisos)

    def _transicion(self, k, tre, tre_b, A, B, T_B, misma, tipo, info, stop_medio, segs,
                    empalmes, transiciones, colas, todos):
        p = self.p
        g, e = self.g, self.e
        tr = tre.tramo
        # continuidad perfecta: mismo material seguido → solo cambia el nivel
        if misma and B.c0 == A.c1 + 1 and abs(A.t_fin - T_B) < 0.001 and tipo in ("fundido", "corte"):
            B.lag = A.lag
            W = 2.0 * A.pulso()
            ven = (T_B - g - W, T_B - g)
            for s in STEMS:
                f = Fundido(ven[0], ven[1], "potencia", 1.0)
                segs[id(A)].sale[s] = f
                segs[id(B)].entra[s] = f
            B.union = "continuo"
            empalmes.append(Empalme(k, "continuo", T_B, A.c1, B.c0, ven, 0.0, {}, A.cancion.slug))
            transiciones.append(TransicionReal(k, k + 1, "continuo", T_B, ven,
                                               "mismo material seguido: solo cambia el nivel"))
            return
        if tipo == "fundido":
            al, W = info["alineacion"], info["W"]
            if al == "antes":
                ven = (T_B - g - W, T_B - g)
                lag, rs = self._correlaciones(A, B, ven, buscar_lag=misma) if misma else (0.0, todos(0.0))
                if misma:
                    B.lag = lag
                for s in STEMS:
                    segs[id(A)].sale[s] = Fundido(ven[0], ven[1], "potencia", rs[s])
                    if s in self.ritmicos and not misma:
                        segs[id(B)].entra[s] = Fundido(T_B - g, T_B - g + e, "coseno")
                    else:
                        segs[id(B)].entra[s] = Fundido(ven[0], ven[1], "potencia", rs[s])
                det = f"fundido de {tr.transicion.tiempos:g} tiempos antes del downbeat (con el material previo del que entra)"
            else:
                ven = (T_B - g, T_B - g + W)
                rl = p["transiciones"]["ritmicos_salida_tiempos"] * A.pulso()
                for s in STEMS:
                    segs[id(B)].entra[s] = Fundido(T_B - g, T_B - g + e, "coseno")
                    if s in self.ritmicos:
                        segs[id(A)].sale[s] = Fundido(T_B - g - rl, T_B - g, "potencia")
                    else:
                        segs[id(A)].sale[s] = Fundido(ven[0], ven[1], "potencia")
                det = f"entra a golpe; el anterior se apaga en {tr.transicion.tiempos:g} tiempos"
            if not misma:
                det += "; batería y bajo no se superponen"
            transiciones.append(TransicionReal(k, k + 1, "fundido", T_B, ven, det + f" ({al})"))
        elif tipo == "corte":
            L = p["empalmes"]["empalme_tiempos"] * B.pulso(B.c0)
            ven = (T_B - g - L, T_B - g)
            lag, rs = self._correlaciones(A, B, ven, buscar_lag=misma) if misma else (0.0, todos(0.0))
            if misma:
                B.lag = lag
            for s in STEMS:
                segs[id(A)].sale[s] = Fundido(ven[0], ven[1], "potencia", rs[s])
                if s in self.ritmicos and not misma:
                    segs[id(B)].entra[s] = Fundido(T_B - g, T_B - g + e, "coseno")
                else:
                    segs[id(B)].entra[s] = Fundido(ven[0], ven[1], "potencia", rs[s])
            transiciones.append(TransicionReal(k, k + 1, "corte", T_B, ven, "corte en el downbeat"))
        else:   # cola | pausa
            T_s = T_B if (tipo == "cola" and stop_medio) else A.t_fin
            S = tr.transicion.segundos if tipo == "cola" else None
            ven, det = self._apagar(A, T_s, S, segs, colas, tipo)
            for s in STEMS:
                segs[id(B)].entra[s] = Fundido(T_B - g, T_B - g + e, "coseno")
            if tipo == "cola" and stop_medio:
                det += "; el directo para en el downbeat del siguiente (mitad de compás del anterior)"
            transiciones.append(TransicionReal(k, k + 1, tipo, T_B, ven, det, T_s))

    # ---------------------------------------------------------------- piezas
    def _entrada(self, B: Corrida, ent: dict) -> dict:
        g, e = self.g, self.e
        T = B.t0
        if ent["tipo"] == "golpe":
            return {s: Fundido(T - g, T - g + e, "coseno") for s in STEMS}
        W = ent["tiempos"] * B.pulso(B.c0)
        if B.cancion.t(B.c0) >= W + g:     # hay material previo: entra antes y llega pleno al downbeat
            return {s: Fundido(T - g - W, T - g, "potencia") for s in STEMS}
        return {s: Fundido(T - g, T - g + W, "potencia") for s in STEMS}

    def _apagar(self, A: Corrida, T_s: float, S: float | None, segs, colas, tipo: str):
        """Termina el sonido directo en T_s y deja una cola (real si es el final de la canción)."""
        p = self.p
        g = self.g
        c = A.cancion
        sg = segs[id(A)]
        natural = c.es_ultimo(A.c1) and abs(T_s - A.t_fin) < 1e-3
        if natural:
            sg.natural = True
            if S is not None:          # cola: la cola real, con fundido en S segundos
                for s in STEMS:
                    sg.sale[s] = Fundido(T_s, T_s + S, "coseno")
                return (T_s, T_s + S), f"cola real de la canción, se apaga en {S:g} s"
            for s in STEMS:
                sg.sale[s] = None
            return (T_s, c.n / SR + A.off), "cola real de la canción (suena entera)"
        f = p["transiciones"]["corte_cola_tiempos"] * A.pulso()
        rl = p["transiciones"]["ritmicos_salida_tiempos"] * A.pulso()
        rv = p["transiciones"]["reverb"]
        for s in STEMS:
            if s in self.ritmicos:
                sg.sale[s] = Fundido(T_s - g - rl, T_s - g, "potencia")
            else:
                sg.sale[s] = Fundido(T_s - g - f, T_s - g, "potencia")
        V = rv["ventana_tiempos"] * A.pulso()
        fin = (T_s - g + S) if S is not None else None
        colas.append(Cola(A, T_s - g - V, T_s - g, Fundido(T_s - g - f, T_s - g, "potencia"),
                          fin, list(rv["stems"]), rv["nivel_db"]))
        if S is not None:
            return (T_s - g - f, fin), f"el directo para en el compás; cola de reverb de {S:g} s"
        return (T_s - g - f, T_s - g + rv["dur"]), "el directo para en el compás; la cola de reverb decae sola"

    def _final(self, tre: TramoReal, A: Corrida, segs, colas) -> TransicionReal:
        tr = tre.tramo
        tipo = tr.transicion.tipo
        T_s = A.t_fin
        g = self.g
        if tipo == "fundido":
            W = tr.transicion.tiempos * A.pulso()
            ven = (T_s - g - W, T_s - g)
            for s in STEMS:
                segs[id(A)].sale[s] = Fundido(ven[0], ven[1], "potencia")
            return TransicionReal(tr.indice, None, "fundido", T_s, ven,
                                  f"fundido final de {tr.transicion.tiempos:g} tiempos", T_s)
        if tipo == "cola":
            ven, det = self._apagar(A, T_s, tr.transicion.segundos, segs, colas, tipo)
            return TransicionReal(tr.indice, None, "cola", T_s, ven, det, T_s)
        if tipo == "final" and not A.cancion.es_ultimo(A.c1):
            self.avisos.append(f"{tr.nombre}: 'final' pide terminar con la canción, pero el material "
                               f"termina en el compás {A.c1} de {A.cancion.n_compases}: cierro con cola de reverb "
                               "(usá \"acortar\": \"inicio\" para conservar el final)")
        ven, det = self._apagar(A, T_s, None, segs, colas, tipo)
        return TransicionReal(tr.indice, None, tipo, T_s, ven, det, T_s)


def armar(plan: Plan, dur_voz: float, leer_audio: bool = True) -> EDL:
    return Armador(plan, dur_voz, leer_audio).armar()
