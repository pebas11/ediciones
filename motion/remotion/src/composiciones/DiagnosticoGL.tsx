import {ThreeCanvas} from '@remotion/three';
import React, {useEffect, useState} from 'react';
import {AbsoluteFill, useCurrentFrame, useVideoConfig} from 'remotion';

/**
 * Diagnóstico del WebGL disponible en el navegador de render.
 * Lo usa `scripts/diagnostico-gl.mjs`: imprime una línea `DIAG_GL {...}` en la consola
 * del navegador y dibuja un cubo con sombra para confirmar que R3F funciona.
 */
type InfoGL = {
  webgl2: boolean;
  webgl1: boolean;
  vendor: string | null;
  renderer: string | null;
  version: string | null;
  maxTexture: number | null;
  maxSamples: number | null;
  floatRT: boolean;
  halfFloatRT: boolean;
};

const leerInfoGL = (): InfoGL => {
  const canvas = document.createElement('canvas');
  const gl2 = canvas.getContext('webgl2');
  const gl = gl2 ?? canvas.getContext('webgl');
  if (!gl) {
    return {
      webgl2: false,
      webgl1: false,
      vendor: null,
      renderer: null,
      version: null,
      maxTexture: null,
      maxSamples: null,
      floatRT: false,
      halfFloatRT: false,
    };
  }
  const dbg = gl.getExtension('WEBGL_debug_renderer_info');
  const info: InfoGL = {
    webgl2: Boolean(gl2),
    webgl1: true,
    vendor: String(
      dbg ? gl.getParameter(dbg.UNMASKED_VENDOR_WEBGL) : gl.getParameter(gl.VENDOR),
    ),
    renderer: String(
      dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : gl.getParameter(gl.RENDERER),
    ),
    version: String(gl.getParameter(gl.VERSION)),
    maxTexture: Number(gl.getParameter(gl.MAX_TEXTURE_SIZE)),
    maxSamples: gl2 ? Number(gl2.getParameter(gl2.MAX_SAMPLES)) : null,
    floatRT: Boolean(gl.getExtension('EXT_color_buffer_float')),
    halfFloatRT: Boolean(
      gl.getExtension('EXT_color_buffer_half_float') ?? gl.getExtension('EXT_color_buffer_float'),
    ),
  };
  gl.getExtension('WEBGL_lose_context')?.loseContext();
  return info;
};

export const DiagnosticoGL: React.FC = () => {
  const {width, height} = useVideoConfig();
  const frame = useCurrentFrame();
  const [info] = useState(leerInfoGL);

  useEffect(() => {
    // eslint-disable-next-line no-console
    console.log('DIAG_GL ' + JSON.stringify(info));
  }, [info]);

  return (
    <AbsoluteFill style={{backgroundColor: '#15130f'}}>
      <ThreeCanvas width={width} height={height} shadows camera={{position: [3, 2.2, 4], fov: 40}}>
        <color attach="background" args={['#15130f']} />
        <ambientLight intensity={0.3} />
        <directionalLight
          position={[4, 6, 3]}
          intensity={2.2}
          castShadow
          shadow-mapSize={[1024, 1024]}
        />
        <mesh castShadow position={[0, 0.6, 0]} rotation={[0.4, frame * 0.02, 0]}>
          <boxGeometry args={[1, 1, 1]} />
          <meshStandardMaterial color="#c9a46a" roughness={0.6} />
        </mesh>
        <mesh receiveShadow rotation={[-Math.PI / 2, 0, 0]}>
          <planeGeometry args={[10, 10]} />
          <meshStandardMaterial color="#3a342b" />
        </mesh>
      </ThreeCanvas>
      <AbsoluteFill
        style={{
          padding: 80,
          color: '#efe6d6',
          fontFamily: 'monospace',
          fontSize: 30,
          whiteSpace: 'pre-wrap',
        }}
      >
        {JSON.stringify(info, null, 2)}
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
