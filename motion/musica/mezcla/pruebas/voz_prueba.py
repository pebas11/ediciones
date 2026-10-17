#!/usr/bin/env python3
"""Voz de prueba realista para el mezclador: TTS en español (edge-tts) con pausas de distintos
largos, piso de ruido de sala y la misma entrega que `motion/tools/voz`: 48 kHz, 24 bit, mono,
−16 LUFS, pico real ≤ −1,5 dBTP.

    python3 motion/musica/mezcla/pruebas/voz_prueba.py              # → salida/_mezcla_pruebas/voz_prueba.wav

edge-tts necesita internet. Se busca un Python que lo tenga: el actual, $EDGE_TTS_PYTHON o
el entorno de la herramienta de voz (motion/tools/voz/.venv). Las frases quedan en caché.
Junto al WAV se escribe voz_prueba.json con el inicio y el fin de cada frase.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
MUSICA = AQUI.parents[1]
sys.path.insert(0, str(MUSICA))

import numpy as np          # noqa: E402
import soundfile as sf      # noqa: E402

from mezcla import SR       # noqa: E402

SALIDA = MUSICA / "salida" / "_mezcla_pruebas"
VOZ = "es-AR-TomasNeural"
VELOCIDAD = "-6%"

# (texto, pausa después en segundos). Intro de 8 s sin voz y final de 10 s.
INTRO_S = 8.0
FINAL_S = 10.0
GUION = [
    ("Cada noche, cuando cerramos los ojos, el cerebro no se apaga.", 0.8),
    ("Al contrario:", 0.35),
    ("empieza uno de los trabajos más delicados de todo el día.", 0.9),
    ("Ordena lo que vivimos, separa lo importante de lo que sobra,", 0.4),
    ("y guarda los recuerdos en un lugar donde puedan durar años.", 2.6),
    ("Pensemos en un día cualquiera.", 0.5),
    ("Miles de imágenes, conversaciones, olores y caminos.", 0.6),
    ("Casi todo eso se va a olvidar, y está bien que así sea.", 0.9),
    ("Lo que queda es una selección, y esa selección se hace de noche.", 2.0),
    ("Durante mucho tiempo creímos que soñar era un accidente.", 0.6),
    ("Un ruido de fondo, imágenes sueltas sin ningún sentido.", 1.2),
    ("Pero los registros de actividad cerebral contaron otra historia.", 0.5),
    ("Mientras dormimos, las mismas neuronas que se encendieron durante el día", 0.3),
    ("vuelven a encenderse, en el mismo orden, pero mucho más rápido.", 0.7),
    ("Como si el cerebro repasara la jornada en cámara rápida.", 6.0),
    ("Y acá aparece la parte más sorprendente.", 1.0),
    ("Ese repaso no es una copia exacta.", 0.5),
    ("El cerebro mezcla, combina y prueba versiones nuevas de lo que pasó.", 0.8),
    ("Por eso los sueños se sienten tan extraños:", 0.4),
    ("son el taller donde la memoria se reconstruye.", 3.5),
    ("Hay experimentos que lo muestran con claridad.", 0.5),
    ("Personas que aprenden una tarea por la tarde la resuelven mejor al día siguiente,", 0.3),
    ("pero solo si durmieron.", 0.8),
    ("Sin sueño, la mejora casi desaparece.", 4.0),
    ("Si nos despiertan en esa etapa, recordamos el sueño con detalle.", 0.25),
    ("Si no, se pierde en minutos.", 0.25),
    ("Y aun así, el trabajo queda hecho.", 0.25),
    ("Lo aprendido se vuelve más firme, más rápido de usar, más nuestro.", 1.6),
    ("Dormir no es tiempo perdido.", 0.4),
    ("Es la otra mitad del aprendizaje.", 2.2),
    ("La próxima vez que sueñes algo absurdo, pensalo así:", 0.5),
    ("no es un error.", 0.6),
    ("Es tu cerebro, armando el día de mañana.", 0.0),
]

TTS_PY = r"""
import asyncio, json, os, ssl, sys
import edge_tts
try:
    import edge_tts.communicate as ec
    ca = '/root/.ccr/ca-bundle.crt'
    if os.path.exists(ca):
        ec._SSL_CTX = ssl.create_default_context(cafile=ca)   # CA del proxy (no se desactiva TLS)
except Exception:
    pass
trabajos = json.load(sys.stdin)
async def uno(t):
    c = edge_tts.Communicate(t['texto'], t['voz'], rate=t['velocidad'], proxy=os.environ.get('HTTPS_PROXY'))
    await c.save(t['archivo'])
async def todos():
    for t in trabajos:
        await uno(t)
