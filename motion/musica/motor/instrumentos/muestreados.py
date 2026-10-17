"""Instrumentos con muestras reales (VSCO-2 CE y VCSL, CC0)."""
from __future__ import annotations

import numpy as np

from ..nucleo import SR, desde_db, rng, rampa, mezclar_en, cortar
from ..efectos import biquad, sosf
from .base import Banco, Instrumento, envolvente_nota, CACHE


def _a_estereo(seg: np.ndarray) -> np.ndarray:
    if seg.shape[1] == 2:
        return seg
    return np.repeat(seg, 2, axis=1) * np.float32(0.7071)


def _balance(y: np.ndarray, pan: float, ancho: float = 1.0) -> np.ndarray:
    if ancho != 1.0:
        m = 0.5 * (y[:, 0] + y[:, 1])
        s = 0.5 * (y[:, 0] - y[:, 1]) * ancho
        y = np.stack([m + s, m - s], axis=1)
    if pan:
        a = (np.clip(pan, -1, 1) + 1) * np.pi / 4
        y = y * np.array([min(1.0, np.cos(a) * np.sqrt(2)), min(1.0, np.sin(a) * np.sqrt(2))],
                         dtype=np.float32)
    return y


def zona_estable(mono: np.ndarray):
    """(inicio, fin, nivel_rms) del sostenido: donde la envolvente queda a ±4 dB de su mediana
    (deja afuera el ataque lento de las capas suaves y la caída final de la muestra)."""
    L = len(mono)
    h = int(0.05 * SR)
    nb = max(1, L // h)
    e = np.sqrt((mono[: nb * h].reshape(nb, h) ** 2).mean(axis=1) + 1e-12)
    k = 6
    e = np.sqrt(np.convolve(e ** 2, np.ones(k) / k, mode="same"))
    edb = 20 * np.log10(e)
    a, b = int(0.2 * nb), max(int(0.2 * nb) + 1, int(0.8 * nb))
    med = float(np.median(edb[a:b]))
    ok = np.nonzero(edb >= med - 4.0)[0]
    ok = ok[ok >= int(0.12 * nb)]
    if len(ok) < 10:
        return int(0.35 * L), int(0.85 * L), 10 ** (med / 20)
    s0 = (ok[0] + 6) * h
    s1 = (ok[-1] - 6) * h
    if s1 - s0 < int(1.2 * SR):
        s0, s1 = int(0.35 * L), int(0.85 * L)
    return s0, s1, 10 ** (med / 20)


def extender(a: np.ndarray, n_total: int, semilla) -> np.ndarray:
    """Alarga una muestra sostenida con bucles de fundido largo, alineados por correlación.

    La zona de bucle se detecta en la envolvente (sin ataque ni caída final) y
    su nivel se aplana suavemente para que el sostenido no "serruche". Cada
    salto vuelve a un punto distinto de esa zona, así una nota de 20 s no repite
    el mismo ciclo. El fundido compensa la correlación entre los dos tramos."""
    L = len(a)
    if L >= n_total:
        return a[:n_total]
    g = rng("extender", semilla)
    mono0 = a.mean(axis=1).astype(np.float64)
    s0, s1, nivel = zona_estable(mono0)
    # aplanar el nivel desde s0 (rampa de 0,5 s): ganancia = nivel / envolvente lenta
    h = int(0.05 * SR)
    nb = L // h + 1
    pad = np.pad(mono0, (0, nb * h - L))
    e = np.sqrt((pad.reshape(nb, h) ** 2).mean(axis=1) + 1e-12)
    e = np.sqrt(np.convolve(e ** 2, np.ones(8) / 8, mode="same"))
    gan = np.clip(nivel / e, 0.5, 2.0)
    gan = np.interp(np.arange(L), (np.arange(nb) + 0.5) * h, gan)
    w = np.clip((np.arange(L) - s0) / (0.5 * SR) + 1.0, 0, 1)
    gan = 1.0 + (gan - 1.0) * w
    a = (a * gan[:, None]).astype(np.float32)
    X = int(0.32 * SR)
    if s1 - s0 < 3 * X:
        X = max(2048, (s1 - s0) // 3)
    mono = a.mean(axis=1).astype(np.float64)
    partes = [a[:s1].astype(np.float32)]
    total = s1
    p = s1  # posición de la fuente donde termina lo copiado
    W = 4096
    P = 600
    partes = [a[:s1].astype(np.float32)]
    while total < n_total:
        lo = s0 + X
        hi = max(lo + 1, p - X - int(0.45 * SR))
        q0 = int(g.integers(lo, hi)) if hi > lo else lo
        # alinear q con la forma de onda alrededor del centro del fundido
        cen_p = p - X // 2
        tpl = mono[cen_p - W // 2: cen_p + W // 2]
        a0 = max(W // 2, q0 - X // 2 - P)
        b0 = min(L - W // 2, q0 - X // 2 + P)
        big = mono[a0 - W // 2: b0 + W // 2]
        if len(big) > len(tpl) and len(tpl) == W:
            cc = np.correlate(big, tpl, mode="valid")
            q = a0 + int(np.argmax(cc)) + X // 2
        else:
            q = q0
        q = int(np.clip(q, X, L - 1))
        xa = a[p - X:p].astype(np.float64)
        xb = a[q - X:q].astype(np.float64)
        ma, mb = xa.mean(axis=1), xb.mean(axis=1)
        rho = float(np.dot(ma, mb) / (np.sqrt(np.dot(ma, ma) * np.dot(mb, mb)) + 1e-12))
        t = (np.arange(X) + 0.5) / X
        ga, gb = np.cos(np.pi * t / 2), np.sin(np.pi * t / 2)
        norm = 1.0 / np.sqrt(np.maximum(0.25, ga ** 2 + gb ** 2 + 2 * rho * ga * gb))
        cruce = (xa * (ga * norm)[:, None] + xb * (gb * norm)[:, None]).astype(np.float32)
        partes[-1] = partes[-1][:-X] if len(partes[-1]) > X else partes[-1][:0]
        partes.append(cruce)
        cuerpo = a[q:p].astype(np.float32)
        partes.append(cuerpo)
        total = sum(len(z) for z in partes)
    y = np.concatenate(partes, axis=0)
    return y[:n_total]


class Muestreador(Instrumento):
    """Instrumento genérico de muestras con capas de velocidad.

    * banco      : nombre en manifest.json ("piano", "arpa", "violines", …)
    * rango_db   : rango dinámico de la velocidad (vel 1 = 0 dB)
    * capas_vel  : velocidades donde empieza y termina el cruce entre capas
    * ataque     : fundido de entrada (s) · soltar: caída al soltar (s)
    * sostener   : True = la nota suena hasta apagarse sola (arpa, glock),
                   salvo que la nota tenga apagar=True
    * largo_max  : tope de duración cuando sostiene (s)
    * abrir      : paneo según altura (graves a la izquierda, agudos a la derecha)
    * ancho      : ancho estéreo de la muestra · tope_hz: pasabajos fijo
    """

    def __init__(self, banco: str, rango_db=24.0, curva=1.0, capas_vel=(0.3, 0.85),
                 ataque=0.0015, soltar=0.3, sostener=False, largo_max=10.0, pan=0.0,
                 abrir=0.0, ancho=1.0, tope_hz=None, ganancia_db=0.0, transponer=0):
        self.banco_nombre = banco
        self.rango_db, self.curva, self.capas_vel = rango_db, curva, capas_vel
        self.ataque, self.soltar, self.sostener, self.largo_max = ataque, soltar, sostener, largo_max
        self.pan, self.abrir, self.ancho, self.tope_hz = pan, abrir, ancho, tope_hz
        self.ganancia_db, self.transponer = ganancia_db, transponer
        self.nombre = banco
        # calibración: una nota sostenida a vel 0.6 ronda −26 LUFS (ver README)
        self.calib_db = self.CALIB.get(banco, 0.0)

    CALIB = {"piano": 4.7, "arpa": 6.9, "glock": 7.0, "vibrafono": 0.9, "violines": -12.2,
             "violas": -7.2, "chelos": -11.9, "contrabajo": -6.6, "violines_trem": -7.9,
             "violas_trem": -0.3, "chelos_trem": 2.1, "violines_pizz": 6.2, "chelos_pizz": 8.9,
             "contrabajo_pizz": 7.1}

    @property
    def banco(self) -> Banco:
        return Banco.de(self.banco_nombre)

    # ------------------------------------------------------------ helpers
    def pesos_capas(self, vel: float):
        L = self.banco.n_capas
        if L == 1:
            return [(0, 1.0)]
        v0, v1 = self.capas_vel
        p = np.clip((vel - v0) / max(1e-6, v1 - v0), 0, 1) * (L - 1)
        c0 = int(np.floor(p))
        f = p - c0
        if c0 >= L - 1:
            return [(L - 1, 1.0)]
        if f < 0.04:
            return [(c0, 1.0)]
        if f > 0.96:
            return [(c0 + 1, 1.0)]
        # potencia constante entre capas
        return [(c0, float(np.cos(f * np.pi / 2))), (c0 + 1, float(np.sin(f * np.pi / 2)))]

    def soltar_de(self, midi: float, nt) -> float:
        return float(nt.x.get("soltar", self.soltar))

    def ganancia(self, vel: float) -> float:
        return float(desde_db(self.calib_db + self.ganancia_db +
                              self.rango_db * (max(vel, 1e-3) ** self.curva - 1)))

    def pan_de(self, midi: float, nt) -> float:
        p = nt.x.get("pan", self.pan)
        if self.abrir:
            p += self.abrir * np.clip((midi - 62) / 24, -1, 1)
        return float(np.clip(p, -1, 1))

    def leer(self, midi, capa, n_total, offset, clave, sostenida=False, semilla=0):
        """Audio (n_total, 2) de la capa para esa altura, transpuesto y alargado si hace falta."""
        b = self.banco
        i = b.elegir(midi, capa, clave)
        semis = midi - b.midi[i] - b.cents[i] / 100.0
        ratio = 2.0 ** (semis / 12)
        n_in = int((n_total + offset) * ratio) + 64
        a = b.remuestreado(i, semis, n_in)
        if sostenida and len(a) < n_total + offset:
            k = ("ext", b.nombre, i, round(ratio, 7))
            ext = CACHE.get(k)
            if ext is None or len(ext) < n_total + offset:
                ext = extender(b.remuestreado(i, semis, None), int((n_total + offset) * 1.15) + SR,
                               (b.nombre, i, round(ratio, 6)))
                CACHE.put(k, ext)
            a = ext
        seg = a[offset: offset + n_total]
        seg = _a_estereo(np.asarray(seg, dtype=np.float32)) * np.float32(desde_db(b.ajuste_db[i]))
        if len(seg) < n_total:
            seg = np.concatenate([seg, np.zeros((n_total - len(seg), 2), np.float32)])
        return seg

    def post_nota(self, y, nt, midi, ctx, pista, n_on):
        return y

    def render(self, notas, ctx, pista):
        out = super().render(notas, ctx, pista)
        if self.tope_hz:  # filtro fijo: aplicarlo a la suma equivale a hacerlo nota por nota
            out = sosf(biquad("pb", self.tope_hz, 0.6), out)
        return out

    # ------------------------------------------------------------ voz
    def voz(self, nt, ctx, pista):
        midi = nt.midi + self.transponer
        i0 = ctx.muestra(nt.t)
        n_on = max(32, self.fin_nota(nt, ctx, pista) - i0)
        if self.sostener and not nt.x.get("apagar"):
            # suena hasta apagarse sola: el largo natural de la muestra (tope largo_max)
            b = self.banco
            i = b.elegir(midi, 0)
            natural = int(b.dur[i] * SR / 2.0 ** ((midi - b.midi[i]) / 12.0))
            n_on = min(int(self.largo_max * SR), max(n_on, natural))
        n_sol = int(self.soltar_de(midi, nt) * SR)
        n_total = n_on + n_sol
        clave = int(round(nt.t * 4)) + int(midi)
        y = np.zeros((n_total, 2), dtype=np.float32)
        for capa, w in self.pesos_capas(nt.vel):
            y += w * self.leer(midi, capa, n_total, 0, clave)
        y *= envolvente_nota(n_total, n_on, nt.x.get("ataque", self.ataque), n_sol / SR)[:, None]
        y = self.post_nota(y, nt, midi, ctx, pista, n_on)
        y *= np.float32(self.ganancia(nt.vel))
        y = _balance(y, self.pan_de(midi, nt), self.ancho)
        return y, i0


# =================================================================== piano ==
class Piano(Muestreador):
    """Piano de fieltro: piano vertical real (VCSL, Knight) tocado suave y apagado con fieltro.

    * fieltro  : 0..1, cuánto se oscurece y se ablanda el ataque
    * brillo   : 0..1, corrimiento general del pasabajos
    * mecanica : 0..1, ruiditos reales de apagadores (muestras de "release") y del pedal
    * Usa pedal de resonancia: `pista.pedal_por_compas(...)` o `pista.pedal(a, b)`.
    """
    usa_pedal = True

    def __init__(self, fieltro=0.65, brillo=0.5, mecanica=0.5, rango_db=26.0, **kw):
        kw.setdefault("capas_vel", (0.35, 0.9))
        kw.setdefault("ataque", 0.002)
        super().__init__("piano", rango_db=rango_db, **kw)
        self.fieltro, self.brillo, self.mecanica = fieltro, brillo, mecanica
        self.nombre = "piano"

    def soltar_de(self, midi, nt):
        if "soltar" in nt.x:
            return nt.x["soltar"]
        if midi >= 89:  # sin apagadores en el agudo extremo
            return 1.8
        return float(np.interp(midi, [36, 60, 84], [0.5, 0.3, 0.16]))

    def corte(self, midi, vel):
        base = 1600.0 * 2 ** (1.6 * (self.brillo - 0.5)) * 2 ** (-1.1 * self.fieltro)
        return float(np.clip(base * 2 ** (2.6 * vel) * 2 ** ((midi - 60) / 22), 500, 12000))

    def post_nota(self, y, nt, midi, ctx, pista, n_on):
        fc = self.corte(midi, nt.vel)
        y2 = sosf(biquad("pb", fc, 0.62), y)
        if self.fieltro > 0:
            # ataque de fieltro: arranca más oscuro y se abre en ~30 ms
            na = min(len(y2), int((0.012 + 0.03 * self.fieltro) * SR))
            if na > 8:
                muy = sosf(biquad("pb", max(250.0, fc * 0.3), 0.6), y[:na])
                w = rampa(na)[:, None]
                y2[:na] = muy * (1 - w) + y2[:na] * w
        y2 = y2.astype(np.float32)
        # ruido de apagador al soltar (muestras reales de release)
        if self.mecanica > 0 and midi < 89:
            try:
                rb = Banco.de("piano_soltar")
                i = rb.elegir(midi, 0)
                r = cortar(np.asarray(rb.audio(i)), int(0.9 * SR), 0.08)
                r = _a_estereo(r) * np.float32(desde_db(rb.ajuste_db[i] - 15 + 6 * nt.vel) * self.mecanica)
                r = sosf(biquad("pb", 2500.0, 0.6), r)
                ini = min(n_on, len(y2) - 1)
                if ini + len(r) > len(y2):
                    y2 = np.concatenate([y2, np.zeros((ini + len(r) - len(y2), 2), np.float32)])
                y2[ini:ini + len(r)] += r
            except KeyError:
                pass
        return y2

    def render(self, notas, ctx, pista):
        out = super().render(notas, ctx, pista)
        if self.mecanica > 0 and pista is not None and pista.pedales:
            try:
                pb = Banco.de("piano_pedal")
            except KeyError:
                return out
            on = [i for i, e in enumerate(pb.muestras) if "on" in e.get("articulacion", "")]
            off = [i for i, e in enumerate(pb.muestras) if "off" in e.get("articulacion", "")]
            for k, (a, b) in enumerate(pista.pedales):
                for t, lista, gdb in ((a, on, -30), (b, off, -33)):
                    if not lista:
                        continue
                    i = lista[k % len(lista)]
                    s = _a_estereo(cortar(np.asarray(pb.audio(i)), int(1.2 * SR), 0.15))
                    s = s * np.float32(desde_db(gdb) * self.mecanica)
                    s = sosf(biquad("pb", 1800.0, 0.6), s)
                    mezclar_en(out, s, ctx.muestra(t))
        return out


# ===================================================== percusión afinada ====
class Arpa(Muestreador):
    """Arpa de concierto (VCSL). Deja sonar las cuerdas (apagar=True en la nota para cortar)."""

    def __init__(self, rango_db=22.0, largo_max=6.0, **kw):
        kw.setdefault("capas_vel", (0.45, 0.95))
        kw.setdefault("abrir", 0.25)
        kw.setdefault("tope_hz", 9000.0)
        super().__init__("arpa", rango_db=rango_db, sostener=True, largo_max=largo_max,
                         soltar=0.25, **kw)
        self.nombre = "arpa"


class Glock(Muestreador):
    """Glockenspiel (VCSL, 3 capas). Suena tal cual se escribe (rango G5–C8)."""

    def __init__(self, rango_db=20.0, largo_max=4.5, **kw):
        kw.setdefault("capas_vel", (0.3, 0.9))
        kw.setdefault("tope_hz", 10000.0)
        super().__init__("glock", rango_db=rango_db, sostener=True, largo_max=largo_max,
                         soltar=0.2, **kw)
        self.nombre = "glock"


class Vibrafono(Muestreador):
    """Vibráfono con baquetas blandas (VCSL) y motor simulado.

    El motor modula en amplitud la banda de la fundamental (como los discos de
    los resonadores), con fase global para que todas las notas laten juntas.
    * motor_hz: velocidad del motor (0 = apagado) · motor_prof: 0..1
    * Usa pedal (pista.pedal...) y apaga al soltar."""
    usa_pedal = True

    def __init__(self, motor_hz=5.0, motor_prof=0.35, rango_db=22.0, **kw):
        kw.setdefault("capas_vel", (0.3, 0.85))
        kw.setdefault("soltar", 0.35)
        kw.setdefault("tope_hz", 9000.0)
        super().__init__("vibrafono", rango_db=rango_db, **kw)
        self.motor_hz, self.motor_prof = motor_hz, motor_prof
        self.nombre = "vibrafono"

    def post_nota(self, y, nt, midi, ctx, pista, n_on):
        if self.motor_hz <= 0 or self.motor_prof <= 0:
            return y
        f0 = 440 * 2 ** ((midi - 69) / 12)
        low = sosf(biquad("pb", f0 * 1.6, 0.7), y)
        t = (ctx.muestra(nt.t) + np.arange(len(y))) / SR
        am = 1 - self.motor_prof * (0.5 + 0.5 * np.sin(2 * np.pi * self.motor_hz * t))
        return (y - low + low * am[:, None]).astype(np.float32)


# ================================================================ cuerdas ===
class Cuerdas(Muestreador):
    """Sección de cuerdas real (VSCO-2 CE) con crescendos que cambian de timbre.

    * banco: "violines", "violas", "chelos", "contrabajo" (o "*_trem" para trémolo)
    * La dinámica de cada nota es vel (→ vel_fin si se indica en la nota, con
      curva suave) multiplicada por la automatización 'expresion' (0..1) de la
      pista. La dinámica cruza las capas (p → f), sube el volumen y abre el brillo.
    * legato=True en la nota (o "_" en la mini-notación): entra sin el golpe de
      arco y con ataque lento, fundiéndose con la anterior.
    * doble=True: duplica con otra muestra levemente desplazada (sección más grande).
    """

    PAN = {"violines": -0.35, "violas": 0.12, "chelos": 0.3, "contrabajo": 0.42}
    # las muestras de sección son muy abiertas (pares espaciados): se cierran un poco para
    # que la imagen tenga centro y sea compatible en mono (el contrabajo, casi mono)
    ANCHO = {"violines": 0.7, "violas": 0.9, "chelos": 0.8, "contrabajo": 0.5}

    def __init__(self, banco="violines", rango_db=22.0, ataque=0.08, soltar=0.55, doble=False,
                 legato_offset=0.11, **kw):
        base = banco.split("_")[0]
        kw.setdefault("pan", self.PAN.get(base, 0.0))
        kw.setdefault("ancho", self.ANCHO.get(base, 1.0))
        kw.setdefault("capas_vel", (0.3, 0.8))
        super().__init__(banco, rango_db=rango_db, ataque=ataque, soltar=soltar, **kw)
        self.doble, self.legato_offset = doble, legato_offset
        self.nombre = banco

    def voz(self, nt, ctx, pista):
        midi = nt.midi + self.transponer
        i0 = ctx.muestra(nt.t)
        n_on = max(32, self.fin_nota(nt, ctx, pista) - i0)
        n_sol = int(nt.x.get("soltar", self.soltar) * SR)
        n_total = n_on + n_sol
        legato = bool(nt.x.get("legato"))
        offset = int(self.legato_offset * SR) if legato else 0
        ataque = nt.x.get("ataque", 0.17 if legato else self.ataque)
        clave = int(round(nt.t * 4)) + int(midi)
        # dinámica en el tiempo
        v0 = nt.vel
        v1 = nt.x.get("vel_fin", v0)
        f = np.linspace(0, 1, n_total)
        f = np.clip(f * n_total / max(1, n_on), 0, 1)
        dyn = v0 + (v1 - v0) * (0.5 - 0.5 * np.cos(np.pi * f))
        if pista is not None and "expresion" in pista.autos:
            dyn = dyn * pista.autos["expresion"].en_muestras(n_total, ctx.tempo, i0)
        dyn = np.clip(dyn, 0.0, 1.0)
        L = self.banco.n_capas
        y = np.zeros((n_total, 2), dtype=np.float32)
        if L >= 2:
            a, b = self.capas_vel
            w1 = np.clip((dyn - a) / (b - a), 0, 1)
            w1 = w1 * w1 * (3 - 2 * w1)
            for capa, w in ((0, np.cos(w1 * np.pi / 2)), (L - 1, np.sin(w1 * np.pi / 2))):
                if w.max() < 0.02:
                    continue
                s = self.leer(midi, capa, n_total, offset, clave, sostenida=True)
                y += s * w[:, None].astype(np.float32)
        else:
            y += self.leer(midi, 0, n_total, offset, clave, sostenida=True)
        if self.doble:
            b = self.banco
            capa = 0 if dyn.mean() < 0.55 else L - 1
            i_pri = b.elegir(midi, capa, clave)
            i2 = b.elegir(midi, capa, clave + 1, excluir=(i_pri,))
            semis = midi - b.midi[i2] - b.cents[i2] / 100.0 + 0.05
            a2 = b.remuestreado(i2, semis, None)
            if len(a2) < n_total + offset + 900:
                a2 = extender(a2, n_total + offset + SR, (b.nombre, i2, "doble"))
            d = int(0.013 * SR)
            s2 = _a_estereo(np.asarray(a2[offset: offset + n_total], np.float32))
            s2 = s2 * np.float32(desde_db(b.ajuste_db[i2] - 4.0))
            s2 = np.concatenate([np.zeros((d, 2), np.float32), s2])[:n_total]
            if len(s2) < n_total:
                s2 = np.concatenate([s2, np.zeros((n_total - len(s2), 2), np.float32)])
            # la copia se abre apenas hacia el otro lado (sin invertir canales: imagen
            # compatible en mono)
            lado = 0.3 if self.pan_de(midi, nt) <= 0 else -0.3
            y += _balance(s2, lado)
        env = envolvente_nota(n_total, n_on, ataque, n_sol / SR, "cos")
        gain = desde_db(self.calib_db + self.ganancia_db + self.rango_db * (np.maximum(dyn, 1e-3) ** 0.9 - 1))
        y *= (env * gain)[:, None].astype(np.float32)
        y = _balance(y, self.pan_de(midi, nt), self.ancho)
        return y, i0


def Violines(**kw):
    return Cuerdas("violines", **kw)


def Violas(**kw):
    return Cuerdas("violas", **kw)


def Chelos(**kw):
    return Cuerdas("chelos", **kw)


def Contrabajo(**kw):
    kw.setdefault("rango_db", 20.0)
    return Cuerdas("contrabajo", **kw)


def CuerdasTrem(seccion="chelos", **kw):
    """Trémolo de sección (violines, violas o chelos): tensión, misterio."""
    kw.setdefault("ataque", 0.05)
    return Cuerdas(f"{seccion}_trem", **kw)


class Pizzicato(Muestreador):
    """Pizzicato de sección: "violines", "chelos" o "contrabajo"."""

    def __init__(self, seccion="violines", rango_db=20.0, **kw):
        kw.setdefault("pan", Cuerdas.PAN.get(seccion, 0.0))
        kw.setdefault("ancho", Cuerdas.ANCHO.get(seccion, 1.0))
        kw.setdefault("capas_vel", (0.35, 0.9))
        super().__init__(f"{seccion}_pizz", rango_db=rango_db, sostener=True, largo_max=2.5,
                         soltar=0.15, **kw)
        self.nombre = f"{seccion}_pizz"
