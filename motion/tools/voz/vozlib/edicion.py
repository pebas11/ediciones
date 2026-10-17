"""Propuesta de edición (EDL): silencios, muletillas, repeticiones, arranques en falso y bloopers.

Modelo de cortes (para que cualquier combinación de cortes aplicados quede natural):
    - Cada corte es un intervalo [inicio, fin) sobre la línea de tiempo de voz_limpia.wav.
    - Alrededor de cada palabra que queda se respetan márgenes: `margen_pre` antes de su
      inicio (constante) y `margen_post(palabra)` después de su fin (según la puntuación).
    - La pausa que queda en cualquier unión = margen_post(última palabra que queda) +
      margen_pre, es decir, la pausa objetivo (0,28 s; 0,32 s tras coma; 0,45 s tras punto).
    Como todos los cortes usan los mismos márgenes, la unión de cortes solapados (un silencio
    adentro de un blooper, una muletilla pegada a un arranque en falso) da el mismo resultado
    que si se hubieran calculado juntos.
"""

from __future__ import annotations

import bisect
import re

import numpy as np
from rapidfuzz import fuzz

from . import dsp, transcribir, util

PARAMS = {
    "umbral_pausa_s": 0.45,  # pausas más largas se acortan
    "pausa_objetivo_s": 0.28,  # dentro de la oración
    "pausa_coma_s": 0.32,
    "pausa_fin_oracion_s": 0.45,
    "margen_pre_s": 0.15,  # antes de cada palabra que queda (ataque, inspiración)
    "inicio_s": 0.30,  # silencio que se deja al principio
    "final_s": 0.50,  # y al final
    "confianza_min_aplicar": 0.75,
    "ventana_repeticion_s": 30.0,
    "similitud_min": 85.0,  # rapidfuzz ratio para arranques/repeticiones
    "similitud_min_blooper": 75.0,  # más tolerante si hay un marcador de blooper
    "fundido_ms": 20,
}

FIN_ORACION = re.compile(r"[.?!…]+[\"'”»)\]]*$")
COMA = re.compile(r"[,;:]+[\"'”»)\]]*$")
SUSPENSIVOS = re.compile(r"(\.\.\.|…)[\"'”»)\]]*$")

# muletilla (forma colapsada: letras repetidas → una) → confianza base
MULETILLAS = {"eh": 0.9, "e": 0.55, "em": 0.9, "ehm": 0.92, "m": 0.9, "hm": 0.85, "mh": 0.85,
              "mhm": 0.8, "uh": 0.85, "um": 0.85, "ah": 0.45, "este": 0.3}
CONECTORES = {"y", "que", "pero", "entonces", "bueno", "sea", "porque", "como", "digamos", "pues",
              "tipo", "o"}
FUNCIONALES = {"el", "la", "los", "las", "un", "una", "unos", "unas", "de", "del", "en", "a", "al",
               "y", "o", "que", "con", "por", "para", "se", "lo", "le", "les", "me", "te", "nos",
               "es", "su", "sus", "mi", "mis", "tu", "tus", "yo", "como", "pero", "si", "cuando",
               "porque", "este", "esta", "eso", "esto", "ese", "esa", "hay", "son", "fue", "era"}
ENFATICAS = {"no", "si", "muy", "mas", "ya", "nunca", "siempre", "chau", "dale", "bien", "nada",
             "todo", "claro", "obvio", "re"}

# marcadores de blooper: (secuencia normalizada, peso)
MARCADORES = [
    (("me", "equivoque"), 0.95), (("me", "confundi"), 0.85), (("me", "trabe"), 0.95),
    (("me", "trabo"), 0.9), (("arranco", "de", "nuevo"), 0.95), (("empiezo", "de", "nuevo"), 0.95),
    (("vamos", "de", "nuevo"), 0.9), (("lo", "hago", "de", "nuevo"), 0.95),
    (("la", "hago", "de", "nuevo"), 0.95), (("de", "nuevo"), 0.75), (("otra", "vez"), 0.7),
    (("de", "vuelta"), 0.65), (("la", "repito"), 0.9), (("lo", "repito"), 0.9),
    (("repito",), 0.55), (("corto",), 0.75), (("corta",), 0.6), (("cortamos",), 0.6),
    (("corte",), 0.5), (("perdon",), 0.75), (("perdona",), 0.6), (("disculpen",), 0.6),
    (("no", "no", "no"), 0.85), (("a", "ver"), 0.45), (("ay",), 0.5), (("uy",), 0.5),
    (("ups",), 0.6), (("mierda",), 0.6), (("puta",), 0.6), (("carajo",), 0.6),
    (("la", "puta"), 0.7), (("que", "boludo"), 0.7), (("espera",), 0.45), (("pera",), 0.45),
    (("esperen",), 0.5), (("risas",), 0.8), (("risa",), 0.7), (("tos",), 0.7), (("tose",), 0.7),
]
RISA = re.compile(r"^(ja|je|ji)+j?$")

TIPOS_CONTENIDO = ("muletilla", "repeticion", "arranque_falso", "blooper", "ruido",
                   "sonido_sin_texto", "manual")


def colapsar(norm: str) -> str:
    return re.sub(r"(.)\1+", r"\1", norm)


# ----------------------------------------------------------------------------
# Utilidades sobre la lista de palabras
# ----------------------------------------------------------------------------


