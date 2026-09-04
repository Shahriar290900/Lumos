/*
 * lumos.js — the Lumos web app: 3D hero, routing, and the tutor.
 *
 * ADR-005: 3D is progressive enhancement. Every view works without WebGL, and
 * the scene is torn down entirely under `prefers-reduced-motion`. The hero is
 * the only place 3D appears, because a student on a low-end Android over a
 * throttled connection needs the tutor, not the particles.
 *
 * ADR-011: availability comes from the registry. Nothing here decides whether a
 * subject can be asked about; it renders what `/curriculum` returns, including
 * the blocked reasons verbatim.
 */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const REDUCED = matchMedia("(prefers-reduced-motion: reduce)").matches;
const state = { offerings: [], health: null, current: null, docs: [] };

/* ─────────────────────────────────────────────────────────────────────────
 * The 3D hero
 *
 * A wand-cast trail of gold motes drawn toward the cursor, over a slow drift
 * of dust. Two draw calls total: one Points for the trail, one for the dust.
 * No models, no textures, no loaders — the whole scene is procedural, so it
 * adds nothing to the page weight beyond three.js itself.
 * ──────────────────────────────────────────────────────────────────────── */
function initHero(canvas) {
  if (REDUCED || typeof THREE === "undefined") return null;
  let gl;
  try {
    gl = new THREE.WebGLRenderer({ canvas, antialias: false, alpha: true,
                                   powerPreference: "low-power" });
  } catch { return null; }              // no WebGL: the CSS gradient stands in

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(58, 1, 0.1, 100);
  camera.position.z = 15;

  const size = () => {
    const r = canvas.getBoundingClientRect();
    // Cap at 1.5: a 3x retina buffer quadruples fragment cost for no visible gain.
    gl.setPixelRatio(Math.min(devicePixelRatio, 1.5));
    gl.setSize(r.width, r.height, false);
    camera.aspect = r.width / Math.max(r.height, 1);
    camera.updateProjectionMatrix();
  };

  // A soft round sprite, drawn once into a canvas. Cheaper and sharper than a
  // downloaded texture, and it cannot fail to load.
  const sprite = (() => {
    const c = document.createElement("canvas");
    c.width = c.height = 64;
    const g = c.getContext("2d");
    const grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    grd.addColorStop(0, "rgba(255,240,205,1)");
    grd.addColorStop(0.35, "rgba(217,172,95,0.65)");
    grd.addColorStop(1, "rgba(217,172,95,0)");
    g.fillStyle = grd;
    g.fillRect(0, 0, 64, 64);
    return new THREE.CanvasTexture(c);
  })();

  const TRAIL = 260, DUST = 220;

  const trailPos = new Float32Array(TRAIL * 3);
  const trail = new THREE.Points(
    new THREE.BufferGeometry().setAttribute("position",
      new THREE.BufferAttribute(trailPos, 3)),
    new THREE.PointsMaterial({
      size: 0.42, map: sprite, transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending, color: 0xf0cd8a, opacity: 0.95,
    }));
  scene.add(trail);

  const dustPos = new Float32Array(DUST * 3);
  for (let i = 0; i < DUST; i++) {
    dustPos[i * 3] = (Math.random() - 0.5) * 34;
    dustPos[i * 3 + 1] = (Math.random() - 0.5) * 20;
    dustPos[i * 3 + 2] = (Math.random() - 0.5) * 14;
  }
  const dust = new THREE.Points(
    new THREE.BufferGeometry().setAttribute("position",
      new THREE.BufferAttribute(dustPos, 3)),
    new THREE.PointsMaterial({
      size: 0.16, map: sprite, transparent: true, depthWrite: false,
      blending: THREE.AdditiveBlending, color: 0xd9ac5f, opacity: 0.42,
    }));
  scene.add(dust);

  // The trail is a chain: each mote eases toward the one ahead, and the head
  // eases toward the cursor. That produces the whip of the wand stroke without
  // any physics — the lag between links *is* the curve.
  const target = new THREE.Vector3(0, 0, 0);
  const head = new THREE.Vector3(0, 0, 0);
  let idle = 0, running = true, raf = 0;

  const onMove = (e) => {
    const r = canvas.getBoundingClientRect();
    const nx = ((e.clientX - r.left) / r.width) * 2 - 1;
    const ny = -(((e.clientY - r.top) / r.height) * 2 - 1);
    target.set(nx * 13, ny * 8, 0);
    idle = 0;
  };
  addEventListener("pointermove", onMove, { passive: true });

  const clock = new THREE.Clock();
  function frame() {
    if (!running) return;
    raf = requestAnimationFrame(frame);
    const t = clock.getElapsedTime();
    idle += 1 / 60;

    // With no pointer — a touch device, or a still hand — the trail draws a
    // slow lissajous so the hero is never a dead rectangle.
    if (idle > 2.5) target.set(Math.sin(t * 0.42) * 11, Math.cos(t * 0.31) * 6.5, 0);

    head.lerp(target, 0.12);
    for (let i = TRAIL - 1; i > 0; i--) {
      const a = i * 3, b = (i - 1) * 3;
      trailPos[a] += (trailPos[b] - trailPos[a]) * 0.34;
      trailPos[a + 1] += (trailPos[b + 1] - trailPos[a + 1]) * 0.34;
      trailPos[a + 2] += (trailPos[b + 2] - trailPos[a + 2]) * 0.34;
    }
    trailPos[0] = head.x; trailPos[1] = head.y; trailPos[2] = head.z;
    trail.geometry.attributes.position.needsUpdate = true;

    dust.rotation.y = t * 0.018;
    dust.rotation.x = Math.sin(t * 0.1) * 0.05;
    gl.render(scene, camera);
  }

  size();
  addEventListener("resize", size, { passive: true });
  frame();

  // Stop when the hero scrolls away or the tab hides. An animation loop running
  // behind a hidden tab is a battery bug on the exact devices this targets.
  const io = new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting && !running) { running = true; frame(); }
    else if (!entry.isIntersecting) { running = false; cancelAnimationFrame(raf); }
  }, { threshold: 0.02 });
  io.observe(canvas);
  addEventListener("visibilitychange", () => {
    if (document.hidden) { running = false; cancelAnimationFrame(raf); }
    else if (!running) { running = true; frame(); }
  });

  return { stop: () => { running = false; cancelAnimationFrame(raf); } };
}

