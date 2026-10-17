import {useFrame, useThree} from '@react-three/fiber';
import {
  DepthOfFieldEffect,
  EffectComposer,
  EffectPass,
  RenderPass,
  ToneMappingEffect,
  ToneMappingMode,
} from 'postprocessing';
import React, {useEffect, useLayoutEffect, useMemo} from 'react';
import {useCurrentFrame, useVideoConfig} from 'remotion';
import {
  HalfFloatType,
  NoToneMapping,
  UnsignedByteType,
  Vector2,
  type PerspectiveCamera,
  type Scene,
} from 'three';
import {EfectoGrano} from './EfectoGrano';
import {PaseCapa, type UniformsCapa} from './PaseCapa';

export type AjustesGrano = {
  /** Amplitud del grano (0.03–0.08 se ve como película). 0 = sin grano. */
  readonly intensidad?: number;
  /** Tamaño de la celda de grano en px (≥ 1.5 sobrevive mejor a la compresión de YouTube). */
  readonly escala?: number;
  /** Cuadros que dura cada patrón (2 a 60 fps = grano a 30 Hz). */
  readonly cadencia?: number;
  /** Oscurecimiento de bordes 0..1. */
  readonly vineta?: number;
  /** Dónde empieza la viñeta (0 = centro, 1 = bordes). */
  readonly radio?: number;
  readonly semilla?: number;
};

export type Tono = 'agx' | 'aces' | 'neutral';

const MODOS: Record<Tono, ToneMappingMode> = {
  agx: ToneMappingMode.AGX,
  aces: ToneMappingMode.ACES_FILMIC,
  neutral: ToneMappingMode.NEUTRAL,
};

/**
 * Postproceso con pmndrs/postprocessing, armado A MANO (sin @react-three/postprocessing).
 *
 * Por qué: el <EffectComposer> de @react-three/postprocessing crea el composer en un
 * useEffect y suma los pases 2–3 commits después, y <DepthOfField> recrea el efecto
 * cada vez que cambia el foco. Con <ThreeCanvas> (que dibuja UNA vez por cuadro) eso
 * deja vacío el primer cuadro de cada still/tramo y rompe el DOF con cámara en
 * movimiento. Acá:
 *  - el composer y los pases se crean en el render (useMemo): están listos antes de que
 *    <ThreeCanvas> dibuje el primer cuadro;
 *  - el foco se actualiza por uniforms en useLayoutEffect (no se recrea nada);
 *  - composer.render() recibe un delta fijo (1/fps): determinista.
 * Para sumar efectos (Bloom, SMAA, etc.), agregarlos a la cadena de abajo.
 */
export const Postproceso: React.FC<{
  readonly msaa: number;
  readonly tono?: Tono;
  readonly dof?: {
    readonly distancia: number;
    readonly rango: number;
    readonly bokeh?: number;
  } | null;
  /** Escena que se dibuja después del DOF (partículas, polvo, etc.). */
  readonly capa?: {
    readonly escena: Scene;
    readonly uniforms: UniformsCapa;
  } | null;
  /** Grano + viñeta en el mismo pase que el tone mapping (casi gratis). null = sin. */
  readonly grano?: AjustesGrano | null;
  /** Resolución del desenfoque del DOF (0.5 = mitad; menos = más rápido y más blando). */
  readonly dofEscala?: number;
  /** Buffers de 8 bits en vez de HalfFloat (más rápido sin GPU; recorta luces > 1). */
  readonly bufer8?: boolean;
}> = ({
  msaa,
  tono = 'agx',
  dof = null,
  capa = null,
  grano = null,
  dofEscala = 0.5,
  bufer8 = false,
}) => {
  const {fps} = useVideoConfig();
  const frame = useCurrentFrame();
  const gl = useThree((s) => s.gl);
  const scene = useThree((s) => s.scene);
  const camera = useThree((s) => s.camera);
  const size = useThree((s) => s.size);
  const conDof = dof !== null;
  const conGrano = grano !== null;

  const cadena = useMemo(() => {
    const composer = new EffectComposer(gl, {
      multisampling: msaa,
      frameBufferType: bufer8 ? UnsignedByteType : HalfFloatType,
    });
    composer.addPass(new RenderPass(scene, camera));
    const efectoDof = conDof
      ? new DepthOfFieldEffect(camera, {
          focusDistance: 8,
          focusRange: 3,
          bokehScale: 3,
          resolutionScale: dofEscala,
        })
      : null;
    const tonemap = new ToneMappingEffect({mode: MODOS[tono]});
    const efectoGrano = conGrano
      ? new EfectoGrano({aspecto: size.width / size.height})
      : null;
    // El DOF es un efecto de convolución: va en su propio pase. Después, la capa sin
    // profundidad (partículas) y al final el tone mapping, que la incluye.
    if (efectoDof) composer.addPass(new EffectPass(camera, efectoDof));
    if (capa)
      composer.addPass(new PaseCapa(capa.escena, camera, capa.uniforms));
    // Tone mapping + grano/viñeta: postprocessing los fusiona en UN pase de pantalla completa.
    composer.addPass(
      efectoGrano
        ? new EffectPass(camera, tonemap, efectoGrano)
        : new EffectPass(camera, tonemap),
    );
    composer.setSize(size.width, size.height);
    return {composer, efectoDof, efectoGrano};
    // size se maneja aparte para no recrear la cadena
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    gl,
    scene,
    camera,
    msaa,
    conDof,
    tono,
    capa,
    conGrano,
    dofEscala,
    bufer8,
  ]);

  useLayoutEffect(() => {
    cadena.composer.setSize(size.width, size.height);
    if (capa)
      gl.getDrawingBufferSize(capa.uniforms.uResolucion.value as Vector2);
  }, [cadena, size.width, size.height, capa, gl]);

  // Foco y planos de cámara por cuadro: uniforms, sin recrear nada.
  useLayoutEffect(() => {
    if (capa) {
      const cam = camera as PerspectiveCamera;
      capa.uniforms.uCerca.value = cam.near;
      capa.uniforms.uLejos.value = cam.far;
      capa.escena.fog = scene.fog;
    }
    if (cadena.efectoGrano && grano) {
      cadena.efectoGrano.semilla =
        (grano.semilla ?? 0) * 7919 +
        Math.floor(frame / Math.max(1, grano.cadencia ?? 2));
      cadena.efectoGrano.ajustar(grano);
    }
    if (cadena.efectoDof && dof) {
      cadena.efectoDof.cocMaterial.focusDistance = dof.distancia;
      cadena.efectoDof.cocMaterial.focusRange = dof.rango;
      cadena.efectoDof.bokehScale = dof.bokeh ?? 3;
    }
  });

  // El tone mapping lo hace el efecto: el renderer no tiene que aplicar otro.
  useLayoutEffect(() => {
    const previo = gl.toneMapping;
    gl.toneMapping = NoToneMapping;
    return () => {
      gl.toneMapping = previo;
    };
  }, [gl]);

  useEffect(() => () => cadena.composer.dispose(), [cadena]);

  // Prioridad 1: reemplaza el render automático de R3F.
  useFrame(() => {
    cadena.composer.render(1 / fps);
  }, 1);

  return null;
};
