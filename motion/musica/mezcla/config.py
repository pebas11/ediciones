"""Parámetros del mezclador: valores por defecto, fusión con el plan y con la línea de comandos.

Todos los parámetros viven en un árbol de diccionarios (`DEFECTOS`). El plan puede cambiar
cualquiera en `"parametros"` y la CLI con `--param ruta.al.valor=X`. Las claves desconocidas
son un error (con sugerencia), así un error de tipeo no pasa en silencio.
"""
from __future__ import annotations

import copy
import difflib
import json

from . import STEMS

DEFECTOS: dict = {
    "voz": {
        "lufs_esperado": -16.0,      # sonoridad esperada del archivo de voz (aviso si se aparta > 1 LU)
        "umbral_db": -32.0,          # actividad: dB por debajo del nivel activo del habla (p95)
        "histeresis_db": 6.0,        # la actividad se apaga recién `histeresis_db` más abajo
        "min_habla_ms": 60.0,        # ráfagas más cortas no cuentan como habla
        "hueco_palabras_ms": 300.0,  # huecos más cortos quedan dentro de la frase
    },
    "ducking": {
        "activo": True,
        "lookahead_ms": 50.0,        # la bajada empieza este tiempo ANTES de la voz
        "ataque_ms": 80.0,           # duración de la bajada (rampa coseno)
        "relajacion_ms": 600.0,      # duración de la subida en las pausas (rampa coseno)
        "mantener_ms": 200.0,        # espera después de la última sílaba antes de subir
        "pausa_minima_s": 0.6,       # pausas más cortas: la música no sube (anti-bombeo)
        "pausa_completa_s": 2.0,     # pausas de este largo o más: sube del todo
        "profundidad_db": {"melodia": -10.0, "armonia": -6.0, "textura": -6.0,
                           "bateria": -3.0, "bajo": -3.0},
        "eq": {
            "activo": True,
            "desde_hz": 1500.0,      # franja de presencia de la voz
            "hasta_hz": 4000.0,
            "ganancia_db": -4.0,     # en el centro de la franja (campana ancha)
            "stems": ["armonia", "melodia", "textura"],
        },
    },
    "niveles": {
        "musica_bajo_voz_lu": -20.0,  # cama vs voz en sonoridad de corto plazo, mientras habla
        "ventana_lu": 2.0,            # tolerancia: ±2 → 18–22 dB por debajo de la voz
        "conservar_dinamica": 0.5,    # fracción de la diferencia de sonoridad entre secciones que se respeta
        "realce_pausas_db": 3.0,      # extra en pausas largas
        "pausa_larga_s": 2.5,
        "realce_intro_db": 6.0,       # extra antes de la primera palabra y después de la última
        "rampa_realce_s": 1.2,
        "rampa_bloque_tiempos": 2.0,  # cambio de nivel entre secciones: rampa que termina en el downbeat
        "corregir": True,             # segunda pasada: mide la cama real y corrige cada bloque
        "tolerancia_lu": 0.5,
        "guardia_voz": True,          # baja la cama donde, mientras se habla, supera objetivo + ventana
        "guardia_max_db": 6.0,
    },
    "empalmes": {
        "loop_tiempos": 1.0,          # fundido en cada vuelta de loop
        "empalme_tiempos": 0.5,       # fundido en saltos entre secciones y cortes
        "guarda_ms": 30.0,            # los fundidos terminan este tiempo antes del downbeat (ataques humanizados)
        "entrada_ms": 10.0,           # fundido de entrada en las entradas "a golpe"
        "alinear_fase_ms": 5.0,       # búsqueda de desfase en empalmes de la misma canción (0 = no)
        "stems_ritmicos": ["bateria", "bajo"],   # nunca se superponen entre canciones distintas
    },
    "transiciones": {
        "fundido_tiempos": 4.0,
        "cola_s": 3.0,
        "pausa_silencio_s": 2.0,
        "final_fundido_tiempos": 8.0,
        "corte_cola_tiempos": 0.5,    # en cola/pausa: fundido del sonido directo antes de la cola de reverb
        "ritmicos_salida_tiempos": 0.5,
        "reverb": {
            "nivel_db": -12.0,        # cola sintética respecto de la señal de entrada (IR de energía 1)
            "dur": 3.6, "predelay_ms": 28.0, "brillo": 0.45, "ancho": 1.0,
            "ventana_tiempos": 2.0,   # cuánto material previo alimenta la reverb
            "stems": ["armonia", "melodia", "textura"],
        },
    },
    "master": {
        "lufs": -14.0,
        "techo_dbtp": -1.0,
        "lookahead_ms": 5.0,
        "relajacion_ms": 80.0,
        "margen_db": 0.1,
        "max_reduccion_voz_db": 1.0,  # aviso si el limitador trabaja más que esto sobre la voz
    },
    "salidas": {
        "fps": 60.0,
        "rango_db": 48.0,             # envolventes: rango dinámico mapeado a 0..1
        "png": True,
        "qa": True,
    },
}


class ErrorParametros(ValueError):
    pass


def _tipo(v) -> str:
    if isinstance(v, bool):
        return "booleano"
    if isinstance(v, (int, float)):
        return "número"
    if isinstance(v, str):
        return "texto"
    if isinstance(v, list):
        return "lista"
    if isinstance(v, dict):
        return "objeto"
    return type(v).__name__


def sugerir(clave: str, opciones) -> str:
    m = difflib.get_close_matches(clave, list(opciones), n=1, cutoff=0.6)
    return f" (¿quisiste decir '{m[0]}'?)" if m else ""


