import React from 'react';
import {AbsoluteFill, useVideoConfig} from 'remotion';
import {parallax, type EstadoCamara} from '../lib/camara';

/**
 * Capa 2D que se mueve como si estuviera a `profundidad` metros delante de la cámara
 * de referencia. Usa el mismo EstadoCamara que el 3D, así ambos quedan pegados.
 * profundidad chica = primer plano (se mueve mucho); grande = fondo (casi quieto).
 */
export const CapaParallax: React.FC<{
  readonly camara: EstadoCamara;
  readonly referencia: EstadoCamara;
  readonly profundidad: number;
  readonly children: React.ReactNode;
  readonly style?: React.CSSProperties;
}> = ({camara, referencia, profundidad, children, style}) => {
  const {width, height} = useVideoConfig();
  const {dx, dy, escala} = parallax(
    camara,
    referencia,
    profundidad,
    width,
    height,
  );
  return (
    <AbsoluteFill
      style={{
        translate: `${dx}px ${dy}px`,
        scale: escala,
        transformOrigin: '50% 50%',
        // SIN will-change: con will-change Chrome reutiliza el rasterizado de un cuadro
        // anterior y lo re-muestrea; el resultado depende de la historia y el primer cuadro
        // de un tramo no coincide con el mismo cuadro a mitad de un render (medido).
        ...style,
      }}
    >
      {children}
    </AbsoluteFill>
  );
};
