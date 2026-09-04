/* app.js — runs on every page. Reports what the system can actually do. */
import { $, api, esc } from "./api.js";

const LABEL = {
  live: "generation live",
  mock: "mocked explanation",
  unavailable: "no generation model",
  error: "generation error",
};

(async function status() {
  const el = $("#status");
  if (!el) return;
  const { ok, body } = await api.health();
  if (!ok || !body) { el.textContent = "api unreachable"; return; }
  el.innerHTML = `db ${esc(body.database)} · <b>${esc(LABEL[body.generation] || body.status)}</b>`;
  // The full reason on hover — the pill has no room for it, but the note is
  // where the honesty actually lives.
  if (body.generation_note) el.title = body.generation_note;
})();
