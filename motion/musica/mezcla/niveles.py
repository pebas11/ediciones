"""Sonoridad BS.1770-4 por sub-bloques de 100 ms (memoria acotada) y niveles por bloque musical.

Con la potencia ponderada K de cada sub-bloque de 100 ms salen, sin volver a filtrar:
* LUFS integrado (bloques de 400 ms al 75 %, compuertas −70 LUFS y −10 LU),
* LUFS momentáneo (400 ms) y de corto plazo (3 s), con salto de 100 ms,
* y el integrado restringido a una máscara (p. ej. "solo mientras habla la voz").
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.signal import sosfilt, sosfilt_zi

from . import SR, STEMS

# Ponderación K de BS.1770 a 48 kHz (coeficientes del estándar)
K_SOS = np.array([[1.53512485958697, -2.69169618940638, 1.19839281085285,
                   1.0, -1.69065929318241, 0.73248077421585],
                  [1.0, -2.0, 1.0, 1.0, -1.99004745483398, 0.99007225036621]])
SUB = int(0.1 * SR)          # 100 ms
BLOQUE = 4                   # 400 ms = 4 sub-bloques
CORTO = 30                   # 3 s = 30 sub-bloques


def potencia_k_bloques(x: np.ndarray, trozo: int = 1 << 21) -> np.ndarray:
    """Potencia ponderada K (suma de canales) media por sub-bloque de 100 ms."""
    if x.ndim == 1:
        x = x[:, None]
    n, ch = x.shape
    nb = n // SUB
    out = np.zeros(nb + (1 if n % SUB else 0))
    zi = np.repeat(sosfilt_zi(K_SOS)[:, :, None], ch, axis=2) * 0.0
    resto = np.zeros(0)
    pos_bloque = 0
    for a in range(0, n, trozo):
        seg = x[a:a + trozo].astype(np.float64)
        y, zi = sosfilt(K_SOS, seg, axis=0, zi=zi)
        p = (y * y).sum(axis=1)
        if len(resto):
            p = np.concatenate([resto, p])
        k = len(p) // SUB
        if k:
            out[pos_bloque:pos_bloque + k] = p[:k * SUB].reshape(k, SUB).mean(axis=1)
            pos_bloque += k
        resto = p[k * SUB:]
    if len(resto):
        out[pos_bloque] = resto.mean()
        pos_bloque += 1
    return out[:pos_bloque]


def _lk(p):
    return -0.691 + 10.0 * np.log10(np.maximum(p, 1e-30))


def bloques_400(p: np.ndarray) -> np.ndarray:
    """Potencia media de los bloques de 400 ms (salto 100 ms): índice j cubre sub-bloques j..j+3."""
    if len(p) < BLOQUE:
        return np.zeros(0)
    cs = np.concatenate([[0.0], np.cumsum(p)])
    return (cs[BLOQUE:] - cs[:-BLOQUE]) / BLOQUE


def integrado(p: np.ndarray, mascara: np.ndarray | None = None) -> float | None:
    """LUFS integrado a partir de sub-bloques de 100 ms. `mascara` (por bloque de 400 ms)
    restringe qué bloques entran (antes de las compuertas)."""
    z = bloques_400(p)
    if mascara is not None:
        m = np.asarray(mascara, bool)[:len(z)]
        z = z[:len(m)][m]
    if len(z) == 0:
        return None
    z = z[_lk(z) > -70.0]
    if len(z) == 0:
        return None
    rel = _lk(z.mean()) - 10.0
    z2 = z[_lk(z) > rel]
    return float(_lk(z2.mean())) if len(z2) else None


def corto_plazo(p: np.ndarray, salto: int = 5) -> tuple[np.ndarray, np.ndarray]:
    """LUFS de corto plazo (3 s). Devuelve (centros en s, LUFS) con salto de `salto`×100 ms."""
    if len(p) < CORTO:
        return np.zeros(0), np.zeros(0)
    cs = np.concatenate([[0.0], np.cumsum(p)])
    ini = np.arange(0, len(p) - CORTO + 1, salto)
    z = (cs[ini + CORTO] - cs[ini]) / CORTO
    return (ini + CORTO / 2) * 0.1, np.maximum(_lk(z), -90.0)


def momentaneo(p: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    z = bloques_400(p)
    return (np.arange(len(z)) + BLOQUE / 2) * 0.1, np.maximum(_lk(z), -90.0)


def lufs(x: np.ndarray) -> float | None:
    return integrado(potencia_k_bloques(x))


def fraccion_ventanas(mask_sub: np.ndarray, ancho: int, salto: int = 1) -> np.ndarray:
    """Fracción de cada ventana de `ancho` sub-bloques (salto `salto`) cubierta por la máscara."""
    m = np.asarray(mask_sub, np.float64)
    if len(m) < ancho:
        return np.zeros(0)
    cs = np.concatenate([[0.0], np.cumsum(m)])
    k = np.arange(0, len(m) - ancho + 1, salto)
    return (cs[k + ancho] - cs[k]) / ancho


def mascara_sub(voz, n_sub: int) -> np.ndarray:
    """Fracción de habla de cada sub-bloque de 100 ms."""
    out = np.zeros(n_sub)
    for a, b in voz.frases:
        i0, i1 = a / 0.1, b / 0.1
        k0, k1 = int(np.floor(i0)), int(np.ceil(i1))
        for k in range(max(0, k0), min(n_sub, k1)):
            out[k] += max(0.0, min(k + 1, i1) - max(k, i0))
    return np.clip(out, 0, 1)


# ======================================================== niveles por bloque ==
@dataclass
class Bloque:
    """Una sección de una canción dentro de un tramo: recibe una ganancia propia."""
    tramo: int
    seccion: str
    cancion: object
    rangos: list = field(default_factory=list)      # [(t0, t1)] en la línea de tiempo
    mapas: list = field(default_factory=list)       # [(t0, t1, off)]: fuente = línea de tiempo − off
    fuente: tuple = (0.0, 0.0)                      # la sección en la canción (s)
    rel_estimado: float | None = None               # cama − voz estimado bajo la voz (sin ganancia)
    nivel_db: float = 0.0                           # nivel_db del tramo (para el techo de la guardia)
    metodo: str = ""                                # cómo se estimó (bajo_voz | seccion)
    l_entero: float | None = None                   # LUFS de la sección sin ducking (fuente)
    l_duck: float | None = None                     # LUFS con el ducking pleno (fuente)
    l_voz: float | None = None                      # LUFS de la voz mientras suena el bloque
    objetivo_lu: float = 0.0                        # cama − voz buscado (bajo voz)
    ganancia_db: float = 0.0
    medido_lu: float | None = None
    correccion_db: float = 0.0
    ventanas: int = 0

    @property
    def clave(self):
        return (self.tramo, self.seccion)

    @property
    def inicio(self):
        return min(a for a, _ in self.rangos)

    @property
    def fin(self):
        return max(b for _, b in self.rangos)

    @property
    def duracion(self):
        return sum(b - a for a, b in self.rangos)


def construir_bloques(edl) -> list[Bloque]:
    bloques: dict = {}
    for tre in edl.tramos:
        k = tre.tramo.indice
        for cr in tre.corridas:
            c = cr.cancion
            for b in range(cr.c0, cr.c1 + 1):
                s = c.seccion_de(b)
                bl = bloques.get((k, s.nombre))
                if bl is None:
                    bl = Bloque(k, s.nombre, c, fuente=(c.t(s.c0), c.t(s.c1 + 1)))
                    bloques[(k, s.nombre)] = bl
                bl.rangos.append((cr.tl(b), cr.tl(b + 1)))
                bl.mapas.append((cr.tl(b), cr.tl(b + 1), cr.off))
    return list(bloques.values())


def potencias_control(ctrl, n_sub: int, plan) -> dict:
    """Ganancias de potencia medias por sub-bloque de 100 ms que el ducking, el realce y la EQ
    dinámica aplican a cada stem (para proyectar la sonoridad sin renderizar)."""
    from .ducking import PASO
    paso = SUB // PASO                     # puntos de control por sub-bloque (100)
    out = {}
    pd = plan.parametros["ducking"]
    eq_stems = set(pd["eq"]["stems"]) if pd["activo"] and pd["eq"]["activo"] else set()
    def por_sub(db):
        v = 10 ** (np.asarray(db, np.float64) / 10)
        n = min(len(v) // paso, n_sub)
        r = np.ones(n_sub)
        r[:n] = v[: n * paso].reshape(n, paso).mean(axis=1)
        return r
    realce = por_sub(ctrl.realce)
    d_sub = np.zeros(n_sub)
    n = min(len(ctrl.d) // paso, n_sub)
    d_sub[:n] = ctrl.d[: n * paso].reshape(n, paso).mean(axis=1)
    for s in STEMS:
        out[s] = por_sub(ctrl.duck_db(s)) * realce
    out["_d"] = d_sub
    out["_eq_stems"] = eq_stems
    return out


def estimar(bloques: list[Bloque], plan, voz, p_voz_sub: np.ndarray | None, mask_sub: np.ndarray | None,
            pot_ctrl: dict | None = None, excluir=()):
    """Ganancia inicial de cada bloque: lleva la sonoridad de la sección (con el ducking pleno)
    a voz + objetivo, donde objetivo = musica_bajo_voz_lu + nivel_db del tramo + una parte de
    la diferencia natural de la sección respecto del resto del tramo (conservar_dinamica),
    acotada a ±ventana_lu."""
    P = plan.parametros
    pn = P["niveles"]
    prof = P["ducking"]["profundidad_db"] if P["ducking"]["activo"] else {s: 0.0 for s in STEMS}
    lv_global = voz.lufs_mezcla if voz is not None and voz.lufs_mezcla is not None else -16.0
    for bl in bloques:
        tr = plan.tramos[bl.tramo]
        c = bl.cancion
        pot = c.potencias_k()
        a, b = int(round(bl.fuente[0] / 0.1)), int(round(bl.fuente[1] / 0.1))
        duck = tr.ducking
        pr = dict(prof)
        if duck is False:
            pr = {s: 0.0 for s in STEMS}
        elif isinstance(duck, dict):
            pr.update(duck.get("profundidad_db", {}))
        idx_sec = np.arange(a, min(b, len(pot["armonia"])))
        amp_ent = {s: 10 ** (o / 20) for s in STEMS if (o := tr.stems.get(s, 0.0)) is not None}
        amp_duck = {s: g * 10 ** (pr.get(s, 0.0) / 20) for s, g in amp_ent.items()}
        p_ent = c.potencia_mezcla(amp_ent, idx_sec)
        p_duck = c.potencia_mezcla(amp_duck, idx_sec)
        bl.l_entero = integrado(p_ent)
        bl.l_duck = integrado(p_duck)
        # Estimación con la misma métrica que la medición: se "proyecta" la potencia K de la
        # fuente (con el ducking pleno) sobre la línea de tiempo y se toma la mediana de
        # (cama − voz) en ventanas de 3 s con ≥ 70 % de habla, solo dentro del bloque.
        bl.l_voz, bl.rel_estimado, bl.metodo = None, None, "seccion"
        if p_voz_sub is not None and mask_sub is not None:
            T = len(p_voz_sub)
            pd = np.full(T, np.nan)
            for (t0, t1, off) in bl.mapas:
                kk = np.arange(int(np.ceil(t0 / 0.1 - 0.5)), int(np.ceil(t1 / 0.1 - 0.5)))
                kk = kk[(kk >= 0) & (kk < T)]
                if len(kk) == 0:
                    continue
                ks = np.clip(np.round(kk - off / 0.1).astype(np.int64), 0, len(pot["armonia"]) - 1)
                amp = {}
                for s, g in amp_ent.items():
                    if pot_ctrl is not None:      # la curva de ducking real (con pausas y realce)
                        w = pot_ctrl[s][kk]
                        if s in pot_ctrl["_eq_stems"]:
                            fe = c.factor_eq(s, plan.parametros["ducking"]["eq"])
                            w = w * (1.0 - (1.0 - fe) * pot_ctrl["_d"][kk])
                    else:
                        w = 10 ** (pr.get(s, 0.0) / 10)
                    amp[s] = g * np.sqrt(w)
                acc = c.potencia_mezcla(amp, ks)
                pd[kk] = acc
            if np.isfinite(pd).sum() >= CORTO:
                # misma métrica que la medición: cama − voz con compuerta de habla, solo dentro del
                # bloque y lejos de las transiciones
                m = (np.asarray(mask_sub[:T]) >= 0.5) & np.isfinite(pd)
                k = np.ones(CORTO)
                num_c = np.convolve(np.where(m, pd, 0.0), k, mode="same")
                num_v = np.convolve(np.where(m, p_voz_sub[:T], 0.0), k, mode="same")
                den = np.convolve(m.astype(np.float64), k, mode="same")
                centros = (np.arange(T) + 0.5) * 0.1
                ok = (den >= 10) & (num_c > 0) & (num_v > 0) & np.isfinite(pd)
                for (ea, eb) in excluir:
                    ok &= ~((centros + 1.5 > ea) & (centros - 1.5 < eb))
                ok[np.arange(T) % 5 != 0] = False       # una ventana cada 0,5 s (como el informe)
                if ok.sum() >= 3:
                    bl.rel_estimado = float(np.median(10 * np.log10(num_c[ok] / num_v[ok])))
                    bl.l_voz = float(np.median(_lk(num_v[ok] / den[ok])))
                    bl.metodo = "bajo_voz"
        if bl.l_voz is None:
            bl.l_voz = lv_global
    # objetivo con parte de la dinámica natural de cada sección dentro de su tramo
    for k in {bl.tramo for bl in bloques}:
        delt = [bl for bl in bloques if bl.tramo == k and bl.l_entero is not None]
        if not delt:
            continue
        pesos = np.array([bl.duracion for bl in delt])
        pot_media = np.sum(pesos * 10 ** (np.array([bl.l_entero for bl in delt]) / 10)) / pesos.sum()
        l_med = 10 * np.log10(pot_media)
        tr = plan.tramos[k]
        for bl in delt:
            dif = np.clip(pn["conservar_dinamica"] * (bl.l_entero - l_med), -pn["ventana_lu"], pn["ventana_lu"])
            bl.objetivo_lu = pn["musica_bajo_voz_lu"] + tr.nivel_db + float(dif)
            bl.nivel_db = tr.nivel_db
            if bl.rel_estimado is not None:
                g = bl.objetivo_lu - bl.rel_estimado
            else:
                ld = bl.l_duck if bl.l_duck is not None else -60.0
                g = bl.l_voz + bl.objetivo_lu - ld
            bl.ganancia_db = float(np.clip(g, -40.0, 30.0))
    for bl in bloques:
        if bl.l_entero is None:      # sección en silencio
            bl.objetivo_lu = pn["musica_bajo_voz_lu"] + plan.tramos[bl.tramo].nivel_db
            bl.ganancia_db = 0.0
    return bloques


def medir_relativo(p_cama: np.ndarray, p_voz: np.ndarray, mask_sub: np.ndarray, salto: int = 5,
                   min_habla: float = 0.7):
    """Cama − voz en LUFS de corto plazo (3 s, salto 0,5 s) en ventanas con ≥ 70 % de habla.
    Devuelve (centros_s, relativo_lu, fraccion_habla) de TODAS las ventanas (NaN donde no aplica)."""
    n = min(len(p_cama), len(p_voz), len(mask_sub))
    t, lc = corto_plazo(p_cama[:n], salto)
    _, lv = corto_plazo(p_voz[:n], salto)
    fr = fraccion_ventanas(mask_sub[:n], CORTO, salto)[:len(t)]
    rel = np.where((fr >= min_habla) & (lv > -60), lc - lv, np.nan)
    return t, rel, fr, lc, lv


def ventanas_del_bloque(bl: Bloque, t: np.ndarray, excluir=()) -> np.ndarray:
    """Ventanas de 3 s (centros t) que caen dentro del bloque y no tocan una transición entre
    tramos (ahí suena también el otro tramo: la medición no sería de este bloque)."""
    m = np.zeros(len(t), bool)
    for (a, b) in bl.rangos:
        m |= (t >= a) & (t < b)
    for (a, b) in excluir:
        m &= ~((t + 1.5 > a) & (t - 1.5 < b))
    return m


def corregir(bloques: list[Bloque], t, rel, tol: float, excluir=()) -> bool:
    """Ajusta la ganancia de cada bloque con la mediana medida (cama − voz). True si cambió algo."""
    cambio = False
    for bl in bloques:
        m = ventanas_del_bloque(bl, t, excluir)
        vals = rel[m & np.isfinite(rel)]
        bl.ventanas = int(len(vals))
        if len(vals) >= 3:
            bl.medido_lu = float(np.median(vals))
            d = bl.objetivo_lu - bl.medido_lu
            if abs(d) > tol:
                bl.correccion_db += d
                bl.ganancia_db += d
                cambio = True
    return cambio


def relativo_en_habla(p_cama: np.ndarray, p_voz: np.ndarray, mask_sub: np.ndarray, ancho: int = CORTO,
                      min_habla: int = 10):
    """Cama − voz (LU) en ventanas de 3 s centradas en cada sub-bloque, contando SOLO los
    sub-bloques con habla (compuerta de habla): mide la música bajo la voz sin mezclar la subida
    de las pausas. NaN donde hay menos de `min_habla` sub-bloques (1 s) de habla en la ventana."""
    n = min(len(p_cama), len(p_voz), len(mask_sub))
    m = (np.asarray(mask_sub[:n]) >= 0.5).astype(np.float64)
    k = np.ones(ancho)
    num_c = np.convolve(m * p_cama[:n], k, mode="same")
    num_v = np.convolve(m * p_voz[:n], k, mode="same")
    den = np.convolve(m, k, mode="same")
    with np.errstate(divide="ignore", invalid="ignore"):
        rel = 10 * np.log10(num_c / num_v)
    rel[(den < min_habla) | (num_v <= 0) | (num_c <= 0)] = np.nan
    return rel


def tipo_region(voz, n: int) -> np.ndarray:
    """Por sub-bloque de 100 ms: 0 habla, 1 pausa entre frases, 2 intro (antes de la primera
    palabra), 3 final (después de la última)."""
    t = (np.arange(n) + 0.5) * 0.1
    tipo = np.ones(n, np.int8)
    if not voz.frases:
        tipo[:] = 2
        return tipo
    tipo[t < voz.frases[0][0]] = 2
    tipo[t >= voz.frases[-1][1]] = 3
    for a, b in voz.frases:
        tipo[(t >= a) & (t < b)] = 0
    return tipo


def techos(p_cama, p_voz, mask_sub, voz, bloques: list, P: dict, l_voz: float, gan_master: float):
    """Reducción (dB por sub-bloque de 100 ms) para que la cama nunca pase sus techos:
      * mientras se habla: cama − voz (con compuerta de habla) ≤ objetivo + nivel del tramo + ventana;
      * en pausas: sonoridad de corto plazo de la cama ≤ voz − |techo_pausas_lu|;
      * intro y final sin voz: ≤ techo_sin_voz_lufs en la mezcla final (con la ganancia del master).
    Se sostiene 1 s y se suaviza (rampas de ~0,5 s). Devuelve (reducción, exceso_por_tipo)."""
    pn = P["niveles"]
    n = min(len(p_cama), len(p_voz), len(mask_sub))
    # 1) bajo la voz
    rel = relativo_en_habla(p_cama, p_voz, mask_sub)[:n]
    techo = np.full(n, pn["musica_bajo_voz_lu"] + pn["ventana_lu"])
    for bl in bloques:
        for (a, b) in bl.rangos:
            techo[max(0, int(a / 0.1)):max(0, int(b / 0.1))] = \
                pn["musica_bajo_voz_lu"] + bl.nivel_db + pn["ventana_lu"]
    tipo = tipo_region(voz, n)
    # solo donde se habla: en una pausa la música tiene permiso para subir (lo controla el techo
    # de pausas); medirla con el habla de los bordes la bajaría justo donde debe respirar
    exc_habla = np.clip(np.nan_to_num(rel - techo[:len(rel)], nan=0.0), 0.0, None)
    exc_habla = np.where(tipo[:len(exc_habla)] == 0, exc_habla, 0.0)
    # 2) sin voz: sonoridad de corto plazo (3 s centrada) de la cama
    k = np.ones(CORTO) / CORTO
    st = _lk(np.convolve(p_cama[:n], k, mode="same"))
    techo_sv = np.full(n, np.inf)
    techo_sv[tipo == 1] = l_voz + pn["techo_pausas_lu"]
    techo_sv[(tipo == 2) | (tipo == 3)] = pn["techo_sin_voz_lufs"] - gan_master - 0.3
    exc_sv = np.where(tipo > 0, np.clip(st - techo_sv, 0.0, None), 0.0)
    exceso = np.clip(np.maximum(exc_habla, exc_sv), 0.0, pn["guardia_max_db"])
    resumen = {"bajo_voz_max_db": round(float(exc_habla.max()), 2) if len(exc_habla) else 0.0,
               "pausas_max_db": round(float(exc_sv[tipo == 1].max()), 2) if (tipo == 1).any() else 0.0,
               "sin_voz_max_db": round(float(exc_sv[tipo >= 2].max()), 2) if (tipo >= 2).any() else 0.0}
    if exceso.max() <= 0.05:
        return np.zeros(n), resumen
    from scipy.ndimage import maximum_filter1d, uniform_filter1d
    red = maximum_filter1d(exceso, size=11, mode="constant")
    red = uniform_filter1d(uniform_filter1d(red, size=7, mode="constant"), size=7, mode="constant")
    return np.clip(red, 0.0, pn["guardia_max_db"]), resumen


class CurvaTramo:
    """Ganancia (dB) de un tramo en el tiempo: constante por bloque, con una rampa coseno de
    `rampa_tiempos` que termina `guarda` antes del downbeat donde cambia la sección."""

    def __init__(self, tre, bloques: dict, rampa_tiempos: float, guarda: float):
        k = tre.tramo.indice
        barras = []
        for cr in tre.corridas:
            for b in range(cr.c0, cr.c1 + 1):
                barras.append((cr.tl(b), cr.cancion.seccion_de(b).nombre, cr.pulso(b)))
        barras.sort()
        self.g0 = bloques[(k, barras[0][1])].ganancia_db if barras else 0.0
        self.cambios = []
        prev = barras[0][1] if barras else None
        for (t, sec, pul) in barras[1:]:
            if sec != prev:
                g_prev = bloques[(k, prev)].ganancia_db
                g_new = bloques[(k, sec)].ganancia_db
                if abs(g_new - g_prev) > 1e-6:
                    t1 = t - guarda
                    self.cambios.append((t1 - rampa_tiempos * pul, t1, g_new - g_prev))
                prev = sec

    def __call__(self, t: np.ndarray) -> np.ndarray:
        g = np.full(np.shape(t), self.g0, dtype=np.float64)
        for (a, b, d) in self.cambios:
            x = np.clip((t - a) / max(1e-6, b - a), 0.0, 1.0)
            g += d * (0.5 - 0.5 * np.cos(np.pi * x))
        return g
