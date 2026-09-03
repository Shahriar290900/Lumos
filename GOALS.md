# Lumos Goal Register

Status: `[ ]` not started · `[~]` in progress · `[x]` complete with evidence · `[!]` blocked

A goal is complete only when its acceptance criteria are met **and** the evidence is recorded. Building successfully is not evidence.

## Phase 0 — Foundation
- [x] **LUMOS-000 Reconnaissance** — evidence: `RECONNAISSANCE_REPORT.md`, `evidence/*.json`, `scripts/audit_corpus.py`
- [ ] LUMOS-001 Repository bootstrap: monorepo layout, tooling, lint, typecheck
- [ ] LUMOS-002 Design system + brand tokens (dark magical academy: deep navy/black, warm gold)
- [ ] LUMOS-003 Agent operating system (`.claude/` skills, agents, hooks, state files)
- [ ] LUMOS-004 CI baseline + test harness (must run with an empty `.env` via the mock provider)

## Phase 0.5 — Curriculum and data foundation
- [ ] **LUMOS-004A Curriculum registry + coverage gates** ← **NEXT GOAL**
- [ ] LUMOS-004B Canonical chunk schema + legacy normalisation adapter
- [ ] LUMOS-004C Corpus cleaning: dedup, Unicode NFC, Bangla repair, re-chunking
- [ ] LUMOS-004D Licence and provenance registry
- [!] LUMOS-004E Retrieval evaluation set per available corpus — *needs subject-teacher review*

## Phase 1 — Product MVP
- [!] LUMOS-005 Authentication + roles — *blocked: BLOCK-006, BLOCK-007*
- [!] LUMOS-006 Neon schema + migrations — *blocked: BLOCK-002 for deployment; local Postgres unblocks development*
- [!] LUMOS-007 Curriculum ingestion MVP — *scope blocked: BLOCK-001*
- [ ] LUMOS-008 Hybrid retrieval with RRF on pgvector + Postgres FTS
- [ ] LUMOS-009 BGE reranking + source-priority policy
- [ ] LUMOS-010 Tutor API + SSE streaming
- [ ] LUMOS-011 Citation + confidence validation
- [ ] LUMOS-012 Student dashboard
- [ ] LUMOS-013 Practice engine

## Phase 2 — Multimodal
- [ ] LUMOS-014 Voice STT/TTS behind provider interfaces
- [ ] LUMOS-015 Image and document understanding
- [!] LUMOS-016 Multi-part question dependency tracking — *blocked: no past-paper data exists (BLOCK-001)*

## Phase 3 — Experience
- [ ] LUMOS-017 3D magical homepage
- [ ] LUMOS-018 Cursor-reactive light, parallax, depth response
- [ ] LUMOS-019 Accessibility, reduced-motion and WebGL-absent fallbacks

## Phase 4 — Trust, scale, competition
- [ ] LUMOS-020 Evaluation harness + golden set + regression suite
- [!] LUMOS-021 Security and privacy audit — *blocked: BLOCK-007*
- [ ] LUMOS-022 Performance and load testing (low-end Android, throttled network)
- [!] LUMOS-023 Production deployment — *blocked: BLOCK-002/003/004*
- [ ] LUMOS-024 Technical documentation for external review
- [ ] LUMOS-025 Demo video and presentation readiness

---

## LUMOS-004A — Curriculum Registry + Coverage Gates

**Depends on:** a Postgres instance (local container is sufficient)
**Blocks:** LUMOS-007, LUMOS-008, LUMOS-012, and the availability contract of every UI surface

**Description.** Make the system the authority on what curriculum content exists. Registry shape: `curriculum → syllabus_version → subject → level → unit → source_document → chunk`, with per-subject indexing status, evaluation status, source-priority policy, supported languages, licence/provenance reference, and a `published` flag defaulting to false. Seed from the verified 180-record inventory. Serve availability over an API the front end is the only consumer of. Reject requests for unavailable subjects server-side, before retrieval.

**Acceptance criteria**
- [ ] Migration creates the registry tables from an empty database and is reversible
- [ ] Seed reflects the verified inventory exactly: English 43, ICT 120, Physics 17; `published = false` for all three
- [ ] `Bangla`, `Chemistry`, `Biology`, `Mathematics` are representable as *known but unavailable*, so the UI can explain rather than omit
- [ ] The availability rule requires all of: curriculum, syllabus version, level, source provenance, indexed chunk count > 0, passing evaluation record
- [ ] `GET /curriculum` returns availability; the front end has no other source of it
- [ ] A request naming an unavailable subject is rejected before retrieval with a clear message
- [ ] Unit tests cover the availability rule, including the regression case: subject present in the UI, zero chunks, must be unavailable
- [ ] Integration test: empty DB → migrate → seed → API returns the expected availability set
- [ ] CI asserts that `scripts/audit_corpus.py` output and the registry seed agree
- [ ] `CURRICULUM_INVENTORY.md` is regenerated from the registry rather than hand-maintained
- [ ] Runs with an empty `.env` against a local Postgres; no model provider called; no secret introduced

**Security considerations.** Licence and provenance fields may carry contractual terms — treat as internal. The availability check must be server-side; a client-side gate is not a gate.

**Performance considerations.** Trivial data volume. Index `(curriculum, subject, level)` — it becomes the hot metadata filter in the retrieval path.

**Evidence required.** Migration up/down transcript, test output, API response sample, and the CI consistency check passing.
