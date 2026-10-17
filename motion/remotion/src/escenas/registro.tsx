import React from 'react';
import {LineaDeTiempo, type PropsLinea, type RegistroEscenas} from '../composiciones/LineaDeTiempo';
import {ProveedorCalidad, type Calidad} from '../three/calidad';
import {EscenaMundo3D} from './EscenaMundo3D';
import {EscenaTitulo} from './EscenaTitulo';
import {EscenaTrazos} from './EscenaTrazos';

/**
 * Registro de tipos de escena del video de EJEMPLO: "tipo" de la hoja de cues →
 * componente. El video real va a tener su propio registro con las escenas del estilo
 * definitivo; la línea de tiempo no cambia.
 */
export const REGISTRO_EJEMPLO: RegistroEscenas = {
  mundo3d: EscenaMundo3D,
  trazos: EscenaTrazos,
  titulo: EscenaTitulo,
};

export type PropsVideo = PropsLinea & {readonly calidad: Calidad};

/** Composición del video de ejemplo: hoja de cues + registro + calidad. */
export const VideoEjemplo: React.FC<PropsVideo> = ({calidad, ...props}) => (
  <ProveedorCalidad calidad={calidad}>
    <LineaDeTiempo {...props} registro={REGISTRO_EJEMPLO} />
  </ProveedorCalidad>
);