class Palabras:
    """Copia de trabajo de las palabras (no modifica la transcripción original)."""

    def __init__(self, palabras: list[dict], dur: float):
        self.p = []
        for k, w in enumerate(palabras):
            c = dict(w)
            c.setdefault("i_orig", w.get("i", k))
            c["i"] = k
            c.setdefault("norm", transcribir.normalizar(c["texto"]))
            c["col"] = colapsar(c["norm"])
            self.p.append(c)
        self.n = len(self.p)
        self.dur = dur
        self.inicios_t = [w["inicio"] for w in self.p]

    def gap_antes(self, k: int) -> float:
        return self.p[k]["inicio"] - self.p[k - 1]["fin"] if k > 0 else self.p[k]["inicio"]

    def gap_despues(self, k: int) -> float:
        return (self.p[k + 1]["inicio"] - self.p[k]["fin"]) if k + 1 < self.n else \
            self.dur - self.p[k]["fin"]

    def puntuacion(self, k: int) -> str:
        t = self.p[k]["texto"]
        if FIN_ORACION.search(t):
            return "fin"
        if COMA.search(t):
            return "coma"
        return ""

    def texto(self, a: int, b: int) -> str:
        return " ".join(self.p[k]["texto"] for k in range(max(a, 0), min(b, self.n - 1) + 1))

    def contexto(self, a: int, b: int, ancho: int = 8, marca: str | None = None) -> str:
        """Texto de las palabras a..b entre ⟦ ⟧ con `ancho` palabras de contexto a cada lado.
        Con b = a − 1 (rango vacío) sirve para marcar un punto entre dos palabras."""
        izq = self.texto(a - ancho, a - 1) if a > 0 else ""
        der = self.texto(b + 1, b + ancho) if b + 1 < self.n else ""
        medio = marca if marca is not None else self.texto(a, b)
        pre = "…" if a - ancho > 0 else ""
        post = "…" if b + ancho < self.n - 1 else ""
        return f"{pre}{izq} ⟦{medio}⟧ {der}{post}".strip()

    def contexto_punto(self, k_prev: int | None, marca: str) -> str:
        """Contexto para algo que está entre la palabra k_prev y la siguiente."""
        a = 0 if k_prev is None else k_prev + 1
        return self.contexto(a, a - 1, marca=marca)


def margen_post(P: Palabras, k: int, prm: dict) -> float:
    pun = P.puntuacion(k)
    total = {"fin": prm["pausa_fin_oracion_s"], "coma": prm["pausa_coma_s"]}.get(pun, prm["pausa_objetivo_s"])
    return max(0.05, total - prm["margen_pre_s"])


def frases(P: Palabras) -> list[tuple[int, int]]:
    res, i0 = [], 0
    for k in range(P.n - 1):
        gap = P.gap_despues(k)
        pun = P.puntuacion(k)
        if pun == "fin" or gap >= 0.30 or (pun == "coma" and gap >= 0.12):
            res.append((i0, k))
            i0 = k + 1
    if P.n:
        res.append((i0, P.n - 1))
    return res


# ----------------------------------------------------------------------------
# Detectores
# ----------------------------------------------------------------------------


def confianza_muletilla(P: Palabras, k: int) -> float:
    w = P.p[k]
    c = w["col"]
    if c not in MULETILLAS:
        return 0.0
    base = MULETILLAS[c]
    texto = w["texto"]
    pun_despues = bool(re.search(r"[,.…;:!?]+[\"'”»)\]]*$", texto))
    gp, gn = P.gap_antes(k), P.gap_despues(k)
    prev_pun = P.puntuacion(k - 1) if k > 0 else "fin"
    dur = w["fin"] - w["inicio"]
    if c == "este":
        if SUSPENSIVOS.search(texto) or (pun_despues and gn >= 0.15) or gn >= 0.30:
            base += 0.35
        elif pun_despues:
            base += 0.2
        if dur >= 0.40:
            base += 0.15
        if gp >= 0.2 or prev_pun or (k > 0 and (P.p[k - 1]["col"] in CONECTORES or
                                                P.p[k - 1]["col"] in MULETILLAS)):
            base += 0.15
        if k + 1 < P.n and not pun_despues and gn < 0.12:
            base -= 0.35  # "este video": demostrativo
    else:
        if texto.rstrip("\"'”»)]").endswith("?"):
            base -= 0.4  # "¿eh?": pregunta de cierre, no muletilla
        aislada_izq = gp >= 0.12 or bool(prev_pun)
        aislada_der = gn >= 0.12 or pun_despues
        if aislada_izq and aislada_der:
            base += 0.06
        if c in ("e", "ah") and not pun_despues and gn < 0.1 and gp < 0.1:
            base -= 0.3  # "e" conjunción ("padres e hijos")
        if c == "e" and pun_despues and aislada_izq:
            base += 0.25  # "E." suelto: así transcribe "eh" el modelo medium
    return float(min(max(base, 0.0), 0.98))


