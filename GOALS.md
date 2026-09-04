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
- [x] **LUMOS-004B Canonical chunk schema + legacy normalisation adapter** — evidence: migration 0002, 263 canonical chunks, 120 passing tests, `evidence/legacy_normalisation.json`
- [ ] **LUMOS-004C Corpus cleaning: Bangla repair, boundary repair, re-chunking** ← **NEXT GOAL**
- [ ] LUMOS-004D Licence and provenance registry
- [!] LUMOS-004E Retrieval evaluation set per available corpus — *needs subject-teacher review*

## Phase 1 — Product MVP
- [!] LUMOS-005 Authentication + roles — *blocked: BLOCK-006, BLOCK-007*
- [~] LUMOS-006 Neon schema + migrations — *migration runner and first migration exist and are tested locally; deployment blocked by BLOCK-002*
- [~] LUMOS-007 Curriculum ingestion MVP — *past-paper adapter done; mark schemes, examiner reports and the OCR textbook path remain*
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

## LUMOS-004B — Canonical chunk schema + legacy normalisation adapter — COMPLETE (2026-09-04)

All acceptance criteria met, verified by an end-to-end run from an empty database.

| Criterion | Evidence |
|---|---|
| A canonical schema exists and is documented | `packages/db/migrations/0002_canonical_chunks.up.sql`, `docs/CHUNK_SCHEMA.md` |
| The 180 legacy chunks normalise into it | run: 23 documents, 180 source records, 180 chunks — ICT 120, English 43, Physics 17 |
| Normalisation is deterministic and idempotent | second run: `created=0 updated=0 unchanged=180`; `test_writing_the_same_chunks_twice_changes_nothing` |
| Provenance is preserved | `extraction_method`, `provenance_status`, `text_raw`, `legacy_metadata` on every chunk; schema refuses a transformed chunk with no raw text |
| Source, document and session distinctions preserved | `chunk_retrieval_context` carries `document_type`, `source_priority`, `paper_code`, `session_year`, `session_series` |
| A complete exam question is one structural chunk | `test_a_whole_question_is_stored_and_retrieved_as_one_unit`; 41 AS questions, each with its sub-parts |
| The schema supports the May/June 2024 demo set | 83 questions / 440 marks parsed and stored across WPH11–16 |
| Extraction method and uncertainty are explicit | per-document routing; 105 ICT records `verbatim` and 15 `normalized`, reflecting what actually changed |
| 004A behaviour intact | availability unchanged; no offering became available; all 004A tests still pass |
| Full suite passes | 120 tests |
| Empty-database migration works | `migrate up` from empty → 9 tables, 2 views |
| Migration reversal works | `down` → 0002 removed, registry intact; `down --to 0000` → empty |
| Consistency checks pass | `check_registry_consistency.py` OK, and proved to fire on injected identity drift |
| No private PDFs committed | `.gitignore`, pre-commit hook, CI guard; evidence files hold counts only |
| Documentation reflects verified state | `CURRICULUM_INVENTORY.md` regenerated from the registry |

Defects found and fixed along the way: the 004A seed wrote doubled legacy paths
(`raw_data/raw_data/...`); the 0002 down migration dropped `chunks` before the
view that reads it; single-letter Roman numerals `(i)`/`(v)`/`(x)` were parsed as
first-level sub-parts; and the legacy reconciliation counted every chunk in an
offering rather than only its legacy records.

---

## LUMOS-004C — Corpus cleaning and re-chunking

**Depends on:** LUMOS-004B (complete)
**Blocks:** LUMOS-008 (nothing should be indexed before it is clean)

**Description.** Repair and re-chunk the normalised legacy corpora, and extend
ingestion to the source types the past-paper adapter does not yet cover.

**Acceptance criteria**
- [ ] Bangla vowel-sign and conjunct repair applied to the 73 damaged ICT records, with a reviewed sample and a measured before/after
- [ ] English re-chunked from ~2,000-token whole units to 400–600-token sections with 50-token overlap at real boundaries
- [ ] Repaired chunks are `derived`, not `verbatim`, and keep their original text
- [ ] Bullet-glyph and mid-word truncation repair for English records
- [ ] Mark-scheme adapter, including the MCQ table strategy the terminator does not cover
- [ ] Examiner-report adapter, discarding handwritten candidate-script regions
- [ ] OCR path for the 225-page textbook, with per-page confidence recorded
- [ ] Every cleaning rule is a separate, reversible stage with its own test
- [ ] Re-chunking preserves provenance: every derived chunk traces to its source page
- [ ] Counts reconcile after re-chunking, with the change explained in the run report
