"""Mezclador final de música y voz (ver `motion/musica/MEZCLA.md`).

    python3 motion/musica/mezcla_voz.py --voz voz_final.wav --plan plan.json --out salida/

Módulos:
    config     parámetros por defecto, fusión y validación de claves
    canciones  catálogo de canciones renderizadas (cues.json + stems) y lectura de audio
    plan       esquema del plan musical (plan.json), validación con mensajes claros
    voz        carga de la voz, actividad (habla / pausas) y envolvente
    armado     edición musical: compases, loops, acortes, anclas y transiciones → EDL
    render     EDL → stems armados (fundidos adaptativos, colas de reverb) → cama
    ducking    control de ducking por stem, realce en pausas y EQ dinámica
    niveles    sonoridad BS.1770 por bloques de 100 ms y niveles por bloque musical
    master     ganancia a −14 LUFS, limitador true-peak con anticipo, dither y WAV
    informe    métricas de QA (niveles, clicks, empalmes, ducking) → informe.json
    envolventes  envolventes.json por cuadro para la animación (formato de Remotion)
    grafico    mezcla.png para revisar sin oídos
"""
import os as _os

# Hilos limitados ANTES de importar numpy/scipy/numba: la máquina se comparte.
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
           "NUMBA_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    _os.environ.setdefault(_v, "2")

SR = 48000
STEMS = ("bateria", "bajo", "armonia", "melodia", "textura")
VERSION = "1.0"
