# Lumos Blockers

Items that require a human decision or a provisioning action. Nothing here can be resolved by the engineering agent alone.

Status values: `OPEN` · `DECIDED` · `RESOLVED`

---

## BLOCK-001 — Whitepaper describes a corpus that does not exist in the repositories

**Severity:** Critical · **Status:** OPEN · **Owner:** Hameem

`Lumos_Whitepaper.pdf` states, in §1 and §4:

> "the ingestion pipeline has processed a curriculum corpus of approximately 2.58 GB spanning examination sessions from 2009 to January 2026"
> "**Phase 1 (implemented).** Pearson Edexcel Physics, A-Level, sessions 2009 through January 2026 … question papers, mark schemes, examiner reports, textbooks, and revision guides, ingested into a linked, chunked, vector-indexed corpus."

Verified reality across both repositories: **17 chunks** of Astrophysics/Cosmology revision notes (spec area 5.6, 36 KB) plus a 79 KB notes PDF. No question paper, mark scheme, examiner report or textbook is present. No ingestion code targets those document types. No record in the corpus carries a question, sub-question, marks or dependency field, so the boundary-detection, sub-question parsing and `depends_on` extraction described in whitepaper §5.3–§5.7 have no implementation and no data.

**Why this cannot wait.** BCOLBD final-round scoring awards 20 points for "*a well-documented and accessible code repository*" and 20 for "*clean, well-commented code and a deployment-ready inference model demonstrating the AI model's functionality and reproducibility*". An evaluator who reads the whitepaper and then opens the repository finds the gap. It is better found now, by us.

**Question for the owner:** does the 2.58 GB corpus exist somewhere outside these repositories — a local disk, a private repo, Drive, an HF dataset — or was the claim aspirational?

**Paths, depending on the answer:**

| If | Then |
|---|---|
| The corpus exists elsewhere | Provide access. It becomes the LUMOS-007 ingestion input, and the whitepaper needs no correction — but the pipeline described in §5.3–§5.7 still has to be *built*, because it does not exist in code. |
| It does not exist | Decide between: (a) acquire and ingest a real Edexcel Physics corpus before the final round; (b) issue a corrected technical document for the final round that states verified scope accurately, keeping the whitepaper as the preliminary-round artifact it already is; (c) present the multi-part architecture as designed-and-partially-implemented, with the 180-record corpus as the honest demonstrated scope. |

**Recommendation:** whichever path is chosen, the final-round technical documentation must describe what the repository actually contains. A reproducibility claim an evaluator can falsify in five minutes costs more than a smaller honest scope.

**Blocks:** LUMOS-007 (ingestion scope), LUMOS-016 (multi-part questions — no data to build against), LUMOS-024 (technical documentation), LUMOS-025 (demo).

---

## BLOCK-002 — Neon project not provisioned

**Severity:** High · **Status:** OPEN

No Neon project, no `DATABASE_URL`, no pgvector instance. Needed for the curriculum registry, migrations and all retrieval work.

**Needed:** a Neon project (region choice matters for Bangladesh latency — evaluate `ap-southeast-1` against the alternatives), with pgvector enabled and a development branch.

**Note:** LUMOS-004A can proceed against a local Postgres container, so this does not block the next goal — only its deployment.

**Blocks:** LUMOS-006, deployment of LUMOS-004A.

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

## BLOCK-005 — Model serving decision and budget ceiling

**Severity:** High · **Status:** OPEN

The Model Gateway needs at least one real provider before any generation work can be evaluated. The development machine (2017 MacBook Air) cannot host inference.

**Needed:**

- Provider choice for development: HF Inference Endpoint vs. HF GPU Space.
- Model choice. Current-generation candidates verified to exist on the Hub: `Qwen/Qwen3.5-4B` (Apache-2.0), `google/gemma-4-E4B-it` (Apache-2.0). The whitepaper's stack (Qwen2.5-7B, Qwen2-VL-7B, Gemma-2-2B) is a generation behind. `BAAI/bge-m3` and `BAAI/bge-reranker-v2-m3` remain correct and should not change.
- **A monthly budget ceiling and a documented shutdown procedure.** GPU endpoints bill while running; an endpoint left up over a weekend is the most likely way this project overspends.
- Whether the earlier `shahriarhameem/shikhbo-ai` HF Space is being retired or reused.

**Note:** the mock provider is being built regardless and unblocks all development and CI without any credential.

**Blocks:** LUMOS-010 evaluation, LUMOS-020.

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

**Needed:** per-source licence status recorded in the registry before any corpus is published, and a decision on whether the current corpus may be used for a public demo, a competition submission, or a commercial launch — these are three different thresholds.

**Blocks:** publishing any corpus; LUMOS-004D.

---

## BLOCK-009 — Bangla OCR damage: repairable or re-extract?

**Severity:** Medium · **Status:** OPEN (needs a study, not a decision yet)

73 of 120 ICT records carry vowel-sign/conjunct corruption. Whether normalisation plus targeted repair rules is sufficient, or whether the source PDFs must be re-extracted with a better Bangla OCR pipeline, is unknown.

**Needed:** access to the source PDFs the ICT corpus was extracted from, if they still exist. Without them, re-extraction is impossible and repair is the only option.

**Blocks:** LUMOS-004C quality gate.

---

## Resolved

*(none yet)*
