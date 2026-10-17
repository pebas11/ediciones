"""Motor de síntesis y producción musical del proyecto (48 kHz, estéreo, determinista).

Uso típico (ver README.md):

    from motor import *
    C = Cancion("Umbral", slug="01-umbral", bpm=88, compas=(4, 4), tonalidad="D lidio", semilla=7)
    C.seccion("intro", 8, energia=0.15, emocion="misterio")
    ...
"""
import os as _os

# Limitar hilos ANTES de importar numpy/scipy/numba (la máquina se comparte).
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMBA_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    _os.environ.setdefault(_v, "2")

from .nucleo import (SR, db, desde_db, midi_a_hz, hz_a_midi, nota, nombre_nota,  # noqa: E402,F401
                     rng, Auto)
from .teoria import (Acorde, acorde, escala, conducir, voicing_abierto,  # noqa: E402,F401
                     MODOS)
from .secuencia import Cancion, Pista, Nota, melodia  # noqa: E402,F401
from .instrumentos import *  # noqa: E402,F401,F403
from .figuras import espiral, columna  # noqa: E402,F401
from .efectos import (EQ, Filtro, Saturacion, Chorus, Tremolo, Ducking,  # noqa: E402,F401
                      Compresor, Ancho, Paneo)

__all__ = [n for n in dir() if not n.startswith("_")]
