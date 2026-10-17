import * as THREE from 'three';
import {GLSL_SIMPLEX_3D} from './glsl';
import type {UniformsCapa} from './PaseCapa';

/**
 * Materiales con shader propio. Patrones reutilizables:
 *
 * 1. crearMaterialEnsueno(): MeshStandardMaterial extendido con onBeforeCompile.
 *    Conserva luces PBR, sombras y niebla de three.js y agrega GLSL propio
 *    (desplazamiento por ruido + borde fresnel). Trae un MeshDepthMaterial con el
 *    MISMO desplazamiento para que la sombra coincida con la forma deformada.
 * 2. crearMaterialParticulas(): ShaderMaterial puro para partículas instanciadas,
 *    con niebla y "bokeh" por distancia al plano de foco.
 * 3. crearMaterialCielo(): ShaderMaterial de fondo (domo) sin luces.
 *
 * El tiempo SIEMPRE entra por un uniform (uTiempo = cuadro / fps), nunca por un reloj:
 * así cada cuadro es reproducible en cualquier pestaña y en cualquier tramo.
 * Actualizar uniforms en useLayoutEffect o durante el render, NO en useEffect:
 * <ThreeCanvas> dibuja el cuadro en un useEffect que corre antes que los de los hijos.
 */

// ---------------------------------------------------------------------------
// 1. Superficie desplazada (lit, con sombras)
// ---------------------------------------------------------------------------

export type UniformsEnsueno = {
  uTiempo: {value: number};
  uAmplitud: {value: number};
  uFrecuencia: {value: number};
  uVelocidad: {value: number};
  uColorB: {value: THREE.Color};
  uColorBorde: {value: THREE.Color};
  uIntensidadBorde: {value: number};
  uPotenciaBorde: {value: number};
};

const DESPLAZAMIENTO = /* glsl */ `
uniform float uTiempo;
uniform float uAmplitud;
uniform float uFrecuencia;
uniform float uVelocidad;
${GLSL_SIMPLEX_3D}
float ensDesplazamiento(vec3 p) {
  vec3 q = p * uFrecuencia + vec3(0.0, uTiempo * uVelocidad, uTiempo * uVelocidad * 0.6);
  float n = snoise(q) * 0.78 + snoise(q * 2.03 + 11.7) * 0.22;
  return n * uAmplitud;
}
`;

export const crearMaterialEnsueno = ({
  color = '#b88a5a',
  colorB = '#e6cfa8',
  colorBorde = '#9fb7d6',
  rugosidad = 0.55,
  metalicidad = 0.05,
}: {
  color?: THREE.ColorRepresentation;
  colorB?: THREE.ColorRepresentation;
  colorBorde?: THREE.ColorRepresentation;
  rugosidad?: number;
  metalicidad?: number;
} = {}) => {
  const uniforms: UniformsEnsueno = {
    uTiempo: {value: 0},
    uAmplitud: {value: 0.18},
    uFrecuencia: {value: 1.4},
    uVelocidad: {value: 0.25},
    uColorB: {value: new THREE.Color(colorB)},
    uColorBorde: {value: new THREE.Color(colorBorde)},
    uIntensidadBorde: {value: 0.45},
    uPotenciaBorde: {value: 3.0},
  };

  const material = new THREE.MeshStandardMaterial({
    color,
    roughness: rugosidad,
    metalness: metalicidad,
  });
  material.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    shader.vertexShader = shader.vertexShader
      .replace(
        '#include <common>',
        `#include <common>\n${DESPLAZAMIENTO}\nvarying float vEns;`,
      )
      .replace(
        '#include <beginnormal_vertex>',
        /* glsl */ `
        vec3 objectNormal = vec3(normal);
        #ifdef USE_TANGENT
          vec3 objectTangent = vec3(tangent.xyz);
        #endif
        // Normal de la superficie desplazada por diferencias finitas.
        {
          vec3 ref = abs(normal.y) < 0.99 ? vec3(0.0, 1.0, 0.0) : vec3(1.0, 0.0, 0.0);
          vec3 tg = normalize(cross(normal, ref));
          vec3 bt = normalize(cross(normal, tg));
          float e = 0.012;
          vec3 p0 = position + normal * ensDesplazamiento(position);
          vec3 pt = position + tg * e;
          vec3 pb = position + bt * e;
          pt += normal * ensDesplazamiento(pt);
          pb += normal * ensDesplazamiento(pb);
          objectNormal = normalize(cross(pt - p0, pb - p0));
        }`,
      )
      .replace(
        '#include <begin_vertex>',
        /* glsl */ `
        float ensD = ensDesplazamiento(position);
        vec3 transformed = position + normal * ensD;
        vEns = ensD / max(uAmplitud, 1e-4);`,
      );
    shader.fragmentShader = shader.fragmentShader
      .replace(
        '#include <common>',
        /* glsl */ `#include <common>
        uniform vec3 uColorB;
        uniform vec3 uColorBorde;
        uniform float uIntensidadBorde;
        uniform float uPotenciaBorde;
        varying float vEns;`,
      )
      .replace(
        '#include <color_fragment>',
        /* glsl */ `#include <color_fragment>
        diffuseColor.rgb = mix(diffuseColor.rgb, uColorB, smoothstep(-0.6, 0.9, vEns) * 0.6);`,
      )
      .replace(
        '#include <opaque_fragment>',
        /* glsl */ `
        float ensF = pow(1.0 - saturate(dot(normal, normalize(vViewPosition))), uPotenciaBorde);
        outgoingLight += uColorBorde * ensF * uIntensidadBorde;
        #include <opaque_fragment>`,
      );
  };
  material.customProgramCacheKey = () => 'ensueno-v1';

  // Sombra: mismo desplazamiento en el material de profundidad.
  const profundidad = new THREE.MeshDepthMaterial({
    depthPacking: THREE.RGBADepthPacking,
  });
  profundidad.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    shader.vertexShader = shader.vertexShader
      .replace('#include <common>', `#include <common>\n${DESPLAZAMIENTO}`)
      .replace(
        '#include <begin_vertex>',
        'vec3 transformed = position + normal * ensDesplazamiento(position);',
      );
  };
  profundidad.customProgramCacheKey = () => 'ensueno-depth-v1';

  return {material, profundidad, uniforms};
};

