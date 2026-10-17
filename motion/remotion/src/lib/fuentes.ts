import {loadFont} from '@remotion/fonts';
import {staticFile} from 'remotion';

/**
 * Tipografía del proyecto (CLAUDE.md): League Spartan para titulares, DM Sans para el
 * cuerpo y DM Mono para rótulos. Archivos locales en public/fuentes (OFL), así el
 * render no depende de internet.
 *
 * Por qué no @remotion/google-fonts por defecto: en el contenedor la red intercepta TLS
 * con una CA propia y Chrome rechaza fonts.gstatic.com (net::ERR_CERT_AUTHORITY_INVALID);
 * funciona solo agregando --ignore-certificate-errors (probado con la composición
 * PruebaGoogleFonts). Con archivos locales el render no depende de la red y da lo mismo
 * en Linux, en Windows y sin conexión.
 *
 * loadFont() bloquea el render (delayRender) hasta que la fuente está lista.
 */
export const FUENTES = {
  titular: '"League Spartan", "DM Sans", sans-serif',
  cuerpo: '"DM Sans", "League Spartan", sans-serif',
  mono: '"DM Mono", monospace',
} as const;

const ARCHIVOS: ReadonlyArray<readonly [family: string, archivo: string, peso: string]> = [
  ['League Spartan', 'league-spartan-latin-400-normal.woff2', '400'],
  ['League Spartan', 'league-spartan-latin-500-normal.woff2', '500'],
  ['League Spartan', 'league-spartan-latin-600-normal.woff2', '600'],
  ['League Spartan', 'league-spartan-latin-700-normal.woff2', '700'],
  ['League Spartan', 'league-spartan-latin-800-normal.woff2', '800'],
  ['League Spartan', 'league-spartan-latin-900-normal.woff2', '900'],
  ['DM Sans', 'dm-sans-latin-400-normal.woff2', '400'],
  ['DM Sans', 'dm-sans-latin-500-normal.woff2', '500'],
  ['DM Sans', 'dm-sans-latin-700-normal.woff2', '700'],
  ['DM Mono', 'dm-mono-latin-400-normal.woff2', '400'],
  ['DM Mono', 'dm-mono-latin-500-normal.woff2', '500'],
];

let cargadas: Promise<unknown> | null = null;

/** Idempotente: se puede llamar desde varios módulos. */
export const cargarFuentes = (): Promise<unknown> => {
  if (!cargadas) {
    cargadas = Promise.all(
      ARCHIVOS.map(([family, archivo, weight]) =>
        loadFont({family, url: staticFile(`fuentes/${archivo}`), weight, display: 'block'}),
      ),
    );
  }
  return cargadas;
};

cargarFuentes();
