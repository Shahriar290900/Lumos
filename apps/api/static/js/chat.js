/*
 * chat.js — the study coach: pick a paper, open a question, get marked.
 *
 * Three panes, one flow:
 *
 *   rail    curriculum -> level -> subject -> papers   (from the registry)
 *   paper   the PDF itself                             (presigned, expiring)
 *   tutor   questions in that paper, then ask or mark  (RAG + citations)
 *
 * Everything here is read from the API. The previous version of this page had
 * a hardcoded "Question 3: Momentum" with invented mark-scheme lines, which is
 * exactly the failure this project exists to prevent — a demo that looks like
 * it works because the data is fake. Nothing in this file invents content: if
 * a paper has no questions parsed, it says so.
 */

import { $, $$, api, esc } from "./api.js";

const state = {
  offerings: [],
  offering: null,     // the selected offering object
  documents: [],
  paper: null,        // the open document
  questions: [],
  question: null,     // selected question_number
  mode: "ask",
};

/* ── rail ──────────────────────────────────────────────────────────────── */

function uniq(values) {
  return [...new Set(values)];
}

function renderSelectors() {
  const curricula = uniq(state.offerings.map((o) => o.curriculum_name));
  $("#curriculumSel").innerHTML = curricula
    .map((c) => `<option>${esc(c)}</option>`).join("");
  renderLevels();
}

function renderLevels() {
  const curriculum = $("#curriculumSel").value;
  const levels = uniq(state.offerings
    .filter((o) => o.curriculum_name === curriculum)
    .map((o) => o.level_name));
  $("#levelSel").innerHTML = levels.map((l) => `<option>${esc(l)}</option>`).join("");
  renderSubjects();
}

function renderSubjects() {
  const curriculum = $("#curriculumSel").value;
  const level = $("#levelSel").value;
  const subjects = state.offerings.filter(
    (o) => o.curriculum_name === curriculum && o.level_name === level);
  $("#subjectSel").innerHTML = subjects.map((o) =>
    `<option value="${esc(o.slug)}">${esc(o.subject_name_en)}` +
    `${o.is_available ? "" : " · locked"}</option>`).join("");
  selectOffering();
}

async function selectOffering() {
  const slug = $("#subjectSel").value;
  state.offering = state.offerings.find((o) => o.slug === slug) || null;
  state.paper = null;
  state.questions = [];
  state.question = null;
  renderQuestions();
  renderScope();

  const box = $("#offeringState");
  if (!state.offering) { box.innerHTML = ""; return; }

  // The registry's verdict, verbatim. A locked subject shows exactly why,
  // rather than being hidden from the list (ADR-011).
  if (state.offering.is_available) {
    box.innerHTML = `<div class="state-ok">${state.offering.indexed_chunk_count}
      indexed chunks &middot; ready</div>`;
  } else {
    box.innerHTML = `<div class="state-locked"><b>Not available yet</b>
      <ul>${(state.offering.blocked_reasons || []).map((r) =>
        `<li>${esc(r)}</li>`).join("")}</ul></div>`;
  }
  await loadPapers(slug);
}

const TYPE_LABEL = { past_paper: "QP", mark_scheme: "MS", examiner_report: "ER" };

async function loadPapers(slug) {
  const list = $("#paperList");
  list.innerHTML = `<div class="meta">loading&hellip;</div>`;
  const { ok, body } = await api.documents(slug);
  if (!ok || !body) { list.innerHTML = `<div class="meta">could not load</div>`; return; }

  state.documents = body.documents;
  if (!body.count) {
    list.innerHTML = `<div class="meta">No papers are cleared for delivery in
      this subject. Material that grounds an answer is not automatically
      material a student may open.</div>`;
    return;
  }

  // Grouped by paper code, so the three documents for one exam sit together
  // rather than scattered through a flat list of eighteen.
  const groups = {};
  for (const d of state.documents) (groups[d.paper_code || "Other"] ??= []).push(d);

  list.innerHTML = Object.entries(groups).map(([code, docs]) => `
    <div class="paper-group">
      <div class="paper-code">${esc(code)}</div>
      <div class="paper-btns">
        ${docs.map((d) => `<button class="doc-btn" data-doc="${esc(d.document_id)}"
            data-type="${esc(d.type)}" title="${esc(d.title)}">
            ${esc(TYPE_LABEL[d.type] || d.type)}</button>`).join("")}
      </div>
    </div>`).join("");

  $$("[data-doc]", list).forEach((b) => b.onclick = () => openPaper(b.dataset.doc));
}

