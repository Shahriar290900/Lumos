# Lumos Blockers

Items that require a human decision or a provisioning action. Nothing here can be resolved by the engineering agent alone.

Status values: `OPEN` · `DECIDED` · `RESOLVED`

---

## BLOCK-001 — Whitepaper corpus claim: DECIDED

**Severity:** Critical · **Status:** DECIDED (2026-09-04) · **Owner:** Hameem

**Decision.** The ~2.58 GB Edexcel Physics corpus described in `Lumos_Whitepaper.pdf` §1, §4 and §5.2 is **treated as unverified and historical** until it is independently located and audited. It is not present in either legacy repository and is not claimed as implemented anywhere in this project.

Standing prohibitions, in force from now on:

- do not fabricate the missing corpus
- do not generate placeholder Edexcel papers
- do not claim the full Edexcel Physics corpus is implemented
- do not modify the whitepaper silently
- do not redistribute potentially copyrighted source material

**Verified baseline** (`scripts/audit_corpus.py`, `evidence/curriculum_audit_local.json`):
SSC English 43 · SSC ICT 120 · Edexcel IAL Physics Astrophysics/Cosmology 17 · **total 180 legacy chunks**.

**What was added instead.** A real, private Edexcel source set now exists at `private_source_materials/Edexcel Physics/` — 19 licensed PDFs, 125 MB, catalogued and checksummed in `evidence/source_catalog.json`:

| Set | Documents | Registry offering | Scope |
|---|---|---|---|
| WPH11/12/13 — question papers, mark schemes, examiner reports | 9 | `edexcel-ial/physics/international-as` | **Demo scope** |
| *Student Book 1* (Topics 1-4, AS content) | 1 | `edexcel-ial/physics/international-as` | **Demo scope** |
| WPH14/15/16 — question papers, mark schemes, examiner reports | 9 | `edexcel-ial/physics/a2` | Held, not indexed |

These are **not** equivalent to the claimed 2.58 GB archive: one session, not 2009-2026. They are licensed for private ingestion only, must never be committed (ADR-017), and cannot back a public offering until BLOCK-008 is resolved.

**Follow-on:** BLOCK-001A.

---

## BLOCK-001A — Locate and independently verify the claimed 2.58 GB Edexcel corpus

**Severity:** High · **Status:** OPEN · **Owner:** Hameem

The whitepaper is a filed competition document that describes a corpus spanning examination sessions from 2009 to January 2026, ingested and Phase 1 implemented. What exists is one session (2024 May/June) plus one textbook.

**Task.** Determine whether the archive exists anywhere — a local disk, a private repository, cloud storage, an HF dataset — and if so, catalogue and checksum it with `scripts/catalog_sources.py` so its scale can be stated from evidence rather than recollection.

**If it does not exist**, the final-round technical documentation must describe the corpus the repository actually holds. BCOLBD scores 20 points for "a deployment-ready inference model demonstrating the AI model's functionality and **reproducibility**" and 20 for "a complete code repository"; a reproducibility claim an evaluator can falsify in five minutes costs more than a smaller honest scope.

**Do not** fabricate or synthesise the missing corpus under any circumstances.

**Blocks:** LUMOS-024 (technical documentation), LUMOS-025 (demo), any public claim about Edexcel coverage.

---

## BLOCK-002 — Neon project: mostly resolved

**Severity:** Low · **Status:** PARTLY RESOLVED (2026-09-04) · **Owner:** Hameem

**Resolved.** A Neon project exists in `ap-southeast-1` — the region this blocker asked us to evaluate for Bangladesh latency — running **PostgreSQL 18.6 with pgvector 0.8.6**. It is now the development database. The full verification gate passes against it end to end: migrations up and down from empty, seed, both normalisation adapters, idempotency, the consistency gate, and 120 tests.

Migrations and seed proved provider-agnostic exactly as predicted. **No application or test code needed changing** — including the test harness, which creates and drops throwaway databases per session. That was expected to break, and did not: this project's Neon instance does have a `postgres` maintenance database, `pg_terminate_backend` is permitted for the owner role, and `CREATE DATABASE` works over both the pooled and direct endpoints.

**Measured cost.** The suite runs in **93 s** against Neon versus **3.9 s** against CI's local container — roughly 24× slower, entirely network round trips to Singapore. Acceptable for a local loop; CI remains the fast gate.

**Still open.**

- No production branch, no separate staging database. The development database is the only one.
- The committed `.env.example` documents `DIRECT_DATABASE_URL`; migrations and the test harness must use the **unpooled** host (no `-pooler`), which is what is configured locally.

**Blocks:** nothing currently. LUMOS-006 is unblocked for development.

---

## BLOCK-003 — Cloudflare zone and R2 bucket not provisioned

**Severity:** Medium · **Status:** OPEN

No zone, no R2 bucket, no domain decision. Needed for asset delivery, curriculum page images and the 3D homepage assets.

**Needed:** domain name decision, zone, R2 bucket, and a scoped API token (least privilege — not a global key).

**Blocks:** LUMOS-017, LUMOS-023.

---

## BLOCK-004 — Render services not provisioned

**Severity:** Medium · **Status:** OPEN

