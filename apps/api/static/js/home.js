/* home.js — the scene, and a registry summary read live. */
import { $, api, esc } from "./api.js";
import { initScene } from "./scene.js";

initScene($("#scene"));

(async function summary() {
  const { ok, body } = await api.curriculum();
  if (!ok || !body) return;
  const available = body.offerings.filter((o) => o.is_available);
  const indexed = body.offerings.reduce((n, o) => n + (o.indexed_chunk_count || 0), 0);
  const count = $("#availCount");
  if (count) count.textContent =
    `${available.length} of ${body.offerings.length} subjects available`;

  const box = $("#registrySummary");
  if (!box) return;
  const tile = (value, label, note) =>
    `<div class="card"><h3 style="font-size:30px;color:var(--gold-hi);margin:0">${value}</h3>
     <p style="color:var(--text);font-size:13px;margin:4px 0 2px">${label}</p>
     <p>${note}</p></div>`;
  box.innerHTML =
      tile(indexed.toLocaleString(), "indexed chunks", "embedded and searchable right now")
    + tile(available.length, "subjects available", "cleared by the registry to be asked about")
    + tile(body.offerings.length - available.length, "subjects held back",
           "registered, with their blocking reasons shown")
    + tile(body.offerings.length, "subjects registered",
           "including those with no corpus at all");
})();
