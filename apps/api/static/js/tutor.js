/* tutor.js — ask, and render what came back honestly. */
import { $, $$, api, esc, fillOfferings } from "./api.js";

const EXAMPLES = [
  "How do I calculate gravitational potential energy?",
  "Explain the photoelectric effect.",
  "What affects the resistance of a wire?",
];

function withCitations(text, citations) {
  const known = new Set(citations.map((c) => c.marker));
  return esc(text).replace(/\[(\d{1,2})\]/g, (m, n) =>
    known.has(+n) ? `<span class="cite">${n}</span>` : m);
}

async function ask() {
  const slug = $("#offering").value;
  const query = $("#q").value.trim();
  if (!query) return;
  const out = $("#answer");
  out.innerHTML = `<div class="note-box working">Casting…</div>`;
  $("#go").disabled = true;

  const { ok, status, body } = await api.ask(query, slug);
  $("#go").disabled = false;

  if (status === 409) {
    const d = body.detail || {};
    out.innerHTML = `<div class="note-box warn">
      <b>Not available yet.</b> ${esc(d.message_en || "")}
      <ul class="reasons">${(d.blocked_reasons || []).map((r) =>
        `<li>${esc(r)}</li>`).join("")}</ul>
      <p class="meta">The registry refused this before any retrieval ran.
        That is the coverage gate working, not an error.</p></div>`;
    return;
  }
  if (!ok || !body) {
    out.innerHTML = `<div class="note-box bad">${esc(
      JSON.stringify((body || {}).detail || "request failed"))}</div>`;
    return;
  }

  let banner = "";
  if (body.limitation === "no_generation_model")
    banner = `<div class="note-box warn"><b>No generation model.</b> Retrieval ran
      and the citations are real, but nothing is configured to write the
      explanation yet.</div>`;
  else if (body.limitation)
    banner = `<div class="note-box warn"><b>Stated limitation:</b>
      ${esc(body.limitation)}</div>`;
  else
    banner = `<div class="note-box ok"><b>Grounded.</b> ${(body.citations || []).length}
      citation(s), each resolving to a passage retrieved for this question.</div>`;

  const r = body.retrieval || {};
  out.innerHTML = banner
    + `<div class="answer">${withCitations(body.answer || "", body.citations || [])}</div>`
    + ((body.citations || []).length ? `<h4>Sources</h4><ol class="sources">${
        body.citations.map((c) => `<li><span class="cite">${c.marker}</span>
          <div><b>${esc(c.document || c.offering)}</b><div class="meta">${
            [c.paper_code, c.question_number && "Q" + c.question_number,
             c.page && "page " + c.page, c.section]
            .filter(Boolean).map(esc).join(" · ")}</div></div></li>`).join("")}</ol>` : "")
    + `<h4>Retrieval</h4><div class="meta mono">language ${esc(r.language)} ·
        lexical ${r.lexical_found} · semantic ${r.semantic_found} ·
        reranked ${r.reranked} · candidates ${r.candidates}</div>`
    + ((body.warnings || []).length
        ? `<h4>Warnings</h4><div class="meta mono">${
            body.warnings.map(esc).join("<br>")}</div>` : "");
}

(async function init() {
  const { ok, body } = await api.curriculum();
  if (ok && body) fillOfferings($("#offering"), body.offerings);
  $("#examples").innerHTML = EXAMPLES.map((q) =>
    `<button class="chip">${esc(q)}</button>`).join("");
  $$(".chip").forEach((c) => c.onclick = () => { $("#q").value = c.textContent.trim(); ask(); });
  $("#go").onclick = ask;
  $("#q").addEventListener("keydown", (e) => { if (e.key === "Enter") ask(); });
})();
