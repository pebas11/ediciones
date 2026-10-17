"""Catálogo de canciones renderizadas por el motor: cues.json + stems, compases y lectura de audio.

Cada canción vive en `motion/musica/salida/<slug>/` con `cues.json` y `stems/*.wav`
(48 kHz, mismo largo; sumados = premaster). Acá no se modifica nada: solo se lee.

Convenciones (las de `cues.json`):
* compases 1-indexados; `downbeats_s` trae n+1 valores (el último es el final del último compás);
* `compas_fin` de secciones y loops es inclusivo; los loops van de downbeat a downbeat.
* "pulso" = tiempo sentido del compás: 4/4 → 4, 3/4 → 3, 6/8 → 2, 12/8 → 4.
"""
from __future__ import annotations

import json
import unicodedata
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import soundfile as sf

from . import SR, STEMS

DIR_SALIDA = Path(__file__).resolve().parents[1] / "salida"


class ErrorCancion(ValueError):
    pass


def normalizar(txt: str) -> str:
    t = unicodedata.normalize("NFKD", str(txt)).encode("ascii", "ignore").decode().lower()
    return "".join(c for c in t if c.isalnum())


def pulsos_por_compas(num: int, den: int) -> int:
    if den == 8 and num % 3 == 0 and num >= 6:
        return num // 3          # compuesto: 6/8 → 2, 9/8 → 3, 12/8 → 4
    return max(1, num)


@dataclass
class Seccion:
    nombre: str
    c0: int            # primer compás
    c1: int            # último compás (inclusive)
    energia: float
    emocion: str
    bajo_voz: bool
    loop: tuple[int, int]   # (primer compás, último compás inclusive)
    lufs: float | None


