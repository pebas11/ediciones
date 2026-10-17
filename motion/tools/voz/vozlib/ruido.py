"""Reducción de ruido con límite de atenuación (para que suene natural).

Backends, en el orden que prueba `auto`:
    dfn          DeepFilterNet3 desde Python (pip deepfilternet + torch CPU).
    dfn-bin      El ejecutable oficial `deep-filter` (mismo modelo DFN3, sin Python ni torch).
                 Útil en Windows si no se puede instalar deepfilternet.
    rnnoise      Filtro `arnndn` de ffmpeg con un modelo de github.com/richardpl/arnndn-models.
    noisereduce  Compuerta espectral (pip noisereduce). Último recurso.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
import tempfile
import types
import urllib.request
import zipfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from . import util

DFN_ZIP_URL = "https://github.com/Rikorose/DeepFilterNet/raw/main/models/DeepFilterNet3.zip"
DFN_BIN_URLS = {
    ("Linux", "x86_64"): "deep-filter-0.5.6-x86_64-unknown-linux-musl",
    ("Linux", "aarch64"): "deep-filter-0.5.6-aarch64-unknown-linux-gnu",
    ("Windows", "AMD64"): "deep-filter-0.5.6-x86_64-pc-windows-msvc.exe",
    ("Darwin", "arm64"): "deep-filter-0.5.6-aarch64-apple-darwin",
    ("Darwin", "x86_64"): "deep-filter-0.5.6-x86_64-apple-darwin",
}
DFN_BIN_BASE = "https://github.com/Rikorose/DeepFilterNet/releases/download/v0.5.6/"
RNNOISE_URL = "https://raw.githubusercontent.com/richardpl/arnndn-models/master/{}"


def mezcla_desde_atenuacion(atenuacion_db: float) -> float:
    """Fracción de señal procesada que deja pasar como máximo `atenuacion_db` de reducción."""
    return float(1.0 - 10 ** (-abs(atenuacion_db) / 20.0))


def _descargar(url: str, destino: Path) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_suffix(destino.suffix + ".part")
    util.log(f"  descargando {url}")
    with urllib.request.urlopen(url, timeout=120) as r, open(tmp, "wb") as f:
        while True:
            b = r.read(1 << 20)
            if not b:
                break
            f.write(b)
    os.replace(tmp, destino)
    return destino


# ----------------------------------------------------------------------------
# Procesamiento por bloques con contexto y fundido (para modelos con estado)
# ----------------------------------------------------------------------------


def por_bloques(x: np.ndarray, sr: int, fn, bloque_s: float = 60.0, contexto_s: float = 2.0,
                fundido_s: float = 0.05, paralelo: int = 1) -> np.ndarray:
    n = len(x)
    L = int(bloque_s * sr)
    C = int(contexto_s * sr)
    F = int(fundido_s * sr)
    if n <= L + C:
        return fn(x)
    nucleos = [(s, min(n, s + L)) for s in range(0, n, L)]
    regiones = [(max(0, s - C), min(n, e + C)) for s, e in nucleos]

    def trabajo(k):
        lo, hi = regiones[k]
        return fn(x[lo:hi])

    if paralelo > 1:
        with ThreadPoolExecutor(max_workers=paralelo) as ex:
            salidas = list(ex.map(trabajo, range(len(nucleos))))
    else:
        salidas = [trabajo(k) for k in range(len(nucleos))]
    y = np.zeros(n, dtype=np.float32)
    peso = np.zeros(n, dtype=np.float32)
    for (s, e), (lo, hi), out in zip(nucleos, regiones, salidas):
        a = max(lo, s - F // 2)
        b = min(hi, e + F // 2)
        seg = out[a - lo : b - lo]
        w = np.ones(b - a, dtype=np.float32)
        if a > 0 and s > 0:
            k = min(F, b - a)
            w[:k] = np.linspace(0, 1, k, dtype=np.float32)
        if b < n:
            k = min(F, b - a)
            w[-k:] = np.minimum(w[-k:], np.linspace(1, 0, k, dtype=np.float32))
        y[a:b] += seg[: b - a] * w
        peso[a:b] += w
    return y / np.maximum(peso, 1e-6)


# ----------------------------------------------------------------------------
# DeepFilterNet3 (Python)
# ----------------------------------------------------------------------------

_DFN = None


def _parche_torchaudio():
    """deepfilternet 0.5.6 importa torchaudio.backend.common, que torchaudio ≥ 2.1 ya no trae.
    Solo usa AudioMetaData como tipo: alcanza con un módulo sustituto."""
    try:
        import torchaudio.backend.common  # noqa: F401
    except Exception:
        m = types.ModuleType("torchaudio.backend.common")

        class AudioMetaData:  # noqa: D401 - sustituto
            pass

        m.AudioMetaData = AudioMetaData
        sys.modules.setdefault("torchaudio.backend", types.ModuleType("torchaudio.backend"))
        sys.modules["torchaudio.backend.common"] = m


def _dir_modelo_dfn(modelos: Path) -> Path:
    d = modelos / "deepfilternet" / "DeepFilterNet3"
    if (d / "config.ini").exists():
        return d
    z = modelos / "deepfilternet" / "DeepFilterNet3.zip"
    if not z.exists():
        _descargar(DFN_ZIP_URL, z)
    with zipfile.ZipFile(z) as zf:
        zf.extractall(modelos / "deepfilternet")
    return d


def dfn_disponible() -> bool:
    try:
        _parche_torchaudio()
        import df.enhance  # noqa: F401
        import torch  # noqa: F401

        return True
    except Exception:
        return False


def _cargar_dfn(modelos: Path, hilos: int):
    global _DFN
    if _DFN is None:
        _parche_torchaudio()
        import torch
        from df.enhance import init_df

        torch.set_num_threads(hilos)
        model, st, _ = init_df(str(_dir_modelo_dfn(modelos)), log_level="ERROR", log_file=None)
        _DFN = (model, st)
    return _DFN


def ruido_dfn(x: np.ndarray, sr: int, atenuacion_db: float, hilos: int, modelos: Path) -> np.ndarray:
    import torch
    from df.enhance import enhance

    assert sr == 48000, "DeepFilterNet3 trabaja a 48 kHz"
    model, st = _cargar_dfn(modelos, hilos)

    def fn(seg):
        with torch.no_grad():
            t = torch.from_numpy(np.ascontiguousarray(seg, dtype=np.float32))[None]
            y = enhance(model, st, t, pad=True, atten_lim_db=atenuacion_db)
        return y.numpy()[0].astype(np.float32)

    return por_bloques(x, sr, fn, bloque_s=60.0, contexto_s=2.0)


# ----------------------------------------------------------------------------
# DeepFilterNet3 (ejecutable oficial deep-filter)
# ----------------------------------------------------------------------------


def _ruta_dfn_bin(modelos: Path, descargar: bool = True) -> Path | None:
    env = os.environ.get("VOZ_DEEP_FILTER")
    if env and Path(env).exists():
        return Path(env)
    exe = "deep-filter.exe" if platform.system() == "Windows" else "deep-filter"
    p = modelos / "deepfilternet" / exe
    if p.exists():
        return p
    import shutil

    w = shutil.which("deep-filter")
    if w:
        return Path(w)
    if not descargar:
        return None
    nombre = DFN_BIN_URLS.get((platform.system(), platform.machine()))
    if not nombre:
        return None
    try:
        _descargar(DFN_BIN_BASE + nombre, p)
        p.chmod(0o755)
        return p
    except Exception as e:
        util.log(f"  no pude descargar deep-filter: {e}")
        return None


def ruido_dfn_bin(x: np.ndarray, sr: int, atenuacion_db: float, hilos: int, modelos: Path) -> np.ndarray:
    import soundfile as sf

    exe = _ruta_dfn_bin(modelos)
    if exe is None:
        raise RuntimeError("deep-filter no disponible")

    def fn(seg):
        with tempfile.TemporaryDirectory(prefix="dfnbin_") as td:
            td = Path(td)
            ent = td / "in.wav"
            sf.write(str(ent), seg.astype(np.float32), sr, subtype="FLOAT")
            r = subprocess.run([str(exe), "-D", "-a", f"{abs(atenuacion_db):g}", "-o", str(td / "out"),
                                str(ent)], capture_output=True, text=True)
            if r.returncode != 0:
                raise RuntimeError(f"deep-filter falló: {r.stderr[-800:]}")
            y, _ = sf.read(str(td / "out" / "in.wav"), dtype="float32")
        if y.ndim > 1:
            y = y[:, 0]
        out = np.zeros(len(seg), dtype=np.float32)
        out[: min(len(y), len(seg))] = y[: len(seg)]
        return out

    # el binario usa un solo hilo: se reparten bloques entre `hilos` procesos
    return por_bloques(x, sr, fn, bloque_s=60.0, contexto_s=2.0, paralelo=max(1, hilos))


# ----------------------------------------------------------------------------
# RNNoise (ffmpeg arnndn)
# ----------------------------------------------------------------------------


def _modelo_rnnoise(modelos: Path, nombre: str = "std.rnnn") -> Path:
    p = modelos / "rnnoise" / nombre
    if not p.exists():
        _descargar(RNNOISE_URL.format(nombre), p)
    return p


def ruido_rnnoise(x: np.ndarray, sr: int, atenuacion_db: float, hilos: int, modelos: Path,
                  modelo: str = "std.rnnn") -> np.ndarray:
    import soundfile as sf

    m = _modelo_rnnoise(modelos, modelo)
    mix = mezcla_desde_atenuacion(atenuacion_db)
    with tempfile.TemporaryDirectory(prefix="rnn_") as td:
        td = Path(td).resolve()
        ent, sal = td / "in.wav", td / "out.wav"
        sf.write(str(ent), x.astype(np.float32), sr, subtype="FLOAT")
        # Se corre ffmpeg parado en la carpeta del modelo y se le pasa solo el nombre: así no
        # hay que escapar "C:\..." dentro del filtro (en Windows es una trampa clásica).
        util.correr_ffmpeg(["-i", str(ent), "-af", f"arnndn=m={m.name}:mix={mix:.4f}",
                            "-c:a", "pcm_f32le", str(sal)], hilos=hilos, cwd=m.resolve().parent)
        y, _ = sf.read(str(sal), dtype="float32")
    out = np.zeros(len(x), dtype=np.float32)
    out[: min(len(y), len(x))] = y[: len(x)]
    return out


# ----------------------------------------------------------------------------
# noisereduce
# ----------------------------------------------------------------------------


def ruido_noisereduce(x: np.ndarray, sr: int, atenuacion_db: float, hilos: int,
                      modelos: Path) -> np.ndarray:
    import noisereduce as nr

    from . import analisis

    act = analisis.actividad(x, sr)
    hop = int(act["hop_s"] * sr)
    quietos = np.flatnonzero(act["db"] < act["piso"] + 3)
    if len(quietos) > 50:
        ruido = np.concatenate([x[i * hop : i * hop + hop] for i in quietos[:3000]])
        y = nr.reduce_noise(y=x, sr=sr, y_noise=ruido, stationary=True,
                            prop_decrease=mezcla_desde_atenuacion(atenuacion_db), n_jobs=hilos)
    else:
        y = nr.reduce_noise(y=x, sr=sr, stationary=False,
                            prop_decrease=mezcla_desde_atenuacion(atenuacion_db), n_jobs=hilos)
    return y.astype(np.float32)


BACKENDS = {
    "dfn": ruido_dfn,
    "dfn-bin": ruido_dfn_bin,
    "rnnoise": ruido_rnnoise,
    "noisereduce": ruido_noisereduce,
}


def reducir_ruido(x: np.ndarray, sr: int, backend: str = "auto", atenuacion_db: float = 15.0,
                  hilos: int = 2, modelos: Path | None = None) -> tuple[np.ndarray, dict]:
    modelos = Path(modelos) if modelos else util.directorio_modelos()
    if backend in ("ninguno", "off", "no"):
        return x, {"backend": "ninguno"}
    orden = [backend] if backend != "auto" else ["dfn", "dfn-bin", "rnnoise", "noisereduce"]
    errores = {}
    for b in orden:
        if b == "dfn" and not dfn_disponible():
            errores[b] = "deepfilternet no instalado"
            continue
        if b == "dfn-bin" and _ruta_dfn_bin(modelos, descargar=True) is None:
            errores[b] = "ejecutable deep-filter no disponible para esta plataforma"
            continue
        try:
            y = BACKENDS[b](x, sr, atenuacion_db, hilos, modelos)
            info = {"backend": b, "atenuacion_max_db": atenuacion_db}
            if errores:
                info["descartados"] = errores
            return y, info
        except Exception as e:  # probar el siguiente
            errores[b] = f"{type(e).__name__}: {e}"
            util.log(f"  backend {b} falló: {errores[b]}")
    raise RuntimeError(f"Ningún backend de ruido funcionó: {errores}")
