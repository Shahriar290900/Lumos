# Lumos Goal Register

Status: `[ ]` not started · `[~]` in progress · `[x]` complete with evidence · `[!]` blocked

A goal is complete only when its acceptance criteria are met **and** the evidence is recorded. Building successfully is not evidence.

## Phase 0 — Foundation
- [x] **LUMOS-000 Reconnaissance** — evidence: `RECONNAISSANCE_REPORT.md`, `evidence/*.json`, `scripts/audit_corpus.py`
- [ ] LUMOS-001 Repository bootstrap: monorepo layout, tooling, lint, typecheck
- [ ] LUMOS-002 Design system + brand tokens (dark magical academy: deep navy/black, warm gold)
- [ ] LUMOS-003 Agent operating system (`.claude/` skills, agents, hooks, state files)
- [~] LUMOS-004 CI baseline + test harness — *`.github/workflows/ci.yml` and 47 tests exist and run with an empty `.env`; not yet executed on GitHub*

## Phase 0.5 — Curriculum and data foundation
- [x] **LUMOS-004A Curriculum registry + coverage gates** — evidence: `packages/db/migrations/0001_curriculum_registry.up.sql`, 47 passing tests, `scripts/check_registry_consistency.py`, generated `CURRICULUM_INVENTORY.md`
- [ ] **LUMOS-004B Canonical chunk schema + legacy normalisation adapter** ← **NEXT GOAL**
- [ ] LUMOS-004C Corpus cleaning: dedup, Unicode NFC, Bangla repair, re-chunking
- [ ] LUMOS-004D Licence and provenance registry
- [!] LUMOS-004E Retrieval evaluation set per available corpus — *needs subject-teacher review*

## Phase 1 — Product MVP
- [!] LUMOS-005 Authentication + roles — *blocked: BLOCK-006, BLOCK-007*
- [~] LUMOS-006 Neon schema + migrations — *migration runner and first migration exist and are tested locally; deployment blocked by BLOCK-002*
- [ ] LUMOS-007 Curriculum ingestion MVP — *scope settled; design in `docs/INGESTION_DESIGN.md`*
- [ ] LUMOS-008 Hybrid retrieval with RRF on pgvector + Postgres FTS
- [ ] LUMOS-009 BGE reranking + source-priority policy
- [ ] LUMOS-010 Tutor API + SSE streaming
- [ ] LUMOS-011 Citation + confidence validation
- [ ] LUMOS-012 Student dashboard
- [ ] LUMOS-013 Practice engine

## Phase 2 — Multimodal
- [ ] LUMOS-014 Voice STT/TTS behind provider interfaces
- [ ] LUMOS-015 Image and document understanding
- [ ] LUMOS-016 Multi-part question dependency tracking — *unblocked: real past papers now held; context comes from chunk granularity, not parsed edges (ADR-016)*

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

## LUMOS-004A — Curriculum Registry + Coverage Gates — COMPLETE (2026-09-04)

All acceptance criteria met. Evidence:

| Criterion | Evidence |
|---|---|
| Migration from empty, reversible | `test_migration_from_empty_database_and_back` — up → 7 tables + 1 view, down → 0, up again |
| Seed reflects the verified inventory | `test_seeded_counts_match_the_corpus_auditor` — ICT 120, English 43, Physics 17, total 180 |
| Empty subjects representable as known-but-unavailable | `test_empty_subjects_are_known_but_unavailable` |
| Availability requires evidence, not intention | `test_each_clause_blocks_availability` (10 cases) + 4 schema-constraint tests |
| `GET /curriculum` is the only source of availability | `test_curriculum_listing_returns_availability_and_notes` |
| Unavailable subject refused before retrieval | `test_tutor_refuses_an_unavailable_subject_before_retrieval` — 409 with reasons, never an answer |
| The বাংলা regression case | `test_subject_with_zero_chunks_is_never_available`, `test_seeded_bangla_offering_is_unavailable` |
| Auditor and registry agree, enforced in CI | `scripts/check_registry_consistency.py`, proved to fire on injected drift |
| `CURRICULUM_INVENTORY.md` generated, not hand-written | `scripts/generate_inventory.py --check` |
| Runs with an empty `.env`, no model provider | full suite green with `AI_PROVIDER=mock` |

Beyond scope, because the material arrived mid-goal: 19 private Edexcel PDFs catalogued and checksummed, ingestion route determined per document, and `.githooks/pre-commit` protecting them from ever being committed.

---

## LUMOS-004B — Canonical chunk schema + legacy normalisation adapter

**Depends on:** LUMOS-004A (complete)
**Blocks:** LUMOS-004C, LUMOS-007, LUMOS-008

**Description.** Create the `chunks` table implementing `docs/CHUNK_SCHEMA.md`, and a legacy adapter mapping the three observed JSONL shapes onto it: deduplicate by content hash (137 records exist identically in both repositories), reconcile `chapter_title` / `chapter_name` (80 / 100 split), inject `curriculum`, `language`, `document_type` and `source_priority`, recompute `token_count` with the real tokeniser, resolve free-text prerequisites to IDs where possible, and emit a per-corpus ingestion report.

**Acceptance criteria**
- [ ] `chunks` table with the canonical fields, `provenance_hash` unique, and a foreign key to `source_documents`
- [ ] Adapter maps all 180 legacy records with zero data loss; original text retained alongside canonical text
- [ ] Deduplication proven on the 137 cross-repository duplicates
- [ ] `chapter_title` and `chapter_name` both resolve; no chunk carries a null chapter label
- [ ] `token_count` recomputed; legacy values retained for comparison but never trusted
- [ ] Per-corpus ingestion report written to `evidence/`, reviewed before any status change
- [ ] `indexed_chunk_count` updated from the chunks table, never set by hand
- [ ] Consistency gate extended to compare chunk counts against the adapter's output
- [ ] Unit tests per transformation; no network, no model provider
