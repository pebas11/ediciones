import {evolvePath} from '@remotion/paths';
import React, {useMemo} from 'react';

/**
 * Trazo SVG que se dibuja: progreso 0 = nada, 1 = completo.
 * evolvePath (@remotion/paths) calcula dasharray/dashoffset con el largo real del path.
 * Para usar dentro de un <svg>.
 */
export const Trazo: React.FC<{
  readonly d: string;
  readonly progreso: number;
  readonly color?: string;
  readonly grosor?: number;
  readonly opacidad?: number;
  /** Dibuja desde el final hacia el principio. */
  readonly invertido?: boolean;
}> = ({
  d,
  progreso,
  color = '#efe3cf',
  grosor = 3,
  opacidad = 1,
  invertido = false,
}) => {
  const p = Math.min(1, Math.max(0, progreso));
  // evolvePath mide el path: memorizar el cálculo del largo por (d, p) es barato igual.
  const {strokeDasharray, strokeDashoffset} = useMemo(
    () => evolvePath(p, d),
    [p, d],
  );
  if (p <= 0) return null;
  return (
    <path
      d={d}
      fill="none"
      stroke={color}
      strokeWidth={grosor}
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeDasharray={strokeDasharray}
      strokeDashoffset={
        invertido ? -Number(strokeDashoffset) : strokeDashoffset
      }
      opacity={opacidad}
    />
  );
};

/**
 * Path suave (Catmull-Rom → Bézier cúbicas) que pasa por los puntos dados.
 * Útil para curvas orgánicas generadas con ruido.
 */
export const pathSuave = (
  puntos: ReadonlyArray<readonly [number, number]>,
  tension = 1,
): string => {
  if (puntos.length < 2) return '';
  const p = puntos;
  let d = `M ${p[0][0].toFixed(2)} ${p[0][1].toFixed(2)}`;
  for (let i = 0; i < p.length - 1; i++) {
    const p0 = p[Math.max(0, i - 1)];
    const p1 = p[i];
    const p2 = p[i + 1];
    const p3 = p[Math.min(p.length - 1, i + 2)];
    const c1x = p1[0] + ((p2[0] - p0[0]) / 6) * tension;
    const c1y = p1[1] + ((p2[1] - p0[1]) / 6) * tension;
    const c2x = p2[0] - ((p3[0] - p1[0]) / 6) * tension;
    const c2y = p2[1] - ((p3[1] - p1[1]) / 6) * tension;
    d += ` C ${c1x.toFixed(2)} ${c1y.toFixed(2)}, ${c2x.toFixed(2)} ${c2y.toFixed(2)}, ${p2[0].toFixed(2)} ${p2[1].toFixed(2)}`;
  }
  return d;
};
