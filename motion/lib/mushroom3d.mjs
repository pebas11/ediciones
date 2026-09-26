// Modelo 3D procedural de Psilocybe cubensis: sombrero con umbo, laminillas, anillo y pie
// con el azulado típico. Todo determinista (ruido con semilla fija).
import { THREE, fbm, noise3 } from './three-stage.mjs';

const C = (h) => new THREE.Color(h);
const lerpC = (a, b, t) => a.clone().lerp(b, Math.min(1, Math.max(0, t)));

export function buildMushroom({ seed = 1, stemH = 1.75, capScale = 1, age = 0.8 } = {}) {
  // age: 0 = joven (sombrero en campana, naranja-marrón, motas del velo, pie grueso) → 1 = maduro (convexo/plano, dorado pálido)
  const L = (a, b) => a + (b - a) * age;
  const group = new THREE.Group();
  const S = seed * 17.3;

  /* ------------------------------ sombrero ------------------------------ */
  const R = L(0.8, 1.0), H = L(0.74, 0.48), U = L(0.025, 0.085), PE = L(1.9, 2.3), QE = L(0.62, 0.85);
  const topY = (r) => H * Math.pow(Math.max(0, 1 - Math.pow(r / R, PE)), QE) + U * Math.exp(-Math.pow(r / (0.14 * R), 2)) - 0.05 * Math.pow(r / R, 6);
  const UD = L(0.22, 0.14);   // concavidad de la cara inferior (más cerrada en jóvenes)
  const yUnder = (r) => -0.075 + UD * (1 - Math.pow(r / (0.975 * R), 1.6));
  const prof = [];
  for (let i = 0; i <= 56; i++) { const r = Math.max(0.001, (i / 56) * R); prof.push(new THREE.Vector2(r, topY(r))); }
  // borde: en jóvenes se curva hacia adentro (hacia el pie)
  prof.push(new THREE.Vector2(R * L(0.985, 0.997), -0.075 - L(0.03, 0)), new THREE.Vector2(R * L(0.93, 0.978), -0.085 - L(0.035, 0)));
  for (let i = 1; i <= 24; i++) { const r = 0.975 * R - (0.975 * R - 0.07) * (i / 24); prof.push(new THREE.Vector2(r, yUnder(r))); }
  const capGeo = new THREE.LatheGeometry(prof, 200);
  {
    const p = capGeo.attributes.position, col = new Float32Array(p.count * 3);
    const umbo = lerpC(C('#6B3414'), C('#9A5B22'), age), caramel = lerpC(C('#A0521E'), C('#C98A3E'), age), gold = lerpC(C('#C77A33'), C('#DDB36B'), age), lip = lerpC(C('#D9A869'), C('#EFE3C8'), age), under = C('#1d1218'), bruise = C('#2A5FCC'), veil = C('#F6F1E7');
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
        const t = r / (0.95 * R);
        c = t < 0.25 ? lerpC(umbo, caramel, t / 0.25) : t < 0.7 ? lerpC(caramel, gold, (t - 0.25) / 0.45) : lerpC(gold, lip, (t - 0.7) / 0.3);
        // estrías radiales finas + manchas
        const streak = 0.13 * noise3(phi * 34 + S, r * 3.5, 0.5) + 0.08 * fbm(cx * 9, y * 9 + S, cz * 9);
        c.multiplyScalar(1 + streak);
        // restos del velo: manchitas pálidas cerca del borde
        const v = noise3(cx * 22 + S, r * 22, cz * 22);
        const vt = L(0.4, 0.62);                       // jóvenes: más motas del velo, en todo el sombrero
        if (t > L(0.25, 0.8) && v > vt) c.lerp(veil, Math.min(0.85, (v - vt) * 4));
        // azulado (oxidación de la psilocina) cerca del borde, en manchas
        const b = fbm(cx * 3.1 + 40 + S, r * 2, cz * 3.1);
        if (t > 0.72 && b > 0.18) c.lerp(bruise, Math.min(0.55, (b - 0.18) * 2.2) * (t - 0.72) / 0.28);
      }
      col.set([c.r, c.g, c.b], i * 3);
    }
    capGeo.setAttribute('color', new THREE.BufferAttribute(col, 3));
    capGeo.computeVertexNormals();
  }
  const capMat = new THREE.MeshPhysicalMaterial({ side: THREE.DoubleSide, vertexColors: true, roughness: 0.52, clearcoat: 0.18, clearcoatRoughness: 0.55, sheen: 0.55, sheenRoughness: 0.55, sheenColor: C('#ffd08f') });
  const cap = new THREE.Mesh(capGeo, capMat);
  cap.castShadow = true; cap.receiveShadow = true;

  /* ------------------------------ laminillas ------------------------------ */
  const yU = yUnder;
  const N = 120, SEG = 14, pos = [], cols = [], idx = [];
  const gDark = C('#1E1218'), gEdge = C('#6E5560');
  for (let g = 0; g < N; g++) {
    const a = (g / N) * Math.PI * 2 + 0.002 * noise3(g, 1, S);
    const r0 = (g % 4 === 0 ? 0.13 : g % 2 === 0 ? 0.38 : 0.64) * R, r1 = 0.95 * R;
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
  const SR = L(0.15, 0.105);  // pie grueso (≈ 1/4–1/3 del sombrero), según fotos de referencia
  const stemR = (t) => SR * (0.86 + 0.28 * t) + 0.035 * Math.pow(Math.max(0, t - 0.8) / 0.2, 2) - SR * 0.5 * Math.pow(Math.max(0, t - 0.965) / 0.035, 2);
  // el pie sube 0,22 dentro del sombrero (queda oculto): nunca puede haber un hueco entre pie y sombrero
  const IN = 0.16 * capScale;
  sp.push(new THREE.Vector2(0.001, IN), new THREE.Vector2(SR * 0.92, IN), new THREE.Vector2(SR * 0.95, IN * 0.4));
  for (let i = 0; i <= 90; i++) { const t = i / 90; const apex = 0.1 * SR * Math.max(0, 1 - t / 0.06); sp.push(new THREE.Vector2(Math.max(0.001, stemR(t) + apex), -t * stemH)); }
  sp.push(new THREE.Vector2(SR * 0.9, -stemH - 0.12), new THREE.Vector2(0.001, -stemH - 0.14)); // entra en la tierra
  const stemGeo = new THREE.LatheGeometry(sp, 96);
  const bend = (t) => ({ x: 0.1 * Math.sin(Math.PI * t * 1.2) - 0.06 * t * t, z: 0.06 * Math.sin(Math.PI * t * 0.7) });
  {
    const p = stemGeo.attributes.position, col = new Float32Array(p.count * 3);
    const cream = C('#E4DDD1'), warm = C('#DCCDB2'), blue = C('#3E6FD6'), dirt = C('#8A6A4E');
    for (let i = 0; i < p.count; i++) {
      let x = p.getX(i), y = p.getY(i), z = p.getZ(i);
      const t = Math.max(0, Math.min(1, -y / stemH)), phi = Math.atan2(z, x);
      const fib = 1 + 0.03 * fbm(Math.cos(phi) * 7 + S, y * 9, Math.sin(phi) * 7) + 0.03 * noise3(phi * 44, y * 1.2, S);
      x *= fib; z *= fib;
      const b = bend(t); x += b.x; z += b.z;
      p.setXYZ(i, x, y, z);
      let c = lerpC(warm, cream, Math.min(1, t * 3));
      const n = fbm(Math.cos(phi) * 2.5 + 11, y * 3.5 + S, Math.sin(phi) * 2.5);
      const blueAmt = Math.max(0, (t - 0.55) / 0.45) * (0.45 + 0.55 * Math.max(0, n + 0.2));
      c = c.lerp(blue, Math.min(0.75, blueAmt));
      if (t > 0.9) c = c.lerp(dirt, Math.min(0.6, (t - 0.9) * 6 * (0.5 + 0.5 * n)));
      // textura fibrosa/afelpada del pie
      c.multiplyScalar(1 + 0.12 * noise3(phi * 60, y * 0.9, S) + 0.06 * noise3(phi * 14, y * 26, S));
      col.set([c.r, c.g, c.b], i * 3);
    }
    stemGeo.setAttribute('color', new THREE.BufferAttribute(col, 3));
    stemGeo.computeVertexNormals();
  }
  const stem = new THREE.Mesh(stemGeo, new THREE.MeshPhysicalMaterial({ side: THREE.DoubleSide, vertexColors: true, roughness: 0.7, sheen: 0.5, sheenRoughness: 0.5, sheenColor: C('#f4ece0') }));
  stem.castShadow = true; stem.receiveShadow = true;

  /* ------------------------------ anillo (velo) ------------------------------ */
  const RK = SR / 0.1;
  const rp = [[0.098, 0.0], [0.13, -0.012], [0.17, -0.04], [0.195, -0.085], [0.188, -0.11], [0.17, -0.1], [0.12, -0.05], [0.1, -0.03]].map(([x, y]) => new THREE.Vector2(x * RK, y));
  const ringGeo = new THREE.LatheGeometry(rp, 72);
  {
    const p = ringGeo.attributes.position, col = new Float32Array(p.count * 3), dark = C('#3E2A33'), pale = C('#CDBFB0');
    for (let i = 0; i < p.count; i++) {
      const x = p.getX(i), y = p.getY(i), z = p.getZ(i), phi = Math.atan2(z, x), r = Math.hypot(x, z);
      const tear = r > 0.16 * RK ? 1 + 0.12 * noise3(phi * 7 + S, 2, 3) : 1;
      p.setXYZ(i, x * tear, y - (r > 0.16 * RK ? 0.02 * Math.max(0, noise3(phi * 9, 5, S)) : 0), z * tear);
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
  // la cara inferior del sombrero (en r≈pie) apoya exactamente sobre la punta del pie
  capGroup.position.set(0, stemH - yUnder(Math.min(0.9 * R, SR / capScale)) * capScale - 0.01, 0);
  capGroup.rotation.set(0.03, 0.3, -0.04);
  group.add(stemGroup, capGroup);

  // puntos de anclaje para anotaciones
  const anchor = (x, y, z, parent) => { const o = new THREE.Object3D(); o.position.set(x, y, z); parent.add(o); return o; };
  const anchors = {
    umbo: anchor(0, topY(0), 0, capGroup),
    capEdge: anchor(-0.95 * R, 0.02, 0.1, capGroup),
    gills: anchor(0.55 * R, -0.02, 0.35 * R, capGroup),
    ring: anchor(bR.x + 0.19 * RK, -tRing * stemH - 0.08, bR.z, stemGroup),
    stem: anchor(bend(0.5).x + SR, -0.5 * stemH, bend(0.5).z, stemGroup),
    base: anchor(bend(0.95).x, -0.95 * stemH, bend(0.95).z, stemGroup),
  };

  // materiales para el "escaneo" (wireframe que se vuelve sólido)
  const solids = [cap, gills, stem, ring];
  const wireMat = new THREE.MeshBasicMaterial({ color: C('#7FE9FF'), wireframe: true, transparent: true, opacity: 0.35, depthWrite: false });
  const wires = solids.map((m) => { const w = new THREE.Mesh(m.geometry, wireMat); m.parent.add(w); w.position.copy(m.position); w.rotation.copy(m.rotation); return w; });

  return { group, capGroup, stemGroup, cap, gills, stem, ring, anchors, solids, wires, wireMat };
}

/** Mechones de pasto (hojas finas curvas, instanciadas). Evita un radio alrededor de los puntos dados. */
export function buildGrass({ count = 1400, w = 7, d = 3.6, avoid = [], seed = 4, rng } = {}) {
  const r = rng || ((s) => () => (s = (s * 1664525 + 1013904223) >>> 0) / 4294967296)(seed);
  // hoja: tira de 7 segmentos, afinada y curvada (altura 1, se escala por instancia)
  const segs = 7, pos = [], col = [], idx = [];
  const base = C('#27301c'), tip = C('#7b8752'), dry = C('#9c8a62');
  for (let i = 0; i <= segs; i++) {
    const t = i / segs, wdt = 0.0085 * (1 - t * 0.9), bend = 0.34 * t * t;
    pos.push(-wdt, t, bend, wdt, t, bend);
    const c = base.clone().lerp(tip, Math.pow(t, 1.3)); col.push(c.r, c.g, c.b, c.r, c.g, c.b);
    if (i < segs) { const q = i * 2; idx.push(q, q + 1, q + 2, q + 1, q + 3, q + 2); }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('color', new THREE.Float32BufferAttribute(col, 3));
  g.setIndex(idx); g.computeVertexNormals();
  const mesh = new THREE.InstancedMesh(g, new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.85, side: THREE.DoubleSide }), count);
  const tint = new THREE.Color();
  const m = new THREE.Matrix4(), q = new THREE.Quaternion(), e = new THREE.Euler();
  let n = 0, guard = 0;
  while (n < count && guard++ < count * 20) {
    // mechones: centros de grupo + dispersión
    const cx = (r() - 0.5) * (w - 0.3), cz = (r() - 0.5) * (d - 0.3);
    if (avoid.some(([ax, az, ar]) => Math.hypot(cx - ax, cz - az) < ar)) continue;
    const k = 6 + Math.floor(r() * 14);
    for (let j = 0; j < k && n < count; j++) {
      const x = cx + (r() - 0.5) * 0.12, z = cz + (r() - 0.5) * 0.12;
      if (Math.abs(x) > w / 2 - 0.05 || Math.abs(z) > d / 2 - 0.05) continue;
      const h = 0.25 + Math.pow(r(), 1.5) * 0.75;
      e.set((r() - 0.5) * 0.35, r() * Math.PI * 2, (r() - 0.5) * 0.35); q.setFromEuler(e);
      m.compose(new THREE.Vector3(x, -0.01, z), q, new THREE.Vector3(1 + r() * 0.6, h, 1));
      mesh.setMatrixAt(n, m);
      // variación de color por hoja: algunas secas, otras más oscuras
      tint.setRGB(1, 1, 1); const u = r();
      if (u < 0.18) tint.copy(dry).multiplyScalar(1.6); else tint.setScalar(0.7 + r() * 0.45);
      mesh.setColorAt(n++, tint);
    }
  }
  mesh.count = n; mesh.castShadow = true; mesh.receiveShadow = true;
  return mesh;
}