// ---------------------------------------------------------------------------
// 2. Partículas instanciadas
// ---------------------------------------------------------------------------

export type UniformsParticulas = {
  uTiempo: {value: number};
  uTamano: {value: number};
  uEnfoque: {value: number};
  uRangoEnfoque: {value: number};
  uCaja: {value: THREE.Vector3};
  uSubida: {value: number};
  uColor: {value: THREE.Color};
  uOpacidad: {value: number};
  uBrillo: {value: number};
};

const VERT_PARTICULAS = /* glsl */ `
uniform float uTiempo;
uniform float uTamano;
uniform float uEnfoque;
uniform float uRangoEnfoque;
uniform vec3 uCaja;
uniform float uSubida;
attribute vec3 aPos;
attribute vec4 aSemilla;
varying vec2 vUv;
varying float vAlpha;
varying float vDesenfoque;
#ifdef CAPA_SUAVE
varying float vVistaZ;
#endif
#include <common>
#include <fog_pars_vertex>

void main() {
  vec3 p = aPos;
  float t = uTiempo;
  // Deriva lateral periódica por partícula (sin estado: depende solo de t).
  p.x += sin(t * (0.21 + aSemilla.x * 0.23) + aSemilla.y * 6.2831) * 0.32;
  p.z += cos(t * (0.17 + aSemilla.z * 0.19) + aSemilla.w * 6.2831) * 0.32;
  // Subida lenta con vuelta al fondo de la caja (mod): vale para cualquier t.
  float alto = uCaja.y;
  p.y = mod(p.y + alto * 0.5 + t * uSubida * (0.35 + aSemilla.x), alto) - alto * 0.5;

  vec4 mvPosition = modelViewMatrix * vec4(p, 1.0);
  float dist = -mvPosition.z;
  float desenfoque = clamp(abs(dist - uEnfoque) / uRangoEnfoque, 0.0, 1.0);
  float tam = uTamano * (0.45 + aSemilla.y * 0.9) * (1.0 + desenfoque * 2.2);
  // Billboard en espacio de vista: el quad siempre mira a la cámara.
  mvPosition.xy += position.xy * tam;
  gl_Position = projectionMatrix * mvPosition;

  vUv = position.xy;
  vDesenfoque = desenfoque;
  // Al desenfocar, el disco crece y su energía se reparte: baja la opacidad.
  vAlpha = (0.35 + 0.65 * aSemilla.z) / (1.0 + desenfoque * 4.0);
  #ifdef CAPA_SUAVE
  vVistaZ = mvPosition.z;
  #endif
  #include <fog_vertex>
}
`;

const FRAG_PARTICULAS = /* glsl */ `
uniform vec3 uColor;
uniform float uOpacidad;
uniform float uBrillo;
varying vec2 vUv;
varying float vAlpha;
varying float vDesenfoque;
#ifdef CAPA_SUAVE
uniform sampler2D uProfundidad;
uniform vec2 uResolucion;
uniform float uCerca;
uniform float uLejos;
varying float vVistaZ;
#endif
#include <common>
#include <packing>
#include <fog_pars_fragment>

void main() {
  float r = length(vUv);
  float suavidad = mix(0.35, 0.85, vDesenfoque);
  float a = 1.0 - smoothstep(1.0 - suavidad, 1.0, r);
  #ifdef CAPA_SUAVE
  // Oclusión suave contra la geometría de la escena principal (profundidad del composer).
  float zEscena = texture2D(uProfundidad, gl_FragCoord.xy / uResolucion).r;
  float vzEscena = perspectiveDepthToViewZ(zEscena, uCerca, uLejos);
  a *= smoothstep(0.0, 0.35, vVistaZ - vzEscena);
  #endif
  if (a <= 0.002) discard;
  gl_FragColor = vec4(uColor * uBrillo, a * vAlpha * uOpacidad);
  #include <tonemapping_fragment>
  #include <colorspace_fragment>
  #include <fog_fragment>
}
`;

