"""Aplicación de la EDL: cortes con fundido de igual potencia, re-mapeo de palabras y video."""

from __future__ import annotations

import math
from fractions import Fraction
from pathlib import Path

import numpy as np

from . import edicion, util

TIPOS_VALIDOS = {"silencio", *edicion.TIPOS_CONTENIDO}


# ----------------------------------------------------------------------------
# Intervalos
# ----------------------------------------------------------------------------


def cortes_aplicados(edl: dict, palabras: list[dict], dur: float) -> tuple[list[tuple[float, float]], list[str], list[dict]]:
    """Cortes con aplicar=true, validados. Nunca deja un corte dentro de una palabra que
    queda: si un corte pisa una palabra que ningún corte aplicado saca, se recorta al borde."""
    avisos = []
    cortes = []
    ids = set()
    for c in edl.get("cortes", []):
        cid = c.get("id") or f"m{len(ids) + 1:03d}"
        if cid in ids:
            avisos.append(f"id repetido {cid}")
        ids.add(cid)
        if not c.get("aplicar", False):
            continue
        try:
            a, b = float(c["inicio"]), float(c["fin"])
        except (KeyError, TypeError, ValueError):
            avisos.append(f"{cid}: inicio/fin inválidos, se ignora")
            continue
        if c.get("tipo") not in TIPOS_VALIDOS:
            avisos.append(f"{cid}: tipo desconocido «{c.get('tipo')}» (se aplica igual)")
        a, b = max(0.0, a), min(dur, b)
        if b - a < 0.005:
            avisos.append(f"{cid}: corte vacío o invertido, se ignora")
            continue
        cortes.append({**c, "id": cid, "inicio": a, "fin": b})

    # palabras que saca algún corte aplicado (rango "palabras" o > 50 % cubierta)
    def cubierta(w, iv):
        d = w["fin"] - w["inicio"]
        if d <= 0:
            return 0.0
        return sum(max(0.0, min(b, w["fin"]) - max(a, w["inicio"])) for a, b in iv) / d

    sacadas = set()
    for c in cortes:
        r = c.get("palabras")
        if r and len(r) == 2:
            sacadas.update(range(int(r[0]), int(r[1]) + 1))
    union = edicion.union_intervalos([(c["inicio"], c["fin"]) for c in cortes])
    for k, w in enumerate(palabras):
        if cubierta(w, union) > 0.5:
            sacadas.add(k)

    # proteger palabras que quedan
    for c in cortes:
        for k, w in enumerate(palabras):
            if k in sacadas:
                continue
            if w["fin"] <= c["inicio"] or w["inicio"] >= c["fin"]:
                continue
            # el corte pisa la palabra k que queda: recortar el lado que la toca
            antes = c["inicio"], c["fin"]
            if w["inicio"] <= c["inicio"] < w["fin"]:
                c["inicio"] = min(c["fin"], w["fin"] + 0.01)
            if w["inicio"] < c["fin"] <= w["fin"]:
                c["fin"] = max(c["inicio"], w["inicio"] - 0.01)
            if c["inicio"] < w["inicio"] and c["fin"] > w["fin"]:
                # la palabra quedó en el medio del corte: partirlo en dos
                cortes.append({**c, "id": c["id"] + "b", "inicio": w["fin"] + 0.01})
                c["fin"] = w["inicio"] - 0.01
            avisos.append(f"{c['id']}: pisaba «{w['texto']}» ({w['inicio']:.2f}–{w['fin']:.2f}); "
                          f"{antes[0]:.3f}–{antes[1]:.3f} → {c['inicio']:.3f}–{c['fin']:.3f}")
    iv = edicion.union_intervalos([(c["inicio"], c["fin"]) for c in cortes if c["fin"] - c["inicio"] > 0.005])
    return iv, avisos, cortes


def mantener(quitar: list[tuple[float, float]], dur: float, minimo: float = 0.02) -> list[tuple[float, float]]:
    segs = []
    t = 0.0
    for a, b in quitar:
        if a - t >= minimo:
            segs.append((t, a))
        t = max(t, b)
    if dur - t >= minimo:
        segs.append((t, dur))
    return segs


# ----------------------------------------------------------------------------
# Bordes: baja energía y cruce por cero (o grilla de cuadros si hay video)
# ----------------------------------------------------------------------------


