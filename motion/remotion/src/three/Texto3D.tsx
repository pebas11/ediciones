import {Text} from '@react-three/drei';
import {useThree} from '@react-three/fiber';
import React, {Suspense, useCallback, useEffect, useLayoutEffect, useRef} from 'react';
import {useDelayRender} from 'remotion';

/**
 * Texto 3D (SDF de troika vía drei <Text>) seguro para render cuadro a cuadro.
 *
 * troika arma los glifos en un web worker, de forma asincrónica y SIN avisarle a React:
 * si no se espera, el primer cuadro de un still o de un tramo sale sin texto. Este
 * componente retiene el render (delayRender) hasta que troika avisa con onSync, y
 * vuelve a dibujar el cuadro actual (advance) antes de liberarlo. Si el texto cambia,
 * vuelve a esperar.
 *
 * Detalles que importan (aprendidos a la fuerza):
 * - <Text> suspende al montar (precarga la fuente). Va dentro de un <Suspense> PROPIO:
 *   si la suspensión subiera, React descartaría el estado de este componente y un
 *   delayRender creado en el render quedaría huérfano (timeout).
 * - El delayRender se crea en useLayoutEffect (solo en commit) y antes del useEffect en
 *   el que <ThreeCanvas> dibuja.
 *
 * `fuente`: .woff/.ttf/.otf (troika NO lee woff2), p. ej. staticFile('fuentes/x.woff').
 */
export const Texto3D: React.FC<React.ComponentProps<typeof Text> & {readonly fuente: string}> = ({
  fuente,
  onSync,
  ...props
}) => {
  const {delayRender, continueRender} = useDelayRender();
  const advance = useThree((s) => s.advance);
  const contenido = `${fuente}|${String(props.children ?? '')}`;
  const sincronizado = useRef<string | null>(null);
  const pendiente = useRef<number | null>(null);

  useLayoutEffect(() => {
    if (sincronizado.current !== contenido && pendiente.current === null) {
      pendiente.current = delayRender(`Esperando glifos de troika (${String(props.children).slice(0, 30)})`);
    }
  });

  // Si se desmonta antes de sincronizar, no dejar el render trabado.
  useEffect(
    () => () => {
      if (pendiente.current !== null) continueRender(pendiente.current);
    },
    [continueRender],
  );

  const alSincronizar = useCallback(
    (malla: Parameters<NonNullable<React.ComponentProps<typeof Text>['onSync']>>[0]) => {
      onSync?.(malla);
      sincronizado.current = contenido;
      if (pendiente.current !== null) {
        advance(performance.now());
        continueRender(pendiente.current);
        pendiente.current = null;
      }
    },
    [advance, continueRender, contenido, onSync],
  );

  return (
    <Suspense fallback={null}>
      <Text font={fuente} onSync={alSincronizar} {...props} />
    </Suspense>
  );
};