/* ─────────────────────────────────────────────────────────────────────────
 * The hero film
 *
 * The transformation clip: a dark library, a wand cast, gold light spreading.
 * It plays once and holds on its final frame, so the hero settles into the
 * illuminated scene rather than looping a 10-second animation behind the text.
 *
 * 4.8 MB, so it is loaded on merit and not by default. Skipped entirely under
 * reduced motion, on a narrow screen, when the browser reports a slow
 * connection, and when the user has asked to save data. In every one of those
 * cases the still is already painted and the hero looks finished.
 * ──────────────────────────────────────────────────────────────────────── */
function initHeroFilm() {
  const video = $("#heroVideo");
  const still = $("#heroStill");
  if (!video) return;

  const conn = navigator.connection || {};
  const slow = conn.saveData === true ||
               /^(slow-)?2g$/.test(conn.effectiveType || "");
  if (REDUCED || slow || innerWidth < 720) {
    video.remove();
    // The end frame is the scene lit — the right resting state when the film
    // will not play at all.
    still.src = "/static/media/hero-end.jpg";
    return;
  }

  video.src = "/static/media/hero.mp4";
  video.preload = "auto";
  video.addEventListener("canplaythrough", () => {
    video.classList.add("on");
    video.play().catch(() => {
      // Autoplay refused, which some mobile browsers do even when muted.
      // Fall back to the lit still rather than leaving a dark frame.
      video.remove();
      still.src = "/static/media/hero-end.jpg";
    });
  }, { once: true });

  video.addEventListener("ended", () => {
    // Hold the last frame. Swapping the still underneath first means no flash
    // of the dark start frame when the video element is finally removed.
    still.src = "/static/media/hero-end.jpg";
    still.decode?.().catch(() => {}).finally(() => video.classList.remove("on"));
  }, { once: true });

  video.addEventListener("error", () => {
    video.remove();
    still.src = "/static/media/hero-end.jpg";
  }, { once: true });

  // Do not burn a decoder on a hero nobody is looking at.
  addEventListener("visibilitychange", () => {
    if (document.hidden) video.pause();
    else if (!video.ended) video.play().catch(() => {});
  });
}