def buscar_marcadores(P: Palabras, a: int, b: int) -> list[tuple[int, int, float, str]]:
    """Marcadores de blooper dentro de las palabras a..b (inclusive)."""
    encontrados = []
    cols = [P.p[k]["col"] for k in range(a, b + 1)]
    norms = [P.p[k]["norm"] for k in range(a, b + 1)]
    k = 0
    while k < len(norms):
        mejor = None
        for seq, peso in MARCADORES:
            L = len(seq)
            if tuple(norms[k : k + L]) == seq or tuple(cols[k : k + L]) == seq:
                if mejor is None or L > len(mejor[0]):
                    mejor = (seq, peso)
        if mejor is None and RISA.match(norms[k] or "x") and len(norms[k]) >= 4:
            mejor = (("risa",), 0.6)
        if mejor:
            L = len(mejor[0])
            encontrados.append((a + k, a + k + L - 1, mejor[1], " ".join(mejor[0])))
            k += L
        else:
            k += 1
    return encontrados


def _sim_prefijo(sA: str, palabras_B: list[str], nA: int) -> float:
    if not palabras_B:
        return 0.0
    sims = []
    for m in (nA - 1, nA, nA + 1):
        if 1 <= m <= len(palabras_B):
            sims.append(fuzz.ratio(sA, " ".join(palabras_B[:m])))
    sB = " ".join(palabras_B)
    sims.append(fuzz.ratio(sA, sB[: len(sA)]))
    return float(max(sims))