/* ── paper ─────────────────────────────────────────────────────────────── */

async function openPaper(documentId) {
  const doc = state.documents.find((d) => d.document_id === documentId);
  state.paper = doc || null;
  state.question = null;

  $$(".doc-btn").forEach((b) => b.classList.toggle("on", b.dataset.doc === documentId));
  $("#paperTitle").textContent = doc ? doc.title : "No paper open";
  $("#paperBody").innerHTML = `<div class="empty"><p class="meta">Signing a link&hellip;</p></div>`;

  const { ok, body } = await api.documentUrl(documentId);
  if (!ok || !body.url) {
    $("#paperBody").innerHTML = `<div class="empty">
      <p><b>This document is not served.</b></p>
      <p class="meta">${esc((body?.detail || {}).message || "refused")}</p></div>`;
    $("#openRaw").style.display = "none";
    return;
  }

  // An <object> rather than <iframe>: it degrades to its own children when the
  // browser has no PDF viewer, which is the case on most Android devices —
  // and this product targets low-end Android.
  $("#paperBody").innerHTML = `
    <object data="${esc(body.url)}#toolbar=1&navpanes=0" type="application/pdf"
            class="pdf-frame">
      <div class="empty">
        <p>Your browser will not display PDFs inline.</p>
        <a class="btn gold" href="${esc(body.url)}" target="_blank" rel="noopener">
          Open the paper</a>
      </div>
    </object>`;
  const raw = $("#openRaw");
  raw.href = body.url;
  raw.style.display = "inline-block";

  await loadQuestions(documentId);
}

/* ── questions ─────────────────────────────────────────────────────────── */

async function loadQuestions(documentId) {
  const { ok, body } = await api.documentQuestions(documentId);
  state.questions = ok && body ? body.questions : [];
  renderQuestions();
}

function renderQuestions() {
  const box = $("#questionChips");
  if (!state.questions.length) {
    box.innerHTML = `<span class="meta">${state.paper
      ? "no questions parsed from this document"
      : "open a paper"}</span>`;
    return;
  }
  box.innerHTML = state.questions.map((q) =>
    `<button class="qchip" data-q="${esc(q.question_number)}"
       title="${q.marks ? q.marks + " marks" : ""}">Q${esc(q.question_number)}</button>`
  ).join("");
  $$(".qchip", box).forEach((b) => b.onclick = () => {
    state.question = state.question === b.dataset.q ? null : b.dataset.q;
    $$(".qchip", box).forEach((x) =>
      x.classList.toggle("on", x.dataset.q === state.question));
    renderScope();
  });
}

function renderScope() {
  const tag = $("#scopeTag");
  if (state.question && state.paper) {
    tag.textContent = `${state.paper.paper_code} Q${state.question}`;
    tag.classList.add("on");
  } else {
    tag.textContent = state.mode === "check"
      ? "pick a question to be marked" : "";
    tag.classList.toggle("on", false);
  }
  $("#q").placeholder = state.mode === "check"
    ? "Write your answer and I will mark it…"
    : "Ask about this paper…";
}

/* ── thread ────────────────────────────────────────────────────────────── */

function bubble(html, who = "tutor-msg") {
  const el = document.createElement("div");
  el.className = `msg ${who}`;
  el.innerHTML = `<div class="bubble">${html}</div>`;
  $("#thread").appendChild(el);
  $("#thread").scrollTop = $("#thread").scrollHeight;
  return el;
}

function withCitations(text, citations) {
  const known = new Set((citations || []).map((c) => c.marker));
  return esc(text).replace(/\[(\d{1,2})\]/g, (m, n) =>
    known.has(+n) ? `<span class="cite">${n}</span>` : m);
}

function sourceList(citations) {
  if (!citations?.length) return "";
  return `<div class="sources">${citations.map((c) => `
    <div class="src"><span class="cite">${c.marker}</span>
      <span>${esc(c.document || c.offering)}<span class="meta">${
        [c.paper_code, c.question_number && "Q" + c.question_number,
         c.page && "page " + c.page].filter(Boolean).map(esc).join(" · ")
      }</span></span></div>`).join("")}</div>`;
}

