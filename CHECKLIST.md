# Lumos Checklist

Last verified **2026-09-04** at commit `70b8e39`.

Nothing is ticked here on intention. A box is ticked when a command succeeded and
the evidence is recorded in `GOALS.md`. Where this file and the code disagree,
the code wins — say so rather than editing either quietly.

---

## What works today — verified end to end

### Infrastructure
- [x] Repository restored from bundle, **5 commits, pushed** to `github.com/Shahriar290900/Lumos`
- [x] **CI green** — 3 jobs, every step, first run ever on `b722d17` and again on `70b8e39`
- [x] Python environment — `.venv` on 3.12.2 locally, **3.11.16 in CI** (accepted divergence, ADR-023)
- [x] **Neon** — `ap-southeast-1`, PostgreSQL 18.6, pgvector 0.8.6, unpooled endpoint
- [x] `git config core.hooksPath .githooks` set on the working clone
- [x] `.env` present, mode 600, gitignored, invisible to `git status`

### Database and schema
- [x] Migration up from empty → 9 tables, 2 views, 9 enums
- [x] Migration `down`, `down --to 0000`, and up again — only `schema_migrations` survives
- [x] Seed from evidence — 2 curricula, 9 offerings, 42 source documents, 3 corpus snapshots
- [x] Availability is one SQL view with machine-readable `blocked_reasons` (ADR-013)
- [x] `require_available()` raises rather than returning a flag

### Corpus
- [x] Corpus audit reproduces **180 records** — ICT 120, English 43, Physics 17
- [x] **263 canonical chunks** — 180 legacy records + 83 exam questions
- [x] Past papers parsed — **83 questions, 440 marks** across WPH11–16; AS scope 41 / 210
- [x] Normalisation idempotent — second run reports `created=0 updated=0 unchanged=180`
- [x] Chunk identity derived, not assigned (ADR-018)
- [x] Provenance per chunk, `text_raw` retained on every transformed chunk (ADR-021)
- [x] Consistency gate passes, and is proved to fire on injected drift
- [x] `CURRICULUM_INVENTORY.md` generated and **reproducible** — defect fixed in 004B.1

### Safety
- [x] 19 private Edexcel PDFs on disk, **0 tracked in git**
- [x] Pre-commit hook proved to block a forced `git add -f` of a PDF
- [x] CI guard: no licensed material, no file over 10 MB, no credential patterns
- [x] No source text in any committed file — evidence carries counts and checksums only
- [x] Full suite passes with `AI_PROVIDER=mock` and no model credential

### Test surface
- [x] **124 tests** — identical count locally and in CI
- [x] Runtime: 99 s against Neon, 4.0 s in CI

---

## What does not work yet — stated plainly

- [ ] **The Model Gateway does not exist.** `services/models/` is not created. `AI_PROVIDER=mock` is set in tests and CI and **nothing reads it**. No generation of any kind has ever run.
- [ ] **Nothing is indexed.** No embeddings, no vector index, no FTS index, so there is no retrieval and **0 of 9 offerings are available**. That is correct behaviour, not a defect.
- [ ] **No web application.** `apps/web/` does not exist. `apps/api/` serves the registry and a `/tutor/ask` route that passes the coverage gate and then returns 501 — deliberately, to prove the gate runs before retrieval.
- [ ] **No authentication.** No user model, no sessions.
- [ ] Mark schemes, examiner reports and the 225-page textbook are catalogued and routed but **not ingested**.
- [ ] Bangla corruption in 73 ICT records is **measured, not repaired**. 66 records also carry broken word splits.
- [ ] English chunks remain whole textbook units of ~2,000 tokens.
- [ ] **Tesseract is not installed** — required by LUMOS-004C.3.
- [ ] No Cloudflare zone, R2 bucket, Render service, or model endpoint.
- [ ] No production or staging database branch. Development only.

---

## Goals remaining

5 of 33 goals complete. `[~]` in progress · `[!]` blocked on a human decision.

### Phase 0.5 — curriculum and data foundation
- [ ] **LUMOS-004C.1** Legacy text repair — Bangla, English re-chunking, glyph and truncation repair ← **NEXT**
- [ ] **LUMOS-004C.2** Mark-scheme and examiner-report adapters, plus cross-document linking
- [ ] **LUMOS-004C.3** Textbook OCR, 225 pages
- [ ] LUMOS-004D Licence and provenance registry — *needs BLOCK-008*
- [!] LUMOS-004E Retrieval evaluation set — *needs subject-teacher review*
- [ ] LUMOS-004F Model Gateway + mock provider + `gemma4:e4b` — *not blocked; the mock needs no credential*