/* ─────────────────────────────────────────────────────────────────────────
 * Data
 * ──────────────────────────────────────────────────────────────────────── */
async function loadHealth() {
  try { state.health = await (await fetch("/health")).json(); }
  catch { state.health = { status: "unreachable" }; }
  const h = state.health;
  const label = { live: "generation live", mock: "mocked explanation",
                  unavailable: "no generation model", error: "generation error"
                }[h.generation] || h.status;
  $("#status").innerHTML = h.status === "unreachable"
    ? `<b>API unreachable</b>`
    : `db ${esc(h.database)} · <b>${esc(label)}</b>`;
  $("#status").title = h.generation_note || "";
}

async function loadCurriculum() {
  const data = await (await fetch("/curriculum")).json();
  state.offerings = data.offerings;
  const available = state.offerings.filter((o) => o.is_available);
  state.current = (available[0] || state.offerings[0] || null)?.slug ?? null;
  $("#availCount").textContent = `${available.length} of ${state.offerings.length}`;
}

/* ─────────────────────────────────────────────────────────────────────────
 * Views
 * ──────────────────────────────────────────────────────────────────────── */
function offeringOptions() {
  return state.offerings.map((o) =>
    `<option value="${esc(o.slug)}"${o.slug === state.current ? " selected" : ""}>
       ${esc(o.subject_name_en)} — ${esc(o.level_name)}${o.is_available ? "" : "  · not available"}
     </option>`).join("");
}

const views = {
  tutor: () => `
    <section class="pane">
      <h2>Ask the tutor</h2>
      <p class="sub">Answers come only from the declared corpus. Every citation
        resolves to a passage retrieved for that question, and insufficient
        evidence produces a stated limitation rather than a guess.</p>
      <div class="ask">
        <select id="offering">${offeringOptions()}</select>
        <input id="q" type="text" placeholder="How do I calculate gravitational potential energy?">
        <button id="go" class="gold">Cast Lumos</button>
      </div>
      <div class="chips">
        ${["How do I calculate gravitational potential energy?",
           "Explain the photoelectric effect.",
           "What affects the resistance of a wire?"]
          .map((q) => `<button class="chip">${esc(q)}</button>`).join("")}
      </div>
      <div id="answer"></div>
    </section>`,

  curriculum: () => `
    <section class="pane">
      <h2>Curriculum registry</h2>
      <p class="sub">The single source of availability. A subject is available only
        with indexed chunks, a known licence and a passing evaluation — never
        because a card exists.</p>
      <div class="grid">
        ${state.offerings.map((o) => `
          <article class="offering ${o.is_available ? "on" : "off"}">
            <header>
              <h3>${esc(o.subject_name_en)}</h3>
              <span class="pill ${o.is_available ? "yes" : "no"}">
                ${o.is_available ? "available" : "not yet"}</span>
            </header>
            <div class="meta">${esc(o.level_name)} · ${esc(o.curriculum_name || "")}</div>
            <div class="bar"><i style="width:${Math.min(100, (o.indexed_chunk_count || 0) / 2)}%"></i></div>
            <div class="meta">${o.indexed_chunk_count || 0} indexed chunks</div>
            ${(o.blocked_reasons || []).length
              ? `<ul class="reasons">${o.blocked_reasons.map((r) =>
                  `<li>${esc(r)}</li>`).join("")}</ul>`
              : `<div class="meta ok">no blocking conditions</div>`}
            ${o.display_note_en ? `<p class="note">${esc(o.display_note_en)}</p>` : ""}
          </article>`).join("")}
      </div>
    </section>`,

  sources: () => `
    <section class="pane">
      <h2>Source documents</h2>
      <p class="sub">Exam papers, mark schemes and examiner reports can be opened.
        The textbook cannot: it grounds answers and is never shown, because it is a
        commercial work rather than freely published exam material.</p>
      <div class="ask">
        <select id="docOffering">${offeringOptions()}</select>
        <button id="loadDocs" class="gold">Load documents</button>
      </div>
      <div id="docs"></div>
    </section>`,

  how: () => `
    <section class="pane">
      <h2>How an answer is built</h2>
      <p class="sub">Five stages. Each can refuse, and a refusal is a real answer.</p>
      <ol class="steps">
        <li><b>Availability</b><span>The registry decides. Nothing downstream runs for a
          subject it has not cleared — that check is a SQL view, not an <code>if</code>.</span></li>
        <li><b>Retrieval</b><span>Postgres full-text and pgvector in one query, the
          curriculum filter applied before ranking, fused with Reciprocal Rank Fusion at k=60.</span></li>
        <li><b>Confidence</b><span>Too little evidence produces a stated limitation.
          The search is never widened until something comes back.</span></li>
        <li><b>Generation</b><span>One model, <code>gemma4:e4b</code>. When it is
          unavailable the tutor says so rather than answering from something else.</span></li>
        <li><b>Validation</b><span>A citation that does not resolve to this turn's
          context is stripped, and an answer left with none is not shown as grounded.</span></li>
      </ol>
    </section>`,
};

