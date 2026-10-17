import {Audio} from '@remotion/media';
import {ThreeCanvas} from '@remotion/three';
import React, {useMemo} from 'react';
import {
  AbsoluteFill,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import {z} from 'zod';
import {CapaParallax} from '../capas/CapaParallax';
import {CodigoDeCuadro} from '../capas/Depuracion';
import {Grano} from '../capas/Grano';
import {LineaDePalabras} from '../capas/LineaDePalabras';
import {Titulo} from '../capas/Titulo';
import {pathSuave, Trazo} from '../capas/Trazo';
import {Vineta} from '../capas/Vineta';
import {
  nivelAR,
  ProveedorAudio,
  pulso,
  useEnvolventes,
  volumenConDucking,
} from '../lib/audio';
import {crearAzar, entre} from '../lib/azar';
import {
  escalaEnPantalla,
  estadoCamara,
  proyectar,
  type OpcionesRig,
} from '../lib/camara';
import {useJSON} from '../lib/datos';
import '../lib/fuentes';
import {fbm, progreso} from '../lib/movimiento';
import {ProveedorTiempoAbsoluto} from '../lib/tiempo';
import {cuadroDePalabra, useTranscripcion} from '../lib/transcripcion';
import {CALIDAD} from '../three/calidad';
import {CENTRO_ENSUENO, MundoPrueba, PALETA_PRUEBA} from '../three/MundoPrueba';

/**
 * PRUEBA TÉCNICA (10 s, 1920×1080, 60 fps). No es un diseño: ejercita todo lo que va a
 * necesitar el video largo y sirve de banco de pruebas para medir el render.
 *
 *  3D: luces y sombras, shader propio, 50k partículas instanciadas, niebla, DOF y
 *      tone mapping en postproceso, cámara en movimiento (rig puro compartido con 2D).
 *  2D: trazos SVG que se dibujan (con parallax), anotación anclada a un punto 3D,
 *      titular con fuente web local, frase de la voz desde la transcripción.
 *  Overlay: grano sembrado + viñeta.
 *  Audio: música (con ducking por la voz), voz sintética y clics de sincronía.
 *  Depuración: código de cuadro + marca de sincronía (scripts/verificar-sync.py).
 */
export const esquemaPrueba = z.object({
  calidad: z.enum(['final', 'borrador']),
  depuracion: z.boolean(),
  tono: z.enum(['agx', 'aces', 'neutral']),
  /**
   * Ajustes finos para medir el costo de cada parte (scripts/bench.mjs).
   * Pisan los del preset de calidad.
   */
  perfil: z
    .object({
      msaa: z.number().optional(),
      dof: z.boolean().optional(),
      postproceso: z.boolean().optional(),
      particulas: z.number().optional(),
      sombra: z.number().optional(),
      dpr: z.number().optional(),
      grano: z.boolean().optional(),
      granoCss: z.boolean().optional(),
      dofEscala: z.number().optional(),
      bufer8: z.boolean().optional(),
      vineta: z.boolean().optional(),
      trazos: z.boolean().optional(),
      texto: z.boolean().optional(),
      sin3d: z.boolean().optional(),
    })
    .optional(),
});

export type PropsPrueba = z.infer<typeof esquemaPrueba>;

export const RIG_PRUEBA: OpcionesRig = {
  claves: [
    {t: 0, posicion: [8.6, 2.7, 9.6], objetivo: [0, 1.5, 0], fov: 34},
    {
      t: 4,
      posicion: [5.1, 2.1, 7.3],
      objetivo: [0, 1.5, 0],
      fov: 34,
      curva: 'respiro',
    },
    {
      t: 7,
      posicion: [0.9, 1.85, 6.1],
      objetivo: [0, 1.6, 0],
      fov: 32,
      curva: 'respiro',
    },
    {
      t: 10,
      posicion: [-3.7, 1.95, 5.1],
      objetivo: [0, 1.6, 0],
      fov: 30,
      curva: 'respiro',
    },
  ],
  respiracion: {amplitud: [0.06, 0.04, 0.06], frecuencia: 0.25},
  rolido: {amplitud: 0.012},
};

/** Curvas orgánicas deterministas para la capa de trazos (en px de 1920×1080). */
const crearCurvas = () => {
  const azar = crearAzar('curvas-prueba');
  return Array.from({length: 3}, (_, k) => {
    const y0 = 700 + k * 70 + entre(azar, -20, 20);
    const pts: Array<[number, number]> = [];
    for (let i = 0; i <= 14; i++) {
      const x = 110 + i * 62;
      const y =
        y0 +
        fbm('curvas', i * 0.35, {frecuencia: 1, octavas: 2, canal: k}) * 70 -
        i * 9;
      pts.push([x, y]);
    }
    return pathSuave(pts);
  });
};

export const PruebaTecnica: React.FC<PropsPrueba> = ({
  calidad,
  depuracion,
  tono,
  perfil,
}) => {
  const frame = useCurrentFrame();
  const {fps, width, height, durationInFrames} = useVideoConfig();
  const t = frame / fps;
  const q = {...CALIDAD[calidad], ...perfil};
  // Con postproceso, grano y viñeta van en WebGL (casi gratis). Si no, viñeta CSS y
  // grano CSS solo en escenas 2D o si se pide (sin GPU cuesta ~130 ms por cuadro).
  const granoWebgl =
    !perfil?.sin3d && q.postproceso && q.grano && !perfil?.granoCss;
  const granoCss =
    !granoWebgl &&
    perfil?.grano !== false &&
    (Boolean(perfil?.sin3d) || Boolean(perfil?.granoCss));

  const env = useEnvolventes(staticFile('datos/envolventes-prueba.json'));
  const voz = useTranscripcion(staticFile('datos/transcripcion-prueba.json'));
  const sync = useJSON<{clics: number[]}>(staticFile('datos/sync-prueba.json'));

  const camara = estadoCamara(t, RIG_PRUEBA);
  // Referencia del parallax: la misma cámara SIN la deriva. Las capas 2D flotan con la
  // "respiración" de la cámara y siguen en cuadro aunque la cámara recorra metros.
  const camaraBase = estadoCamara(t, {claves: RIG_PRUEBA.claves});
  const curvas = useMemo(crearCurvas, []);

  // Reacción al audio, precalculada (sin FFT en el render).
  const energia = env
    ? nivelAR(env, 'musica', frame, {
        banda: 'graves',
        ataque: 0.02,
        relajacion: 0.3,
      })
    : 0;
  const golpe = env?.musica
    ? pulso(env.musica.downbeats, frame, {caida: 18})
    : 0;
  const volMusica = useMemo(
    () =>
      env
        ? volumenConDucking(env, {fuente: 'voz', base: 0.85, reduccion: 0.55})
        : 0.85,
    [env],
  );

  // La anotación arranca cuando la voz dice "luz" (palabra clave → cuadro).
  const inicioAnotacion = voz ? cuadroDePalabra(voz, 'luz', fps) / fps : 5.5;

  // 2D anclado al 3D: el centro de la forma proyectado con la MISMA cámara.
  const centro = proyectar(CENTRO_ENSUENO, camara, width, height);
  const radioPx = escalaEnPantalla(1.32, centro.z, camara.fov, height);
  const anotacion = progreso(frame, fps, {
    inicio: inicioAnotacion,
    duracion: 0.9,
    curva: 'appleOut',
  });
  const finAnotacion = progreso(frame, fps, {
    inicio: 8.6,
    duracion: 0.5,
    curva: 'appleIn',
  });
  const circulo = `M ${centro.x + radioPx} ${centro.y} A ${radioPx} ${radioPx} 0 1 1 ${centro.x + radioPx - 0.01} ${centro.y - 0.5}`;
  const guia = `M ${centro.x + radioPx * 0.72} ${centro.y - radioPx * 0.72} L ${centro.x + radioPx * 1.45} ${centro.y - radioPx * 1.3} L ${centro.x + radioPx * 2.4} ${centro.y - radioPx * 1.3}`;

  const fundido = interpolate(
    frame,
    [0, 0.6 * fps, durationInFrames - 0.6 * fps, durationInFrames - 1],
    [0, 1, 1, 0],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
    },
  );

  return (
    <ProveedorTiempoAbsoluto>
      <ProveedorAudio envolventes={env}>
        <AbsoluteFill style={{backgroundColor: PALETA_PRUEBA.niebla}}>
          <AbsoluteFill style={{opacity: fundido}}>
            {perfil?.sin3d ? null : (
              <ThreeCanvas
                width={width}
                height={height}
                shadows
                dpr={q.dpr}
                gl={{
                  antialias: !q.postproceso,
                  powerPreference: 'high-performance',
                }}
                camera={{fov: 34, near: 0.1, far: 120, position: [8, 3, 9]}}
              >
                <MundoPrueba
                  tiempo={t}
                  camara={camara}
                  calidad={q}
                  energia={energia}
                  pulso={golpe}
                  tono={tono}
                />
              </ThreeCanvas>
            )}

            {/* Trazos en primer plano: se mueven como si estuvieran a 1,2 m de la cámara */}
            {perfil?.trazos === false ? null : (
              <CapaParallax
                camara={camara}
                referencia={camaraBase}
                profundidad={1.2}
              >
                <svg
                  width={width}
                  height={height}
                  style={{position: 'absolute', inset: 0}}
                >
                  {curvas.map((d, k) => (
                    <Trazo
                      key={k}
                      d={d}
                      progreso={progreso(frame, fps, {
                        inicio: 1.6 + k * 0.18,
                        duracion: 2.2,
                        curva: 'apple',
                      })}
                      color={PALETA_PRUEBA.ensuenoB}
                      grosor={2.5 - k * 0.5}
                      opacidad={
                        (0.75 - k * 0.15) *
                        (1 -
                          progreso(frame, fps, {
                            inicio: 7.8,
                            duracion: 0.8,
                            curva: 'appleIn',
                          }))
                      }
                    />
                  ))}
                </svg>
              </CapaParallax>
            )}

            {/* Anotación pegada a la forma 3D */}
            {perfil?.trazos === false ? null : (
              <svg
                width={width}
                height={height}
                style={{position: 'absolute', inset: 0}}
              >
                <g opacity={1 - finAnotacion}>
                  <Trazo
                    d={circulo}
                    progreso={anotacion}
                    color={PALETA_PRUEBA.borde}
                    grosor={2}
                  />
                  <Trazo
                    d={guia}
                    progreso={progreso(frame, fps, {
                      inicio: inicioAnotacion + 0.45,
                      duracion: 0.6,
                      curva: 'appleOut',
                    })}
                    color={PALETA_PRUEBA.borde}
                    grosor={2}
                  />
                </g>
              </svg>
            )}

            {perfil?.vineta === false || granoWebgl ? null : (
              <Vineta intensidad={0.6} radio={0.5} />
            )}
            {granoCss ? (
              <Grano intensidad={0.14} escala={1.5} cadencia={2} />
            ) : null}

            {/* Texto por encima de viñeta y grano */}
            {perfil?.texto === false ? null : (
              <>
                <AbsoluteFill
                  style={{padding: '0 140px', justifyContent: 'center'}}
                >
                  <Titulo
                    texto="Prueba de render"
                    entra={0.8}
                    sale={4.2}
                    tamano={132}
                    style={{marginTop: -220}}
                  />
                </AbsoluteFill>
                <AbsoluteFill
                  style={{
                    justifyContent: 'flex-end',
                    alignItems: 'center',
                    paddingBottom: 150,
                  }}
                >
                  <LineaDePalabras
                    transcripcion={voz}
                    style={{maxWidth: 1300}}
                  />
                </AbsoluteFill>
              </>
            )}
          </AbsoluteFill>

          {depuracion ? (
            <CodigoDeCuadro cuadrosSync={sync?.clics ?? []} />
          ) : null}
        </AbsoluteFill>

        <Audio
          src={staticFile('audio/prueba-musica.wav')}
          volume={volMusica}
          name="Música"
        />
        <Audio src={staticFile('audio/prueba-voz.wav')} volume={1} name="Voz" />
        {depuracion ? (
          <Audio
            src={staticFile('audio/prueba-clics.wav')}
            volume={1}
            name="Clics de sincronía"
          />
        ) : null}
      </ProveedorAudio>
    </ProveedorTiempoAbsoluto>
  );
};