### Phase 1 — product MVP
- [!] LUMOS-005 Authentication + roles — *BLOCK-006, BLOCK-007*
- [~] LUMOS-006 Neon schema + migrations — *works in development; no production branch*
- [~] LUMOS-007 Curriculum ingestion MVP — *past papers done; three source types remain*
- [ ] LUMOS-008 Hybrid retrieval, RRF on pgvector + Postgres FTS
- [ ] LUMOS-009 BGE reranking + source-priority policy
- [ ] LUMOS-010 Tutor API + SSE streaming
- [ ] LUMOS-011 Citation + confidence validation
- [ ] LUMOS-012 Student dashboard
- [ ] LUMOS-013 Practice engine

### Phase 0 — foundation, deferred
- [ ] LUMOS-001 Monorepo layout, lint, typecheck
- [ ] LUMOS-002 Design system + brand tokens
- [ ] LUMOS-003 Agent operating system (`.claude/`)

### Phase 2 — multimodal
- [ ] LUMOS-014 Voice STT/TTS behind provider interfaces
- [ ] LUMOS-015 Image and document understanding
- [ ] LUMOS-016 Multi-part question dependency tracking — *unblocked (ADR-016)*

### Phase 3 — experience
- [ ] LUMOS-017 3D magical homepage
- [ ] LUMOS-018 Cursor-reactive light, parallax, depth
- [ ] LUMOS-019 Accessibility, reduced motion, WebGL-absent fallbacks

### Phase 4 — trust, scale, competition
- [ ] LUMOS-020 Evaluation harness + golden set + regression suite
- [!] LUMOS-021 Security and privacy audit — *BLOCK-007*
- [ ] LUMOS-022 Performance and load testing (low-end Android, throttled network)
- [!] LUMOS-023 Production deployment — *BLOCK-003, BLOCK-004*
- [ ] LUMOS-024 Technical documentation for external review
- [ ] LUMOS-025 Demo video and presentation readiness

---

## Human decisions outstanding

Nothing here can be resolved by the engineering agent alone.

- [x] Whitepaper corpus position (BLOCK-001) — **decided**
- [x] Neon project (BLOCK-002) — **provisioned**; production branch still open
- [x] Model choice and hosting (BLOCK-005) — **`gemma4:e4b`, remote** (ADR-022)
- [ ] **Endpoint, budget ceiling and shutdown procedure** (BLOCK-005) — *the most likely way this project overspends*
- [ ] Verify the exact Ollama tag with `ollama show gemma4:e4b` (BLOCK-005)
- [ ] Locate the claimed 2.58 GB Edexcel corpus, or confirm it does not exist (BLOCK-001A)
- [ ] Cloudflare zone, R2 bucket, domain (BLOCK-003)
- [ ] Render services (BLOCK-004)
- [ ] Auth provider (BLOCK-006)
- [ ] Under-18 data policy (BLOCK-007) — *most users are minors*
- [ ] Source licensing: private demo, competition, or commercial (BLOCK-008)
- [ ] Locate the source PDFs behind the ICT corpus, if they exist (BLOCK-009)

---

## Verification gates

- [x] Python environment works
- [x] Neon connectivity verified — full gate green end to end
- [x] Migration up, down and up again from empty
- [x] Corpus audit reproduces committed evidence
- [x] Normalisation idempotent
- [x] Generated inventory current and reproducible
- [x] Full test suite green, locally and in CI
- [x] Model Gateway health check against the **mock** provider — *pending LUMOS-004F*
- [ ] Model Gateway health check against a **real** provider (BLOCK-005)
- [ ] Tesseract installed and OCR quality measured
- [ ] Cloudflare auth verified
- [ ] R2 upload and read verified
- [ ] Render health check verified
- [ ] `pnpm` toolchain works
- [ ] Playwright installed; baseline test passes

> The mock-provider gate is ticked as *pending* deliberately: the suite runs with
> `AI_PROVIDER=mock` today, but no gateway reads that variable, so there is
> nothing yet to health-check. It becomes a real tick at LUMOS-004F.

---

## Competition readiness (BCOLBD final round, /100)

| Component | Points | State |
|---|---:|---|
| Technical documentation | 20 | Governing documents exist; not yet written for an external reader |
| Code repository, quality and **reproducibility** | 20 | Repository public and reproducible from a clean clone; inventory defect fixed |
| Demo video, max 10 min | 30 | Not started |
| Live presentation, 1 min intro per member | 30 | Not started |

- [x] Repository public, reproducible from a clean clone, evidence machine-generated
- [ ] Deployment-ready inference model demonstrated — *needs LUMOS-004F and BLOCK-005*
- [ ] Technical documentation an external evaluator can follow
- [ ] Demo video, English or English-subtitled
- [ ] Live presentation prepared
- [ ] **Whitepaper claims reconciled with repository reality** (BLOCK-001A) — *an evaluator can falsify the 2.58 GB claim in five minutes*

**Demo scope is Edexcel IAL AS Physics only** — WPH11/12/13 and *Student Book 1*.
Every other subject is registered as known-but-unavailable so the interface can
explain itself rather than omit.
