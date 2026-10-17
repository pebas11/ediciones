import {CURVAS, deriva3, type NombreCurva} from './movimiento';

/**
 * Rig de cámara como función pura del tiempo. El MISMO estado alimenta:
 *  - la cámara de Three.js (<CamaraRig>, src/three/CamaraRig.tsx),
 *  - el parallax de las capas 2D (<CapaParallax>, src/capas/CapaParallax.tsx),
 *  - el anclaje de elementos 2D a puntos 3D (proyectar()).
 * Así lo 2D y lo 3D se mueven juntos sin leer nada del renderer.
 *
 * Convención igual a three.js: Y arriba, la cámara mira hacia `objetivo`, fov vertical
 * en grados.
 */
export type Vec3 = readonly [number, number, number];

export type ClaveCamara = {
  /** Segundos (relativos a la escena o absolutos, según quién llame). */
  readonly t: number;
  readonly posicion: Vec3;
  readonly objetivo: Vec3;
  readonly fov?: number;
  /** Curva del tramo que TERMINA en esta clave. */
  readonly curva?: NombreCurva;
};

export type EstadoCamara = {
  readonly posicion: Vec3;
  readonly objetivo: Vec3;
  readonly fov: number;
  /** Giro sobre el eje de visión, en radianes. */
  readonly rolido: number;
};

export type OpcionesRig = {
  readonly claves: readonly ClaveCamara[];
  /** Deriva tipo "cámara en mano/flotando" sumada a la posición (unidades de mundo). */
  readonly respiracion?: {
    readonly amplitud: number | Vec3;
    readonly frecuencia?: number;
    readonly semilla?: string;
  };
  /** Rolido suave en radianes. */
  readonly rolido?: {readonly amplitud: number; readonly frecuencia?: number};
};