const VERDICT_CLASS = { correct: "ok", partially_correct: "warn", incorrect: "bad" };

async function send() {
  const text = $("#q").value.trim();
  if (!text) return;
  if (!state.offering) { bubble("Choose a subject first."); return; }

  bubble(esc(text), "me");
  $("#q").value = "";
  $("#q").style.height = "auto";
  $("#go").disabled = true;
  const pending = bubble(`<span class="meta">Thinking…</span>`);

  try {
    if (state.mode === "check") {
      if (!state.question || !state.paper) {
        pending.querySelector(".bubble").innerHTML =
          "Pick a question first — I mark against that question's mark scheme, " +
          "so I need to know which one.";
        return;
      }
      const { ok, status, body } = await api.check(
        text, state.offering.slug, state.paper.paper_code, state.question);
      pending.querySelector(".bubble").innerHTML =
        renderCheck(ok, status, body);
    } else {
      const { ok, status, body } = await api.ask(
        state.question && state.paper
          ? `Regarding ${state.paper.paper_code} question ${state.question}: ${text}`
          : text,
        state.offering.slug);
      pending.querySelector(".bubble").innerHTML = renderAsk(ok, status, body);
    }
  } catch (e) {
    pending.querySelector(".bubble").innerHTML =
      `<span class="bad">request failed: ${esc(e.message)}</span>`;
  } finally {
    $("#go").disabled = false;
    $("#thread").scrollTop = $("#thread").scrollHeight;
  }
}

function renderLocked(body) {
  const d = body.detail || {};
  return `<b>Not available yet.</b> ${esc(d.message_en || "")}
    <ul class="reasons">${(d.blocked_reasons || []).map((r) =>
      `<li>${esc(r)}</li>`).join("")}</ul>
    <span class="meta">The registry refused this before any retrieval ran.</span>`;
}

function renderAsk(ok, status, body) {
  if (status === 409) return renderLocked(body);
  if (!ok || !body) return `<span class="bad">that did not work</span>`;
  const notice = body.is_mock
    ? `<div class="flag warn">Mocked explanation — retrieval and sources are real.</div>`
    : body.limitation
      ? `<div class="flag warn">${esc(body.limitation.replace(/_/g, " "))}</div>` : "";
  return notice + withCitations(body.answer || "", body.citations)
       + sourceList(body.citations);
}

function renderCheck(ok, status, body) {
  if (status === 409) return renderLocked(body);
  if (!ok || !body) return `<span class="bad">that did not work</span>`;
  if (body.limitation && !body.feedback) {
    return `<div class="flag warn">${esc(body.limitation.replace(/_/g, " "))}</div>`;
  }
  const cls = VERDICT_CLASS[body.verdict] || "warn";
  const head = `<div class="verdict ${cls}">${esc(
    body.verdict.replace(/_/g, " "))}${body.marks_available
      ? ` · ${body.marks_available} mark${body.marks_available > 1 ? "s" : ""}` : ""}</div>`;
  // Grounding is stated, not implied. When the model marked well but did not
  // cite inline, the sources shown are what it was given — the API says so.
  const flag = body.grounded ? ""
    : `<div class="flag warn">not cited inline; the sources below are what it
        was marked against</div>`;
  return head + flag + withCitations(body.feedback || "", body.citations)
       + sourceList(body.citations);
}

/* ── wiring ────────────────────────────────────────────────────────────── */

(async function init() {
  const { ok, body } = await api.curriculum();
  if (!ok || !body) {
    $("#offeringState").innerHTML = `<div class="state-locked">registry unreachable</div>`;
    return;
  }
  state.offerings = body.offerings;
  renderSelectors();

  $("#curriculumSel").onchange = renderLevels;
  $("#levelSel").onchange = renderSubjects;
  $("#subjectSel").onchange = selectOffering;

  $$(".mode").forEach((b) => b.onclick = () => {
    state.mode = b.dataset.mode;
    $$(".mode").forEach((x) => x.classList.toggle("on", x === b));
    renderScope();
  });

  $("#go").onclick = send;
  const box = $("#q");
  box.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); }
  });
  box.addEventListener("input", () => {
    box.style.height = "auto";
    box.style.height = Math.min(box.scrollHeight, 160) + "px";
  });

  $("#railToggle").onclick = () => $("#rail").classList.toggle("collapsed");
})();