class Cancion:
    """Una canción renderizada: mapa de compases y acceso a sus stems."""

    def __init__(self, carpeta: Path):
        self.carpeta = Path(carpeta)
        ruta = self.carpeta / "cues.json"
        try:
            c = json.loads(ruta.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise ErrorCancion(f"{self.carpeta.name}: falta cues.json") from None
        except json.JSONDecodeError as e:
            raise ErrorCancion(f"{ruta}: JSON inválido ({e})") from None
        self.cues = c
        self.slug = c.get("slug", self.carpeta.name)
        self.titulo = c.get("titulo", self.slug)
        self.bpm = float(c.get("bpm", 0) or 0)
        comp = str(c.get("compas", "4/4"))
        try:
            num, den = (int(v) for v in comp.split("/"))
        except ValueError:
            raise ErrorCancion(f"{self.slug}: compás inválido en cues.json: {comp!r}") from None
        self.num, self.den = num, den
        self.compas_txt = comp
        self.pulsos = pulsos_por_compas(num, den)
        self.db = np.asarray(c.get("downbeats_s", []), dtype=np.float64)
        if len(self.db) < 2 or np.any(np.diff(self.db) <= 0):
            raise ErrorCancion(f"{self.slug}: downbeats_s ausentes o no crecientes en cues.json")
        self.n_compases = len(self.db) - 1
        self.secciones: list[Seccion] = []
        for s in c.get("secciones", []):
            lp = s.get("loop") or {}
            c0, c1 = int(s["compas_inicio"]), int(s["compas_fin"])
            loop = (int(lp.get("compas_inicio", c0)), int(lp.get("compas_fin", c1)))
            if not (c0 <= loop[0] <= loop[1] <= c1):
                loop = (c0, c1)
            self.secciones.append(Seccion(s["nombre"], c0, c1, float(s.get("energia", 0.5)),
                                          str(s.get("emocion", "")), bool(s.get("bajo_voz", False)),
                                          loop, s.get("lufs")))
        if not self.secciones:
            self.secciones.append(Seccion("todo", 1, self.n_compases, 0.5, "", False,
                                          (1, self.n_compases), None))
        cola = c.get("cola") or {}
        self.fin_musica_s = float(cola.get("inicio_s", self.db[-1]))
        self.duracion_s = float(c.get("duracion_s", 0) or 0)
        # stems
        self.rutas = {s: self.carpeta / "stems" / f"{s}.wav" for s in STEMS}
        faltan = [s for s, r in self.rutas.items() if not r.exists()]
        if faltan:
            raise ErrorCancion(f"{self.slug}: faltan stems {faltan} en {self.carpeta / 'stems'}")
        largos = set()
        for s, r in self.rutas.items():
            info = sf.info(str(r))
            if info.samplerate != SR:
                raise ErrorCancion(f"{self.slug}: {r.name} está a {info.samplerate} Hz (se espera {SR})")
            largos.add(info.frames)
        if len(largos) != 1:
            raise ErrorCancion(f"{self.slug}: los stems no tienen el mismo largo ({sorted(largos)}): "
                               "¿se está renderizando todavía?")
        self.n = largos.pop()
        if self.duracion_s and abs(self.n / SR - self.duracion_s) > 0.05:
            raise ErrorCancion(f"{self.slug}: los stems duran {self.n / SR:.2f} s y cues.json dice "
                               f"{self.duracion_s:.2f} s: ¿render incompleto?")
        self._potencias = None
        self._factor_eq: dict = {}

    # ------------------------------------------------------------ compases
    def __repr__(self):
        return f"Cancion({self.slug}, {self.bpm:g} bpm, {self.compas_txt}, {self.n_compases} compases)"

    def t(self, compas: float, pulso: float = 1.0) -> float:
        """Segundos del pulso `pulso` (1 = downbeat) del compás `compas` (1-indexado)."""
        c = int(compas)
        if c < 1 or c > self.n_compases + 1:
            raise ErrorCancion(f"{self.slug}: compás {c} fuera de rango (1–{self.n_compases})")
        base = self.db[c - 1]
        if pulso == 1.0 or c == self.n_compases + 1:
            return float(base)
        return float(base + (pulso - 1.0) * self.dur(c) / self.pulsos)

    def dur(self, compas: int) -> float:
        c = int(compas)
        if c > self.n_compases:   # fuera del final: se extrapola con el último compás
            return float(self.db[-1] - self.db[-2])
        return float(self.db[c] - self.db[c - 1])

    def pulso_s(self, compas: int) -> float:
        return self.dur(compas) / self.pulsos

    def compas_en(self, t: float) -> int:
        i = int(np.searchsorted(self.db, t, side="right"))
        return int(np.clip(i, 1, self.n_compases))

    def seccion(self, nombre: str) -> Seccion:
        for s in self.secciones:
            if s.nombre == nombre:
                return s
        n = normalizar(nombre)
        for s in self.secciones:
            if normalizar(s.nombre) == n:
                return s
        raise KeyError(nombre)

    def seccion_de(self, compas: int) -> Seccion:
        for s in self.secciones:
            if s.c0 <= compas <= s.c1:
                return s
        return self.secciones[-1] if compas > self.secciones[-1].c1 else self.secciones[0]

    def es_ultimo(self, compas: int) -> bool:
        return compas >= self.n_compases

    # ------------------------------------------------------------ audio
    def leer(self, stem: str, a: int, b: int) -> np.ndarray:
        """Muestras [a, b) del stem (estéreo float32); fuera del archivo devuelve ceros."""
        n = int(b - a)
        out = np.zeros((max(0, n), 2), np.float32)
        lo, hi = max(0, int(a)), min(self.n, int(b))
        if hi > lo:
            with sf.SoundFile(str(self.rutas[stem])) as f:
                f.seek(lo)
                x = f.read(hi - lo, dtype="float32", always_2d=True)
            if x.shape[1] == 1:
                x = np.repeat(x, 2, axis=1)
            out[lo - a: lo - a + len(x)] = x[:, :2]
        return out

    def leer_suma(self, a: int, b: int, stems=STEMS, ganancias=None) -> np.ndarray:
        acc = np.zeros((max(0, int(b - a)), 2), np.float32)
        for s in stems:
            g = 1.0 if ganancias is None else ganancias.get(s, 1.0)
            if g:
                acc += self.leer(s, a, b) * np.float32(g)
        return acc

    # ------------------------------------------------------------ análisis (perezoso, en memoria)
    def potencias_k(self):
        """Potencias ponderadas K en sub-bloques de 100 ms: las propias de cada stem (clave = stem)
        y las cruzadas entre pares (clave = (stem_i, stem_j)), para calcular la sonoridad de
        cualquier combinación de ganancias sin renderizar: P = Σ a_i² P_ii + 2 Σ a_i a_j P_ij.
        Las cruzadas importan: el dron y el pad comparten fundamentales y suman más que sus
        potencias por separado."""
        if self._potencias is None:
            from scipy.signal import sosfilt, sosfilt_zi
            from .niveles import K_SOS, SUB
            trozo = SUB * 200                       # 20 s
            nb = int(np.ceil(self.n / SUB))
            claves = list(STEMS) + [(a, b) for i, a in enumerate(STEMS) for b in STEMS[i + 1:]]
            acc = {k: np.zeros(nb) for k in claves}
            cuenta = np.zeros(nb)
            zi = {s: np.repeat(sosfilt_zi(K_SOS)[:, :, None], 2, axis=2) * 0.0 for s in STEMS}
            for a in range(0, self.n, trozo):
                b = min(self.n, a + trozo)
                y = {}
                for s in STEMS:
                    y[s], zi[s] = sosfilt(K_SOS, self.leer(s, a, b).astype(np.float64), axis=0, zi=zi[s])
                idx = (a + np.arange(b - a)) // SUB
                cuenta += np.bincount(idx, minlength=nb)[:nb]
                for k in claves:
                    if isinstance(k, str):
                        prod = (y[k] * y[k]).sum(axis=1)
                    else:
                        prod = (y[k[0]] * y[k[1]]).sum(axis=1)
                    acc[k] += np.bincount(idx, weights=prod, minlength=nb)[:nb]
            for k in claves:
                acc[k] /= np.maximum(cuenta, 1)
            self._potencias = acc
        return self._potencias

    def potencia_mezcla(self, amp: dict, idx) -> np.ndarray:
        """Potencia K por sub-bloque (índices `idx` de la fuente) de Σ amp_s · stem_s, con amp_s
        escalar o array por sub-bloque."""
        pot = self.potencias_k()
        out = np.zeros(len(idx))
        for i, a in enumerate(STEMS):
            if a not in amp:
                continue
            ga = amp[a]
            out += ga * ga * pot[a][idx]
            for b in STEMS[i + 1:]:
                if b in amp:
                    out += 2.0 * ga * amp[b] * pot[(a, b)][idx]
        return np.maximum(out, 0.0)

    def factor_eq(self, stem: str, eq: dict) -> float:
        """Fracción de la potencia ponderada K del stem que queda con la EQ dinámica a fondo
        (para estimar niveles sin renderizar)."""
        clave = (stem, eq["desde_hz"], eq["hasta_hz"], eq["ganancia_db"])
        if clave not in self._factor_eq:
            from scipy.signal import welch, sosfreqz
            from .niveles import K_SOS
            from .ducking import sos_eq
            x = self.leer(stem, 0, self.n).mean(axis=1)
            if np.abs(x).max() < 1e-6:
                self._factor_eq[clave] = 1.0
            else:
                f, P = welch(x, SR, nperseg=8192)
                _, hk = sosfreqz(K_SOS, worN=f, fs=SR)
                _, hb = sosfreqz(sos_eq(eq["desde_hz"], eq["hasta_hz"]), worN=f, fs=SR)
                g = 10 ** (eq["ganancia_db"] / 20)
                pk = P * np.abs(hk) ** 2
                self._factor_eq[clave] = float(np.sum(pk * np.abs(1 - (1 - g) * hb) ** 2) / (np.sum(pk) + 1e-30))
        return self._factor_eq[clave]


# ---------------------------------------------------------------- catálogo --
def catalogo(dir_salida: Path | None = None) -> dict[str, Path]:
    d = Path(dir_salida) if dir_salida else DIR_SALIDA
    out = {}
    if not d.exists():
        return out
    for p in sorted(d.iterdir()):
        if p.is_dir() and not p.name.startswith("_") and (p / "cues.json").exists():
            out[p.name] = p
    return out


class Catalogo:
    def __init__(self, dir_salida: Path | None = None):
        self.dir = Path(dir_salida) if dir_salida else DIR_SALIDA
        self.rutas = catalogo(self.dir)
        self._cargadas: dict[str, Cancion] = {}

    def resolver(self, nombre) -> str:
        """slug exacto, número ("01", 1), nombre ("umbral") o título → slug."""
        if not self.rutas:
            raise ErrorCancion(f"no hay canciones renderizadas en {self.dir}")
        txt = str(nombre).strip()
        if txt in self.rutas:
            return txt
        n = normalizar(txt)
        for slug in self.rutas:
            num, _, nom = slug.partition("-")
            if txt.isdigit() and num.isdigit() and int(num) == int(txt):
                return slug
            if n and (n == normalizar(nom) or n == normalizar(slug)):
                return slug
        for slug, p in self.rutas.items():
            try:
                tit = json.loads((p / "cues.json").read_text(encoding="utf-8")).get("titulo", "")
            except Exception:
                tit = ""
            if n and n == normalizar(tit):
                return slug
        raise ErrorCancion(f"la canción '{nombre}' no existe en {self.dir} "
                           f"(hay: {', '.join(self.rutas)})")

    def cargar(self, nombre) -> Cancion:
        slug = self.resolver(nombre)
        if slug not in self._cargadas:
            self._cargadas[slug] = Cancion(self.rutas[slug])
        return self._cargadas[slug]