const sumar = (a: Vec3, b: Vec3): Vec3 => [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
const restar = (a: Vec3, b: Vec3): Vec3 => [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
const escalar = (a: Vec3, k: number): Vec3 => [a[0] * k, a[1] * k, a[2] * k];
const punto = (a: Vec3, b: Vec3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const cruz = (a: Vec3, b: Vec3): Vec3 => [
  a[1] * b[2] - a[2] * b[1],
  a[2] * b[0] - a[0] * b[2],
  a[0] * b[1] - a[1] * b[0],
];
const normalizar = (a: Vec3): Vec3 => {
  const l = Math.hypot(a[0], a[1], a[2]) || 1;
  return [a[0] / l, a[1] / l, a[2] / l];
};
export const distancia = (a: Vec3, b: Vec3) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]);

/** Catmull-Rom uniforme entre p1 y p2 (p0 y p3 son los vecinos). */
const catmullRom = (p0: Vec3, p1: Vec3, p2: Vec3, p3: Vec3, u: number): Vec3 => {
  const u2 = u * u;
  const u3 = u2 * u;
  const f = (a: number, b: number, c: number, d: number) =>
    0.5 * (2 * b + (-a + c) * u + (2 * a - 5 * b + 4 * c - d) * u2 + (-a + 3 * b - 3 * c + d) * u3);
  return [f(p0[0], p1[0], p2[0], p3[0]), f(p0[1], p1[1], p2[1], p3[1]), f(p0[2], p1[2], p2[2], p3[2])];
};

/** Estado de la cámara en el segundo t. Las claves tienen que estar ordenadas por t. */
export const estadoCamara = (t: number, {claves, respiracion, rolido}: OpcionesRig): EstadoCamara => {
  if (claves.length === 0) throw new Error('El rig de cámara necesita al menos una clave.');
  let posicion: Vec3;
  let objetivo: Vec3;
  let fov: number;
  if (claves.length === 1 || t <= claves[0].t) {
    posicion = claves[0].posicion;
    objetivo = claves[0].objetivo;
    fov = claves[0].fov ?? 35;
  } else if (t >= claves[claves.length - 1].t) {
    const c = claves[claves.length - 1];
    posicion = c.posicion;
    objetivo = c.objetivo;
    fov = c.fov ?? 35;
  } else {
    let k = 0;
    while (k < claves.length - 2 && t > claves[k + 1].t) k++;
    const a = claves[k];
    const b = claves[k + 1];
    const u = CURVAS[b.curva ?? 'apple']((t - a.t) / (b.t - a.t));
    const prev = claves[Math.max(0, k - 1)];
    const next = claves[Math.min(claves.length - 1, k + 2)];
    posicion = catmullRom(prev.posicion, a.posicion, b.posicion, next.posicion, u);
    objetivo = catmullRom(prev.objetivo, a.objetivo, b.objetivo, next.objetivo, u);
    fov = (a.fov ?? 35) + ((b.fov ?? 35) - (a.fov ?? 35)) * u;
  }
  if (respiracion) {
    const d = deriva3(respiracion.semilla ?? 'camara', t, {
      amplitud: respiracion.amplitud,
      frecuencia: respiracion.frecuencia ?? 0.12,
    });
    posicion = sumar(posicion, d);
    // El objetivo deriva menos: la cámara "flota" sin perder el encuadre.
    objetivo = sumar(objetivo, escalar(d, 0.35));
  }
  const giro = rolido
    ? rolido.amplitud * deriva3('rolido', t, {amplitud: 1, frecuencia: rolido.frecuencia ?? 0.08})[0]
    : 0;
  return {posicion, objetivo, fov, rolido: giro};
};

/** Base ortonormal de la cámara (derecha, arriba, adelante), con rolido. */
export const baseCamara = (c: EstadoCamara) => {
  const adelante = normalizar(restar(c.objetivo, c.posicion));
  let derecha = normalizar(cruz(adelante, [0, 1, 0]));
  let arriba = cruz(derecha, adelante);
  if (c.rolido) {
    const cs = Math.cos(c.rolido);
    const sn = Math.sin(c.rolido);
    const d2 = sumar(escalar(derecha, cs), escalar(arriba, sn));
    const a2 = sumar(escalar(arriba, cs), escalar(derecha, -sn));
    derecha = d2;
    arriba = a2;
  }
  return {derecha, arriba, adelante};
};

export type PuntoPantalla = {
  readonly x: number;
  readonly y: number;
  /** Profundidad sobre el eje de visión (unidades de mundo). */
  readonly z: number;
  readonly visible: boolean;
};

/** Proyecta un punto 3D a píxeles de pantalla (igual que PerspectiveCamera.lookAt). */
export const proyectar = (p: Vec3, c: EstadoCamara, ancho: number, alto: number): PuntoPantalla => {
  const {derecha, arriba, adelante} = baseCamara(c);
  const d = restar(p, c.posicion);
  const x = punto(d, derecha);
  const y = punto(d, arriba);
  const z = punto(d, adelante);
  const focal = alto / 2 / Math.tan(((c.fov * Math.PI) / 180) / 2);
  const zz = Math.max(z, 1e-4);
  return {x: ancho / 2 + (x * focal) / zz, y: alto / 2 - (y * focal) / zz, z, visible: z > 0};
};

/** Tamaño en píxeles de un objeto de `tamanoMundo` unidades a profundidad z. */
export const escalaEnPantalla = (tamanoMundo: number, z: number, fov: number, alto: number) =>
  (tamanoMundo * (alto / 2)) / Math.tan(((fov * Math.PI) / 180) / 2) / Math.max(z, 1e-4);

/**
 * Parallax de una capa 2D plana "ubicada" a `profundidad` unidades delante de la cámara
 * de referencia. Devuelve cuánto moverla y escalarla para que se comporte como un objeto
 * del mundo 3D cuando la cámara se mueve de `referencia` a `actual`.
 */
export const parallax = (
  actual: EstadoCamara,
  referencia: EstadoCamara,
  profundidad: number,
  ancho: number,
  alto: number,
): {dx: number; dy: number; escala: number} => {
  const {adelante} = baseCamara(referencia);
  const ancla = sumar(referencia.posicion, escalar(adelante, profundidad));
  const p0 = proyectar(ancla, referencia, ancho, alto);
  const p1 = proyectar(ancla, actual, ancho, alto);
  return {
    dx: p1.x - p0.x,
    dy: p1.y - p0.y,
    // Incluye acercamiento (z) y zoom (fov).
    escala: p1.visible
      ? escalaEnPantalla(1, p1.z, actual.fov, alto) / escalaEnPantalla(1, p0.z, referencia.fov, alto)
      : 1,
  };
};
