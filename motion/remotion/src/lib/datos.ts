import {useEffect, useState} from 'react';
import {useDelayRender} from 'remotion';

/**
 * Carga de JSON desde public/ (vía staticFile) con caché por pestaña.
 * - cargarJSON(): promesa; sirve también dentro de calculateMetadata.
 * - useJSON(): hook que bloquea el render (delayRender) hasta tener los datos.
 *
 * Cada pestaña de render carga el archivo una sola vez, no una vez por cuadro.
 */
const cache = new Map<string, Promise<unknown>>();

export const cargarJSON = <T = unknown>(src: string): Promise<T> => {
  let p = cache.get(src);
  if (!p) {
    p = fetch(src).then((r) => {
      if (!r.ok) {
        throw new Error(`No se pudo cargar ${src}: HTTP ${r.status}`);
      }
      return r.json();
    });
    cache.set(src, p);
    p.catch(() => cache.delete(src));
  }
  return p as Promise<T>;
};

/**
 * `src` = null → no carga nada y devuelve null (para datos opcionales).
 * `src` tiene que ser fijo durante la vida del componente.
 */
export const useJSON = <T>(src: string | null, transformar?: (crudo: unknown) => T): T | null => {
  const {delayRender, continueRender, cancelRender} = useDelayRender();
  // delayRender lo antes posible (en el primer render), no en un efecto: evita una
  // carrera en la que Remotion captura el cuadro antes de que empiece la carga.
  const [handle] = useState(() => (src ? delayRender(`Cargando ${src}`) : null));
  const [datos, setDatos] = useState<{src: string; valor: T} | null>(null);

  useEffect(() => {
    if (!src) return;
    let vivo = true;
    cargarJSON(src)
      .then((crudo) => {
        if (!vivo) return;
        setDatos({src, valor: transformar ? transformar(crudo) : (crudo as T)});
        if (handle !== null) continueRender(handle);
      })
      .catch((e) => cancelRender(e));
    return () => {
      vivo = false;
    };
    // `transformar` suele ser una función inline: no se incluye para no recargar en cada render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src, handle, continueRender, cancelRender]);

  return datos && datos.src === src ? datos.valor : null;
};