class Detector:
    def __init__(self, P: Palabras, prm: dict):
        self.P = P
        self.prm = prm
        n = P.n
        self.conf_mul = [confianza_muletilla(P, k) for k in range(n)]
        self.es_marcador = [False] * n
        self.marcadores = buscar_marcadores(P, 0, n - 1) if n else []
        for m0, m1, _, _ in self.marcadores:
            for k in range(m0, m1 + 1):
                self.es_marcador[k] = True
        self.contenido = [k for k in range(n)
                          if self.conf_mul[k] < 0.5 and not self.es_marcador[k]]
        self.pos_cont = {k: idx for idx, k in enumerate(self.contenido)}
        self.inicios = [k for k in self.contenido if self._es_inicio_clausula(k)]
        self.inicios_t = [P.p[k]["inicio"] for k in self.inicios]
        self.fr = frases(P)
        self.frase_de = {}
        for fi, (a, b) in enumerate(self.fr):
            for k in range(a, b + 1):
                self.frase_de[k] = fi

    def _es_inicio_clausula(self, k: int) -> bool:
        if k == 0:
            return True
        P = self.P
        if P.gap_antes(k) >= 0.12 or P.puntuacion(k - 1):
            return True
        return self.conf_mul[k - 1] >= 0.5 or self.es_marcador[k - 1]

    def _contenido_entre(self, a: int, b: int) -> list[int]:
        """Índices de palabras de contenido en [a, b)."""
        lo = bisect.bisect_left(self.contenido, a)
        hi = bisect.bisect_left(self.contenido, b)
        return self.contenido[lo:hi]

    def _contenido_desde(self, j: int, maximo: int) -> list[int]:
        lo = bisect.bisect_left(self.contenido, j)
        return self.contenido[lo : lo + maximo]

    def _clausula_desde(self, j: int) -> list[int]:
        """Palabras de contenido desde j hasta el fin de su oración (o pausa ≥ 0,6 s)."""
        P = self.P
        res = []
        for k in self._contenido_desde(j, 60):
            if res and P.gap_antes(k) >= 0.6:
                break
            res.append(k)
            if P.puntuacion(k) == "fin":
                break
        return res

    def _toma_previa(self, limite: int, j: int, sim_min: float) -> tuple[int, list, float] | None:
        """Busca el inicio de cláusula i < limite más temprano (dentro de la ventana) tal que
        TODO el contenido entre i y `limite` coincide con el comienzo de lo que sigue desde j."""
        P, prm = self.P, self.prm
        t_lim = P.p[limite]["inicio"] if limite < P.n else P.dur
        desde = bisect.bisect_left(self.inicios_t, t_lim - prm["ventana_repeticion_s"])
        for idx in range(desde, len(self.inicios)):
            i = self.inicios[idx]
            if i >= limite:
                break
            A = self._contenido_entre(i, limite)
            if not A or len(A) > 25:
                continue
            sA = " ".join(P.p[k]["norm"] for k in A)
            if len(sA.replace(" ", "")) < 5:
                continue
            B = self._contenido_desde(j, len(A) + 4)
            sim = _sim_prefijo(sA, [P.p[k]["norm"] for k in B], len(A))
            if sim >= sim_min:
                return i, A, sim
        return None

    # --- muletillas ---------------------------------------------------------
    def muletillas(self) -> list[dict]:
        cortes = []
        umbral = self.prm["confianza_min_aplicar"]
        for k in range(self.P.n):
            c = round(self.conf_mul[k], 2)
            if c >= 0.35:
                w = self.P.p[k]
                if w["col"] == "este":
                    detalle = (" seguido de pausa: muletilla, no demostrativo" if c >= umbral
                               else " (¿muletilla o demostrativo? revisar)")
                else:
                    detalle = " aislada" if c >= umbral else " (dudosa, revisar)"
                cortes.append({"tipo": "muletilla", "palabras": [k, k], "confianza": c,
                               "motivo": f"Muletilla «{w['texto']}»{detalle}"})
        return cortes

    # --- arranques en falso y repeticiones ---------------------------------
    def reinicios(self) -> list[dict]:
        P, prm = self.P, self.prm
        cortes = []
        for j in self.inicios:
            r = self._toma_previa(j, j, prm["similitud_min"])
            if r is None:
                continue
            i, A, sim = r
            clausula_B = self._clausula_desde(j)
            prefijo_estricto = len(clausula_B) >= len(A) + 2
            conf = 0.55 + 0.4 * (sim - 85) / 15
            entre = range(A[-1] + 1, j)
            vacila = P.gap_antes(j) >= 0.4 or any(self.conf_mul[k] >= 0.5 or self.es_marcador[k]
                                                  for k in entre)
            if len(A) == 1:
                # Una sola palabra repetida ("Aumentó. Aumentó de una manera…") es muchas veces
                # un recurso del texto: sin vacilación entre medio, no llega al umbral.
                conf -= 0.3
            else:
                if len(A) >= 3:
                    conf += 0.05
                if prefijo_estricto:
                    conf += 0.15
            if vacila:
                conf += 0.1
            if not prefijo_estricto and len(A) <= 3:
                conf -= 0.2  # "¡Es increíble! ¡Es increíble!" puede ser énfasis
            conf = float(min(max(conf, 0.05), 0.97))
            tipo = "arranque_falso" if prefijo_estricto else "repeticion"
            motivo = (f"{'Arranque en falso' if prefijo_estricto else 'Frase repetida'}: "
                      f"«{P.texto(i, j - 1)}» se retoma enseguida (similitud {sim:.0f} %). "
                      "Se queda la última toma completa.")
            cortes.append({"tipo": tipo, "palabras": [i, j - 1], "confianza": round(conf, 2),
                           "motivo": motivo, "similitud": round(sim, 1)})
        return cortes

    # --- tartamudeos ("la la idea") ----------------------------------------
    def tartamudeos(self) -> list[dict]:
        P = self.P
        cortes = []
        k = 0
        while k < P.n:
            hecho = False
            for L in (3, 2, 1):
                if k + 2 * L > P.n:
                    continue
                a = [P.p[q]["norm"] for q in range(k, k + L)]
                b = [P.p[q]["norm"] for q in range(k + L, k + 2 * L)]
                if a != b or not all(a):
                    continue
                if any(P.gap_despues(q) > 0.8 for q in range(k, k + 2 * L - 1)):
                    continue
                if P.puntuacion(k + L - 1) == "fin":
                    continue  # "...lo que es. Es decir": dos oraciones, no tartamudeo
                if a[0] in ENFATICAS or (L == 1 and a[0] not in FUNCIONALES):
                    continue
                conf = 0.8 if L == 1 else 0.88
                if P.gap_despues(k + L - 1) >= 0.15:
                    conf += 0.07
                cortes.append({"tipo": "repeticion", "palabras": [k, k + L - 1],
                               "confianza": round(conf, 2),
                               "motivo": f"Repetición pegada: «{P.texto(k, k + 2 * L - 1)}»"})
                k += L
                hecho = True
                break
            if not hecho:
                k += 1
        return cortes

    # --- bloopers ------------------------------------------------------------
    def _grupos_marcadores(self) -> list[tuple[int, int, list]]:
        """Corridas de palabras consecutivas que son marcadores o muletillas (con ≥ 1 marcador)."""
        P = self.P
        grupos = []
        k = 0
        while k < P.n:
            if self.es_marcador[k]:
                a = k
                while a > 0 and self.conf_mul[a - 1] >= 0.5 and P.gap_antes(a) < 1.0:
                    a -= 1
                b = k
                while b + 1 < P.n and (self.es_marcador[b + 1] or self.conf_mul[b + 1] >= 0.5) \
                        and P.gap_despues(b) < 1.0:
                    b += 1
                ms = [m for m in self.marcadores if a <= m[0] <= b]
                grupos.append((a, b, ms))
                k = b + 1
            else:
                k += 1
        return grupos

    def bloopers(self) -> list[dict]:
        P, prm = self.P, self.prm
        cortes = []
        for a, b, ms in self._grupos_marcadores():
            prob_no = 1.0
            for _, _, peso, _ in ms:
                prob_no *= (1 - peso)
            score = 1 - prob_no
            # aislamiento: palabras de contenido en las frases que contienen al grupo
            fa, fb = self.fr[self.frase_de[a]][0], self.fr[self.frase_de[b]][1]
            otros = [k for k in range(fa, fb + 1) if not (a <= k <= b) and self.conf_mul[k] < 0.5
                     and not self.es_marcador[k]]
            n_otros = len(otros)
            factor = 1.0 if n_otros == 0 else 0.8 if n_otros <= 2 else 0.5 if n_otros <= 5 else 0.25
            if n_otros and a != fa and b != fb:
                factor *= 0.8  # el marcador queda en medio de una frase con contenido
            s = score * factor
            if s < 0.4:
                continue
            nombres = ", ".join(f"«{m[3]}»" for m in ms)
            sig = self._contenido_desde(b + 1, 1)
            j = sig[0] if sig else None
            toma = None
            if j is not None and P.p[j]["inicio"] - P.p[b]["fin"] <= 15:
                toma = self._toma_previa(a, j, prm["similitud_min_blooper"])
            if toma:
                i, A, sim = toma
                conf = min(0.98, 0.45 + 0.5 * s + 0.2 * (sim - 75) / 25)
                cortes.append({
                    "tipo": "blooper", "palabras": [i, j - 1], "confianza": round(conf, 2),
                    "motivo": (f"Blooper: marcador {nombres} y después se retoma la toma "
                               f"«{P.texto(i, a - 1)}» (similitud {sim:.0f} %). Se saca la toma "
                               "fallida completa y se queda la última."),
                    "similitud": round(sim, 1)})
                continue
            conf = 0.8 * s
            cortes.append({
                "tipo": "blooper", "palabras": [a, b], "confianza": round(conf, 2),
                "motivo": f"Marcador de blooper {nombres} sin toma repetida clara: revisar."})
            # toma fallida probable: desde el último inicio de oración hasta el marcador
            ini = a
            while ini > 0 and P.puntuacion(ini - 1) != "fin" and P.gap_antes(ini) < 0.6:
                ini -= 1
            if ini < a:
                cortes.append({
                    "tipo": "blooper", "palabras": [ini, a - 1],
                    "confianza": round(min(0.45, conf * 0.5), 2),
                    "motivo": f"Posible toma fallida antes de {nombres}: revisar."})
        return cortes


