"""Utilidades comunes: hilos, ffmpeg, audio, JSON, cronómetro y registro."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path

SR = 48000  # frecuencia de trabajo de todo el pipeline

_VARS_HILOS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)


def hilos_desde_argv(defecto: int = 2) -> int:
    """Lee --hilos de sys.argv sin argparse (hay que fijarlo antes de importar numpy)."""
    argv = sys.argv
    for i, a in enumerate(argv):
        if a == "--hilos" and i + 1 < len(argv):
            try:
                return max(1, int(argv[i + 1]))
            except ValueError:
                return defecto
        if a.startswith("--hilos="):
            try:
                return max(1, int(a.split("=", 1)[1]))
            except ValueError:
                return defecto
    return defecto


def configurar_hilos(n: int) -> None:
    """Limita los hilos de BLAS/OpenMP. Llamar antes de importar numpy/torch."""
    for v in _VARS_HILOS:
        os.environ[v] = str(n)


def consola_utf8() -> None:
    """En Windows la consola puede no ser UTF-8: evita errores al imprimir tildes."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# ----------------------------------------------------------------------------
# Registro
# ----------------------------------------------------------------------------

_T0 = time.perf_counter()


def log(msg: str) -> None:
    t = time.perf_counter() - _T0
    print(f"[{t:7.1f}s] {msg}", file=sys.stderr, flush=True)


class Cronometro:
    """Mide cada etapa y calcula segundos por minuto de audio."""

    def __init__(self, duracion_audio_s: float | None = None):
        self.etapas: dict[str, float] = {}
        self.duracion_audio_s = duracion_audio_s

    @contextmanager
    def etapa(self, nombre: str):
        t = time.perf_counter()
        log(f"→ {nombre}")
        try:
            yield
        finally:
            dt = time.perf_counter() - t
            self.etapas[nombre] = self.etapas.get(nombre, 0.0) + dt
            extra = ""
            if self.duracion_audio_s:
                extra = f" ({dt / (self.duracion_audio_s / 60):.1f} s por minuto de audio)"
            log(f"✓ {nombre}: {dt:.1f} s{extra}")

    def resumen(self) -> dict:
        d = self.duracion_audio_s or 0.0
        mins = d / 60 if d else None
        etapas = {
            k: {
                "segundos": round(v, 2),
                "seg_por_min_audio": round(v / mins, 2) if mins else None,
            }
            for k, v in self.etapas.items()
        }
        total = sum(self.etapas.values())
        return {
            "duracion_audio_s": round(d, 2),
            "total_s": round(total, 2),
            "total_seg_por_min_audio": round(total / mins, 2) if mins else None,
            "etapas": etapas,
        }


# ----------------------------------------------------------------------------
# JSON
# ----------------------------------------------------------------------------


def _json_default(o):
    try:
        import numpy as np

        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.ndarray):
            return o.tolist()
        if isinstance(o, np.bool_):
            return bool(o)
    except ImportError:
        pass
    if isinstance(o, Path):
        return o.as_posix()
    raise TypeError(f"No serializable: {type(o)}")


def guardar_json(ruta: Path, datos) -> None:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(ruta.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2, default=_json_default)
        f.write("\n")
    os.replace(tmp, ruta)


def leer_json(ruta: Path):
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def guardar_texto(ruta: Path, texto: str) -> None:
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)


# ----------------------------------------------------------------------------
# ffmpeg
# ----------------------------------------------------------------------------

_FFMPEG: str | None = None


def ffmpeg_exe() -> str:
    """ffmpeg del sistema; si no hay, el de imageio_ffmpeg. VOZ_FFMPEG lo fuerza."""
    global _FFMPEG
    if _FFMPEG:
        return _FFMPEG
    env = os.environ.get("VOZ_FFMPEG")
    if env and Path(env).exists():
        _FFMPEG = env
        return env
    p = shutil.which("ffmpeg")
    if p:
        _FFMPEG = p
        return p
    try:
        import imageio_ffmpeg

        _FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()
        return _FFMPEG
    except Exception as e:  # pragma: no cover
        raise RuntimeError(
            "No encontré ffmpeg. Instalalo (https://ffmpeg.org) o hacé "
            "`pip install imageio-ffmpeg`."
        ) from e


def ffmpeg_version() -> tuple[int, int]:
    out = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-version"], capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    ).stdout
    m = re.search(r"ffmpeg version n?(\d+)\.(\d+)", out)
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2)))


def correr_ffmpeg(args: list[str], hilos: int | None = None, cwd: Path | None = None) -> subprocess.CompletedProcess:
    cmd = [ffmpeg_exe(), "-hide_banner", "-nostdin", "-v", "error", "-y"]
    if hilos:
        cmd += ["-threads", str(hilos)]
    cmd += [str(a) for a in args]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=str(cwd) if cwd else None)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg falló ({r.returncode}): {' '.join(cmd)}\n{r.stderr[-2000:]}")
    return r


_FPS_CONOCIDOS = [Fraction(24000, 1001), Fraction(24), Fraction(25), Fraction(30000, 1001),
                  Fraction(30), Fraction(48000, 1001), Fraction(48), Fraction(50),
                  Fraction(60000, 1001), Fraction(60), Fraction(120000, 1001), Fraction(120)]