/* ─────────────────────────────────────────────────────────────────────────
 * Tutor
 * ──────────────────────────────────────────────────────────────────────── */
function renderCites(text, citations) {
  const known = new Set(citations.map((c) => c.marker));
  return esc(text).replace(/\[(\d{1,2})\]/g, (m, n) =>
    known.has(+n) ? `<span class="cite">${n}</span>` : m);
}

async function ask() {
  const slug = $("#offering").value, query = $("#q").value.trim();
  if (!query) return;
  const out = $("#answer");
  out.innerHTML = `<div class="note-box working">Casting…</div>`;
  $("#go").disabled = true;
  try {
    const res = await fetch("/tutor/ask", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query, slug }),
    });
    const d = await res.json();

    if (res.status === 409) {
      const x = d.detail || {};
      out.innerHTML = `<div class="note-box warn">
        <b>Not available yet.</b> ${esc(x.message_en || "")}
        <ul class="reasons">${(x.blocked_reasons || []).map((r) =>
          `<li>${esc(r)}</li>`).join("")}</ul>
        <p class="meta">The registry refused this before any retrieval ran.
          That is the coverage gate working, not an error.</p></div>`;
      return;
    }
    if (!res.ok) {
      out.innerHTML = `<div class="note-box bad">${esc(JSON.stringify(d.detail || d))}</div>`;
      return;
    }

    let banner = "";
    if (d.is_mock)
      banner = `<div class="note-box warn"><b>Mocked explanation.</b> Retrieval and
        the sources below are real; the prose is not a tutoring answer.</div>`;
    else if (d.limitation === "no_generation_model")
      banner = `<div class="note-box warn"><b>No generation model.</b> Retrieval ran
        and the citations are real, but nothing is configured to write the explanation.</div>`;
    else if (d.limitation)
      banner = `<div class="note-box warn"><b>Stated limitation:</b> ${esc(d.limitation)}</div>`;
    else if (d.grounded)
      banner = `<div class="note-box ok"><b>Grounded.</b> ${d.citations.length}
        citation(s), each resolving to a passage retrieved for this question.</div>`;

    const r = d.retrieval || {};
    out.innerHTML = banner
      + `<div class="answer">${renderCites(d.answer || "", d.citations || [])}</div>`
      + ((d.citations || []).length ? `<h4>Sources</h4><ol class="sources">${
          d.citations.map((c) => `<li><span class="cite">${c.marker}</span>
            <div><b>${esc(c.document || c.offering)}</b><div class="meta">${
              [c.paper_code, c.question_number && "Q" + c.question_number,
               c.page && "page " + c.page, c.section]
              .filter(Boolean).map(esc).join(" · ")}</div></div></li>`).join("")}</ol>` : "")
      + `<h4>Retrieval</h4><div class="meta mono">language ${esc(r.language)} ·
          lexical ${r.lexical_found} · semantic ${r.semantic_found} ·
          reranked ${r.reranked} · candidates ${r.candidates}</div>`
      + ((d.warnings || []).length
          ? `<h4>Warnings</h4><div class="meta mono">${d.warnings.map(esc).join("<br>")}</div>` : "");
  } catch (e) {
    out.innerHTML = `<div class="note-box bad">request failed: ${esc(e.message)}</div>`;
  } finally { $("#go").disabled = false; }
}

