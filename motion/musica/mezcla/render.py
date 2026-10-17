"""Render: EDL → stems armados → ducking y EQ dinámica por stem → cama musical.

Cada segmento lee su tramo de fuente (sin copiar el archivo entero), lo multiplica por su
envolvente (fundido de entrada × fundido de salida × ganancia del bloque × ganancia fija del
stem en ese tramo) y lo suma en la línea de tiempo con desplazamiento entero de muestras
(alineación exacta: no hay interpolación ni remuestreo). Todo por trozos: la memoria no crece
con el largo del video más que lo necesario para un stem y la cama.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import sosfilt, sosfilt_zi

from . import SR, STEMS
from .ducking import Control, sos_eq

TROZO = 1 << 20      # ~22 s por trozo


class Reverb:
    """Reverb de la banda (IR generada por el motor) para las colas sintéticas."""

    def __init__(self, p: dict):
        from motor import efectos as fx
        self.irs = fx.generar_ir(p["dur"], p["predelay_ms"], p["brillo"], p["ancho"], "sala_grande", 1)
        self.conv = fx.Convolver(self.irs)
        self.largo = self.irs.shape[1]

    def __call__(self, x: np.ndarray) -> np.ndarray:
        xx = np.concatenate([x, np.zeros((self.largo, 2), np.float32)])
        return self.conv.procesar(xx)


class Renderizador:
    def __init__(self, edl, plan, ctrl: Control, curvas: dict):
        self.edl = edl
        self.plan = plan
        self.p = plan.parametros
        self.ctrl = ctrl
        self.curvas = curvas            # tramo → CurvaTramo
        self.n = edl.n_total
        self._reverb = None

    @property
    def reverb(self) -> Reverb:
        if self._reverb is None:
            self._reverb = Reverb(self.p["transiciones"]["reverb"])
        return self._reverb

    def _gan_stem(self, tramo: int, stem: str):
        v = self.plan.tramos[tramo].stems.get(stem, 0.0)
        return None if v is None else float(10 ** (v / 20))

    # ------------------------------------------------------------ stems
    def stem(self, s: str) -> np.ndarray:
        buf = np.zeros((self.n, 2), np.float32)
        for sg in self.edl.segmentos:
            self._segmento(buf, sg, s)
        for co in self.edl.colas:
            if s in co.stems:
                self._cola(buf, co, s)
        return buf

    def _segmento(self, buf, sg, s):
        cr = sg.corrida
        gs = self._gan_stem(cr.tramo, s)
        if gs is None:
            return
        off = int(round(cr.off * SR))
        src_a = int(np.floor(sg.s_ini * SR))
        src_b = int(np.ceil(sg.s_fin * SR))
        dst_a = max(0, src_a + off)
        dst_b = min(self.n, src_b + off)
        if dst_b <= dst_a:
            return
        f_in, f_out = sg.entra.get(s), sg.sale.get(s)
        curva = self.curvas[cr.tramo]
        for a in range(dst_a, dst_b, TROZO):
            b = min(dst_b, a + TROZO)
            t = np.arange(a, b, dtype=np.float64) / SR
            env = np.full(b - a, gs, np.float32)
            if f_in is not None:
                env *= f_in.entra(t)
            if f_out is not None:
                env *= f_out.sale(t)
            env *= (10.0 ** (curva(t) / 20.0)).astype(np.float32)
            nz = np.nonzero(env > 1e-7)[0]
            if len(nz) == 0:
                continue
            i0, i1 = int(nz[0]), int(nz[-1]) + 1
            x = cr.cancion.leer(s, a + i0 - off, a + i1 - off)
            buf[a + i0:a + i1] += x * env[i0:i1, None]

    def _cola(self, buf, co, s):
        cr = co.corrida
        gs = self._gan_stem(cr.tramo, s)
        if gs is None:
            return
        off = int(round(cr.off * SR))
        i0 = int(round(co.t_entrada0 * SR))
        i1 = int(round(co.t_corte * SR))
        if i1 - i0 < 64:
            return
        x = cr.cancion.leer(s, i0 - off, i1 - off)
        t_in = np.arange(i0, i1, dtype=np.float64) / SR
        # la entrada de la reverb es lo que sonaba: con su fundido de salida y una entrada suave
        w = co.fundido.sale(t_in).astype(np.float32)
        h = (i1 - i0) // 2
        w[:h] *= (0.5 - 0.5 * np.cos(np.pi * np.arange(h) / h)).astype(np.float32)
        g = gs * float(10 ** (self.curvas[cr.tramo](np.array([co.t_corte]))[0] / 20))
        g *= float(10 ** (co.nivel_db / 20))
        y = self.reverb(x * (w * np.float32(g))[:, None])
        t_out = np.arange(i0, i0 + len(y), dtype=np.float64) / SR
        env = co.fundido.entra(t_out)
        if co.fin is not None:
            x2 = np.clip((t_out - co.t_corte) / max(1e-3, co.fin - co.t_corte), 0.0, 1.0)
            env = env * (0.5 + 0.5 * np.cos(np.pi * x2)).astype(np.float32)
        a, b = max(0, i0), min(self.n, i0 + len(y))
        if b > a:
            buf[a:b] += y[a - i0:b - i0] * env[a - i0:b - i0, None]

    # ------------------------------------------------------------ ducking + EQ
    def duckear(self, buf: np.ndarray, s: str) -> np.ndarray:
        """Aplica (en el lugar) la ganancia de ducking del stem y la EQ dinámica."""
        pd = self.p["ducking"]
        con_eq = pd["activo"] and pd["eq"]["activo"] and s in pd["eq"]["stems"] and \
            float(np.min(self.ctrl.eq)) < 0
        gdb = self.ctrl.duck_db(s)
        sos = zi = None
        if con_eq:
            sos = sos_eq(pd["eq"]["desde_hz"], pd["eq"]["hasta_hz"])
            zi = np.repeat(sosfilt_zi(sos)[:, :, None], 2, axis=2) * 0.0
            eqdb = self.ctrl.eq_db()
        for a in range(0, self.n, TROZO):
            b = min(self.n, a + TROZO)
            x = buf[a:b]
            g = (10.0 ** (self.ctrl.en_muestras(gdb, a, b) / 20.0)).astype(np.float32)
            if con_eq:
                banda, zi = sosfilt(sos, x.astype(np.float64), axis=0, zi=zi)
                ge = (10.0 ** (self.ctrl.en_muestras(eqdb, a, b) / 20.0)).astype(np.float32)
                x = x - (banda.astype(np.float32) * (1.0 - ge)[:, None])
            buf[a:b] = x * g[:, None]
        return buf

    def realzar(self, cama: np.ndarray) -> np.ndarray:
        for a in range(0, self.n, TROZO):
            b = min(self.n, a + TROZO)
            g = (10.0 ** (self.ctrl.en_muestras(self.ctrl.realce, a, b) / 20.0)).astype(np.float32)
            cama[a:b] *= g[:, None]
        return cama

    def cama(self, por_stem=None) -> np.ndarray:
        """Cama completa. `por_stem(s, buf_sin_ducking)` se llama con cada stem armado (QA)."""
        cama = np.zeros((self.n, 2), np.float32)
        for s in STEMS:
            buf = self.stem(s)
            if por_stem is not None:
                por_stem(s, buf)
            self.duckear(buf, s)
            cama += buf
            del buf
        return self.realzar(cama)

    # ------------------------------------------------------------ curvas para el gráfico
    def ganancia_stem_db(self, s: str, t: np.ndarray) -> np.ndarray:
        """Ganancia total del stem (dB) en los tiempos t: suma de envolventes de segmentos (en
        amplitud) × ducking × realce. −inf → se recorta a −60."""
        tot = np.zeros(len(t))
        for sg in self.edl.segmentos:
            cr = sg.corrida
            gs = self._gan_stem(cr.tramo, s)
            if gs is None:
                continue
            t0 = sg.s_ini + cr.off
            t1 = sg.s_fin + cr.off
            m = (t >= t0) & (t < t1)
            if not m.any():
                continue
            tt = t[m]
            env = np.full(len(tt), gs)
            if sg.entra.get(s) is not None:
                env = env * sg.entra[s].entra(tt)
            if sg.sale.get(s) is not None:
                env = env * sg.sale[s].sale(tt)
            env = env * 10 ** (self.curvas[cr.tramo](tt) / 20)
            tot[m] += env
        for co in self.edl.colas:
            if s not in co.stems:
                continue
            fin = co.fin if co.fin is not None else co.t_corte + self.p["transiciones"]["reverb"]["dur"]
            m = (t >= co.fundido.t0) & (t < fin)
            if m.any():
                tt = t[m]
                gs = self._gan_stem(co.corrida.tramo, s) or 0.0
                g = gs * 10 ** ((self.curvas[co.corrida.tramo](np.array([co.t_corte]))[0] + co.nivel_db) / 20)
                dec = 10 ** (-60 * np.clip(tt - co.t_corte, 0, None) / self.p["transiciones"]["reverb"]["dur"] / 20)
                env = co.fundido.entra(tt) * dec * g
                if co.fin is not None:
                    x2 = np.clip((tt - co.t_corte) / max(1e-3, co.fin - co.t_corte), 0, 1)
                    env = env * (0.5 + 0.5 * np.cos(np.pi * x2))
                tot[m] += env
        db = 20 * np.log10(np.maximum(tot, 1e-6))
        db += self.ctrl.en_t(self.ctrl.duck_db(s), t) + self.ctrl.en_t(self.ctrl.realce, t)
        return np.maximum(db, -60.0)
