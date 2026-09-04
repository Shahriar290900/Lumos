/* api.js — the only place that talks to the server, and the escaping everything
   else relies on. Shared by every page so a change to a payload shape is one
   edit rather than four. */

export const $ = (s, r = document) => r.querySelector(s);
export const $$ = (s, r = document) => [...r.querySelectorAll(s)];

export const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

async function json(url, options) {
  // Never rejects. A caller that has to wrap every call in try/catch will
  // eventually forget one, and an unhandled rejection leaves a panel blank with
  // no explanation — which is the one thing this interface must not do.
  try {
    const res = await fetch(url, options);
    let body = null;
    try { body = await res.json(); } catch { /* an error page, not JSON */ }
    return { ok: res.ok, status: res.status, body, error: null };
  } catch (e) {
    return { ok: false, status: 0, body: null, error: e.message || "network error" };
  }
}

export const api = {
  health: () => json("/api/health"),
  curriculum: () => json("/api/curriculum"),
  documents: (slug) => json(`/api/offerings/${slug}/documents`),
  documentUrl: (id) => json(`/api/documents/${id}/url`),
  ask: (query, slug) => json("/api/tutor/ask", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, slug }),
  }),
};

/** Fill the subject picker. Unavailable subjects are listed, and labelled —
 *  hiding them would make the roadmap invisible (ADR-011). */
export function fillOfferings(select, offerings) {
  if (!select) return;
  select.innerHTML = offerings.map((o) =>
    `<option value="${esc(o.slug)}">${esc(o.subject_name_en)} — ${esc(o.level_name)}` +
    `${o.is_available ? "" : "  · not available"}</option>`).join("");
  const first = offerings.find((o) => o.is_available) || offerings[0];
  if (first) select.value = first.slug;
}
