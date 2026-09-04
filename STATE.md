# Lumos State

**Current phase:** Phase 0.5 — Curriculum and data foundation
**Last completed goal:** LUMOS-004B.1 — Bootstrap fixes and model policy (2026-09-04)
**Next goal:** LUMOS-004C.1 — Legacy text repair
**Repository:** `github.com/Shahriar290900/Lumos` — **pushed**, 6 commits, CI green

## Environment — measured 2026-09-04

Recorded because the next goal's OCR stage is constrained by it, not as background.

| | |
|---|---|
| Machine | MacBook Air 2017, Intel, no GPU, 8 GB RAM. Client and orchestrator, **never an inference host** |
| Free disk | **3.5 GB**, after reclaiming 2.1 GB of caches. Was 1.4 GB; still the tightest constraint |
| Docker | **Not installed, and not viable** — Docker Desktop plus its VM image needs ~4 GB (ADR-023) |
| Database | Neon `ap-southeast-1`, PostgreSQL **18.6**, pgvector **0.8.6**, unpooled endpoint |
| Local Python | 3.12.2 in `.venv`. **CI runs 3.11.16** — a known, accepted divergence |
| Suite runtime | ~100 s against Neon · ~4 s in CI. Roughly 25×, all network round trips |
| OCR toolchain | `pypdfium2` present (transitive via pdfplumber). **Tesseract not installed** — needed for 004C.3 |

**Consequences for LUMOS-004C.3.** The 225-page textbook must be rendered and
OCR'd **one page at a time with immediate cleanup**; materialising all 225 renders
at 250 DPI would need 1–2 GB that does not exist. And it will run on this machine,
which deviates from `docs/INGESTION_DESIGN.md` §7 rule 6 ("ingestion is off the
development machine") because no batch host is provisioned. That deviation is
recorded here rather than assumed away; it is a batch job, never on the request
path.

## Completed

**LUMOS-000 Reconnaissance** — corpus baseline corrected from a documented ~1,022 to a verified **180** (ADR-008); ten legacy defects recorded; `RECONNAISSANCE_REPORT.md`.

**LUMOS-004A Curriculum Registry + Coverage Gates** — availability computed in one SQL view with machine-readable reasons; the বাংলা regression closed; 19 private Edexcel PDFs catalogued and checksummed.

**LUMOS-004B Canonical chunk schema + legacy normalisation adapter** — evidence below.

**LUMOS-004B.1 Bootstrap fixes and model policy** — history pushed and CI green for the first time; `gemma4:e4b` recorded as the only generation model (ADR-022); Neon provisioned and the full gate verified against it (ADR-023); a reproducibility defect found and fixed in the inventory generator.

**Decisions taken since (ADR-026)** — the 18 Edexcel exam PDFs will be served in the application; *Student Book 1* is never served and stays retrieval grounding only. This escalated BLOCK-003 (R2) onto the demo critical path, and needs a registry column that does not exist yet.

## Verified — 004B

- **Canonical model** (`chunks`, `normalisation_runs`, `chunk_retrieval_context`, 3 enums) in migration 0002. Applied from empty, reverted, re-applied.
- **263 canonical chunks** exist: 180 normalised legacy records + 83 exam questions.
  - `nctb/ict/ssc` 120 · `nctb/english/ssc` 43 · `edexcel-ial/physics/a2` 17 legacy + 42 questions · `edexcel-ial/physics/international-as` 41 questions
- **Reconciles with the auditor**: 120 / 43 / 17 = 180, matching `evidence/curriculum_audit_local.json` exactly. Enforced in CI.
- **Identity is derived, not assigned** (ADR-018): `uuid5(namespace, "lumos:v1:<document sha256>:<locator>")`. 263 chunks, 263 distinct ids, keys and content hashes. Question 12 appears in four papers as four distinct chunks.
- **Idempotent**: second run of either adapter reports `created=0 updated=0`, all unchanged. Verified for the legacy adapter and all six papers.
- **Provenance per chunk** (ADR-021): 165 `verbatim`, 83 `cleaned`, 15 `normalized`. Every non-verbatim chunk keeps `text_raw`; the schema refuses one that does not.
- **Legacy traceability**: all 180 keep `legacy_chunk_id` and the complete original record in `legacy_metadata`.
- **Three counts, three meanings** (ADR-020): audited / canonical / indexed. `canonical_chunk_count` is a view subquery, so it cannot be set by hand.
- **125 tests pass** with `AI_PROVIDER=mock` and no model credential (120 at 004B, plus 5 inventory-reproducibility tests).
- **Consistency gate extended** to chunk identity, key–document agreement, offering agreement and legacy reconciliation. Proved to fire on injected drift.
- **No source text in any committed file**: evidence reports carry counts, checksums and structure only; test fixtures are synthetic.

## Measured from the real papers

- 83 main questions, 440 marks across WPH11–16. AS demo scope: 41 questions, 210 marks (WPH11 19/80, WPH12 18/80, WPH13 4/50).
- Zero question-numbering gaps in any of the six papers — the `(Total for Question N = M marks)` terminator held throughout.
- MCQs parse with 0 sub-parts and 1 mark; structured questions with 2–5 sub-parts and 5–12 marks; page spans resolve across page breaks.

## Defects found and fixed during 004B

- The 004A seed wrote doubled legacy paths (`raw_data/raw_data/...`), so no legacy document resolved on disk.
- The 0002 down migration dropped `chunks` before the view that reads it, so reversal failed.
- Single-letter Roman numerals `(i)`, `(v)`, `(x)` were parsed as first-level sub-parts, nesting `(ii)` under `(i)`.
- Legacy reconciliation counted every chunk in an offering rather than only its legacy records, so it failed after the paper adapter wrote to the same offering.

## Not true / not done

- **Nothing is indexed.** No embeddings, no lexical index, so no offering is available. Correct, not a defect.
- Mark schemes, examiner reports and the 225-page textbook are catalogued and routed but not yet ingested — LUMOS-004C.
- The Bangla corruption in 73 ICT records is recorded, not repaired.
- English chunks remain whole textbook units of ~2,000 tokens.
- **The Model Gateway does not exist.** `AI_PROVIDER=mock` is set in tests and CI and **nothing reads it**. `services/models/` is not created. That is LUMOS-004F, and no generation of any kind has been run.
- Infrastructure still unprovisioned: no Cloudflare zone, R2 bucket, Render service or model endpoint. Neon is now provisioned (development only, no production branch).
- The ~2.58 GB Edexcel corpus in the whitepaper remains unlocated (BLOCK-001 decided, BLOCK-001A open).

## Open blockers

BLOCK-001A (locate the claimed corpus), BLOCK-003 (Cloudflare/R2), BLOCK-004 (Render), BLOCK-006 (auth), BLOCK-007 (under-18 policy), BLOCK-008 (licensing), BLOCK-009 (Bangla OCR repairability — now on the critical path for 004C.1).

Partly closed: BLOCK-002 (Neon provisioned; no production branch), BLOCK-005 (model and remote hosting decided; endpoint, budget ceiling and shutdown procedure still open).

## Rule

This file is not proof that anything exists. An item moves to "verified" only after a command or API check succeeds and the evidence is recorded.