asyncio.run(todos())
"""


def python_con_edge() -> str:
    cands = [sys.executable, os.environ.get("EDGE_TTS_PYTHON", ""),
             str(MUSICA.parent / "tools" / "voz" / ".venv" / "bin" / "python")]
    for c in cands:
        if c and Path(c).exists():
            r = subprocess.run([c, "-c", "import edge_tts"], capture_output=True)
            if r.returncode == 0:
                return c
    raise SystemExit("no encuentro edge-tts: pip install edge-tts (o EDGE_TTS_PYTHON=/ruta/python)")


def ffmpeg() -> str:
    ff = shutil.which("ffmpeg")
    if ff:
        return ff
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def decodificar(ruta: Path) -> np.ndarray:
    r = subprocess.run([ffmpeg(), "-v", "error", "-i", str(ruta), "-f", "f32le", "-ac", "1",
                        "-ar", str(SR), "-"], capture_output=True, check=True)
    return np.frombuffer(r.stdout, dtype="<f4").astype(np.float32)


def recortar(x: np.ndarray, umbral_db=-50.0) -> np.ndarray:
    """Quita el silencio del principio y del final que agrega el TTS (deja 15 ms)."""
    h = int(0.005 * SR)
    n = len(x) // h
    e = 20 * np.log10(np.sqrt((x[: n * h].reshape(n, h) ** 2).mean(axis=1)) + 1e-9)
    vivo = np.nonzero(e > umbral_db)[0]
    if len(vivo) == 0:
        return x
    a = max(0, vivo[0] * h - int(0.015 * SR))
    b = min(len(x), (vivo[-1] + 1) * h + int(0.015 * SR))
    y = x[a:b].copy()
    f = int(0.004 * SR)
    y[:f] *= np.linspace(0, 1, f)
    y[-f:] *= np.linspace(1, 0, f)
    return y


def ruido_sala(n: int, nivel_db: float, semilla: int = 7) -> np.ndarray:
    """Piso de sala suave (ruido rosado aproximado, filtrado), a `nivel_db` dBFS RMS."""
    from scipy.signal import lfilter
    g = np.random.default_rng(semilla)
    w = g.standard_normal(n)
    b = [0.049922035, -0.095993537, 0.050612699, -0.004408786]
    a = [1, -2.494956002, 2.017265875, -0.522189400]
    p = lfilter(b, a, w)
    p *= 10 ** (nivel_db / 20) / (np.sqrt(np.mean(p ** 2)) + 1e-12)
    return p.astype(np.float32)


def main():
    SALIDA.mkdir(parents=True, exist_ok=True)
    cache = SALIDA / "tts_cache"
    cache.mkdir(exist_ok=True)
    trabajos = []
    rutas = []
    for texto, _ in GUION:
        h = hashlib.blake2b(f"{VOZ}|{VELOCIDAD}|{texto}".encode(), digest_size=8).hexdigest()
        r = cache / f"{h}.mp3"
        rutas.append(r)
        if not r.exists() or r.stat().st_size < 1000:
            trabajos.append({"texto": texto, "voz": VOZ, "velocidad": VELOCIDAD, "archivo": str(r)})
    if trabajos:
        py = python_con_edge()
        print(f"[voz] sintetizando {len(trabajos)} frases con edge-tts ({py})")
        subprocess.run([py, "-c", TTS_PY], input=json.dumps(trabajos).encode(), check=True)
    partes = [np.zeros(int(INTRO_S * SR), np.float32)]
    t = INTRO_S
    frases = []
    for (texto, pausa), r in zip(GUION, rutas):
        x = recortar(decodificar(r))
        frases.append({"texto": texto, "inicio_s": round(t, 3), "fin_s": round(t + len(x) / SR, 3),
                       "pausa_despues_s": pausa})
        partes.append(x)
        t += len(x) / SR
        if pausa > 0:
            partes.append(np.zeros(int(pausa * SR), np.float32))
            t += int(pausa * SR) / SR
    partes.append(np.zeros(int(FINAL_S * SR), np.float32))
    voz = np.concatenate(partes)
    voz += ruido_sala(len(voz), -66.0)
    # −16 LUFS (mono) y pico real ≤ −1,5 dBTP, como la herramienta de voz
    from mezcla.niveles import lufs
    from mezcla.master import picos_reales, ganancia_limitador
    for _ in range(4):
        l = lufs(voz)
        voz *= np.float32(10 ** ((-16.0 - l) / 20))
        est = np.stack([voz, voz], axis=1)
        pk = picos_reales(est)
        g = ganancia_limitador(pk, 10 ** (-1.6 / 20), int(0.005 * SR), 0.06)
        voz = voz * g
        if abs(lufs(voz) + 16.0) < 0.03:
            break
    from mezcla.master import pico_real_db
    tp = pico_real_db(np.stack([voz, voz], axis=1))
    l = lufs(voz)
    dest = SALIDA / "voz_prueba.wav"
    sf.write(str(dest), voz, SR, subtype="PCM_24")
    meta = {"voz": VOZ, "velocidad": VELOCIDAD, "duracion_s": round(len(voz) / SR, 3),
            "lufs": round(l, 2), "pico_dbtp": round(tp, 2), "intro_s": INTRO_S, "final_s": FINAL_S,
            "frases": frases}
    (SALIDA / "voz_prueba.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[voz] {dest}: {len(voz) / SR:.1f} s, {l:.2f} LUFS, {tp:.2f} dBTP, {len(frases)} frases")


if __name__ == "__main__":
    main()
