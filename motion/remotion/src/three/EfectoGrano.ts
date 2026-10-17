import {BlendFunction, Effect} from 'postprocessing';
import {Uniform} from 'three';

/**
 * Grano + viñeta DENTRO del postproceso de Three.js (postprocessing Effect).
 *
 * Se fusiona en el mismo pase de pantalla completa que el tone mapping, así que cuesta
 * casi nada. En cambio, el grano y la viñeta en CSS (capas con mix-blend-mode sobre
 * toda la pantalla) obligan a Chrome a componer cada cuadro por software y cuestan
 * cientos de ms por cuadro sin GPU (medido en README).
 *
 * Determinista: el patrón depende de `semilla` (un entero que la escena cambia cada
 * N cuadros), nunca del reloj. Se aplica DESPUÉS del tone mapping.
 */
const FRAG = /* glsl */ `
uniform float uSemilla;
uniform float uIntensidad;
uniform float uEscala;
uniform float uVineta;
uniform float uRadio;
uniform float uAspecto;

// Hash sin seno (Dave Hoskins): estable entre GPUs y en SwiftShader.
float hash12(vec2 p) {
  vec3 p3 = fract(vec3(p.xyx) * 0.1031);
  p3 += dot(p3, p3.yzx + 33.33);
  return fract((p3.x + p3.y) * p3.z);
}

void mainImage(const in vec4 inputColor, const in vec2 uv, out vec4 outputColor) {
  vec3 c = inputColor.rgb;
  // Viñeta elíptica suave.
  vec2 d = (uv - 0.5) * 2.0;
  d.x *= mix(1.0, uAspecto, 0.35);
  float v = smoothstep(uRadio, 1.45, length(d));
  c *= 1.0 - uVineta * v;
  // Grano: suma de dos hashes (distribución triangular) en celdas de uEscala px.
  vec2 celda = floor(gl_FragCoord.xy / uEscala);
  float s = uSemilla * 0.618034;
  float n = hash12(celda + vec2(s * 97.0, s * 31.0)) + hash12(celda * 1.37 + vec2(s * 13.0, s * 71.0)) - 1.0;
  // El grano se suma en espacio perceptual (gamma 2.2): en lineal se vería exagerado en
  // las sombras. Más visible en medios tonos, como en película.
  vec3 g = pow(max(c, 0.0), vec3(1.0 / 2.2));
  float lum = dot(g, vec3(0.2126, 0.7152, 0.0722));
  float peso = 0.5 + 0.5 * (1.0 - abs(clamp(lum, 0.0, 1.0) * 2.0 - 1.0));
  g += n * uIntensidad * peso;
  outputColor = vec4(pow(max(g, 0.0), vec3(2.2)), inputColor.a);
}
`;

export class EfectoGrano extends Effect {
  constructor({
    intensidad = 0.045,
    escala = 1.5,
    vineta = 0.5,
    radio = 0.55,
    aspecto = 16 / 9,
  }: {
    intensidad?: number;
    escala?: number;
    vineta?: number;
    radio?: number;
    aspecto?: number;
  } = {}) {
    super('EfectoGrano', FRAG, {
      blendFunction: BlendFunction.NORMAL,
      uniforms: new Map<string, Uniform>([
        ['uSemilla', new Uniform(0)],
        ['uIntensidad', new Uniform(intensidad)],
        ['uEscala', new Uniform(escala)],
        ['uVineta', new Uniform(vineta)],
        ['uRadio', new Uniform(radio)],
        ['uAspecto', new Uniform(aspecto)],
      ]),
    });
  }

  set semilla(v: number) {
    (this.uniforms.get('uSemilla') as Uniform).value = v;
  }

  ajustar({
    intensidad,
    escala,
    vineta,
    radio,
  }: {
    intensidad?: number;
    escala?: number;
    vineta?: number;
    radio?: number;
  }) {
    if (intensidad !== undefined)
      (this.uniforms.get('uIntensidad') as Uniform).value = intensidad;
    if (escala !== undefined)
      (this.uniforms.get('uEscala') as Uniform).value = escala;
    if (vineta !== undefined)
      (this.uniforms.get('uVineta') as Uniform).value = vineta;
    if (radio !== undefined)
      (this.uniforms.get('uRadio') as Uniform).value = radio;
  }
}
