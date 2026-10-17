"""Instrumentos disponibles (ver README.md para parámetros y ejemplos)."""
from .base import Instrumento, Banco, CACHE  # noqa: F401
from .muestreados import (Muestreador, Piano, Arpa, Glock, Vibrafono, Cuerdas,  # noqa: F401
                          Violines, Violas, Chelos, Contrabajo, CuerdasTrem, Pizzicato)
from .sintes import Celesta, Rhodes, Pad, Dron, Sub  # noqa: F401
from .bateria import Bateria  # noqa: F401
from .texturas import (Textura, nube_granular, swell_invertido, swell, nube,  # noqa: F401
                       nube_de_banco)

__all__ = ["Instrumento", "Banco", "Muestreador", "Piano", "Arpa", "Glock", "Vibrafono",
           "Cuerdas", "Violines", "Violas", "Chelos", "Contrabajo", "CuerdasTrem", "Pizzicato",
           "Celesta", "Rhodes", "Pad", "Dron", "Sub", "Bateria", "Textura", "nube_granular",
           "swell_invertido", "swell", "nube", "nube_de_banco"]