def cruce_por_cero(x: np.ndarray, n: int, radio: int) -> int:
    a, b = max(1, n - radio), min(len(x) - 1, n + radio)
    if b <= a:
        return n
    seg = x[a - 1 : b + 1]
    cambios = np.flatnonzero(np.signbit(seg[:-1]) != np.signbit(seg[1:])) + a - 1
    if len(cambios) == 0:
        return n
    k = cambios[np.argmin(np.abs(cambios - n))]
    # el de menor |x| entre los dos lados del cruce
    return int(k if abs(x[k]) <= abs(x[k + 1]) else k + 1)


def refinar(segs: list[tuple[float, float]], x: np.ndarray, sr: int, palabras: list[dict],
            fps: Fraction | None = None) -> list[tuple[int, int]]:
    """Pasa los segmentos a muestras. Cada borde interno se lleva al punto de menor energía
    cercano (±15 ms, sin entrar en palabras) y después al cruce por cero más próximo."""
    bordes_palabra = sorted([(w["inicio"], w["fin"]) for w in palabras])
    starts = np.array([a for a, _ in bordes_palabra]) if bordes_palabra else np.array([])
    ends = np.array([b for _, b in bordes_palabra]) if bordes_palabra else np.array([])

    def libre(t):
        """¿t cae fuera de toda palabra (con 8 ms de guarda)?"""
        if len(starts) == 0:
            return True
        return not np.any((starts - 0.008 < t) & (t < ends + 0.008))

    out = []
    n = len(x)
    for k, (a, b) in enumerate(segs):
        sa, sb = int(round(a * sr)), int(round(b * sr))
        if k > 0:
            t = edicion.punto_bajo(x, sr, a, a - 0.015, a + 0.015, radio=0.015)
            if libre(t):
                sa = int(round(t * sr))
            sa = cruce_por_cero(x, sa, int(0.0015 * sr))
        if k < len(segs) - 1:
            t = edicion.punto_bajo(x, sr, b, b - 0.015, b + 0.015, radio=0.015)
            if libre(t):
                sb = int(round(t * sr))
            sb = cruce_por_cero(x, sb, int(0.0015 * sr))
        sa, sb = max(0, min(sa, n)), max(0, min(sb, n))
        if sb > sa:
            out.append((sa, sb))
    return out


# ----------------------------------------------------------------------------
# Render con fundidos de igual potencia centrados en cada unión
# ----------------------------------------------------------------------------


