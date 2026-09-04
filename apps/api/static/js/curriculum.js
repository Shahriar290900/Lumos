/* curriculum.js — every subject, with its blocking reasons verbatim. */
import { $, api, esc } from "./api.js";

async function render() {
  const box = $("#offerings");
  box.innerHTML = `<div class="note-box working">Loading the registry…</div>`;
  const { ok, body, error, status } = await api.curriculum();
  if (!ok || !body) {
    box.innerHTML = `<div class="note-box bad">Could not load the registry
      ${esc(error ? "(" + error + ")" : "(HTTP " + status + ")")}.
      <button class="chip" id="retry" style="margin-left:8px">Retry</button></div>`;
    document.getElementById("retry").onclick = render;
    return;
  }
  box.innerHTML = body.offerings.map((o) => `
    <article class="offering ${o.is_available ? "on" : "off"}">
      <header>
        <h3>${esc(o.subject_name_en)}</h3>
        <span class="pill ${o.is_available ? "yes" : "no"}">
          ${o.is_available ? "available" : "not yet"}</span>
      </header>
      <div class="meta">${esc(o.level_name)} · ${esc(o.curriculum_name || "")}</div>
      <div class="bar"><i style="width:${Math.min(100, (o.indexed_chunk_count || 0) / 2)}%"></i></div>
      <div class="meta">${(o.indexed_chunk_count || 0).toLocaleString()} indexed chunks</div>
      ${(o.blocked_reasons || []).length
        ? `<ul class="reasons">${o.blocked_reasons.map((r) => `<li>${esc(r)}</li>`).join("")}</ul>`
        : `<div class="meta ok">no blocking conditions</div>`}
      ${o.display_note_en ? `<p class="note">${esc(o.display_note_en)}</p>` : ""}
    </article>`).join("");
}
render();
