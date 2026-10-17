import React, {useMemo, useState} from 'react';
import {AbsoluteFill, random, useCurrentFrame, useDelayRender} from 'remotion';
import {crearAzar} from '../lib/azar';

/**
 * Grano de película animado y sembrado.
 *
 * Se genera UNA textura de ruido (determinista por semilla) y en cada paso se la
 * desplaza a una posición pseudoaleatoria con random() de Remotion. Dos capas a escalas
 * distintas esconden la repetición. Cambiar solo background-position es casi gratis
 * por cuadro; no se cambia de imagen, así no hay decodificaciones asincrónicas a mitad
 * del render (el primer cuadro espera a que la textura esté decodificada).
 *
 * `cadencia`: cuadros que dura cada patrón. 2 a 60 fps = grano a 30 Hz, más "fílmico".
 * Ojo con YouTube: el grano fino de 1 px se pierde y sube mucho el bitrate. Mejor
 * `escala` ≥ 1.5 y poca intensidad.
 */
const LADO = 512;

/**
 * - 'overlay': ruido gris centrado en 128 para mix-blend-mode (respeta negros y blancos
 *   puros, pero sin GPU cuesta ~450 ms por cuadro: la fusión lee el fondo cada vez).
 * - 'normal': ruido blanco/negro con alfa, fusión normal. Visualmente casi igual y mucho
 *   más barato. Es el modo por defecto.
 */
const crearTextura = (semilla: string, alfa: boolean): string => {
  const canvas = document.createElement('canvas');
  canvas.width = LADO;
  canvas.height = LADO;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('No hay contexto 2D para generar el grano');
  const img = ctx.createImageData(LADO, LADO);
  const azar = crearAzar(`grano:${semilla}`);
  for (let i = 0; i < LADO * LADO; i++) {
    // Suma de 2 uniformes → distribución triangular, centrada en 128 (gris neutro en overlay).
    const n = azar() + azar() - 1; // [-1, 1], triangular
    if (alfa) {
      const c = n > 0 ? 255 : 0;
      img.data[i * 4] = c;
      img.data[i * 4 + 1] = c;
      img.data[i * 4 + 2] = c;
      img.data[i * 4 + 3] = Math.abs(n) * 255;
    } else {
      const v = 128 + n * 120;
      img.data[i * 4] = v;
      img.data[i * 4 + 1] = v;
      img.data[i * 4 + 2] = v;
      img.data[i * 4 + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  return canvas.toDataURL('image/png');
};

export const Grano: React.FC<{
  readonly intensidad?: number;
  readonly semilla?: string;
  readonly escala?: number;
  readonly cadencia?: number;
  readonly modo?: React.CSSProperties['mixBlendMode'];
}> = ({
  intensidad = 0.12,
  semilla = 'grano',
  escala = 1.5,
  cadencia = 2,
  modo = 'normal',
}) => {
  const frame = useCurrentFrame();
  const {delayRender, continueRender, cancelRender} = useDelayRender();
  const conAlfa = modo === 'normal';
  const url = useMemo(() => crearTextura(semilla, conAlfa), [semilla, conAlfa]);
  const [listo] = useState(() => {
    const h = delayRender('Decodificando textura de grano');
    const img = new Image();
    img.src = url;
    img
      .decode()
      .then(() => continueRender(h))
      .catch((e) => cancelRender(e));
    return true;
  });

  const paso = Math.floor(frame / Math.max(1, cadencia));
  const lado = LADO * escala;
  const dx = Math.floor(random(`${semilla}:x:${paso}`) * lado);
  const dy = Math.floor(random(`${semilla}:y:${paso}`) * lado);
  return (
    <AbsoluteFill
      style={{
        pointerEvents: 'none',
        backgroundImage: `url(${url})`,
        backgroundSize: `${lado}px ${lado}px`,
        backgroundPosition: `${-dx}px ${-dy}px`,
        mixBlendMode: conAlfa ? undefined : modo,
        opacity: listo ? intensidad : 0,
      }}
    />
  );
};
