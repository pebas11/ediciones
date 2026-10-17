"""Genera el fixture sintético con problemas conocidos y la EDL esperada.

Voz por TTS (edge-tts, voz es-AR; gTTS como respaldo) armada con:
    - silencios largos de 1,5–3 s
    - un arranque en falso repetido ("Los hongos no son... Los hongos no son plantas")
    - un blooper ("Ay, perdón, de nuevo.") seguido de la toma buena
    - muletillas ("Eh...", "este...", "mmm")
    - trampas que NO hay que cortar: "Bienvenidos de nuevo al canal" y "Este intercambio"
Degradaciones (cadena de grabación casera): reverb de habitación, ruido rosa, zumbido de 50 Hz
con armónicos, clics de boca, golpes de plosiva y un pico que clipea. Se codifica a MP4 (AAC
estéreo + video de prueba a 30 fps) para probar también la extracción y el corte de video.

Uso:
    python pruebas/generar_fixture.py [--out pruebas/fixtures] [--voz es-AR-TomasNeural]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import ssl
import sys
from pathlib import Path

import numpy as np
from scipy import signal

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))

from vozlib import util  # noqa: E402

SR = 48000

# (tipo, texto o duración, rol)
#   rol: mantener | arranque_falso | blooper_toma | blooper_marca | muletilla
#   en "voz" con muletillas internas se marcan las palabras a sacar con {llaves}
GUION = [
    ("silencio", 0.8, None),
    ("voz", "Hola a todos, ¿cómo andan? Bienvenidos de nuevo al canal.", "mantener"),
    ("silencio", 2.2, None),
    ("voz", "Hoy vamos a hablar de los hongos.", "mantener"),
    ("silencio", 0.35, None),
    ("voz", "Los hongos no son...", "arranque_falso"),
    ("silencio", 0.7, None),
    ("voz", "Los hongos no son plantas, son un reino aparte.", "mantener"),
    ("silencio", 1.6, None),
    ("voz", "Eh...", "muletilla"),
    ("silencio", 0.45, None),
    ("voz", "El micelio es la parte que no vemos, y es enorme.", "mantener"),
    ("silencio", 0.5, None),
    ("voz", "Puede crecer kilómetros bajo el...", "blooper_toma"),
    ("silencio", 0.3, None),
    ("voz", "Ay, perdón, de nuevo.", "blooper_marca"),
    ("silencio", 1.3, None),
    ("voz", "Puede crecer kilómetros bajo el suelo del bosque.", "mantener"),
    ("silencio", 2.8, None),
    ("voz", "Y lo más interesante, {este}...", "mantener"),
    ("silencio", 0.6, None),
    ("voz", "{mmm}, es cómo se comunican entre ellos.", "mantener"),
    ("silencio", 0.5, None),
    ("voz", "¡Es increíble!", "mantener_fuerte"),
    ("silencio", 1.9, None),
    ("voz", "Las raíces de los árboles se conectan con el micelio, y así comparten azúcares y agua.",
     "mantener"),
    ("silencio", 0.4, None),
    ("voz", "Este intercambio es muy importante para el bosque.", "mantener"),
    ("silencio", 1.5, None),
    ("voz", "Bueno, eso es todo por hoy. Gracias por mirar, nos vemos en el próximo video.",
     "mantener"),
    ("silencio", 1.2, None),
]

TIPO_POR_ROL = {
    "arranque_falso": "arranque_falso",
    "blooper_toma": "blooper",
    "blooper_marca": "blooper",
    "muletilla": "muletilla",
}


# ----------------------------------------------------------------------------
# TTS con caché
# ----------------------------------------------------------------------------


def _ctx_ssl():
    ca = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
    ctx = ssl.create_default_context()
    if ca and Path(ca).exists():
        ctx.load_verify_locations(cafile=ca)
    return ctx


async def _edge(texto: str, voz: str, mp3: Path):
    import edge_tts
    import edge_tts.communicate as ec

    ec._SSL_CTX = _ctx_ssl()  # respeta el CA del proxy si lo hay
    com = edge_tts.Communicate(texto, voz, boundary="WordBoundary")
    palabras = []
    with open(mp3, "wb") as f:
        async for ch in com.stream():
            if ch["type"] == "audio":
                f.write(ch["data"])
            elif ch["type"] == "WordBoundary":
                palabras.append({"texto": ch["text"], "inicio": ch["offset"] / 1e7,
                                 "fin": (ch["offset"] + ch["duration"]) / 1e7})
    return palabras


def tts(texto: str, voz: str, cache: Path) -> tuple[np.ndarray, list]:
    cache.mkdir(parents=True, exist_ok=True)
    h = hashlib.sha1(f"{voz}|{texto}".encode()).hexdigest()[:16]
    mp3, js = cache / f"{h}.mp3", cache / f"{h}.json"
    if not (mp3.exists() and js.exists()):
        try:
            palabras = asyncio.run(_edge(texto, voz, mp3))
        except Exception as e:  # respaldo: gTTS (sin marcas de palabra)
            print(f"edge-tts falló ({e}); uso gTTS", file=sys.stderr)
            from gtts import gTTS

            gTTS(texto, lang="es", tld="com.ar").save(str(mp3))
            palabras = []
        js.write_text(json.dumps(palabras, ensure_ascii=False), encoding="utf-8")
    palabras = json.loads(js.read_text(encoding="utf-8"))
    x = util.decodificar(mp3, SR, canales=1)[:, 0]
    return x, palabras


# ----------------------------------------------------------------------------
# Degradaciones
# ----------------------------------------------------------------------------


def rir_habitacion(rt60: float = 0.5, drr_db: float = 4.0, seed: int = 7) -> np.ndarray:
    n = int(rt60 * 1.4 * SR)
    t = np.arange(n) / SR
    rng = np.random.default_rng(seed)
    cola = rng.standard_normal(n) * np.exp(-6.91 * t / rt60)
    cola[: int(0.004 * SR)] = 0.0
    sos = signal.butter(1, 5000, "lowpass", fs=SR, output="sos")  # absorción del aire
    cola = signal.sosfilt(sos, cola)
    h = np.zeros(n)
    h[0] = 1.0
    for d_ms, a in [(2.9, 0.45), (6.8, 0.32), (11.3, -0.28), (16.9, 0.22), (23.5, 0.18)]:
        h[int(d_ms * SR / 1000)] += a
    e_dir = float(np.sum(h ** 2))
    cola *= np.sqrt(e_dir / (np.sum(cola ** 2) * 10 ** (drr_db / 10)))
    return h + cola


def ruido_rosa(n: int, seed: int = 3) -> np.ndarray:
    rng = np.random.default_rng(seed)
    X = np.fft.rfft(rng.standard_normal(n))
    f = np.fft.rfftfreq(n, 1 / SR)
    f[0] = f[1]
    X /= np.sqrt(f)
    p = np.fft.irfft(X, n)
    return p / np.sqrt(np.mean(p ** 2))


def zumbido(n: int, f0: float = 50.0) -> np.ndarray:
    t = np.arange(n) / SR
    niveles = {1: -54, 2: -60, 3: -56, 4: -66, 5: -61, 6: -70, 7: -65, 8: -74, 9: -69}
    z = np.zeros(n)
    rng = np.random.default_rng(11)
    for k, dbfs in niveles.items():
        a = np.sqrt(2) * 10 ** (dbfs / 20)
        z += a * np.sin(2 * np.pi * f0 * k * t + rng.uniform(0, 2 * np.pi))
    return z


def clic(sr: int = SR) -> np.ndarray:
    n = int(0.0012 * sr)
    t = np.arange(n) / sr
    return np.sin(2 * np.pi * 5200 * t) * np.exp(-t / 0.00025)


def golpe_plosiva(sr: int = SR) -> np.ndarray:
    """Golpe de aire en el micrófono: pulso grave (energía en 40–150 Hz) que decae rápido."""
    n = int(0.06 * sr)
    t = np.arange(n) / sr
    rng = np.random.default_rng(5)
    ruido = signal.sosfilt(signal.butter(2, 150, "lowpass", fs=sr, output="sos"), rng.standard_normal(n))
    ruido /= np.max(np.abs(ruido))
    g = (0.8 * np.sin(2 * np.pi * 75 * t) + 0.6 * ruido) * np.exp(-t / 0.015)
    g[: int(0.002 * sr)] *= np.linspace(0, 1, int(0.002 * sr))
    return g / np.max(np.abs(g))


def lufs(x):
    import pyloudnorm

    return pyloudnorm.Meter(SR).integrated_loudness(x.astype(np.float64))


# ----------------------------------------------------------------------------
# Armado
# ----------------------------------------------------------------------------


def _ataque(x: np.ndarray) -> float:
    """Primer instante en que la envolvente (2 ms) supera el máximo − 40 dB."""
    hop = int(0.002 * SR)
    n = len(x) // hop
    env = np.sqrt((x[: n * hop].reshape(n, hop) ** 2).mean(axis=1)) + 1e-9
    L = 20 * np.log10(env)
    k = np.flatnonzero(L > L.max() - 40)
    return float(k[0] * hop / SR) if len(k) else 0.0


def normalizar_palabra(p: str) -> str:
    import re
    import unicodedata

    p = unicodedata.normalize("NFKD", p.lower())
    p = "".join(c for c in p if not unicodedata.combining(c))
    return re.sub(r"[^a-zñ0-9]+", "", p)


def armar(voz: str, cache: Path):
    partes = []
    palabras = []
    eventos = []
    t = 0.0
    for tipo, val, rol in GUION:
        if tipo == "silencio":
            n = int(round(val * SR))
            partes.append(np.zeros(n, dtype=np.float32))
            eventos.append({"tipo": "silencio", "inicio": round(t, 4), "fin": round(t + n / SR, 4)})
            t += n / SR
            continue
        texto_tts = val.replace("{", "").replace("}", "")
        quitar_internas = {normalizar_palabra(w) for w in
                           [s.split("}")[0] for s in val.split("{")[1:]]}
        x, pal = tts(texto_tts, voz, cache)
        # Las marcas de edge-tts vienen corridas ~0,1 s respecto del MP3 decodificado (retardo
        # del códec). Se calibra cada frase con el ataque acústico de su primera palabra.
        delta = _ataque(x) - pal[0]["inicio"] if pal else 0.0
        # la duración de la última palabra de edge-tts incluye cola: se usa el final acústico
        fin_acustico = _ataque(x[::-1].copy())
        fin_acustico = len(x) / SR - fin_acustico
        if pal:
            pal[-1]["fin"] = min(pal[-1]["fin"], fin_acustico - delta + 0.01)
        # recorta silencio inicial/final del TTS para controlar las pausas
        env = np.abs(x) > 10 ** (-50 / 20)
        idx = np.flatnonzero(env)
        a = max(0, idx[0] - int(0.01 * SR))
        b = min(len(x), idx[-1] + int(0.03 * SR))
        x = x[a:b]
        off = a / SR - delta
        if rol == "mantener_fuerte":
            x = x * 10 ** (17 / 20)
        ini = t
        for w in pal:
            nw = normalizar_palabra(w["texto"])
            if rol in TIPO_POR_ROL:
                r = "quitar"
                motivo = TIPO_POR_ROL[rol]
            elif nw in quitar_internas:
                r = "quitar"
                motivo = "muletilla"
                quitar_internas.discard(nw)
            else:
                r = "mantener"
                motivo = None
            palabras.append({"texto": w["texto"], "norm": nw,
                             "inicio": round(ini + w["inicio"] - off, 4),
                             "fin": round(ini + w["fin"] - off, 4),
                             "rol": r, "motivo": motivo, "evento": len(eventos)})
        partes.append(x.astype(np.float32))
        eventos.append({"tipo": "voz", "texto": texto_tts, "rol": rol, "inicio": round(t, 4),
                        "fin": round(t + len(x) / SR, 4)})
        t += len(x) / SR
    seco = np.concatenate(partes)
    return seco, palabras, eventos


def cortes_esperados(palabras: list, eventos: list) -> list:
    """Cortes de contenido (grupos contiguos de palabras a quitar) y silencios largos."""
    esperados = []
    i = 0
    n = len(palabras)
    while i < n:
        if palabras[i]["rol"] != "quitar":
            i += 1
            continue
        j = i
        while j + 1 < n and palabras[j + 1]["rol"] == "quitar":
            j += 1
        tipos = sorted({palabras[k]["motivo"] for k in range(i, j + 1)})
        tipo = "blooper" if "blooper" in tipos else tipos[0]
        prev_fin = palabras[i - 1]["fin"] if i > 0 else 0.0
        sig_ini = palabras[j + 1]["inicio"] if j + 1 < n else None
        esperados.append({
            "tipo": tipo,
            "texto": " ".join(palabras[k]["texto"] for k in range(i, j + 1)),
            "palabras_inicio": palabras[i]["inicio"],
            "palabras_fin": palabras[j]["fin"],
            "margen_izq": prev_fin,
            "margen_der": sig_ini,
            "obligatorio": True,
        })
        i = j + 1
    # silencios largos entre palabras que se mantienen
    keep = [p for p in palabras if p["rol"] == "mantener"]
    for a, b in zip(keep, keep[1:]):
        gap = b["inicio"] - a["fin"]
        quitadas_en_medio = any(p["rol"] == "quitar" and a["fin"] <= p["inicio"] < b["inicio"]
                                for p in palabras)
        if gap >= 1.0 and not quitadas_en_medio:
            esperados.append({"tipo": "silencio", "texto": f"pausa {gap:.2f} s",
                              "palabras_inicio": a["fin"], "palabras_fin": b["inicio"],
                              "margen_izq": a["fin"], "margen_der": b["inicio"],
                              "obligatorio": True})
    esperados.sort(key=lambda e: e["palabras_inicio"])
    return esperados


def degradar(seco: np.ndarray, palabras: list, eventos: list) -> tuple[np.ndarray, dict]:
    n_extra = int(0.8 * SR)
    x = np.concatenate([seco, np.zeros(n_extra, dtype=np.float32)]).astype(np.float64)
    # nivel casero: voz a ~ −27 LUFS (antes del pico fuerte)
    x *= 10 ** ((-27 - lufs(seco)) / 20)
    h = rir_habitacion()
    x = signal.oaconvolve(x, h)[: len(x)]
    n = len(x)
    x += ruido_rosa(n) * 10 ** (-56 / 20)
    x += zumbido(n)
    marcas = {"clics": [], "plosivas": []}
    # clics de boca en pausas, justo antes de que arranque una frase
    voces = [e for e in eventos if e["tipo"] == "voz"]
    for e in voces[2:8:2]:
        tc = e["inicio"] - 0.12
        i0 = int(tc * SR)
        c = clic() * 10 ** (-22 / 20)
        x[i0 : i0 + len(c)] += c
        marcas["clics"].append(round(tc, 4))
    # golpes de plosiva al comienzo de palabras con "p"
    for p in palabras:
        if p["norm"] in ("puede", "plantas") and len(marcas["plosivas"]) < 3:
            i0 = int((p["inicio"] - 0.005) * SR)
            g = golpe_plosiva() * 10 ** (-14 / 20)
            x[i0 : i0 + len(g)] += g
            marcas["plosivas"].append(round(p["inicio"], 4))
    # el grito clipea: recorte duro a fondo de escala
    pico = float(np.max(np.abs(x)))
    marcas["pico_antes_de_recortar_dbfs"] = round(20 * np.log10(pico), 2)
    x = np.clip(x, -1.0, 1.0)
    return x.astype(np.float32), marcas


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=AQUI / "fixtures")
    ap.add_argument("--voz", default="es-AR-TomasNeural")
    ap.add_argument("--sin-video", action="store_true", help="solo audio (m4a)")
    args = ap.parse_args()
    util.consola_utf8()
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    seco, palabras, eventos = armar(args.voz, out / "tts_cache")
    util.escribir_wav(out / "sintetico_seco.wav", seco)
    deg, marcas = degradar(seco, palabras, eventos)
    util.escribir_wav(out / "sintetico_degradado.wav", deg)
    dur = len(deg) / SR
    # MP4: AAC estéreo (mono duplicado) + video de prueba con contador de cuadros
    estereo = out / "_estereo.wav"
    util.escribir_wav(estereo, np.stack([deg, deg], axis=1))
    mp4 = out / ("sintetico.m4a" if args.sin_video else "sintetico.mp4")
    if args.sin_video:
        util.correr_ffmpeg(["-i", estereo, "-c:a", "aac", "-b:a", "160k", mp4])
    else:
        util.correr_ffmpeg(["-f", "lavfi", "-i", f"testsrc=size=640x360:rate=30:duration={dur:.3f}",
                            "-i", estereo, "-map", "0:v", "-map", "1:a", "-c:v", "libx264",
                            "-preset", "ultrafast", "-crf", "30", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-b:a", "160k", "-shortest", mp4])
    estereo.unlink()
    esperado = {
        "archivo": mp4.name,
        "duracion_s": round(dur, 3),
        "voz_tts": args.voz,
        "eventos": eventos,
        "palabras": palabras,
        "cortes_esperados": cortes_esperados(palabras, eventos),
        "degradaciones": {
            "reverb": {"rt60_s": 0.5, "drr_db": 4.0},
            "ruido_rosa_dbfs": -56,
            "zumbido": {"f0_hz": 50, "fundamental_dbfs": -54, "armonicos": 9},
            **marcas,
            "voz_lufs_aprox": -27,
        },
        "texto_final_esperado": " ".join(p["texto"] for p in palabras if p["rol"] == "mantener"),
    }
    util.guardar_json(out / "esperado.json", esperado)
    print(f"fixture: {mp4} ({dur:.1f} s), {len(palabras)} palabras, "
          f"{len(esperado['cortes_esperados'])} cortes esperados")


if __name__ == "__main__":
    main()
