import {Pass} from 'postprocessing';
import * as THREE from 'three';

/**
 * Uniforms compartidos entre el pase y los materiales de la capa (p. ej. partículas):
 * profundidad de la escena principal para ocultarse detrás de la geometría con borde
 * suave ("soft particles"), resolución y planos de la cámara.
 */
export type UniformsCapa = {
  uProfundidad: {value: THREE.Texture | null};
  uResolucion: {value: THREE.Vector2};
  uCerca: {value: number};
  uLejos: {value: number};
};

export const crearUniformsCapa = (): UniformsCapa => ({
  uProfundidad: {value: null},
  uResolucion: {value: new THREE.Vector2(1920, 1080)},
  uCerca: {value: 0.1},
  uLejos: {value: 120},
});

/**
 * Dibuja una escena aparte ENCIMA de la imagen ya procesada (después del DOF y antes
 * del tone mapping). Sirve para elementos que no escriben profundidad, como las
 * partículas: si fueran en la escena principal, el DOF las desenfocaría según lo que
 * tienen detrás. Pide la textura de profundidad estable del composer.
 */
export class PaseCapa extends Pass {
  private readonly uniforms: UniformsCapa;

  constructor(
    escena: THREE.Scene,
    camara: THREE.Camera,
    uniforms: UniformsCapa,
  ) {
    super('PaseCapa', escena, camara);
    this.uniforms = uniforms;
    this.needsSwap = false;
    this.needsDepthTexture = true;
  }

  override setDepthTexture(textura: THREE.Texture | null): void {
    this.uniforms.uProfundidad.value = textura;
  }

  override render(
    renderer: THREE.WebGLRenderer,
    inputBuffer: THREE.WebGLRenderTarget | null,
  ): void {
    const autoClear = renderer.autoClear;
    renderer.autoClear = false;
    renderer.setRenderTarget(this.renderToScreen ? null : inputBuffer);
    renderer.render(this.scene, this.camera);
    renderer.autoClear = autoClear;
  }
}
