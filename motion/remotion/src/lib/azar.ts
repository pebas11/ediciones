import {random} from 'remotion';

/**
 * Azar determinista. Prohibido Math.random(): cada pestaña de render y cada tramo
 * tiene que producir exactamente el mismo cuadro.
 *
 * crearAzar('particulas') devuelve una función que entrega una secuencia fija de
 * números en [0, 1), siempre la misma para la misma semilla. Usa random() de Remotion
 * con semillas de texto ("semilla:k"), que no colisionan entre generadores.
 */
export const crearAzar = (semilla: string) => {
  let k = 0;
  return (): number => random(`${semilla}:${k++}`);
};

export const entre = (azar: () => number, min: number, max: number): number =>
  min + (max - min) * azar();

/** Valor fijo para (semilla, índice) sin estado: útil dentro de un map(). */
export const azarEn = (semilla: string, i: number): number => random(`${semilla}#${i}`);