/**
 * `capa`: si se pasa, el material va en la capa posterior al DOF (ver PaseCapa): no usa
 * el depth test del hardware y se oculta detrás de la geometría leyendo la profundidad.
 */
export const crearMaterialParticulas = (
  color: THREE.ColorRepresentation = '#f1e2c6',
  capa: UniformsCapa | null = null,
) => {
  const uniforms: UniformsParticulas = {
    uTiempo: {value: 0},
    uTamano: {value: 0.025},
    uEnfoque: {value: 6},
    uRangoEnfoque: {value: 6},
    uCaja: {value: new THREE.Vector3(24, 10, 24)},
    uSubida: {value: 0.12},
    uColor: {value: new THREE.Color(color)},
    uOpacidad: {value: 0.85},
    uBrillo: {value: 1},
  };
  const material = new THREE.ShaderMaterial({
    // Copia de los uniforms de niebla: no compartir los objetos globales de UniformsLib.
    uniforms: {
      ...THREE.UniformsUtils.clone(THREE.UniformsLib.fog),
      ...uniforms,
      ...(capa ?? {}),
    },
    vertexShader: VERT_PARTICULAS,
    fragmentShader: FRAG_PARTICULAS,
    defines: capa ? {CAPA_SUAVE: ''} : {},
    transparent: true,
    depthWrite: false,
    depthTest: !capa,
    fog: true,
  });
  return {material, uniforms};
};

/**
 * Geometría instanciada: un quad (-1..1) repetido `cantidad` veces, con posición y
 * semillas por instancia. `azar` tiene que ser determinista (crearAzar).
 */
export const crearGeometriaParticulas = (
  cantidad: number,
  caja: readonly [number, number, number],
  azar: () => number,
) => {
  const geo = new THREE.InstancedBufferGeometry();
  geo.setAttribute(
    'position',
    new THREE.Float32BufferAttribute(
      [-1, -1, 0, 1, -1, 0, 1, 1, 0, -1, 1, 0],
      3,
    ),
  );
  geo.setIndex([0, 1, 2, 0, 2, 3]);
  const pos = new Float32Array(cantidad * 3);
  const sem = new Float32Array(cantidad * 4);
  for (let i = 0; i < cantidad; i++) {
    pos[i * 3] = (azar() - 0.5) * caja[0];
    pos[i * 3 + 1] = (azar() - 0.5) * caja[1];
    pos[i * 3 + 2] = (azar() - 0.5) * caja[2];
    sem[i * 4] = azar();
    sem[i * 4 + 1] = azar();
    sem[i * 4 + 2] = azar();
    sem[i * 4 + 3] = azar();
  }
  geo.setAttribute('aPos', new THREE.InstancedBufferAttribute(pos, 3));
  geo.setAttribute('aSemilla', new THREE.InstancedBufferAttribute(sem, 4));
  geo.instanceCount = cantidad;
  return geo;
};

// ---------------------------------------------------------------------------
// 3. Cielo (domo de fondo)
// ---------------------------------------------------------------------------

export const crearMaterialCielo = ({
  arriba = '#2b2620',
  horizonte = '#5a4d3e',
}: {
  arriba?: THREE.ColorRepresentation;
  horizonte?: THREE.ColorRepresentation;
} = {}) => {
  const uniforms = {
    uTiempo: {value: 0},
    uArriba: {value: new THREE.Color(arriba)},
    uHorizonte: {value: new THREE.Color(horizonte)},
  };
  const material = new THREE.ShaderMaterial({
    uniforms,
    vertexShader: /* glsl */ `
      varying vec3 vDir;
      void main() {
        vDir = normalize(position);
        vec4 p = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        gl_Position = p.xyww; // siempre en el plano lejano
      }`,
    fragmentShader: /* glsl */ `
      uniform float uTiempo;
      uniform vec3 uArriba;
      uniform vec3 uHorizonte;
      varying vec3 vDir;
      #include <common>
      ${GLSL_SIMPLEX_3D}
      void main() {
        float h = clamp(vDir.y * 1.4 + 0.15, 0.0, 1.0);
        vec3 c = mix(uHorizonte, uArriba, smoothstep(0.0, 1.0, h));
        // Nubosidad muy baja frecuencia: rompe el degradé plano sin llamar la atención.
        float n = snoise(vDir * 2.2 + vec3(uTiempo * 0.015, 0.0, 0.0)) * 0.5 + 0.5;
        c *= 0.92 + 0.12 * n;
        gl_FragColor = vec4(c, 1.0);
        #include <tonemapping_fragment>
        #include <colorspace_fragment>
      }`,
    side: THREE.BackSide,
    depthWrite: false,
  });
  return {material, uniforms};
};
