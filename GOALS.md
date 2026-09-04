# Lumos Goal Register

Status: `[ ]` not started · `[~]` in progress · `[x]` complete with evidence · `[!]` blocked

A goal is complete only when its acceptance criteria are met **and** the evidence is recorded. Building successfully is not evidence.

## Phase 0 — Foundation
- [x] **LUMOS-000 Reconnaissance** — evidence: `RECONNAISSANCE_REPORT.md`, `evidence/*.json`, `scripts/audit_corpus.py`
- [ ] LUMOS-001 Repository bootstrap: monorepo layout, tooling, lint, typecheck
- [ ] LUMOS-002 Design system + brand tokens (dark magical academy: deep navy/black, warm gold)
- [ ] LUMOS-003 Agent operating system (`.claude/` skills, agents, hooks, state files)
- [x] **LUMOS-004 CI baseline + test harness** — evidence: `.github/workflows/ci.yml`, 125 tests, first GitHub Actions run green on `b722d17` (three jobs, every step)

## Phase 0.5 — Curriculum and data foundation
- [x] **LUMOS-004A Curriculum registry + coverage gates** — evidence: `packages/db/migrations/0001_curriculum_registry.up.sql`, 47 passing tests, `scripts/check_registry_consistency.py`, generated `CURRICULUM_INVENTORY.md`
- [x] **LUMOS-004B Canonical chunk schema + legacy normalisation adapter** — evidence: migration 0002, 263 canonical chunks, 120 passing tests, `evidence/legacy_normalisation.json`
- [x] **LUMOS-004B.1 Bootstrap fixes and model policy** — evidence below
- [ ] **LUMOS-004C Corpus cleaning: Bangla repair, boundary repair, re-chunking** ← **NEXT GOAL**, in three sub-goals (ADR-025)
  - [x] **LUMOS-004C.1** Legacy text repair: Bangla, English re-chunking, glyph and truncation repair — evidence below
  - [ ] **LUMOS-004C.2** Mark-scheme and examiner-report adapters, cross-document linking, and the **document delivery column** (ADR-026)
  - [ ] **LUMOS-004C.3** Textbook OCR, 225 pages — *grounding only; never served (ADR-026)*
- [ ] LUMOS-004D Licence and provenance registry
- [!] LUMOS-004E Retrieval evaluation set per available corpus — *needs subject-teacher review*
- [x] **LUMOS-004F Model Gateway + mock provider + `gemma4:e4b`** — evidence: `services/models/`, 27 tests; embeddings and reranking verified live on Hugging Face, generation blocked on BLOCK-005

## Phase 1 — Product MVP
- [!] LUMOS-005 Authentication + roles — *blocked: BLOCK-006, BLOCK-007*
- [~] LUMOS-006 Neon schema + migrations — *both migrations apply and reverse against the provisioned Neon project (PostgreSQL 18.6, pgvector 0.8.6, `ap-southeast-1`); no production branch yet*
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

## LUMOS-004B.1 — Bootstrap fixes and model policy — COMPLETE (2026-09-04)

Closing the gaps between the documented state and the real one, before 004C.

| Criterion | Evidence |
|---|---|
| History restored and pushed | 4 commits on `github.com/Shahriar290900/Lumos`; the bundle tip was `b722d17`, one commit *above* the documented `302ebb4` |
| `ci.yml` present | Was in the bundle at 8,205 bytes all along. The copy in `Claude outputs/` is a stale pre-004B version and was not used |
| CI actually runs | First-ever Actions run green on `b722d17`: guard, tests, inventory — every step |
| Licensed material still uncommittable | Hook enabled and committed `100755`; guard, `.gitignore` and CI job all pass with 19 PDFs on disk |
| Model policy recorded | ADR-022; `.env.example`, `CONNECTORS.md`, `MIGRATION_MAP.md`, `BLOCKERS.md`, `ARCHITECTURE.md`, `CLAUDE.md` |
| Superseded models removed from forward-looking docs | Qwen candidate lists gone; Gemini client is **do not port**; `RECONNAISSANCE_REPORT.md` deliberately untouched |
| Database provisioned and verified | Neon `ap-southeast-1`, PostgreSQL 18.6, pgvector 0.8.6; full gate green end to end (ADR-023) |
| Goal-numbering conflict resolved | ADR-024 — 004D stays the licence registry, gateway becomes 004F |
| 004C split recorded | ADR-025 |
| Inventory is reproducible | **Defect found and fixed** — see below; 4 new tests, 3 of which fail against the previous generator |
| Full suite passes | 125 tests against Neon |

