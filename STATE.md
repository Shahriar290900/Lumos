# Lumos State

**Current phase:** Phase 0.5 — Curriculum and data foundation
**Last completed goal:** LUMOS-004A — Curriculum Registry + Coverage Gates (2026-09-04)
**Next goal:** LUMOS-004B — Canonical chunk schema + legacy normalisation adapter
**Repository:** `github.com/Shahriar290900/Lumos`

## Completed

**LUMOS-000 Reconnaissance** (2026-09-04) — both legacy repositories audited; corpus baseline corrected from a documented ~1,022 to a verified **180** (ADR-008); ten code defects recorded with file references; `RECONNAISSANCE_REPORT.md`.

**LUMOS-004A Curriculum Registry + Coverage Gates** (2026-09-04) — evidence below.

## Verified

- **Registry schema** — 7 tables, 1 view, 6 enums, reversible migration. Applied, reverted to empty and re-applied against PostgreSQL 16.13 + pgvector 0.6.0.
- **Availability** is computed in one SQL view with machine-readable `blocked_reasons` (ADR-013). No offering is available; every one explains why.
- **Seed** derives every number from `evidence/*.json` rather than hand-typed constants: 2 curricula, 2 syllabus versions, 4 levels, 8 subjects, 9 offerings, 42 source documents, 3 corpus snapshots.
- **47 tests pass** — availability rule clause by clause, schema constraints, migration from empty and back, seed idempotence, registry/evidence agreement, HTTP behaviour.
- **The regression case is covered.** The বাংলা subject with zero chunks is unavailable, and `POST /tutor/ask` returns 409 with reasons rather than an answer.
- **Consistency gate works and was proved to fire** — corrupting a snapshot count made `scripts/check_registry_consistency.py` exit 1 with the drift named.
- **`CURRICULUM_INVENTORY.md` is generated** from the registry, with a `--check` mode CI runs.
- **19 private Edexcel PDFs catalogued and checksummed** (125 MB). Ingestion route determined per document by probing, not assumed.
- **Licensed material is protected** by `.gitignore`, a `.githooks/pre-commit` hook (self-tested: it blocked a `git add -f` PDF), and a CI guard job.
- **The whole suite runs with an empty `.env`** and `AI_PROVIDER=mock`. No model credential, no GPU.

## Measured, not assumed

- Question papers: `(Total for Question N = M marks)` is a 100 % reliable boundary — 19/19 in WPH11. 41 main questions, 210 marks across the three AS papers.
- **Zero explicit dependency cross-references** in any AS paper. Multi-part context therefore comes from chunk granularity, not parsed `depends_on` edges (ADR-016).
- Examiner reports differ within one session: WPH11/13 need OCR, WPH12/15 parse, WPH14/16 are mixed (ADR-015).
- *Student Book 1*: **no text layer on any of 225 pages**. Full OCR. Tesseract at 250 DPI is good on prose; specification references and equations degrade and need targeted handling.
- Mark schemes carry proper Unicode mathematics and are the repair source for equations lost to glyph failures in the question papers.

## Not true / not done

- No corpus is ingested. `indexed_chunk_count` is 0 everywhere, so nothing is available. Correct, not a defect.
- No infrastructure is provisioned: no Neon project, Cloudflare zone, R2 bucket, Render service or model endpoint.
- The ~2.58 GB Edexcel corpus in the whitepaper remains unlocated (BLOCK-001 decided, BLOCK-001A open).
- No front end. No retrieval. No Model Gateway yet.

## Open blockers

BLOCK-001A (locate the claimed corpus), BLOCK-002 (Neon), BLOCK-003 (Cloudflare/R2), BLOCK-004 (Render), BLOCK-005 (model serving + budget), BLOCK-006 (auth), BLOCK-007 (under-18 policy), BLOCK-008 (licensing), BLOCK-009 (Bangla OCR repairability). BLOCK-001 is decided.

## Rule

This file is not proof that anything exists. An item moves to "verified" only after a command or API check succeeds and the evidence is recorded.