async function loadDocs() {
  const slug = $("#docOffering").value;
  const box = $("#docs");
  box.innerHTML = `<div class="note-box working">Loading…</div>`;
  try {
    const d = await (await fetch(`/offerings/${slug}/documents`)).json();
    if (!d.count) {
      box.innerHTML = `<div class="note-box warn">No documents are cleared for
        delivery in this subject. Material that grounds answers is not
        automatically material a student may open.</div>`;
      return;
    }
    box.innerHTML = `<div class="grid">${d.documents.map((doc) => `
      <article class="doc">
        <h3>${esc(doc.title)}</h3>
        <div class="meta">${esc(doc.type)}${doc.paper_code ? " · " + esc(doc.paper_code) : ""}${
          doc.pages ? " · " + doc.pages + " pages" : ""}</div>
        <button class="gold small" data-doc="${esc(doc.document_id)}">Open PDF</button>
      </article>`).join("")}</div>`;
    $$("[data-doc]", box).forEach((b) => b.onclick = async () => {
      b.disabled = true; b.textContent = "Signing…";
      try {
        const r = await fetch(`/documents/${b.dataset.doc}/url`);
        const j = await r.json();
        if (!r.ok) throw new Error((j.detail || {}).message || "refused");
        open(j.url, "_blank", "noopener");
        b.textContent = "Open PDF";
      } catch (e) {
        b.textContent = "Refused";
        b.title = e.message;
      } finally { b.disabled = false; }
    });
  } catch (e) {
    box.innerHTML = `<div class="note-box bad">${esc(e.message)}</div>`;
  }
}

/* ─────────────────────────────────────────────────────────────────────────
 * Routing — hash based, so the Space needs no server rewrite rules
 * ──────────────────────────────────────────────────────────────────────── */
function route() {
  const name = (location.hash.replace("#", "") || "tutor");
  const view = views[name] ? name : "tutor";
  $("#view").innerHTML = views[view]();
  $$("nav a").forEach((a) =>
    a.toggleAttribute("aria-current", a.getAttribute("href") === "#" + view));

  if (view === "tutor") {
    $("#go").onclick = ask;
    $("#q").addEventListener("keydown", (e) => { if (e.key === "Enter") ask(); });
    $("#offering").onchange = (e) => { state.current = e.target.value; };
    $$(".chip").forEach((c) => c.onclick = () => { $("#q").value = c.textContent.trim(); ask(); });
  }
  if (view === "sources") $("#loadDocs").onclick = loadDocs;
}

addEventListener("hashchange", route);

(async function start() {
  initHeroFilm();
  initHero($("#hero"));
  await loadHealth();
  try { await loadCurriculum(); }
  catch { $("#view").innerHTML = `<div class="note-box bad">Could not load the
    curriculum registry. The API may still be starting.</div>`; return; }
  route();
})();