def _fps_fraccion(valor: float) -> Fraction:
    """Lleva un fps medido (los celulares graban a cuadros variables: 29,98, 30,02…) a la
    tasa estándar más cercana."""
    cerca = min(_FPS_CONOCIDOS, key=lambda f: abs(float(f) - valor))
    if abs(float(cerca) - valor) <= 0.05:
        return cerca
    return Fraction(valor).limit_denominator(1001)


def sondear(ruta: Path) -> dict:
    """Información básica del archivo parseando `ffmpeg -i` (no requiere ffprobe)."""
    r = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-nostdin", "-i", str(ruta)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    txt = r.stderr
    info: dict = {"archivo": Path(ruta).name, "duracion_s": None, "audio": None, "video": None}
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", txt)
    if m:
        info["duracion_s"] = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
    m = re.search(r"Stream #\d+:\d+[^:]*: Audio: ([^,\n]+), (\d+) Hz, ([^,\n]+)", txt)
    if m:
        lay = m.group(3).strip()
        canales = {"mono": 1, "stereo": 2}.get(lay)
        if canales is None:
            mm = re.match(r"(\d+) channels", lay)
            canales = int(mm.group(1)) if mm else (6 if lay.startswith("5.1") else 2)
        info["audio"] = {"codec": m.group(1).strip(), "sr": int(m.group(2)), "canales": canales,
                         "layout": lay}
    m = re.search(r"Stream #\d+:\d+[^:]*: Video: ([^\n]+)", txt)
    if m and "attached pic" not in m.group(1):
        linea = m.group(1)
        v: dict = {"codec": linea.split(",")[0].strip()}
        mr = re.search(r"(\d{2,5})x(\d{2,5})", linea)
        if mr:
            v["ancho"], v["alto"] = int(mr.group(1)), int(mr.group(2))
        # "tbr" es la tasa base que adivina ffmpeg (la nominal); "fps" es el promedio, que en
        # video de celular con cuadros variables da cosas como 29,98
        m_tbr = re.search(r"([\d.]+)(k?) tbr", linea)
        m_fps = re.search(r"([\d.]+) fps", linea)
        fps = None
        if m_tbr and not m_tbr.group(2):  # "90k tbr" (tapa de un mp3) no es una tasa de cuadros
            fps = float(m_tbr.group(1))
        elif m_fps:
            fps = float(m_fps.group(1))
        if fps:
            fr = _fps_fraccion(fps)
            v["fps"] = round(float(fr), 6)
            v["fps_fraccion"] = f"{fr.numerator}/{fr.denominator}"
        info["video"] = v
    if info["audio"] is None:
        raise RuntimeError(f"El archivo no tiene pista de audio legible: {ruta}\n{txt[-800:]}")
    return info


def decodificar(ruta: Path, sr: int = SR, canales: int | None = None, hilos: int | None = None):
    """Decodifica la primera pista de audio a float32 [n, canales] con ffmpeg."""
    import numpy as np
    import soundfile as sf

    with tempfile.TemporaryDirectory(prefix="voz_") as td:
        tmp = Path(td) / "dec.wav"
        args = ["-i", str(ruta), "-map", "0:a:0", "-vn", "-sn", "-dn"]
        if canales:
            args += ["-ac", str(canales)]
        args += ["-ar", str(sr), "-c:a", "pcm_f32le", "-f", "wav", str(tmp)]
        correr_ffmpeg(args, hilos=hilos)
        x, sr2 = sf.read(str(tmp), dtype="float32", always_2d=True)
    assert sr2 == sr
    return np.ascontiguousarray(x)


def leer_wav(ruta: Path):
    import numpy as np
    import soundfile as sf

    x, sr = sf.read(str(ruta), dtype="float32", always_2d=True)
    if x.shape[1] > 1:
        x = x.mean(axis=1, keepdims=True)
    return np.ascontiguousarray(x[:, 0]), sr


def escribir_wav(ruta: Path, x, sr: int = SR, subtipo: str = "FLOAT") -> None:
    import numpy as np
    import soundfile as sf

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    x = np.asarray(x, dtype=np.float32)
    if subtipo != "FLOAT":
        x = np.clip(x, -1.0, 1.0)
    sf.write(str(ruta), x, sr, subtype=subtipo)


def fmt_t(t: float) -> str:
    """Segundos → mm:ss.cc (o h:mm:ss.cc)."""
    if t is None:
        return "--"
    signo = "-" if t < 0 else ""
    t = abs(t)
    h = int(t // 3600)
    m = int((t % 3600) // 60)
    s = t % 60
    if h:
        return f"{signo}{h}:{m:02d}:{s:05.2f}"
    return f"{signo}{m:02d}:{s:05.2f}"


def directorio_herramienta() -> Path:
    return Path(__file__).resolve().parent.parent


def directorio_modelos() -> Path:
    env = os.environ.get("VOZ_MODELOS")
    return Path(env) if env else directorio_herramienta() / "modelos"
