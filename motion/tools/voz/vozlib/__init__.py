"""Pipeline de voz: extracción, limpieza, transcripción y propuesta de edición.

Módulos:
    util         ffmpeg, lectura/escritura de audio, JSON, cronómetro.
    dsp          filtros, envolventes, pico verdadero, suavizado de ganancia.
    analisis     métricas del audio (ruido, LUFS, picos, DC, zumbido, espectro, reverb).
    limpieza     cadena de limpieza natural (pasa-altos ... normalización).
    ruido        backends de reducción de ruido (DeepFilterNet3, RNNoise, noisereduce).
    transcribir  faster-whisper + ajuste de bordes de palabra por energía.
    edicion      propuesta de EDL (silencios, muletillas, repeticiones, bloopers).
    render       aplicación de la EDL (cortes con fundido, re-mapeo de palabras, video).
    espectro     espectrogramas PNG para revisar la limpieza.
"""

__version__ = "1.0.0"
