import React from 'react';
import {AbsoluteFill, Composition, Folder} from 'remotion';
import {DiagnosticoGL} from './composiciones/DiagnosticoGL';
import {PruebaDrei} from './composiciones/PruebaDrei';
import {PruebaGoogleFonts} from './composiciones/PruebaGoogleFonts';
import {metadatosLinea} from './composiciones/LineaDeTiempo';
import {esquemaPrueba, PruebaTecnica} from './composiciones/PruebaTecnica';
import {EscenaMundo3D} from './escenas/EscenaMundo3D';
import {EscenaTitulo} from './escenas/EscenaTitulo';
import {EscenaTrazos} from './escenas/EscenaTrazos';
import {VideoEjemplo, type PropsVideo} from './escenas/registro';

/** Segmento ficticio para previsualizar una escena sola en el Studio. */
const segmentoSuelto = (tipo: string, segundos: number) => ({
  clase: 'escena' as const,
  id: tipo,
  tipo,
  params: {},
  hueco: false,
  inicioCuadro: 0,
  finCuadro: segundos * 60,
  desdeCuadro: 0,
  duracion: segundos * 60,
});

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="PruebaTecnica"
        component={PruebaTecnica}
        schema={esquemaPrueba}
        width={1920}
        height={1080}
        fps={60}
        durationInFrames={600}
        defaultProps={{calidad: 'final', depuracion: true, tono: 'agx'}}
      />

      <Composition
        id="VideoEjemplo"
        component={VideoEjemplo}
        width={1920}
        height={1080}
        fps={60}
        durationInFrames={600}
        defaultProps={{hojaSrc: 'datos/cues-ejemplo.json', calidad: 'final'} as PropsVideo}
        calculateMetadata={metadatosLinea}
      />

      <Folder name="Escenas-ejemplo">
        <Composition
          id="Escena-Mundo3D"
          component={EscenaMundo3D}
          width={1920}
          height={1080}
          fps={60}
          durationInFrames={240}
          defaultProps={{params: {orbita: 30}, segmento: segmentoSuelto('mundo3d', 4)}}
        />
        <Composition
          id="Escena-Trazos"
          component={EscenaTrazos}
          width={1920}
          height={1080}
          fps={60}
          durationInFrames={180}
          defaultProps={{params: {cantidad: 11}, segmento: segmentoSuelto('trazos', 3)}}
        />
        <Composition
          id="Escena-Titulo"
          component={EscenaTitulo}
          width={1920}
          height={1080}
          fps={60}
          durationInFrames={180}
          defaultProps={{params: {texto: 'Sueño lúcido'}, segmento: segmentoSuelto('titulo', 3)}}
        />
      </Folder>

      <Folder name="Diagnostico">
        {/* Cuadro vacío: mide el costo fijo por cuadro (captura + codificación). */}
        <Composition
          id="Vacia"
          component={() => <AbsoluteFill style={{backgroundColor: '#2a231c'}} />}
          width={1920}
          height={1080}
          fps={60}
          durationInFrames={600}
        />
        <Composition
          id="PruebaDrei"
          component={PruebaDrei}
          width={1920}
          height={1080}
          fps={60}
          durationInFrames={120}
        />
        <Composition
          id="PruebaGoogleFonts"
          component={PruebaGoogleFonts}
          width={1920}
          height={1080}
          fps={60}
          durationInFrames={30}
        />
        <Composition
          id="DiagnosticoGL"
          component={DiagnosticoGL}
          width={1920}
          height={1080}
          fps={60}
          durationInFrames={60}
        />
      </Folder>
    </>
  );
};
