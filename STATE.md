# Lumos State

**Current phase:** Phase 0 — Foundation
**Last completed goal:** LUMOS-000 Reconnaissance (2026-09-04)
**Current goal:** LUMOS-004A — Curriculum Registry + Coverage Gates (not started)
**Repository:** `github.com/Shahriar290900/Lumos` — reconnaissance artifacts committed; no product code

## Verified as of 2026-09-04

- Legacy repositories audited at `Shikhbo-Local-App@b783680` and `shikhbo-ai@64b58c9`
- **Corpus: 180 unique records** — SSC English 43, SSC ICT 120, Edexcel IAL Physics 5.6 17. The prebuild pack's ~1,022 figure is superseded (ADR-008)
- 137 records exist identically in both repositories; the naive union of 317 is double-counting
- `shikhbo-ai/rag.py` implements FAISS + BM25 + RRF (k=60) + BGE-Reranker-v2-M3 + confidence gating — the strongest reusable asset
- **No tests exist in either repository**
- **No secrets are committed in either repository** (verified by scan)
- All nine model IDs named across the whitepaper, pack and code exist on the Hugging Face Hub
- Ten code defects recorded in `RECONNAISSANCE_REPORT.md` §C.2, each with a file reference

## Not verified / not true

- The ~2.58 GB Edexcel Physics corpus described in the whitepaper is **not present** in either repository (BLOCK-001)
- Multi-part question parsing, `depends_on` extraction and mark-scheme linkage have **no implementation and no data**
- No infrastructure is provisioned: no Neon project, no Cloudflare zone, no R2 bucket, no Render service, no model endpoint
- Pricing figures quoted in the whitepaper and prebuild pack are not re-verified

## Open blockers

BLOCK-001 (whitepaper corpus gap — **critical**), BLOCK-002 (Neon), BLOCK-003 (Cloudflare/R2), BLOCK-004 (Render), BLOCK-005 (model serving + budget), BLOCK-006 (auth provider), BLOCK-007 (under-18 data policy), BLOCK-008 (source licensing), BLOCK-009 (Bangla OCR repairability). See `BLOCKERS.md`.

## Rule

This file is not proof that anything exists. An item moves to "verified" only after a command or API check succeeds and the evidence is recorded.
