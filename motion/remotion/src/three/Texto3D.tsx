import {Text} from '@react-three/drei';
import {useThree} from '@react-three/fiber';
import React, {useCallback, useState} from 'react';
import {useDelayRender} from 'remotion';

/**
 * Texto 3D (SDF de troika vía drei <Text>) seguro para render cuadro a cuadro.
 *
 * troika arma los glifos en un web worker, de forma asincrónica y SIN Suspense: si no
 * se espera, el primer cuadro de un still o de un tramo sale sin texto. Este componente
 * retiene el render (delayRender) hasta que troika avisa con onSync y vuelve a dibujar
 * el cuadro actual (advance) antes de liberarlo.
 *
 * `fuente`: .woff/.ttf/.otf (troika NO lee woff2), p. ej. staticFile('fuentes/x.woff').
 */
export const Texto3D: React.FC<
  React.ComponentProps<typeof Text> & {readonly fuente: string}
> = ({fuente, onSync, ...props}) => {
  const {delayRender, continueRender} = useDelayRender();
  const advance = useThree((s) => s.advance);
  const [handle, setHandle] = useState<number | null>(() =>
    delayRender(`Esperando glifos de troika (${String(props.children).slice(0, 30)})`),
  );
  const alSincronizar = useCallback(
    (malla: Parameters<NonNullable<React.ComponentProps<typeof Text>['onSync']>>[0]) => {
      onSync?.(malla);
      if (handle !== null) {
        advance(performance.now());
        continueRender(handle);
        setHandle(null);
      }
    },
    [advance, continueRender, handle, onSync],
  );
  return <Text font={fuente} onSync={alSincronizar} {...props} />;
};
