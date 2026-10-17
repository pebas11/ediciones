import {loadFont} from '@remotion/google-fonts/LeagueSpartan';
import React, {useState} from 'react';
import {AbsoluteFill} from 'remotion';

/**
 * Diagnóstico de @remotion/google-fonts. La fuente se pide recién al montar esta
 * composición (no al importar el módulo), así un fallo de red no afecta a las demás.
 * El proyecto usa fuentes LOCALES (src/lib/fuentes.ts); esto solo verifica la vía web.
 */
export const PruebaGoogleFonts: React.FC = () => {
  const [{fontFamily}] = useState(() => loadFont('normal', {weights: ['800'], subsets: ['latin']}));
  return (
    <AbsoluteFill style={{backgroundColor: '#1b1712', justifyContent: 'center', alignItems: 'center'}}>
      <div style={{fontFamily, fontWeight: 800, fontSize: 160, color: '#f3eadb'}}>Google Fonts</div>
    </AbsoluteFill>
  );
};
