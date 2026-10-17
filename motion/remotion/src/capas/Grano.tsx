import React, {useLayoutEffect, useMemo, useRef} from 'react';
import {random, useCurrentFrame, useVideoConfig} from 'remotion';
import {crearAzar} from '../lib/azar';

/**
 * Grano de película animado y sembrado, en CSS/Canvas 2D (para escenas SIN 3D).
 * En escenas 3D usar el grano del postproceso (src/three/EfectoGrano.ts): es gratis.
 *
 * Se genera UNA textura de ruido (determinista por semilla) y en cada paso se pinta en
 * un <canvas> como patrón desplazado a una posición pseudoaleatoria (random() de
 * Remotion). Se dibuja en useLayoutEffect: sincrónico, sin imágenes que decodificar a
 * mitad del render (por eso no se usa background-image, que Remotion no espera).
 *
 * `cadencia`: cuadros que dura cada patrón. 2 a 60 fps = grano a 30 Hz, más "fílmico".
 * Ojo con YouTube: el grano fino de 1 px se pierde y sube mucho el bitrate. Mejor
 * `escala` ≥ 1.5 y poca intensidad. Sin GPU cuesta ~0,13–0,18 s por cuadro (medido).
 */
const LADO = 512;

/**
 * - 'normal' (por defecto): ruido blanco/negro con alfa y fusión normal. Barato.
 * - 'overlay' u otro mix-blend-mode: ruido gris centrado en 128. Respeta negros y blancos
 *   puros, pero sin GPU cuesta ~0,45 s por cuadro (la fusión lee el fondo cada vez).
 */
const crearTextura = (semilla: string, alfa: boolean): HTMLCanvasElement => {
  const canvas = document.createElement('canvas');
  canvas.width = LADO;
  canvas.height = LADO;
  const ctx = canvas.getContext('2d');
  if (!ctx) throw new Error('No hay contexto 2D para generar el grano');
  const img = ctx.createImageData(LADO, LADO);
  const azar = crearAzar(`grano:${semilla}`);
  for (let i = 0; i < LADO * LADO; i++) {
    const n = azar() + azar() - 1; // [-1, 1], distribución triangular
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
  return canvas;
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
  const {width, height} = useVideoConfig();
  const ref = useRef<HTMLCanvasElement>(null);
  const conAlfa = modo === 'normal';
  const textura = useMemo(
    () => crearTextura(semilla, conAlfa),
    [semilla, conAlfa],
  );

  const paso = Math.floor(frame / Math.max(1, cadencia));
  const lado = LADO * escala;
  const dx = Math.floor(random(`${semilla}:x:${paso}`) * lado);
  const dy = Math.floor(random(`${semilla}:y:${paso}`) * lado);

  useLayoutEffect(() => {
    const ctx = ref.current?.getContext('2d');
    if (!ctx) return;
    const patron = ctx.createPattern(textura, 'repeat');
    if (!patron) return;
    patron.setTransform(new DOMMatrix().translate(-dx, -dy).scale(escala));
    ctx.clearRect(0, 0, width, height);
    ctx.imageSmoothingEnabled = false;
    ctx.fillStyle = patron;
    ctx.fillRect(0, 0, width, height);
  }, [textura, dx, dy, escala, width, height]);

  return (
    <canvas
      ref={ref}
      width={width}
      height={height}
      style={{
        position: 'absolute',
        inset: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        mixBlendMode: conAlfa ? undefined : modo,
        opacity: intensidad,
      }}
    />
  );
};
