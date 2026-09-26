// Modelo 3D procedural de Psilocybe cubensis: sombrero con umbo, laminillas, anillo y pie
// con el azulado típico. Todo determinista (ruido con semilla fija).
import { THREE, fbm, noise3 } from './three-stage.mjs';

const C = (h) => new THREE.Color(h);
const lerpC = (a, b, t) => a.clone().lerp(b, Math.min(1, Math.max(0, t)));

export function buildMushroom({ seed = 1, stemH = 1.75, capScale = 1 } = {}) {
  const group = new THREE.Group();
  const S = seed * 17.3;

  /* ------------------------------ sombrero ------------------------------ */
  // perfil de P. cubensis maduro: convexo con umbo, borde levemente curvado hacia abajo
  const prof = [];
  const topY = (r) => 0.5 * Math.pow(Math.max(0, 1 - Math.pow(r, 2.3)), 0.85) + 0.085 * Math.exp(-Math.pow(r / 0.14, 2)) - 0.05 * Math.pow(r, 6);
  const yUnder = (r) => -0.075 + 0.14 * (1 - Math.pow(r / 0.975, 1.6));
  for (let i = 0; i <= 56; i++) { const r = Math.max(0.001, i / 56); prof.push(new THREE.Vector2(r, topY(r))); }
  prof.push(new THREE.Vector2(0.997, -0.072), new THREE.Vector2(0.978, -0.082));
  for (let i = 1; i <= 24; i++) { const r = 0.975 - (0.975 - 0.07) * (i / 24); prof.push(new THREE.Vector2(r, yUnder(r))); }
  const capGeo = new THREE.LatheGeometry(prof, 200);
  {
    const p = capGeo.attributes.position, col = new Float32Array(p.count * 3);
    const umbo = C('#3E1D0E'), caramel = C('#9A4F1C'), gold = C('#CF8E3E'), lip = C('#EBCF98'), under = C('#2A1A22'), bruise = C('#2A5FCC'), veil = C('#F4EBDD');
    for (let i = 0; i < p.count; i++) {
      let x = p.getX(i), y = p.getY(i), z = p.getZ(i);
      const r = Math.hypot(x, z), phi = Math.atan2(z, x);
      const cx = Math.cos(phi), cz = Math.sin(phi);
      // deformación orgánica: bultos suaves + borde ondulado e irregular
      const bump = 0.022 * fbm(cx * 2.2 + S, y * 2.0, cz * 2.2) + 0.03 * Math.pow(r, 3) * fbm(cx * 5 + S, 3.1, cz * 5);
      const k = 1 + bump;
      x *= k; z *= k;
      y += 0.018 * fbm(cx * 3 + S, 7.7, cz * 3) * r + (r > 0.85 ? 0.025 * noise3(cx * 6 + S, 1.3, cz * 6) : 0);
      p.setXYZ(i, x, y, z);
      // color: umbo oscuro → caramelo → dorado → borde pálido; parte inferior violácea (esporas)
      const seg = Math.round((i % (prof.length)) );
      const top = (i % prof.length) <= 58;
      let c;
      if (!top) c = under.clone();
      else {
        const t = r / 0.95;
        c = t < 0.25 ? lerpC(umbo, caramel, t / 0.25) : t < 0.7 ? lerpC(caramel, gold, (t - 0.25) / 0.45) : lerpC(gold, lip, (t - 0.7) / 0.3);
        // estrías radiales finas + manchas
        const streak = 0.13 * noise3(phi * 34 + S, r * 3.5, 0.5) + 0.08 * fbm(cx * 9, y * 9 + S, cz * 9);
        c.multiplyScalar(1 + streak);
        // restos del velo: manchitas pálidas cerca del borde
        const v = noise3(cx * 18 + S, r * 18, cz * 18);
        if (t > 0.8 && v > 0.55) c.lerp(veil, Math.min(0.7, (v - 0.55) * 3));
        // azulado (oxidación de la psilocina) cerca del borde, en manchas
        const b = fbm(cx * 3.1 + 40 + S, r * 2, cz * 3.1);
        if (t > 0.72 && b > 0.18) c.lerp(bruise, Math.min(0.55, (b - 0.18) * 2.2) * (t - 0.72) / 0.28);
      }
      col.set([c.r, c.g, c.b], i * 3);
    }
    capGeo.setAttribute('color', new THREE.BufferAttribute(col, 3));
    capGeo.computeVertexNormals();
  }
  const capMat = new THREE.MeshPhysicalMaterial({ vertexColors: true, roughness: 0.46, clearcoat: 0.35, clearcoatRoughness: 0.45, sheen: 0.55, sheenRoughness: 0.55, sheenColor: C('#ffd08f') });
  const cap = new THREE.Mesh(capGeo, capMat);
  cap.castShadow = true; cap.receiveShadow = true;

  /* ------------------------------ laminillas ------------------------------ */
  const yU = yUnder;
  const N = 120, SEG = 14, pos = [], cols = [], idx = [];
  const gDark = C('#1E1218'), gEdge = C('#6E5560');
  for (let g = 0; g < N; g++) {
    const a = (g / N) * Math.PI * 2 + 0.002 * noise3(g, 1, S);
    const r0 = g % 4 === 0 ? 0.1 : g % 2 === 0 ? 0.38 : 0.64, r1 = 0.95;
    const base = pos.length / 3;
    for (let s = 0; s <= SEG; s++) {
      const u = s / SEG, r = r0 + (r1 - r0) * u;
      const depth = 0.075 * Math.pow(Math.sin(Math.PI * Math.min(1, u * 1.08)), 0.75) * (0.9 + 0.2 * noise3(g * 0.7, u * 3, S));
      const x = Math.cos(a) * r, z = Math.sin(a) * r, y = yU(r) - 0.003;
      pos.push(x, y, z, x * 0.998, y - depth, z * 0.998);
      cols.push(gDark.r, gDark.g, gDark.b, gEdge.r, gEdge.g, gEdge.b);
      if (s < SEG) { const q = base + s * 2; idx.push(q, q + 1, q + 2, q + 1, q + 3, q + 2); }
    }
  }
  const gillGeo = new THREE.BufferGeometry();
  gillGeo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  gillGeo.setAttribute('color', new THREE.Float32BufferAttribute(cols, 3));
  gillGeo.setIndex(idx); gillGeo.computeVertexNormals();
  const gills = new THREE.Mesh(gillGeo, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.85, side: THREE.DoubleSide }));

  const capGroup = new THREE.Group();
  capGroup.add(cap, gills);
  capGroup.scale.setScalar(capScale);

  /* ------------------------------ pie ------------------------------ */
  const sp = [];
  const stemR = (t) => 0.078 + 0.022 * t + 0.05 * Math.pow(Math.max(0, t - 0.8) / 0.2, 2) - 0.06 * Math.pow(Math.max(0, t - 0.965) / 0.035, 2);
  for (let i = 0; i <= 90; i++) { const t = i / 90; sp.push(new THREE.Vector2(Math.max(0.001, stemR(t)), -t * stemH)); }
  sp.push(new THREE.Vector2(0.075, -stemH - 0.12), new THREE.Vector2(0.001, -stemH - 0.14)); // entra en la tierra
  const stemGeo = new THREE.LatheGeometry(sp, 96);
  const bend = (t) => ({ x: 0.1 * Math.sin(Math.PI * t * 1.2) - 0.06 * t * t, z: 0.06 * Math.sin(Math.PI * t * 0.7) });
  {
    const p = stemGeo.attributes.position, col = new Float32Array(p.count * 3);
    const cream = C('#EFE8DC'), warm = C('#E2C9A0'), blue = C('#3E6FD6');
    for (let i = 0; i < p.count; i++) {
      let x = p.getX(i), y = p.getY(i), z = p.getZ(i);
      const t = Math.min(1, -y / stemH), phi = Math.atan2(z, x);
      const fib = 1 + 0.03 * fbm(Math.cos(phi) * 7 + S, y * 9, Math.sin(phi) * 7) + 0.03 * noise3(phi * 44, y * 1.2, S);
      x *= fib; z *= fib;
      const b = bend(t); x += b.x; z += b.z;
      p.setXYZ(i, x, y, z);
      let c = lerpC(warm, cream, Math.min(1, t * 3));
      const n = fbm(Math.cos(phi) * 2.5 + 11, y * 3.5 + S, Math.sin(phi) * 2.5);
      const blueAmt = Math.max(0, (t - 0.55) / 0.45) * (0.45 + 0.55 * Math.max(0, n + 0.2));
      c = c.lerp(blue, Math.min(0.75, blueAmt));
      c.multiplyScalar(1 + 0.1 * noise3(phi * 44, y * 1.2, S) + 0.05 * noise3(phi * 9, y * 20, S));
      col.set([c.r, c.g, c.b], i * 3);
    }
    stemGeo.setAttribute('color', new THREE.BufferAttribute(col, 3));
    stemGeo.computeVertexNormals();
  }
  const stem = new THREE.Mesh(stemGeo, new THREE.MeshPhysicalMaterial({ vertexColors: true, roughness: 0.62, sheen: 0.8, sheenRoughness: 0.4, sheenColor: C('#ffffff') }));
  stem.castShadow = true; stem.receiveShadow = true;

  /* ------------------------------ anillo (velo) ------------------------------ */
  const rp = [[0.098, 0.0], [0.13, -0.012], [0.17, -0.04], [0.195, -0.085], [0.188, -0.11], [0.17, -0.1], [0.12, -0.05], [0.1, -0.03]].map(([x, y]) => new THREE.Vector2(x, y));
  const ringGeo = new THREE.LatheGeometry(rp, 72);
  {
    const p = ringGeo.attributes.position, col = new Float32Array(p.count * 3), dark = C('#3E2A33'), pale = C('#CDBFB0');
    for (let i = 0; i < p.count; i++) {
      const x = p.getX(i), y = p.getY(i), z = p.getZ(i), phi = Math.atan2(z, x), r = Math.hypot(x, z);
      const tear = r > 0.16 ? 1 + 0.12 * noise3(phi * 7 + S, 2, 3) : 1;
      p.setXYZ(i, x * tear, y - (r > 0.16 ? 0.02 * Math.max(0, noise3(phi * 9, 5, S)) : 0), z * tear);
      const c = lerpC(pale, dark, 0.35 + 0.6 * Math.max(0, noise3(phi * 5, r * 10, S + 3)));
      col.set([c.r, c.g, c.b], i * 3);
    }
    ringGeo.setAttribute('color', new THREE.BufferAttribute(col, 3));
    ringGeo.computeVertexNormals();
  }
  const ring = new THREE.Mesh(ringGeo, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.9, side: THREE.DoubleSide }));
  const tRing = 0.13;
  const bR = bend(tRing);
  ring.position.set(bR.x, -tRing * stemH, bR.z);

  /* ------------------------------ ensamblado ------------------------------ */
  const stemGroup = new THREE.Group();
  stemGroup.add(stem, ring);
  stemGroup.position.y = stemH;             // base del pie en y = 0
  capGroup.position.set(0, stemH - 0.045, 0);
  capGroup.rotation.set(0.05, 0.3, -0.07);
  group.add(stemGroup, capGroup);

  // puntos de anclaje para anotaciones
  const anchor = (x, y, z, parent) => { const o = new THREE.Object3D(); o.position.set(x, y, z); parent.add(o); return o; };
  const anchors = {
    umbo: anchor(0, 0.8, 0, capGroup),
    capEdge: anchor(-0.95, 0.02, 0.1, capGroup),
    gills: anchor(0.55, -0.02, 0.35, capGroup),
    ring: anchor(bR.x + 0.19, -tRing * stemH - 0.08, bR.z, stemGroup),
    stem: anchor(bend(0.5).x + 0.11, -0.5 * stemH, bend(0.5).z, stemGroup),
    base: anchor(bend(0.95).x, -0.95 * stemH, bend(0.95).z, stemGroup),
  };

  // materiales para el "escaneo" (wireframe que se vuelve sólido)
  const solids = [cap, gills, stem, ring];
  const wireMat = new THREE.MeshBasicMaterial({ color: C('#7FE9FF'), wireframe: true, transparent: true, opacity: 0.35, depthWrite: false });
  const wires = solids.map((m) => { const w = new THREE.Mesh(m.geometry, wireMat); m.parent.add(w); w.position.copy(m.position); w.rotation.copy(m.rotation); return w; });

  return { group, capGroup, stemGroup, cap, gills, stem, ring, anchors, solids, wires, wireMat };
}