**Reproducibility defect found in `scripts/generate_inventory.py`.** The
normalisation-runs table was irreproducible in two independent ways, and the
committed `CURRICULUM_INVENTORY.md` did not match a regeneration on a second
machine. It ordered rows by `offering_id`, a `gen_random_uuid()` value, so row
order depended on which database instance produced the file. And it selected the
"latest" run per `(offering, adapter)` with `DISTINCT ON` ordered by
`started_at`, but the past-paper adapter records one run per document and every
run of one invocation shares a timestamp because `now()` is transaction-scoped —
a three-way tie broken arbitrarily.

The visible symptom was a wrong number in the document whose purpose is to state
the right one: the AS offering reported **18** source records where it holds
**41**, and the A2 offering **4** where it holds **42**. Both now report the full
batch, summing to the documented 83. This matters beyond tidiness — BCOLBD scores
20 points for a repository an external evaluator can clone and reproduce, and
this file is the first thing such an evaluator would regenerate.

**Deliberately not done:** the planned `TEST_ADMIN_DATABASE` indirection. The
test harness was expected to need it for Neon and does not — this instance has a
`postgres` maintenance database, permits `pg_terminate_backend`, and accepts
`CREATE DATABASE` on both endpoints. All 120 pre-existing tests passed against
Neon with no code change, so the variable would have been speculative.

---

## LUMOS-004C.1 — Legacy text repair — COMPLETE (2026-09-04)

| Criterion | Evidence |
|---|---|
| Bangla repair, measured before and after | 2,212 repairs across **120 of 120 ICT records**; `evidence/legacy_normalisation.json` |
| English re-chunked to 400–600 tokens with 50-token overlap | 43 records → 109 chunks; **0 chunks over 600 tokens**, enforced by the consistency gate |
| Repaired chunks are `derived`, never `verbatim`, and keep their input | 268 `derived`, 22 `verbatim`; schema refuses a transformed chunk with no `text_raw` |
| Bullet-glyph and truncation repair | 61 bullet restorations, 20 hyphenated line breaks rejoined |
| Every rule is a separate, reversible stage with its own test | 4 stages in `services/ingestion/cleaning.py`; 31 unit tests |
| Provenance survives | every piece records `char_start`/`char_end` and its cleaning tally in `legacy_metadata` |
| Counts reconcile, with the change explained | 180 audited → 180 source records present → 290 chunks; reconciliation moved from chunk count to `count(distinct legacy_chunk_id)` |
| Consistency gate extended | source-record reconciliation, "every record yields ≥1 chunk", and a 600-token ceiling |
| Full suite green | 179 tests |

**The recorded damage was understated by about nine times.** `BLOCKERS.md` and
`STATE.md` said 73 of 120 ICT records carried Bangla corruption. That came from an
auditor pattern matching only `যয`. The actual fault is a **consonant doubled
before a pre-base vowel sign** — `ো` decomposes to `ে` + `া`, and a converter
reading the pre-base component as a standalone character emits the consonant
twice. Measured properly it is **2,253 occurrences across all 120 ICT records**,
and English and Physics are untouched.

    ককোননো → কোনো (364)   যযোগাযযোগ → যোগাযোগ (124)
    হললো → হলো (43)        মততো → মতো (28)

**Two auditor patterns were wrong in the other direction too.** `broken_word_split`
reported 66 records, but its 75 ICT matches are correct Bengali — `যেমন-` is a
dash introducing a list and `ই- লার্নিং` is "e-learning", not damage. And
`bullet_ocr_as_letter_e` reported zero because it anchored to a line start; the
bullets are mid-line, because the extractor lost the newlines too.

**Not done here:** `keywords` and `syllabus_reference` remain absent on 163 of 180
records. Nothing in the sources supplies them, so they stay explicit gaps rather
than invented values.

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
