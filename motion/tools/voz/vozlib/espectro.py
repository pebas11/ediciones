"""Espectrogramas PNG (antes/después) para revisar que la limpieza no deje artefactos."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy import signal


def comparar(senales: list[tuple[str, np.ndarray]], sr: int, ruta: Path,
             t0: float | None = None, t1: float | None = None, fmax: float = 16000,
             nperseg: int = 2048, vmin: float = -110, vmax: float = -20, titulo: str = "") -> Path:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = len(senales)
    fig, axs = plt.subplots(n, 1, figsize=(14, 3.0 * n + 0.6), sharex=True, squeeze=False)
    for ax, (nombre, x) in zip(axs[:, 0], senales):
        a = int((t0 or 0) * sr)
        b = int(t1 * sr) if t1 else len(x)
        seg = x[a:b].astype(np.float64)
        # paso adaptativo: ≤ ~2500 columnas aunque el audio dure 25 minutos
        hop = max(nperseg // 4, len(seg) // 2500)
        if len(seg) < nperseg:
            seg = np.pad(seg, (0, nperseg - len(seg)))
        marcos = np.lib.stride_tricks.sliding_window_view(seg, nperseg)[::hop]
        win = signal.get_window("hann", nperseg)
        S = np.abs(np.fft.rfft(marcos * win, axis=1)) ** 2 / (np.sum(win) ** 2) * 2
        S = 10 * np.log10(S.T + 1e-20)
        f = np.fft.rfftfreq(nperseg, 1 / sr)
        t = (np.arange(S.shape[1]) * hop + nperseg / 2) / sr
        sel = f <= fmax
        ext = [(t0 or 0) + (t[0] if len(t) else 0), (t0 or 0) + (t[-1] if len(t) else 0),
               f[sel][0] / 1000, f[sel][-1] / 1000]
        im = ax.imshow(S[sel], origin="lower", aspect="auto", extent=ext, cmap="magma",
                       vmin=vmin, vmax=vmax, interpolation="nearest")
        ax.set_ylabel("kHz")
        ax.set_title(nombre, fontsize=10, loc="left")
    axs[-1, 0].set_xlabel("s")
    fig.colorbar(im, ax=axs[:, 0].tolist(), label="dBFS", pad=0.01)
    if titulo:
        fig.suptitle(titulo, fontsize=11)
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(ruta, dpi=80)
    plt.close(fig)
    return ruta


def espectro_promedio(senales: list[tuple[str, np.ndarray]], sr: int, ruta: Path,
                      fmax: float = 20000, titulo: str = "") -> Path:
    """Espectro promedio (Welch) superpuesto: útil para ver zumbido, ruido y EQ."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(12, 4.5))
    for nombre, x in senales:
        f, P = signal.welch(x.astype(np.float64), fs=sr, nperseg=16384, average="median")
        ax.semilogx(f[1:], 10 * np.log10(P[1:] + 1e-20), label=nombre, lw=1)
    ax.set_xlim(30, fmax)
    ax.set_xlabel("Hz")
    ax.set_ylabel("dB (mediana)")
    ax.grid(True, which="both", alpha=0.3)
    ax.legend()
    if titulo:
        ax.set_title(titulo)
    ruta = Path(ruta)
    fig.savefig(ruta, dpi=80, bbox_inches="tight")
    plt.close(fig)
    return ruta