def renderizar(x: np.ndarray, sr: int, segs: list[tuple[int, int]], fundido_ms: float = 20.0,
               palabras: list[dict] | None = None) -> tuple[np.ndarray, list[int]]:
    """Concatena los segmentos. En cada unión, el segmento que sale se extiende F/2 hacia el
    material cortado con caída cos y el que entra empieza F/2 antes con subida sin
    (sin² + cos² = 1: igual potencia). La duración total = suma de los segmentos, así que
    el re-mapeo de tiempos (y el corte de video) es exacto."""
    K = len(segs)
    N = sum(b - a for a, b in segs)
    out = np.zeros(N, dtype=np.float64)
    F = int(sr * fundido_ms / 1000)
    # la extensión no puede entrar en palabras cortadas: se limita por la distancia libre
    inicios_pal = np.array(sorted(w["inicio"] for w in palabras)) * sr if palabras else np.array([])
    fines_pal = np.array(sorted(w["fin"] for w in palabras)) * sr if palabras else np.array([])
    h = []
    for k in range(K - 1):
        b_k, a_n = segs[k][1], segs[k + 1][0]
        lib_der = a_n - b_k
        if len(inicios_pal):
            sig = inicios_pal[inicios_pal >= b_k]
            if len(sig):
                lib_der = min(lib_der, sig[0] - b_k)
            prev = fines_pal[fines_pal <= a_n]
            if len(prev):
                lib_der = min(lib_der, a_n - prev[-1])
        hk = int(max(int(0.002 * sr), min(F // 2, lib_der)))
        hk = min(hk, (segs[k][1] - segs[k][0]) // 2, (segs[k + 1][1] - segs[k + 1][0]) // 2)
        h.append(max(hk, 1))
    pos = 0
    for k, (a, b) in enumerate(segs):
        L = b - a
        hl = h[k - 1] if k > 0 else 0
        hr = h[k] if k < K - 1 else 0
        lo, hi = a - hl, b + hr
        src = np.zeros(hi - lo)
        s0, s1 = max(lo, 0), min(hi, len(x))
        src[s0 - lo : s0 - lo + (s1 - s0)] = x[s0:s1]
        w = np.ones(len(src))
        if hl:
            t = (np.arange(2 * hl) + 0.5) / (2 * hl)
            w[: 2 * hl] = np.sin(0.5 * math.pi * t)
        if hr:
            t = (np.arange(2 * hr) + 0.5) / (2 * hr)
            w[-2 * hr :] *= np.cos(0.5 * math.pi * t)
        o0 = pos - hl
        out[o0 : o0 + len(src)] += src * w
        pos += L
    return out.astype(np.float32), h


# ----------------------------------------------------------------------------
# Re-mapeo de palabras
# ----------------------------------------------------------------------------


class Mapa:
    def __init__(self, segs_s: list[tuple[float, float]]):
        self.segs = segs_s
        self.ini = [a for a, _ in segs_s]
        self.acum = []
        t = 0.0
        for a, b in segs_s:
            self.acum.append(t)
            t += b - a
        self.total = t

    def t(self, t: float, lado: str = "inicio") -> float:
        """Tiempo original → tiempo nuevo. Si t cae en un corte, va al borde más cercano
        del lado que corresponde (inicio → siguiente segmento, fin → segmento anterior)."""
        import bisect

        k = bisect.bisect_right(self.ini, t) - 1  # último segmento que empieza antes de t
        if k >= 0:
            a, b = self.segs[k]
            if t <= b:
                return self.acum[k] + (t - a)
            # t cae en el corte que sigue al segmento k
            if lado == "fin" or k + 1 >= len(self.segs):
                return self.acum[k] + (b - a)
            return self.acum[k + 1]
        return 0.0


def remapear(palabras: list[dict], quitar: list[tuple[float, float]], mapa: Mapa) -> list[dict]:
    res = []
    for k, w in enumerate(palabras):
        d = max(w["fin"] - w["inicio"], 1e-6)
        cort = sum(max(0.0, min(b, w["fin"]) - max(a, w["inicio"])) for a, b in quitar)
        if cort / d > 0.5:
            continue
        ini, fin = mapa.t(w["inicio"], "inicio"), mapa.t(w["fin"], "fin")
        if fin <= ini:
            fin = ini + 0.02
        res.append({"i": len(res), "texto": w["texto"], "norm": w.get("norm", ""),
                    "inicio": round(ini, 3), "fin": round(fin, 3), "prob": w.get("prob"),
                    "i_original": w.get("i", k), "inicio_original": w["inicio"],
                    "fin_original": w["fin"]})
    return res


def frases_desde_palabras(pal: list[dict], max_dur: float = 6.0, max_chars: int = 84) -> list[dict]:
    """Agrupa palabras en frases cortas (para subtítulos y para animar por frase)."""
    frases, actual = [], []
    for k, w in enumerate(pal):
        actual.append(w)
        texto = " ".join(p["texto"] for p in actual)
        fin_oracion = bool(edicion.FIN_ORACION.search(w["texto"]))
        coma = bool(edicion.COMA.search(w["texto"]))
        sig_gap = pal[k + 1]["inicio"] - w["fin"] if k + 1 < len(pal) else 9
        cortar = (fin_oracion or sig_gap > 0.6 or (coma and len(texto) > 40) or
                  len(texto) > max_chars or w["fin"] - actual[0]["inicio"] > max_dur)
        if cortar:
            frases.append({"inicio": actual[0]["inicio"], "fin": w["fin"], "texto": texto,
                           "palabras": [actual[0]["i"], w["i"]]})
            actual = []
    if actual:
        frases.append({"inicio": actual[0]["inicio"], "fin": actual[-1]["fin"],
                       "texto": " ".join(p["texto"] for p in actual),
                       "palabras": [actual[0]["i"], actual[-1]["i"]]})
    return frases


def srt(frases: list[dict]) -> str:
    def ts(t):
        ms = int(round(t * 1000))
        h, ms = divmod(ms, 3600000)
        m, ms = divmod(ms, 60000)
        s, ms = divmod(ms, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    bloques = [f"{k + 1}\n{ts(f['inicio'])} --> {ts(f['fin'])}\n{f['texto']}\n"
               for k, f in enumerate(frases)]
    return "\n".join(bloques)


# ----------------------------------------------------------------------------
# Video: mismo corte, con cuadros cuantizados y difusión del error
# ----------------------------------------------------------------------------


def cuadros_video(segs_s: list[tuple[float, float]], fps: Fraction) -> list[tuple[int, int]]:
    """Rangos de cuadros [ini, fin) por segmento. El número de cuadros de cada segmento se
    elige para que la duración acumulada del video no se aleje más de medio cuadro de la del
    audio (sin deriva aunque haya cientos de cortes)."""
    res = []
    acum = Fraction(0)
    for a, b in segs_s:
        ini = int(round(Fraction(a).limit_denominator(10 ** 6) * fps))
        prev = int(round(acum * fps))
        acum += Fraction(b - a).limit_denominator(10 ** 6)
        n = int(round(acum * fps)) - prev
        if n > 0:
            res.append((ini, ini + n))
    return res


def script_video(dir_salida: Path, segs_s: list[tuple[float, float]], video_info: dict | None,
                 nombre_audio: str = "voz_final.wav") -> dict:
    fps_txt = (video_info or {}).get("fps_fraccion") or "30/1"
    fps = Fraction(fps_txt)
    rangos = cuadros_video(segs_s, fps)
    terminos = "+".join(f"between(n,{a},{b - 1})" for a, b in rangos)
    grafo = f"[0:v]fps={fps_txt},select='{terminos}',setpts=N/FRAME_RATE/TB[v]\n"
    ffs = dir_salida / "cortar_video.ffscript"
    util.guardar_texto(ffs, grafo)
    resto = (f'-i {nombre_audio} -filter_complex_script cortar_video.ffscript -map "[v]" -map 1:a '
             "-c:v libx264 -preset medium -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k "
             "-movflags +faststart")
    sh = (
        "#!/bin/sh\n"
        "# Corta el video original igual que la voz y le pone voz_final.wav (generado por aplicar.py).\n"
        "# Uso: sh cortar_video.sh /ruta/al/original.mp4 [salida.mp4]\n"
        "# Si tu ffmpeg avisa que -filter_complex_script está obsoleto, usá: -/filter_complex cortar_video.ffscript\n"
        'cd "$(dirname "$0")" || exit 1\n'
        f'ffmpeg -y -i "$1" {resto} "${{2:-video_editado.mp4}}"\n'
    )
    bat = (
        "@echo off\r\n"
        "rem Corta el video original igual que la voz y le pone voz_final.wav (generado por aplicar.py).\r\n"
        "rem Uso: cortar_video.bat C:\\ruta\\al\\original.mp4 [salida.mp4]\r\n"
        "rem Si tu ffmpeg avisa que -filter_complex_script esta obsoleto, usa: -/filter_complex cortar_video.ffscript\r\n"
        'cd /d "%~dp0"\r\n'
        'set SALIDA=%~2\r\n'
        'if "%SALIDA%"=="" set SALIDA=video_editado.mp4\r\n'
        f'ffmpeg -y -i "%~1" {resto} "%SALIDA%"\r\n'
    )
    util.guardar_texto(dir_salida / "cortar_video.sh", sh)
    with open(dir_salida / "cortar_video.bat", "w", encoding="utf-8", newline="") as f:
        f.write(bat)
    return {"fps": fps_txt, "segmentos": len(rangos),
            "cuadros_totales": sum(b - a for a, b in rangos),
            "duracion_video_s": round(sum(b - a for a, b in rangos) / float(fps), 3)}


def cortar_video(dir_salida: Path, original: Path, salida: Path, hilos: int = 2) -> Path:
    """Ejecuta el corte de video con el ffmpeg disponible (elige la sintaxis según la versión)."""
    ver = util.ffmpeg_version()
    ffs = dir_salida / "cortar_video.ffscript"
    if ver >= (7, 0):
        filtro = ["-/filter_complex", str(ffs)]
    else:
        filtro = ["-filter_complex_script", str(ffs)]
    util.correr_ffmpeg(["-i", str(original), "-i", str(dir_salida / "voz_final.wav"), *filtro,
                        "-map", "[v]", "-map", "1:a", "-c:v", "libx264", "-preset", "medium",
                        "-crf", "18", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
                        "-movflags", "+faststart", str(salida)], hilos=hilos)
    return salida
