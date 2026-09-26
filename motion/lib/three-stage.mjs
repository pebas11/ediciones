// Escenario 3D (Three.js) integrado al motor determinista: se renderiza en cada M.seek(t).
import * as THREE from 'three';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/addons/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

export { THREE };

/**
 * Crea renderer + cámara + composer con bloom. El canvas es opaco y dibuja su propio fondo
 * (degradé en un domo), así el bloom no deja halos raros.
 */
export function createStage3D(host, {
  fov = 28, bloom = { strength: 0.55, radius: 0.6, threshold: 0.82 }, exposure = 1.0,
  bgTop = '#1a0f33', bgBottom = '#05030c', bgGlow = '#3a1a5c', env = 0.25,
} = {}) {
  const W = 1920, H = 1080;
  const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true, powerPreference: 'high-performance' });
  renderer.setPixelRatio(window.devicePixelRatio || 1);
  renderer.setSize(W, H);
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = exposure;
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFSoftShadowMap;
  renderer.domElement.style.cssText = 'position:absolute;inset:0;width:1920px;height:1080px';
  host.appendChild(renderer.domElement);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(fov, W / H, 0.05, 200);

  // entorno suave para reflejos físicos (poca intensidad)
  const pmrem = new THREE.PMREMGenerator(renderer);
  scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
  scene.environmentIntensity = env;

  // domo de fondo con degradé + resplandor (shader, sin texturas)
  const dome = new THREE.Mesh(
    new THREE.SphereGeometry(80, 48, 24),
    new THREE.ShaderMaterial({
      side: THREE.BackSide, depthWrite: false,
      uniforms: { top: { value: new THREE.Color(bgTop) }, bottom: { value: new THREE.Color(bgBottom) }, glow: { value: new THREE.Color(bgGlow) }, glowDir: { value: new THREE.Vector3(0.3, 0.25, -1).normalize() } },
      vertexShader: 'varying vec3 vP; void main(){ vP = normalize(position); gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }',
      fragmentShader: `uniform vec3 top; uniform vec3 bottom; uniform vec3 glow; uniform vec3 glowDir; varying vec3 vP;
        void main(){ float h = smoothstep(-0.35, 0.6, vP.y); vec3 c = mix(bottom, top, h);
          float g = pow(max(dot(vP, glowDir), 0.0), 6.0); c += glow * g * 0.9;
          gl_FragColor = vec4(c, 1.0); }`,
    }),
  );
  dome.renderOrder = -10;
  scene.add(dome);

  const composer = new EffectComposer(renderer);
  composer.setPixelRatio(window.devicePixelRatio || 1);
  composer.setSize(W, H);
  composer.addPass(new RenderPass(scene, camera));
  const bloomPass = new UnrealBloomPass(new THREE.Vector2(W / 2, H / 2), bloom.strength, bloom.radius, bloom.threshold);
  composer.addPass(bloomPass);
  composer.addPass(new OutputPass());

  const v = new THREE.Vector3();
  return {
    THREE, renderer, scene, camera, composer, bloomPass, dome,
    render() { composer.render(); },
    /** Proyecta un punto 3D del mundo a píxeles de pantalla (para anotaciones HTML). */
    project(obj3dOrVec) {
      if (obj3dOrVec.isObject3D) obj3dOrVec.getWorldPosition(v); else v.copy(obj3dOrVec);
      v.project(camera);
      return { x: (v.x + 1) / 2 * W, y: (1 - v.y) / 2 * H, behind: v.z > 1 };
    },
  };
}

/* ---------------- ruido determinista (value noise 3D suavizado) ---------------- */
function hash(x, y, z) { let h = (x * 374761393 + y * 668265263 + z * 2147483647) | 0; h = (h ^ (h >>> 13)) * 1274126177 | 0; return ((h ^ (h >>> 16)) >>> 0) / 4294967295; }
const sm = (t) => t * t * (3 - 2 * t);
export function noise3(x, y, z) {
  const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z);
  const xf = sm(x - xi), yf = sm(y - yi), zf = sm(z - zi);
  const l = (a, b, t) => a + (b - a) * t;
  const c = (dx, dy, dz) => hash(xi + dx, yi + dy, zi + dz);
  return l(l(l(c(0, 0, 0), c(1, 0, 0), xf), l(c(0, 1, 0), c(1, 1, 0), xf), yf), l(l(c(0, 0, 1), c(1, 0, 1), xf), l(c(0, 1, 1), c(1, 1, 1), xf), yf), zf) * 2 - 1;
}
export function fbm(x, y, z, oct = 4) { let a = 0, f = 1, s = 0.5; for (let i = 0; i < oct; i++) { a += noise3(x * f, y * f, z * f) * s; f *= 2.03; s *= 0.5; } return a; }
