/* sources.js — what a student may open, and what is refused. */
import { $, $$, api, esc, fillOfferings } from "./api.js";

async function load() {
  const slug = $("#docOffering").value;
  const box = $("#docs");
  box.innerHTML = `<div class="note-box working">Loading…</div>`;

  const { ok, body } = await api.documents(slug);
  if (!ok || !body) {
    box.innerHTML = `<div class="note-box bad">Could not load documents.</div>`;
    return;
  }
  if (!body.count) {
    box.innerHTML = `<div class="note-box warn">No documents are cleared for
      delivery in this subject. Material that grounds an answer is not
      automatically material a student may open.</div>`;
    return;
  }
  box.innerHTML = `<div class="grid">${body.documents.map((d) => `
    <article class="doc">
      <h3>${esc(d.title)}</h3>
      <div class="meta">${esc(d.type)}${d.paper_code ? " · " + esc(d.paper_code) : ""}${
        d.pages ? " · " + d.pages + " pages" : ""}</div>
      <button class="gold small" data-doc="${esc(d.document_id)}">Open PDF</button>
    </article>`).join("")}</div>
    <p class="meta" style="margin-top:16px">Links are signed and expire after 15
      minutes, so access can be withdrawn.</p>`;

  $$("[data-doc]", box).forEach((b) => b.onclick = async () => {
    b.disabled = true;
    const original = b.textContent;
    b.textContent = "Signing…";
    const { ok: got, body: res } = await api.documentUrl(b.dataset.doc);
    b.disabled = false;
    if (got && res.url) { open(res.url, "_blank", "noopener"); b.textContent = original; }
    else { b.textContent = "Refused"; b.title = (res?.detail || {}).message || "refused"; }
  });
}

(async function init() {
  const { ok, body } = await api.curriculum();
  if (ok && body) fillOfferings($("#docOffering"), body.offerings);
  $("#loadDocs").onclick = load;
  load();
})();
