# Lumos Test Matrix

**Status 2026-09-04: 47 tests passing.** The rows marked ✅ below are implemented and green; the rest are not yet written.

**Baseline: there were no tests in either legacy repository.** No `test_*.py`, no `conftest.py`, no `*.spec.js`, no `pytest.ini`, no Playwright or Vitest configuration. The only CI is a tag-triggered installer build that asserts nothing about behaviour. Everything below is a new build.

**Prerequisite:** the deterministic mock model provider. No test may require a GPU or a credential.

| Area | Test | Layer | Required before MVP |
|---|---|---|---:|
| Curriculum | unavailable subject is rejected before retrieval | integration | ✅ |
| Curriculum | subject with zero indexed chunks reports unavailable (C.2.8 regression) | unit | ✅ |
| Curriculum | invalid curriculum/level combination rejected | integration | ✅ |
| Retrieval | only in-scope chunks are retrieved — metadata filter applied **before** ranking (C.2.3 regression) | integration | Yes |
| Retrieval | RRF over fixed rank lists produces the known fused order | unit | Yes |
| Retrieval | source priority preserved through fusion and reranking | integration | Yes |
| Retrieval | reranker unavailable → falls back to RRF order, does not error | integration | Yes |
| Retrieval | Recall@K / Precision@K / MRR measured per language | evaluation | Yes |
| Ingestion | duplicate content across repositories is deduplicated | unit | Yes |
| Ingestion | all three legacy schemas normalise to the canonical schema | unit | Yes |
| Ingestion | `chapter_title` and `chapter_name` both resolve (C.2.2 regression) | unit | Yes |
| Ingestion | re-chunking produces sizes within the target band | unit | Yes |
| Ingestion | Bangla NFC normalisation and repair rules are idempotent | unit | Yes |
| Ingestion | provenance and page references survive every transformation | unit | Yes |
| Citations | every reference in an answer resolves to a retrieved chunk | integration | Yes |
| Citations | an answer citing a non-retrieved source is rejected | integration | Yes |
| Refusal | low-evidence query refuses and does not fabricate a citation | evaluation | Yes |
| Refusal | out-of-corpus query refuses rather than answering from priors | evaluation | Yes |
| Multi-part | dependencies remain available across sub-parts | integration | Phase 2 (BLOCK-001) |
| Auth | register / login / logout / session expiry | integration | Yes |
| Auth | ownership enforced server-side on every resource | integration | Yes |
| Auth | missing `AUTH_SECRET` aborts startup (C.2.9 regression) | unit | Yes |
| Streaming | SSE closes cleanly under timeout and under error | integration | Yes |
| Database | migration from an empty database succeeds and reverses | integration | ✅ |
| Database | expected indexes exist; the metadata-filter query plan is sane | integration | partial |
| Model gateway | provider swap requires no product-code change | unit | Yes |
| Model gateway | provider failure falls back per policy | integration | Yes |
| Model gateway | full suite passes with `AI_PROVIDER=mock` and an empty `.env` | CI | ✅ |
| Security | no secret appears in any client bundle | build-time | Yes |
| Security | no licensed source material or oversized file is tracked in git | CI | ✅ |
| Security | pre-commit hook blocks `git add -f` of a PDF | manual | ✅ |
| Security | prompt-injection corpus does not alter system behaviour | evaluation | Yes |
| Security | upload validation: type, size, path traversal | integration | Phase 2 |
| Browser | core tutor journey with visible citations | Playwright | Yes |
| Browser | subject selection reflects registry availability | Playwright | Yes |
| Browser | error and empty states render | Playwright | Yes |
| Accessibility | keyboard navigation through the tutor journey | Playwright | Yes |
| Accessibility | `prefers-reduced-motion` disables heavy animation | Playwright | Yes |
| Mobile | responsive tutor and dashboard | Playwright | Yes |
| 3D | core journeys work with WebGL unavailable | Playwright | Yes |
| Performance | standard query latency measured, low-end profile + throttled network | performance | Yes |
| AI quality | golden evaluation set, regression-gated | evaluation | Yes |
| AI quality | Bangla and English scored **separately** | evaluation | Yes |

## Implemented so far

`tests/unit/test_availability_rule.py` — the availability rule clause by clause (10 parametrised cases), plus the schema constraints that make an inconsistent row unwritable: indexed-without-chunks, published-on-unknown-licence, published-without-language, visible-without-explanation, malformed checksum, duplicate document, out-of-range priority.

`tests/integration/test_registry_api.py` — migration from empty and back, seed idempotence, registry-versus-auditor agreement, private sources hidden from public reads, source ordering by priority, per-document ingestion routes, the gate raising rather than returning a flag, ambiguous resolution refused rather than guessed, and the HTTP surface including the 409-with-reasons refusal.

## Golden evaluation set

Proportionate to a 180-record corpus: roughly 40–60 questions — ~20 ICT (Bangla), ~15 English, ~15 Physics 5.6, plus ~10 deliberately out-of-corpus to test refusal.

Built with **subject-teacher review**, as the whitepaper §6.1 commits to. A golden set written by the system's own authors measures self-consistency, not correctness.

Committed as versioned JSON with results, so regressions are diffable in review.