No Render service for the FastAPI application or the ingestion worker.

**Blocks:** LUMOS-023.

---

## BLOCK-005 — Model serving: partly decided

**Severity:** High · **Status:** PARTLY DECIDED (2026-09-04) · **Owner:** Hameem

**Decided.**

- **Model: `gemma4:e4b`, and only `gemma4:e4b`.** `google/gemma-4-E4B-it` (Apache-2.0) on Hugging Face; `gemma4:e4b` as the Ollama tag. No Qwen, no Gemini, no GPT, and no fallback chain to a second generation model. An unavailable model fails loudly rather than answering from something else. The whitepaper's Qwen/DeepSeek stack (§5.10) is superseded.
- **Hosting: remote, always.** The development machine (2017 MacBook Air, no GPU, 8 GB RAM) is a client and an orchestrator, never an inference host.
- **Exemptions, deliberate and confirmed:** `BAAI/bge-m3` for embeddings and `BAAI/bge-reranker-v2-m3` for reranking. A decoder LLM has no embedding endpoint, and reranking scores a query–document pair. These are the two jobs `gemma4:e4b` cannot do, not a loophole in the policy.
- **Vision** is Phase 2 and will use `gemma4:e4b`'s own multimodal capability, not a separate vision model.

**Still open.**

- The endpoint itself. `HF_TOKEN` is held; no Inference Endpoint or GPU Space exists yet, so no generation has been run.
- **The exact Ollama tag is unverified.** `ollama show gemma4:e4b` has not been run — Ollama is not installed on the development machine. Whatever it resolves to must be recorded in `CONNECTORS.md` before a provider is wired.
- **A monthly budget ceiling and a documented shutdown procedure.** GPU endpoints bill while running; an endpoint left up over a weekend is the most likely way this project overspends.
- Whether the earlier `shahriarhameem/shikhbo-ai` HF Space is being retired or reused.

**Note:** the mock provider is built regardless and unblocks all development and CI without any credential.

**Blocks:** LUMOS-010 evaluation, LUMOS-020. Does **not** block LUMOS-004F, which ships the gateway and the mock provider.

---

## BLOCK-006 — Authentication provider not decided

**Severity:** Medium · **Status:** OPEN

Legacy used bcrypt passwords + Google OAuth + email OTP over Gmail SMTP app passwords. The SMTP approach is not production-grade.

**Needed:** a decision between rolling auth in the application, a managed provider, or Neon Auth. This interacts with BLOCK-007 — an under-18 user base changes the requirements.

**Blocks:** LUMOS-005.

---

## BLOCK-007 — Under-18 data policy not decided

**Severity:** High (legal/ethical) · **Status:** OPEN

The target user is an SSC student — most are under 18. The whitepaper commits to "parental consent for under-18 accounts" and "no student assessment profiles". Neither is implemented, and no policy document exists.

**Needed:** decisions on minimum age, consent mechanism, what is stored, retention period, deletion mechanism, and whether chat history is retained at all by default.

**Constraint already binding on the build:** collect nothing not required; build no assessment profiles unless explicitly approved.

**Blocks:** LUMOS-005, LUMOS-012, LUMOS-021, public launch.

---

## BLOCK-008 — Curriculum source licensing unrecorded

**Severity:** High (legal) · **Status:** OPEN

The corpus derives from NCTB textbooks and Pearson Edexcel material. No licence, permission or provenance record exists anywhere in either repository. The whitepaper's position — "materials are used as retrieval context, not redistributed; no model is fine-tuned on proprietary content" — is asserted but not implemented or evidenced.

**Update 2026-09-04:** the registry now records `licence_status` per offering and per source document, and the schema refuses to publish an offering whose licence is `unknown` or `restricted`. The Edexcel material is recorded as `permitted_private` on the owner's statement that it is for private ingestion; the NCTB legacy corpora remain `unknown`. Nothing is published, so nothing currently depends on this — but nothing can be.

**Needed:** a decision on whether the current corpus may back a public demo, a competition submission, or a commercial launch — three different thresholds — and, for the Edexcel material, whether `permitted_private` can ever become `permitted_public`.

**Blocks:** publishing any corpus; LUMOS-004D.

---

## BLOCK-009 — Bangla OCR damage: repairable or re-extract?

**Severity:** Medium · **Status:** OPEN (needs a study, not a decision yet)

73 of 120 ICT records carry vowel-sign/conjunct corruption. Whether normalisation plus targeted repair rules is sufficient, or whether the source PDFs must be re-extracted with a better Bangla OCR pipeline, is unknown.

**Needed:** access to the source PDFs the ICT corpus was extracted from, if they still exist. Without them, re-extraction is impossible and repair is the only option.

**Note 2026-09-04:** OCR quality on the Edexcel scans was measured and is good (Tesseract at 250-300 DPI on both the textbook and the examiner reports). That is evidence the OCR toolchain is adequate for Latin script; it says nothing about Bangla, which is a materially harder script and must be measured separately before assuming re-extraction would improve on repair.

**Blocks:** LUMOS-004C quality gate.

---

## Resolved

- **BLOCK-001** — decided 2026-09-04. See above; follow-on tracked as BLOCK-001A.