# ----------------------------------------------------------------------------
# Sonidos sin transcribir (muletillas que Whisper omitió, toses, risas, golpes)
# ----------------------------------------------------------------------------


def sonidos_sin_texto(P: Palabras, x: np.ndarray, sr: int, act: dict) -> list[dict]:
    m = act["mask"].copy()
    hop = act["hop_s"]
    n = len(m)
    cubierto = np.zeros(n, dtype=bool)
    for w in P.p:
        a = max(0, int((w["inicio"] - 0.06) / hop))
        b = min(n, int((w["fin"] + 0.06) / hop) + 1)
        cubierto[a:b] = True
    libre = m & ~cubierto
    ini, lar = dsp.corridas(libre)
    res = []
    voz_db = act["voz_db"]
    fines = np.array([w["fin"] for w in P.p]) if P.n else np.array([])
    inicios = np.array([w["inicio"] for w in P.p]) if P.n else np.array([])
    for i, l in zip(ini, lar):
        dur = l * hop
        if dur < 0.15:
            continue
        t0, t1 = i * hop, (i + l) * hop
        Lr = act["db"][i : i + l]
        # cola de reverb de la palabra anterior: arranca pegada a un final y solo decae
        if len(fines) and np.any((fines <= t0 + 0.01) & (fines >= t0 - 0.15)):
            if Lr.max() <= Lr[: max(2, l // 8)].max() + 1.5 and Lr[-max(2, l // 8):].mean() <= Lr[0] - 6:
                continue
        # ataque de la palabra siguiente que Whisper dejó afuera: termina pegado y solo sube
        if len(inicios) and np.any((inicios >= t1 - 0.01) & (inicios <= t1 + 0.12)):
            if np.all(np.diff(Lr) > -3.0) and Lr[-1] >= Lr[0] + 6:
                continue
        seg = x[int(t0 * sr) : int(t1 * sr)].astype(np.float64)
        if len(seg) < 256:
            continue
        nivel = float(np.max(act["db"][i : i + l]))
        # sonoridad: autocorrelación normalizada en 80–400 Hz
        s16 = dsp.resample(seg.astype(np.float32), sr, 16000).astype(np.float64)
        s16 = s16 - s16.mean()
        ac = np.correlate(s16, s16, "full")[len(s16) - 1 :]
        ac /= ac[0] + 1e-12
        lo, hi = int(16000 / 400), min(int(16000 / 80), len(ac) - 1)
        sonoro = float(np.max(ac[lo:hi])) if hi > lo else 0.0
        if nivel < voz_db - 30:
            continue  # ruido de fondo: se trata como silencio
        # ataque: cuánto sube el nivel en 10 ms (una tos o un golpe arrancan de golpe; una
        # respiración entra suave)
        ataque = float(np.max(Lr[2:] - Lr[:-2])) if l > 3 else 0.0
        if sonoro >= 0.5:
            tipo, conf = "sonido_sin_texto", 0.5 if dur < 1.0 else 0.3
            motivo = (f"Sonido con voz sin transcribir ({dur:.2f} s): ¿muletilla o palabra que "
                      "Whisper omitió? Revisar antes de sacar.")
        elif ataque <= 12.0 and nivel <= voz_db - 8:
            tipo, conf = "respiracion", 0.0
            motivo = f"Respiración ({dur:.2f} s)"
        else:
            if dur > 1.0:
                continue
            tipo, conf = "ruido", 0.6
            motivo = f"Ruido sin voz ({dur:.2f} s, ataque brusco): ¿tos, golpe, risa? Revisar."
        res.append({"tipo": tipo, "t0": round(t0, 3), "t1": round(t1, 3), "confianza": conf,
                    "motivo": motivo, "sonoridad": round(sonoro, 2), "nivel_db": round(nivel, 1),
                    "ataque_db": round(ataque, 1)})
    return res


# ----------------------------------------------------------------------------
# Armado de la EDL
# ----------------------------------------------------------------------------


def punto_bajo(x: np.ndarray, sr: int, t: float, lo: float, hi: float, radio: float = 0.03) -> float:
    """Mueve t al cuadro de 5 ms con menos energía dentro de [lo, hi] ∩ [t−radio, t+radio]."""
    a = max(lo, t - radio)
    b = min(hi, t + radio)
    if b - a < 0.006:
        return float(min(max(t, lo), hi))
    hop = int(0.0025 * sr)
    win = int(0.005 * sr)
    ia, ib = int(a * sr), int(b * sr)
    seg = x[max(0, ia - win // 2) : ib + win // 2].astype(np.float64)
    if len(seg) < win + hop:
        return float(t)
    c = np.concatenate([[0.0], np.cumsum(seg * seg)])
    starts = np.arange(0, len(seg) - win, hop)
    e = c[starts + win] - c[starts]
    k = int(np.argmin(e + 1e-12 * np.abs(starts - (t * sr - ia))))
    return float((max(0, ia - win // 2) + starts[k] + win // 2) / sr)


def _rango_contenido(P: Palabras, k0: int, k1: int, prm: dict, x, sr) -> tuple[float, float]:
    """Intervalo de corte para quitar las palabras k0..k1 dejando pausas naturales."""
    w0, w1 = P.p[k0], P.p[k1]
    if k0 > 0:
        a = P.p[k0 - 1]
        ini = min(a["fin"] + margen_post(P, k0 - 1, prm), w0["inicio"] - 0.01)
        ini = max(ini, a["fin"] + 0.02)
        lo, hi = a["fin"] + 0.02, w0["inicio"] - 0.005
    else:
        ini = max(0.0, w0["inicio"] - 0.1)
        lo, hi = 0.0, w0["inicio"] - 0.005
    if k1 + 1 < P.n:
        b = P.p[k1 + 1]
        fin = max(b["inicio"] - prm["margen_pre_s"], w1["fin"] + 0.02)
        fin = min(fin, b["inicio"] - 0.02)
        lo2, hi2 = w1["fin"] + 0.005, b["inicio"] - 0.02
    else:
        fin = min(P.dur, w1["fin"] + 0.3)
        lo2, hi2 = w1["fin"] + 0.005, P.dur
    if hi > lo:
        ini = punto_bajo(x, sr, ini, lo, hi)
    if hi2 > lo2:
        fin = punto_bajo(x, sr, fin, lo2, hi2)
    return ini, max(fin, ini + 0.01)


def proponer(palabras: list[dict], x: np.ndarray, sr: int, act: dict | None = None,
             prm: dict | None = None) -> dict:
    prm = {**PARAMS, **(prm or {})}
    dur = len(x) / sr
    validas = [dict(w, i_orig=w.get("i", k)) for k, w in enumerate(palabras)
               if not (w.get("sospecha_alucinacion") and w.get("sin_energia"))]
    P = Palabras(validas, dur)
    act = act or transcribir.mapa_actividad(x, sr)
    det = Detector(P, prm)
    contenido = []
    contenido += det.muletillas()
    contenido += det.bloopers()
    contenido += det.reinicios()
    contenido += det.tartamudeos()

    # deduplicar: mismo rango o casi (IoU de palabras > 0,6) → se queda el de más confianza
    contenido.sort(key=lambda c: (-c["confianza"], c["palabras"][0]))
    finales: list[dict] = []
    for c in contenido:
        a, b = c["palabras"]
        dup = None
        for f in finales:
            fa, fb = f["palabras"]
            inter = max(0, min(b, fb) - max(a, fa) + 1)
            union = max(b, fb) - min(a, fa) + 1
            if inter / union > 0.6 and (c["tipo"] in ("blooper", "repeticion", "arranque_falso")
                                        and f["tipo"] in ("blooper", "repeticion", "arranque_falso")
                                        or c["tipo"] == f["tipo"]):
                dup = f
                break
        if dup:
            if c["motivo"] not in dup["motivo"]:
                dup.setdefault("evidencia_extra", []).append(c["motivo"])
            continue
        finales.append(c)

    cortes = []
    for c in finales:
        a, b = c["palabras"]
        ini, fin = _rango_contenido(P, a, b, prm, x, sr)
        texto = P.texto(a, b)
        cortes.append({
            "tipo": c["tipo"], "inicio": round(ini, 3), "fin": round(fin, 3),
            "aplicar": c["confianza"] >= prm["confianza_min_aplicar"],
            "confianza": c["confianza"], "motivo": c["motivo"], "texto": texto,
            "contexto": P.contexto(a, b),
            "palabras": [P.p[a]["i_orig"], P.p[b]["i_orig"]],
            **({"similitud": c["similitud"]} if "similitud" in c else {}),
            **({"evidencia_extra": c["evidencia_extra"]} if "evidencia_extra" in c else {}),
        })

    # sonidos sin texto: también son anclas para no cortar en medio de ellos
    todos_sonidos = sonidos_sin_texto(P, x, sr, act)
    inicios_pal = [w["inicio"] for w in P.p]
    respiraciones = []
    for s in todos_sonidos:
        if s["tipo"] != "respiracion":
            continue
        # una inspiración corta pegada a la frase que sigue se conserva entera (suena natural);
        # las demás se tratan como silencio
        j = bisect.bisect_left(inicios_pal, s["t1"])
        if s["t1"] - s["t0"] <= 0.6 and j < P.n and inicios_pal[j] - s["t1"] <= 0.3:
            respiraciones.append(s)
    sonidos = [s for s in todos_sonidos if s["tipo"] != "respiracion"]
    for s in sonidos:
        k_prev = max([k for k in range(P.n) if P.p[k]["fin"] <= s["t0"]], default=None)
        k_sig = min([k for k in range(P.n) if P.p[k]["inicio"] >= s["t1"]], default=None)
        lo = P.p[k_prev]["fin"] + 0.02 if k_prev is not None else 0.0
        hi = P.p[k_sig]["inicio"] - 0.02 if k_sig is not None else dur
        ini = max(lo, s["t0"] - 0.08)
        fin = min(hi, s["t1"] + 0.08)
        if k_prev is not None:
            ini = min(ini, max(lo, P.p[k_prev]["fin"] + margen_post(P, k_prev, prm)))
        if k_sig is not None:
            fin = max(fin, min(hi, P.p[k_sig]["inicio"] - prm["margen_pre_s"]))
        ctx = P.contexto_punto(k_prev, f"sonido {s['t1'] - s['t0']:.2f} s") if P.n else ""
        cortes.append({"tipo": s["tipo"], "inicio": round(ini, 3), "fin": round(fin, 3),
                       "aplicar": s["confianza"] >= prm["confianza_min_aplicar"],
                       "confianza": s["confianza"], "motivo": s["motivo"], "texto": "",
                       "contexto": ctx, "palabras": None,
                       "sonido": {"t0": s["t0"], "t1": s["t1"], "sonoridad": s["sonoridad"],
                                  "nivel_db": s["nivel_db"]}})

    # silencios: entre anclas consecutivas (palabras, sonidos y respiraciones pegadas a la voz)
    anclas = [(w["inicio"], w["fin"], ("w", k)) for k, w in enumerate(P.p)]
    anclas += [(s["t0"], s["t1"], ("s", None)) for s in sonidos]
    anclas += [(s["t0"], s["t1"], ("r", None)) for s in respiraciones]
    anclas.sort()
    for (a0, a1, ka), (b0, b1, kb) in zip(anclas, anclas[1:]):
        gap = b0 - a1
        if gap <= prm["umbral_pausa_s"]:
            continue
        post = margen_post(P, ka[1], prm) if ka[0] == "w" else prm["pausa_objetivo_s"] - prm["margen_pre_s"]
        pre = 0.05 if kb[0] == "r" else prm["margen_pre_s"]  # la inspiración ya es la entrada
        ini, fin = a1 + post, b0 - pre
        if fin - ini < 0.04:
            continue
        ini = punto_bajo(x, sr, ini, a1 + 0.05, fin - 0.01)
        fin = punto_bajo(x, sr, fin, ini + 0.01, b0 - min(0.06, pre))
        queda = gap - (fin - ini)
        if ka[0] == "w":
            ctx = P.contexto_punto(ka[1], f"pausa {gap:.2f} s → {queda:.2f} s")
        else:
            k_prev = max([k for k in range(P.n) if P.p[k]["fin"] <= a1], default=None)
            ctx = P.contexto_punto(k_prev, f"pausa {gap:.2f} s → {queda:.2f} s")
        cortes.append({"tipo": "silencio", "inicio": round(ini, 3), "fin": round(fin, 3),
                       "aplicar": True, "confianza": 0.95,
                       "motivo": f"Pausa de {gap:.2f} s acortada a {queda:.2f} s",
                       "texto": "", "contexto": ctx, "palabras": None,
                       "pausa_original_s": round(gap, 3), "pausa_resultante_s": round(queda, 3)})
    # silencio inicial y final
    if anclas:
        primero, ultimo = anclas[0][0], anclas[-1][1]
        if primero > prm["inicio_s"] + 0.1:
            fin = punto_bajo(x, sr, primero - prm["inicio_s"], 0.0, primero - 0.1)
            cortes.append({"tipo": "silencio", "inicio": 0.0, "fin": round(fin, 3), "aplicar": True,
                           "confianza": 0.95, "motivo": f"Silencio inicial de {primero:.2f} s",
                           "texto": "", "contexto": "⟦inicio⟧ " + P.texto(0, 6), "palabras": None,
                           "pausa_original_s": round(primero, 3),
                           "pausa_resultante_s": round(primero - fin, 3)})
        if dur - ultimo > prm["final_s"] + 0.1:
            ini = punto_bajo(x, sr, ultimo + prm["final_s"], ultimo + 0.1, dur)
            cortes.append({"tipo": "silencio", "inicio": round(ini, 3), "fin": round(dur, 3),
                           "aplicar": True, "confianza": 0.95,
                           "motivo": f"Silencio final de {dur - ultimo:.2f} s",
                           "texto": "", "contexto": P.texto(P.n - 6, P.n - 1) + " ⟦final⟧",
                           "palabras": None, "pausa_original_s": round(dur - ultimo, 3),
                           "pausa_resultante_s": round(ini - ultimo, 3)})

    cortes.sort(key=lambda c: (c["inicio"], -c["fin"]))
    for k, c in enumerate(cortes):
        c["id"] = f"c{k + 1:03d}"
        c["duracion"] = round(c["fin"] - c["inicio"], 3)
    marcar_contenidos(cortes)
    orden = ["id", "tipo", "inicio", "fin", "duracion", "aplicar", "confianza", "motivo", "texto",
             "contexto", "palabras"]
    cortes = [{**{k: c[k] for k in orden if k in c}, **{k: v for k, v in c.items() if k not in orden}}
              for c in cortes]
    return {
        "version": 1,
        "audio": "voz_limpia.wav",
        "duracion_s": round(dur, 3),
        "sr": sr,
        "parametros": prm,
        "resumen": resumen(cortes, dur),
        "cortes": cortes,
    }


def marcar_contenidos(cortes: list[dict]) -> None:
    aplicados = [c for c in cortes if c["aplicar"] and c["tipo"] != "silencio"]
    for c in cortes:
        c.pop("dentro_de", None)
        for d in aplicados:
            if d is not c and d["inicio"] <= c["inicio"] + 1e-6 and c["fin"] <= d["fin"] + 1e-6:
                c["dentro_de"] = d["id"]
                break


def union_intervalos(iv: list[tuple[float, float]]) -> list[tuple[float, float]]:
    iv = sorted((a, b) for a, b in iv if b > a)
    res: list[list[float]] = []
    for a, b in iv:
        if res and a <= res[-1][1] + 1e-6:
            res[-1][1] = max(res[-1][1], b)
        else:
            res.append([a, b])
    return [(a, b) for a, b in res]


def resumen(cortes: list[dict], dur: float) -> dict:
    tipos: dict[str, dict] = {}
    for c in cortes:
        t = tipos.setdefault(c["tipo"], {"propuestos": 0, "aplicar": 0})
        t["propuestos"] += 1
        t["aplicar"] += int(c["aplicar"])
    quitado = sum(b - a for a, b in union_intervalos([(c["inicio"], c["fin"]) for c in cortes
                                                      if c["aplicar"]]))
    return {"cortes_propuestos": len(cortes),
            "cortes_a_aplicar": sum(int(c["aplicar"]) for c in cortes),
            "por_tipo": tipos,
            "duracion_original_s": round(dur, 2),
            "duracion_estimada_s": round(dur - quitado, 2),
            "segundos_quitados": round(quitado, 2)}


# ----------------------------------------------------------------------------
# cortes.md
# ----------------------------------------------------------------------------


def _md(s: str) -> str:
    return (s or "").replace("|", "\\|").replace("\n", " ")


def cortes_md(edl: dict, titulo: str = "") -> str:
    r = edl["resumen"]
    dur, est = r["duracion_original_s"], r["duracion_estimada_s"]
    pct = 100 * (dur - est) / dur if dur else 0
    L = [f"# Propuesta de cortes{(' — ' + titulo) if titulo else ''}", ""]
    L.append(f"- Duración: **{util.fmt_t(dur)} → {util.fmt_t(est)}** "
             f"(−{util.fmt_t(dur - est)}, {pct:.0f} %) si se aplica la propuesta tal cual.")
    tipos = ", ".join(f"{t} {v['aplicar']}/{v['propuestos']}" for t, v in r["por_tipo"].items())
    L.append(f"- Cortes a aplicar / propuestos: **{r['cortes_a_aplicar']}/{r['cortes_propuestos']}** "
             f"({tipos}).")
    L.append(f"- Tiempos sobre `voz_limpia.wav`. Confianza mínima para aplicar: "
             f"{edl['parametros']['confianza_min_aplicar']}.")
    L += ["", "## Cómo editar", "",
          "1. Copiá `edl_propuesta.json` a `edl_final.json`.",
          "2. En cada corte cambiá `\"aplicar\"` a `true`/`false`; podés mover `inicio`/`fin` "
          "(segundos) o agregar cortes nuevos con `\"tipo\": \"manual\"`.",
          "3. Corré `python aplicar.py <esta carpeta> --edl edl_final.json`.",
          "",
          "Los cortes se unen (si se pisan no pasa nada) y nunca se corta dentro de una palabra "
          "que queda: `aplicar.py` recorta el corte al borde de la palabra y lo avisa.", ""]
    contenido = [c for c in edl["cortes"] if c["tipo"] != "silencio"]
    dudosos = [c for c in contenido if not c.get("dentro_de")]
    L += ["## Cortes de contenido (revisar)", "",
          "| id | tipo | tiempo | dur | conf | aplicar | texto | motivo |",
          "|---|---|---|---|---|---|---|---|"]
    for c in dudosos:
        L.append(f"| {c['id']} | {c['tipo']} | {util.fmt_t(c['inicio'])} | {c['duracion']:.2f} | "
                 f"{c['confianza']:.2f} | {'sí' if c['aplicar'] else '**no**'} | "
                 f"{_md(c['texto'] or '—')} | {_md(c['motivo'])} |")
    L += ["", "### Contexto", ""]
    for c in dudosos:
        L.append(f"- **{c['id']}** ({c['tipo']}, {util.fmt_t(c['inicio'])}): {_md(c['contexto'])}")
    sil = [c for c in edl["cortes"] if c["tipo"] == "silencio"]
    L += ["", f"## Silencios ({len(sil)})", "",
          "| id | tiempo | pausa | queda | aplicar | contexto |", "|---|---|---|---|---|---|"]
    for c in sil:
        dentro = f" (dentro de {c['dentro_de']})" if c.get("dentro_de") else ""
        L.append(f"| {c['id']} | {util.fmt_t(c['inicio'])} | {c.get('pausa_original_s', 0):.2f} | "
                 f"{c.get('pausa_resultante_s', 0):.2f} | {'sí' if c['aplicar'] else 'no'}{dentro} | "
                 f"{_md(c['contexto'])} |")
    return "\n".join(L) + "\n"
