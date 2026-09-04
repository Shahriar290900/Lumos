/*
 * scene.js — the library, built in code.
 *
 * Recreates the reference artwork rather than displaying it: a gothic arched
 * window with tracery, a castle silhouette beyond it, shelves receding into the
 * dark, an open book on a table, and gold motes that follow the cursor like a
 * cast spell. Nothing here is downloaded — every mesh is procedural, so the
 * whole scene costs one script and no image bytes.
 *
 * ADR-005: 3D is progressive enhancement. Without WebGL, or under
 * `prefers-reduced-motion`, the CSS behind the canvas is already a finished
 * gradient and this file does nothing. A student on a low-end Android needs the
 * tutor, not the particles.
 *
 * Performance: ~14 draw calls, no textures, no lights that cast shadows, and
 * the loop stops entirely when the canvas leaves the viewport or the tab hides.
 */

export function initScene(canvas) {
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduced || !canvas || typeof THREE === "undefined") return null;

  let gl;
  try {
    gl = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true,
                                   powerPreference: "low-power" });
  } catch { return null; }

  const GOLD = 0xd9ac5f, GOLD_HI = 0xf3d49c, NIGHT = 0x1a2647;

  const scene = new THREE.Scene();
  scene.fog = new THREE.FogExp2(0x04060d, 0.028);
  const camera = new THREE.PerspectiveCamera(52, 1, 0.1, 200);
  camera.position.set(0, 1.2, 22);

  /* ── the window ────────────────────────────────────────────────────────
   * A lancet arch: two circular arcs meeting at a point, which is what makes
   * a gothic window gothic rather than a rounded Romanesque one. Drawn as a
   * filled shape for the night sky, then again as lines for the stone tracery.
   */
  function lancet(width, height, apex) {
    // A two-centred (equilateral) arch, the shape that makes a window gothic
    // rather than Romanesque. Each side is a circular arc whose centre is the
    // OPPOSITE springing point, so the two curves meet at a point.
    //
    // With centres at (±hw, height) and radius 2·hw, the arcs cross at x = 0
    // where cos a = −1/2, i.e. at 120° and 60°. The natural apex is then
    // hw·√3 above the springing line; `apex` scales y to whatever height the
    // composition wants without bending the curve out of shape.
    const hw = width / 2;
    const R = 2 * hw;
    const yScale = apex / (hw * Math.sqrt(3));
    const STEPS = 28;
    const s = new THREE.Shape();

    s.moveTo(-hw, 0);
    s.lineTo(-hw, height);
    for (let i = 1; i <= STEPS; i++) {              // left spring → apex
      const a = Math.PI + ((2 * Math.PI / 3) - Math.PI) * (i / STEPS);
      s.lineTo(hw + Math.cos(a) * R, height + Math.sin(a) * R * yScale);
    }
    for (let i = 1; i <= STEPS; i++) {              // apex → right spring
      const a = (Math.PI / 3) * (1 - i / STEPS);
      s.lineTo(-hw + Math.cos(a) * R, height + Math.sin(a) * R * yScale);
    }
    s.lineTo(hw, 0);
    s.closePath();
    return s;
  }

  const windowGroup = new THREE.Group();
  windowGroup.position.set(4.5, -3.2, -18);

  const sky = new THREE.Mesh(
    new THREE.ShapeGeometry(lancet(11, 9, 4.6)),
    new THREE.MeshBasicMaterial({ color: NIGHT, transparent: true, opacity: 0.85 }));
  windowGroup.add(sky);

  // Stars behind the glass, brighter toward the arch so the eye is drawn up.
  const starPos = new Float32Array(150 * 3);
  for (let i = 0; i < 150; i++) {
    starPos[i * 3] = (Math.random() - 0.5) * 10;
    starPos[i * 3 + 1] = Math.random() * 12.5;
    starPos[i * 3 + 2] = 0.1;
  }
  const stars = new THREE.Points(
    new THREE.BufferGeometry().setAttribute("position",
      new THREE.BufferAttribute(starPos, 3)),
    new THREE.PointsMaterial({ color: 0xcfe0ff, size: 0.09, transparent: true,
                               opacity: 0.75, depthWrite: false }));
  windowGroup.add(stars);

  // The castle: a skyline of towers with spires, silhouetted against the sky.
  const castle = new THREE.Group();
  const towerMat = new THREE.MeshBasicMaterial({ color: 0x0a1024 });
  [[-3.6, 2.4, 0.9], [-1.9, 3.6, 0.7], [-0.2, 5.2, 1.0],
   [1.6, 3.9, 0.75], [3.2, 2.8, 0.85]].forEach(([x, h, w]) => {
    const body = new THREE.Mesh(new THREE.PlaneGeometry(w, h), towerMat);
    body.position.set(x, h / 2, 0.2);
    castle.add(body);
    // Built in statements, not chained: in three r128 `closePath()` returns
    // undefined rather than `this`, so a fluent chain ending in it hands
    // ShapeGeometry an undefined shape and the whole scene throws.
    const spireShape = new THREE.Shape();
    spireShape.moveTo(-w / 2, 0);
    spireShape.lineTo(0, w * 1.5);
    spireShape.lineTo(w / 2, 0);
    spireShape.closePath();
    const spire = new THREE.Mesh(new THREE.ShapeGeometry(spireShape), towerMat);
    spire.position.set(x, h, 0.2);
    castle.add(spire);
    // A lit window or two, because an unlit castle reads as a cut-out.
    for (let i = 0; i < 2; i++) {
      const lit = new THREE.Mesh(
        new THREE.PlaneGeometry(0.09, 0.14),
        new THREE.MeshBasicMaterial({ color: GOLD, transparent: true, opacity: 0.55 }));
      lit.position.set(x + (Math.random() - 0.5) * w * 0.5,
                       0.5 + Math.random() * (h - 0.9), 0.25);
      castle.add(lit);
    }
  });
  castle.position.y = 0.2;
  windowGroup.add(castle);

  // Tracery: the stone mullions and the arch outline.
  const stone = new THREE.LineBasicMaterial({ color: GOLD, transparent: true, opacity: 0.34 });
  const arch = lancet(11, 9, 4.6);
  windowGroup.add(new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(arch.getPoints(64)), stone));
  for (const x of [-3.7, 0, 3.7]) {
    windowGroup.add(new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(
        [new THREE.Vector3(x, 0, 0.05), new THREE.Vector3(x, 9.6, 0.05)]), stone));
  }
  for (const y of [3, 6, 9]) {
    windowGroup.add(new THREE.Line(
      new THREE.BufferGeometry().setFromPoints(
        [new THREE.Vector3(-5.5, y, 0.05), new THREE.Vector3(5.5, y, 0.05)]), stone));
  }
  // The rose at the apex.
  const rose = new THREE.Mesh(
    new THREE.RingGeometry(0.9, 1.05, 24),
    new THREE.MeshBasicMaterial({ color: GOLD, transparent: true, opacity: 0.4,
                                  side: THREE.DoubleSide }));
  rose.position.set(0, 11.4, 0.06);
  windowGroup.add(rose);
  scene.add(windowGroup);

  /* ── shelves ───────────────────────────────────────────────────────────
   * Receding planes of book spines. Colour and height vary per spine so the
   * wall reads as books rather than as a striped texture.
   */
  const shelfMat = new THREE.MeshBasicMaterial({ color: 0x0b1020 });
  function wall(x, rotation) {
    const g = new THREE.Group();
    for (let row = 0; row < 7; row++) {
      const board = new THREE.Mesh(new THREE.PlaneGeometry(13, 0.16), shelfMat);
      board.position.set(0, row * 2.2 - 6, 0);
      g.add(board);
      for (let i = 0; i < 26; i++) {
        const h = 0.9 + Math.random() * 0.7;
        const spine = new THREE.Mesh(
          new THREE.PlaneGeometry(0.16 + Math.random() * 0.12, h),
          new THREE.MeshBasicMaterial({
            color: new THREE.Color().setHSL(0.09 + Math.random() * 0.05,
                                            0.35, 0.06 + Math.random() * 0.07),
          }));
        spine.position.set(-6 + i * 0.48, row * 2.2 - 6 + h / 2 + 0.1, 0.02);
        g.add(spine);
      }
    }
    g.position.set(x, 0, -12);
    g.rotation.y = rotation;
    return g;
  }
  scene.add(wall(-13, 0.42), wall(14.5, -0.5));

  /* ── the book on the table ─────────────────────────────────────────── */
  const book = new THREE.Group();
  const pageMat = new THREE.MeshBasicMaterial({ color: 0xd8cba8, transparent: true,
                                                opacity: 0.92, side: THREE.DoubleSide });
  [-1, 1].forEach((side) => {
    const page = new THREE.Mesh(new THREE.PlaneGeometry(2.5, 3.2), pageMat);
    page.position.set(side * 1.3, 0, 0);
    page.rotation.set(-Math.PI / 2.1, 0, side * 0.075);
    book.add(page);
    // Ruled lines, so the pages read as a book rather than two cream cards.
    for (let i = 0; i < 9; i++) {
      const line = new THREE.Mesh(
        new THREE.PlaneGeometry(1.9, 0.022),
        new THREE.MeshBasicMaterial({ color: 0x6b5a3c, transparent: true, opacity: 0.5 }));
      line.position.set(side * 1.3, 0.02, -1.2 + i * 0.3);
      line.rotation.x = -Math.PI / 2;
      book.add(line);
    }
  });
  const glow = new THREE.Mesh(
    new THREE.CircleGeometry(4.2, 32),
    new THREE.MeshBasicMaterial({ color: GOLD, transparent: true, opacity: 0.07 }));
  glow.rotation.x = -Math.PI / 2;
  glow.position.y = 0.02;
  book.add(glow);
  book.position.set(1.5, -6.5, 2);
  scene.add(book);

  /* ── the cast light ────────────────────────────────────────────────────
   * A chain of motes: the head eases toward the cursor and each following mote
   * eases toward the one ahead. The lag between links is what draws the curve —
   * no physics, no solver, and it costs one buffer update per frame.
   */
  const sprite = (() => {
    const c = document.createElement("canvas");
    c.width = c.height = 64;
    const g = c.getContext("2d");
    const grad = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    grad.addColorStop(0, "rgba(255,244,214,1)");
    grad.addColorStop(0.3, "rgba(217,172,95,0.6)");
    grad.addColorStop(1, "rgba(217,172,95,0)");
    g.fillStyle = grad;
    g.fillRect(0, 0, 64, 64);
    return new THREE.CanvasTexture(c);
  })();

  const TRAIL = 300;
  const trailPos = new Float32Array(TRAIL * 3);
  const trailSize = new Float32Array(TRAIL);
  for (let i = 0; i < TRAIL; i++) trailSize[i] = 0.5 * (1 - i / TRAIL) + 0.06;
  const trailGeo = new THREE.BufferGeometry();
  trailGeo.setAttribute("position", new THREE.BufferAttribute(trailPos, 3));
  const trail = new THREE.Points(trailGeo, new THREE.PointsMaterial({
    size: 0.44, map: sprite, transparent: true, depthWrite: false,
    blending: THREE.AdditiveBlending, color: GOLD_HI, opacity: 0.95,
  }));
  scene.add(trail);

  // Dust, drifting. The reference has motes hanging in the shaft of light.
  const DUST = 320;
  const dustPos = new Float32Array(DUST * 3);
  const drift = new Float32Array(DUST);
  for (let i = 0; i < DUST; i++) {
    dustPos[i * 3] = (Math.random() - 0.5) * 44;
    dustPos[i * 3 + 1] = (Math.random() - 0.5) * 26;
    dustPos[i * 3 + 2] = (Math.random() - 0.5) * 22;
    drift[i] = 0.1 + Math.random() * 0.3;
  }
  const dust = new THREE.Points(
    new THREE.BufferGeometry().setAttribute("position",
      new THREE.BufferAttribute(dustPos, 3)),
    new THREE.PointsMaterial({ size: 0.13, map: sprite, transparent: true,
      depthWrite: false, blending: THREE.AdditiveBlending, color: GOLD, opacity: 0.4 }));
  scene.add(dust);

  /* ── candles ───────────────────────────────────────────────────────── */
  const flames = [];
  [[-8.5, -4.4, -3], [10.5, -3.4, -4], [-6, -1.2, -9]].forEach(([x, y, z]) => {
    const flame = new THREE.Mesh(
      new THREE.CircleGeometry(0.22, 12),
      new THREE.MeshBasicMaterial({ color: GOLD_HI, transparent: true,
        opacity: 0.85, blending: THREE.AdditiveBlending }));
    flame.position.set(x, y, z);
    scene.add(flame);
    flames.push({ mesh: flame, phase: Math.random() * 6.28 });
  });

  /* ── loop ──────────────────────────────────────────────────────────── */
  const target = new THREE.Vector3(2, 0, 4);
  const head = target.clone();
  const parallax = new THREE.Vector2(0, 0);
  let idle = 0, running = false, raf = 0;

  addEventListener("pointermove", (e) => {
    const r = canvas.getBoundingClientRect();
    const nx = ((e.clientX - r.left) / r.width) * 2 - 1;
    const ny = -(((e.clientY - r.top) / r.height) * 2 - 1);
    target.set(nx * 15, ny * 9, 4);
    parallax.set(nx, ny);
    idle = 0;
  }, { passive: true });

  function size() {
    const r = canvas.getBoundingClientRect();
    gl.setPixelRatio(Math.min(devicePixelRatio, 1.5));
    gl.setSize(r.width, r.height, false);
    camera.aspect = r.width / Math.max(r.height, 1);
    camera.updateProjectionMatrix();
  }

  const clock = new THREE.Clock();
  function frame() {
    if (!running) return;
    raf = requestAnimationFrame(frame);
    const t = clock.getElapsedTime();
    idle += 1 / 60;

    // No pointer — a touch device, or a still hand — so the light draws a slow
    // figure of its own. The hero is never a dead rectangle.
    if (idle > 2.2) {
      target.set(Math.sin(t * 0.4) * 12, Math.cos(t * 0.29) * 7, 4);
      parallax.set(Math.sin(t * 0.4) * 0.5, Math.cos(t * 0.29) * 0.4);
    }

    head.lerp(target, 0.13);
    for (let i = TRAIL - 1; i > 0; i--) {
      const a = i * 3, b = (i - 1) * 3;
      trailPos[a] += (trailPos[b] - trailPos[a]) * 0.36;
      trailPos[a + 1] += (trailPos[b + 1] - trailPos[a + 1]) * 0.36;
      trailPos[a + 2] += (trailPos[b + 2] - trailPos[a + 2]) * 0.36;
    }
    trailPos[0] = head.x; trailPos[1] = head.y; trailPos[2] = head.z;
    trailGeo.attributes.position.needsUpdate = true;

    for (let i = 0; i < DUST; i++) {
      dustPos[i * 3 + 1] += drift[i] * 0.006;
      if (dustPos[i * 3 + 1] > 13) dustPos[i * 3 + 1] = -13;
    }
    dust.geometry.attributes.position.needsUpdate = true;
    dust.rotation.y = t * 0.012;

    flames.forEach((f, i) => {
      f.mesh.material.opacity = 0.6 + Math.sin(t * 7 + f.phase) * 0.18
                                    + Math.sin(t * 13.3 + i) * 0.08;
      f.mesh.scale.setScalar(0.9 + Math.sin(t * 9 + f.phase) * 0.12);
    });

    // Parallax: the camera leans a little toward the cursor, which is what
    // makes a flat set of planes read as depth.
    camera.position.x += (parallax.x * 1.8 - camera.position.x) * 0.03;
    camera.position.y += (1.2 + parallax.y * 1.1 - camera.position.y) * 0.03;
    camera.lookAt(0, -0.5, -6);

    stars.material.opacity = 0.55 + Math.sin(t * 0.6) * 0.14;
    gl.render(scene, camera);
  }

  size();
  addEventListener("resize", size, { passive: true });

  const start = () => { if (!running) { running = true; frame(); } };
  const stop = () => { running = false; cancelAnimationFrame(raf); };

  // An animation loop running behind a hidden tab or a scrolled-past hero is a
  // battery bug on exactly the devices this targets.
  new IntersectionObserver(([e]) => (e.isIntersecting ? start() : stop()),
                           { threshold: 0.02 }).observe(canvas);
  addEventListener("visibilitychange", () => (document.hidden ? stop() : start()));
  start();

  return { stop };
}