def fusionar(base: dict, cambios: dict, ruta: str = "parametros", errores: list | None = None) -> dict:
    """Copia de `base` con `cambios` aplicados en profundidad. Valida claves y tipos."""
    propio = errores is None
    errores = [] if propio else errores
    out = copy.deepcopy(base)
    if not isinstance(cambios, dict):
        errores.append(f"{ruta}: se esperaba un objeto, llegó {_tipo(cambios)}")
    else:
        for k, v in cambios.items():
            r = f"{ruta}.{k}"
            if k not in base:
                errores.append(f"{r}: clave desconocida{sugerir(k, base)}. Válidas: {', '.join(base)}")
                continue
            b = base[k]
            if isinstance(b, dict):
                if not isinstance(v, dict):
                    errores.append(f"{r}: se esperaba un objeto, llegó {_tipo(v)}")
                    continue
                if k == "profundidad_db":
                    for s in v:
                        if s not in STEMS:
                            errores.append(f"{r}.{s}: stem desconocido{sugerir(s, STEMS)}. Válidos: {', '.join(STEMS)}")
                out[k] = fusionar(b, {s: x for s, x in v.items() if s in b}, r, errores)
            elif isinstance(b, bool):
                if not isinstance(v, bool):
                    errores.append(f"{r}: se esperaba true/false, llegó {_tipo(v)}")
                    continue
                out[k] = v
            elif isinstance(b, (int, float)):
                if isinstance(v, bool) or not isinstance(v, (int, float)):
                    errores.append(f"{r}: se esperaba un número, llegó {_tipo(v)} ({v!r})")
                    continue
                out[k] = float(v)
            elif isinstance(b, list):
                if not isinstance(v, list):
                    errores.append(f"{r}: se esperaba una lista, llegó {_tipo(v)}")
                    continue
                if k == "stems" or k == "stems_ritmicos":
                    malos = [s for s in v if s not in STEMS]
                    if malos:
                        errores.append(f"{r}: stems desconocidos {malos}. Válidos: {', '.join(STEMS)}")
                        continue
                out[k] = list(v)
            else:
                out[k] = v
    if propio and errores:
        raise ErrorParametros("\n".join(errores))
    return out


def validar_rangos(p: dict, errores: list):
    """Rangos razonables (errores claros en vez de resultados absurdos)."""
    def rango(ruta, lo, hi):
        partes = ruta.split(".")
        v = p
        for x in partes:
            v = v[x]
        if not (lo <= v <= hi):
            errores.append(f"parametros.{ruta} = {v} fuera de rango [{lo}, {hi}]")

    rango("ducking.lookahead_ms", 0, 500)
    rango("ducking.ataque_ms", 5, 2000)
    rango("ducking.relajacion_ms", 20, 10000)
    rango("ducking.mantener_ms", 0, 3000)
    rango("ducking.pausa_minima_s", 0, 30)
    rango("ducking.pausa_completa_s", 0.05, 60)
    for s, v in p["ducking"]["profundidad_db"].items():
        if not (-40 <= v <= 0):
            errores.append(f"parametros.ducking.profundidad_db.{s} = {v}: tiene que estar entre −40 y 0 dB")
    rango("ducking.eq.ganancia_db", -18, 0)
    rango("ducking.eq.desde_hz", 200, 12000)
    rango("ducking.eq.hasta_hz", 300, 16000)
    if p["ducking"]["eq"]["hasta_hz"] <= p["ducking"]["eq"]["desde_hz"] * 1.1:
        errores.append("parametros.ducking.eq: 'hasta_hz' tiene que ser mayor que 'desde_hz'")
    if p["ducking"]["pausa_completa_s"] <= p["ducking"]["pausa_minima_s"]:
        errores.append("parametros.ducking: 'pausa_completa_s' tiene que ser mayor que 'pausa_minima_s'")
    rango("niveles.musica_bajo_voz_lu", -40, -6)
    rango("niveles.ventana_lu", 0, 10)
    rango("niveles.conservar_dinamica", 0, 1)
    rango("niveles.realce_pausas_db", 0, 18)
    rango("niveles.realce_intro_db", 0, 24)
    rango("niveles.pausa_larga_s", 0.5, 60)
    rango("niveles.guardia_max_db", 0, 18)
    rango("empalmes.loop_tiempos", 0.125, 8)
    rango("empalmes.empalme_tiempos", 0.0625, 8)
    rango("empalmes.guarda_ms", 0, 100)
    rango("empalmes.entrada_ms", 1, 200)
    rango("empalmes.alinear_fase_ms", 0, 20)
    rango("transiciones.fundido_tiempos", 0.25, 64)
    rango("transiciones.cola_s", 0.5, 12)
    rango("transiciones.pausa_silencio_s", 0, 30)
    rango("transiciones.reverb.nivel_db", -40, 0)
    rango("transiciones.reverb.dur", 0.5, 8)
    rango("master.lufs", -30, -8)
    rango("master.techo_dbtp", -6, 0)
    rango("master.lookahead_ms", 1, 20)
    rango("salidas.fps", 1, 240)


def asignar(p: dict, ruta: str, valor_txt: str):
    """`--param ducking.ataque_ms=60` → p["ducking"]["ataque_ms"] = 60 (valor en JSON o texto)."""
    try:
        valor = json.loads(valor_txt)
    except json.JSONDecodeError:
        valor = valor_txt
    partes = ruta.split(".")
    cambio: dict = {}
    nodo = cambio
    for x in partes[:-1]:
        nodo[x] = {}
        nodo = nodo[x]
    nodo[partes[-1]] = valor
    return fusionar(p, cambio, "--param")
