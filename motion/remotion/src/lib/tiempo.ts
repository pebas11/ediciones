import React, {createContext, useContext} from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';

/**
 * Tiempo absoluto del video.
 *
 * Dentro de un <Sequence>, useCurrentFrame() devuelve el cuadro LOCAL (arranca en 0).
 * Para sincronizar con la voz o la música hace falta el cuadro ABSOLUTO de la línea de
 * tiempo maestra. <ProveedorTiempoAbsoluto> lo publica desde el nivel superior.
 *
 * Reglas:
 * - En la composición maestra, envolver todo en <ProveedorTiempoAbsoluto> (fuera de las Sequence).
 * - Una escena registrada sola en el Studio puede envolverse con `desfase` = su inicio en
 *   cuadros: así ve el mismo tiempo absoluto que dentro del video completo.
 * - Si ya hay un proveedor más arriba, los internos no hacen nada (gana el de afuera).
 */
const CuadroAbsoluto = createContext<number | null>(null);

export const ProveedorTiempoAbsoluto: React.FC<{
  readonly desfase?: number;
  readonly children: React.ReactNode;
}> = ({desfase = 0, children}) => {
  const exterior = useContext(CuadroAbsoluto);
  const frame = useCurrentFrame();
  if (exterior !== null) {
    return React.createElement(React.Fragment, null, children);
  }
  return React.createElement(CuadroAbsoluto.Provider, {value: frame + desfase}, children);
};

/** Cuadro absoluto (o el local si no hay proveedor). */
export const useCuadroAbsoluto = (): number => {
  const absoluto = useContext(CuadroAbsoluto);
  const local = useCurrentFrame();
  return absoluto ?? local;
};

/** Segundos absolutos del cuadro actual. */
export const useTiempoAbsoluto = (): number => {
  const {fps} = useVideoConfig();
  return useCuadroAbsoluto() / fps;
};

/**
 * Segundos → cuadro. Redondea al cuadro más cercano: un evento a 1,009 s con 60 fps
 * cae en el cuadro 61 (1,0167 s), que es el que se ve cuando suena.
 */
export const segundosACuadro = (segundos: number, fps: number): number =>
  Math.round(segundos * fps);

export const cuadroASegundos = (cuadro: number, fps: number): number => cuadro / fps;

/** Búsqueda binaria: índice del último elemento con clave <= x, o -1. */
export const ultimoIndiceHasta = <T>(
  lista: readonly T[],
  x: number,
  clave: (v: T) => number,
): number => {
  let lo = 0;
  let hi = lista.length - 1;
  let res = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (clave(lista[mid]) <= x) {
      res = mid;
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return res;
};
