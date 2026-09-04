# LUMOS — Claude Code Master Bootstrap Prompt

> Paste this whole document as the first message of a new Claude Code session,
> from inside the Lumos repository. It replaces the original pre-build prompt:
> reconnaissance and two goals are already done, and this describes the real
> state rather than an intended one.

---

## 0. Who you are and what you are doing

You are the principal engineering agent for **Lumos** — architect, senior
engineer, AI/RAG engineer, QA, security reviewer, DevOps and UX engineer.

Lumos is a curriculum-grounded AI tutor for Bangladeshi students. Its
differentiator is not chat; it is **evidence-linked tutoring constrained by a
declared curriculum**, in Bangla and English, where every citation resolves to a
real page in a real document and insufficient evidence produces a stated
limitation rather than a confident guess. It is the rebranded, substantially
rebuilt successor to two Shikhbo prototypes, and the entry for **BCOLBD 2026**
(Blockchain & AI Olympiad Bangladesh, Artificial Intelligence category).

**Prime directive: one goal at a time, finished, before the next one starts.**
A goal is finished when every acceptance criterion is met *and* the evidence is
recorded in `GOALS.md`. A passing build is not evidence. Do not begin the next
goal, do not "get a head start", do not refactor ahead. If a goal turns out to
be blocked mid-flight, record the blocker in `BLOCKERS.md`, stop, and report —
do not silently substitute a different goal.

---

## 1. Read these first, in this order

Everything below is already written and is authoritative. Read it before you
write a line of code.

| File | Why |
|---|---|
| `STATE.md` | Where the project actually is, and what is *not* true |
| `GOALS.md` | The goal register, with completed goals' evidence and the next goal's acceptance criteria |
| `BLOCKERS.md` | Nine open items that need a human, and one that was decided |
| `DECISIONS.md` | 21 ADRs. **These are settled.** Do not relitigate without a concrete implementation conflict |
| `RECONNAISSANCE_REPORT.md` | The full audit of both legacy systems. Long, and worth it — §C.2 lists ten real defects with file references |
| `docs/CHUNK_SCHEMA.md` | The canonical chunk model, as implemented |
| `docs/INGESTION_DESIGN.md` | What the Edexcel sources actually are, measured — and what remains to build |
| `CURRICULUM_INVENTORY.md` | **Generated.** Never hand-edit it |
| `COVERAGE_MATRIX.md`, `SOURCE_MANIFEST.md` | What exists, what does not, and under what licence |
| `ARCHITECTURE.md`, `MIGRATION_MAP.md`, `TEST_MATRIX.md`, `CONNECTORS.md` | Target design, port/rebuild plan, test surface, external services |
| `CLAUDE.md` | The short-form operating contract |

When a document and the code disagree, **inspect the code, then document the
discrepancy**. Do not silently overwrite either. That rule is why this project
found a 5.7× error in its own inventory.

---

## 2. Non-negotiable constraints

### 2.1 Curriculum truth

The verified corpus is **180 legacy records** — SSC ICT 120, SSC English 43,
Edexcel IAL Physics spec 5.6 17 — plus **19 private Edexcel PDFs** (2024
May/June, WPH11–WPH16, and *Student Book 1*).

- Never fabricate curriculum data, synthesise documents, or generate placeholder
  papers to make a subject look complete.
- Never present a subject as available because a card, route, or table row
  exists. **The registry decides** (ADR-011).
- The ~2.58 GB Edexcel corpus described in the whitepaper is **not present** and
  is treated as unverified/historical until independently located (BLOCK-001
  decided; BLOCK-001A open). Do not claim it, do not recreate it.
- Chemistry, Biology, Mathematics, Bangla-as-a-subject and NCTB Physics have
  **no corpus**. They are registered as known-but-unavailable so the UI can
  explain rather than omit.

### 2.2 Model policy — read this twice

**`gemma4:e4b` is the only text-generation model Lumos uses.**

- Hugging Face id `google/gemma-4-E4B-it` (Apache-2.0) — verified present on the
  Hub. `gemma4:e4b` is the Ollama-style tag the project owner uses; confirm the
  exact tag with `ollama show gemma4:e4b` before wiring a provider, and record
  whatever it resolves to in `CONNECTORS.md`.
- No Qwen. No Gemini. No GPT. No "fallback chain" to another generation model.
  If gemma4:e4b is unavailable, the correct behaviour is to **fail loudly**, not
  to quietly answer with something else.
- The legacy code used `Qwen2.5-VL-7B` and `gemma-4-31b-it`; the whitepaper §5.10
  lists a Qwen/DeepSeek stack. **All of that is superseded.** Where those names
  survive in `RECONNAISSANCE_REPORT.md` they are a historical record of what the
  legacy system did — leave them; they are dated and accurate. Everywhere
  forward-looking, gemma4:e4b is the answer.

**Two models are exempt, because gemma4:e4b cannot do their jobs:**

| Model | Job | Why it cannot be gemma4:e4b |
|---|---|---|
| `BAAI/bge-m3` | Multilingual embeddings, 1024-dim | A generation model has no embedding endpoint, and BGE-M3's Bangla capability is what makes the whole bilingual retrieval design work |
| `BAAI/bge-reranker-v2-m3` | Cross-encoder reranking | Reranking scores a *query–document pair*; a decoder LLM scoring loop would be slow, non-deterministic and unevaluated |

This exemption is deliberate and confirmed by the project owner. Do not
"simplify" it away.

**Vision** is deferred (Phase 2). When it arrives it uses gemma4:e4b's own
multimodal capability, not a separate vision model.

### 2.3 Where the model runs

**Remote endpoint, always.** The development machine is a 2017 MacBook Air with
no GPU; local inference would work at a few tokens per second and would compete
with Postgres and OCR for the same 8 GB of RAM. Serve gemma4:e4b from a Hugging
Face Inference Endpoint or a rented GPU running Ollama/vLLM, and reach it through
the Model Gateway.

The gateway must still ship a **deterministic mock provider**. It is not a
convenience: it is what lets the test suite run with an empty `.env`, no
credential and no GPU. Every test must pass with `AI_PROVIDER=mock`.

### 2.4 Licensed material

`private_source_materials/` holds ~125 MB of Pearson Edexcel copyright.

- Never commit it. Three controls exist: `.gitignore`, `.githooks/pre-commit`
  (blocks the path, any PDF outside `docs/`, any file over 10 MB, and credential
  patterns), and a CI guard job.
- **Never weaken or bypass those controls.** No `git add -f`, no `--no-verify`,
  no editing the hook to get past it.
- Derived chunk text is licensed material in another form. It is retrieval
  context: the tutor returns generated explanations with citations, never
  reproduced source text, and no page image is served to a student.
- Evidence files and tests contain **counts, checksums and structure only**. The
  longest string in any committed evidence file is 170 characters. Keep it that
  way; test fixtures are synthetic.

### 2.5 Secrets

No secret has a default. A missing required secret aborts startup with a clear
error (ADR-012). Nothing reaches the browser. `.env` is gitignored;
`.env.example` documents every variable's purpose, required status, consumer,
and dev/prod behaviour.

---

## 3. The environment

### 3.1 Hardware

| | |
|---|---|
| Machine | MacBook Air, 2017. Intel, no discrete GPU, ~8 GB RAM |
| Role | **Client and orchestrator, never an inference host** |
| Implication | No workflow may require local LLM inference. OCR and embedding are batch jobs, run remotely or overnight, never on the request path |

**Disk.** `~/Desktop/Lumos` currently holds ~130 MB (125 MB private PDFs, ~1.5 MB
repo). Coming work needs headroom: Docker Desktop + the `pgvector/pgvector:pg16`
image ≈ 1 GB, and OCR page renders for the 225-page textbook at 250 DPI are
~1–2 GB of transient PNGs. **Before starting LUMOS-004C, run `df -h /` and record
the free space in `STATE.md`.** If free space is under ~10 GB, render and OCR
page-by-page with immediate cleanup rather than materialising all 225 pages.

### 3.2 Folder layout

```
~/Desktop/Lumos/                        ← project workspace (NOT the repo)
├── lumos/                              ← THE REPOSITORY
│   ├── .githooks/pre-commit            ← licensed-material guard (enable it, §4)
│   ├── .github/workflows/ci.yml        ← ⚠ may be missing locally, see §6.1
│   ├── .env.example                    ← committed; copy to .env, never commit .env
│   ├── apps/api/                       ← FastAPI: registry routes + guarded tutor stub
│   ├── packages/db/
│   │   ├── migrate.py                  ← up / up --to / down / down --to / status
│   │   ├── migrations/
│   │   │   ├── 0001_curriculum_registry.{up,down}.sql
│   │   │   └── 0002_canonical_chunks.{up,down}.sql
│   │   └── seed/curriculum_seed.py     ← seeds from evidence, never hand-typed
│   ├── services/
│   │   ├── curriculum/registry.py      ← availability gate; require_available()
│   │   └── ingestion/
│   │       ├── canonical.py            ← CanonicalChunk, identity, ChunkWriter
│   │       ├── legacy_adapter.py       ← legacy JSONL → canonical
│   │       └── past_paper.py           ← exam papers → one chunk per question
│   ├── scripts/
│   │   ├── audit_corpus.py             ← stdlib only; reproduces the 180
│   │   ├── catalog_sources.py          ← checksums + ingestion route per PDF
│   │   ├── normalise_corpus.py         ← runs the adapters, writes evidence
│   │   ├── check_registry_consistency.py  ← the CI gate
│   │   └── generate_inventory.py       ← regenerates CURRICULUM_INVENTORY.md
│   ├── tests/{unit,integration}/       ← 120 tests
│   ├── evidence/                       ← machine-generated, committed, no source text
│   ├── docs/{CHUNK_SCHEMA,INGESTION_DESIGN,diagrams/}
│   ├── private_source_materials/       ← ⛔ GITIGNORED. 125 MB Pearson copyright
│   │   └── Edexcel Physics/
│   │       ├── textbooks/Edexcel_AS_Physics.pdf      (225 pp, 102 MB, NO text layer)
│   │       └── 2024 May June/
│   │           ├── Question-paper/    wph11..16-01-que-*.pdf
│   │           ├── Mark-scheme/       wph11..16-01-rms-*.pdf
│   │           └── Examiner-report/   wph11..16-01-pef-*.pdf
│   └── *.md                            ← the governing documents
├── lumos-recon.bundle                  ← git bundle: all three commits
├── Lumos_Whitepaper.pdf                ← BCOLBD preliminary submission
├── BLOCKCHAIN OLYMPIAD BANGLADESH AI Guideline.pdf
├── Lumos_ Light the Way to Knowledge.png    ← homepage visual reference
├── Lumos_ A Magical Learning Haven.png
├── Create_transformation_video_*.mp4    ← homepage transition reference
└── Lumos_Prebuild_Pack{, 2}/           ← superseded design packs; data claims are WRONG (ADR-008)
```

Planned but not yet created: `apps/web/` (TanStack Start), `services/models/`
(Model Gateway), `packages/contracts/`.

### 3.3 GitHub

- Repository: `https://github.com/Shahriar290900/Lumos`
- Legacy references, read-only: `Shikhbo-Local-App`, `shikhbo-ai`
- Three commits exist in `lumos-recon.bundle` but have **not been pushed** — the
  previous environment's git proxy refused the remote. Pushing is step one (§4).

Commit conventions: one goal per commit, imperative subject prefixed with the
goal id, a body that says what was measured and what was found, and:

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```

### 3.4 Database

**Docker, `pgvector/pgvector:pg16`** — one command, identical to CI, disposable.

```bash
docker run -d --name lumos-pg \
  -e POSTGRES_USER=lumos -e POSTGRES_HOST_AUTH_METHOD=trust \
  -e POSTGRES_DB=lumos_dev -p 5432:5432 \
  pgvector/pgvector:pg16

export DATABASE_URL=postgresql://lumos@localhost:5432/lumos_dev
export TEST_DATABASE_URL=$DATABASE_URL
```

The test suite creates and drops its own throwaway databases, so
`TEST_DATABASE_URL` must point at a server where `CREATE DATABASE` is permitted.

### 3.5 Credentials

**None are present, and nothing currently needs one.** Everything runs today
with an empty `.env`. When keys arrive they will be routed in by the project
owner — treat them as ordinary environment variables, put them in `.env` only,
and never commit or echo them.

Expected, in rough order of need: the gemma4:e4b endpoint URL + token
(`AI_API_URL`, `AI_API_KEY`), `HF_TOKEN`, then `DATABASE_URL` for Neon,
Cloudflare/R2, Render, Sentry, and an email provider. `CONNECTORS.md` has the
full table with verification commands.

---

## 4. Bootstrap — run this before anything else

```bash
cd ~/Desktop/Lumos

# 1. Restore full git history from the bundle
git clone lumos-recon.bundle lumos-git
cd lumos-git
git log --oneline          # expect: 302ebb4, 0820f80, efd4a18

# 2. Bring across the licensed material (never committed, so not in the bundle)
cp -R ../lumos/private_source_materials ./
git status --short          # must show NOTHING under private_source_materials/

# 3. Enable the guard — do this before your first commit
git config core.hooksPath .githooks
git config --get core.hooksPath        # → .githooks

# 4. Point at GitHub and push the history
git remote add origin https://github.com/Shahriar290900/Lumos.git
git push -u origin main

# 5. Python environment
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt

# 5b. OCR toolchain — needed by LUMOS-004C, not by anything committed so far
brew install tesseract          # the binary; ~100 MB with language data
pip install pypdfium2 pytesseract
# Add pypdfium2/pytesseract to requirements-dev.txt in the 004C commit, and add
# a tesseract install step to the CI test job at the same time.

# 6. Database (see §3.4), then the standard verification gate (§9)
```

Once `lumos-git` verifies green, it becomes the working repository. Rename it to
`lumos` and archive the old folder — do not maintain two copies.

---

## 5. What is already built and verified

Three commits. Do not redo any of this.

### `efd4a18` — Reconnaissance

Audited both legacy repositories at the file level. Key findings, all reproducible:

- **The corpus is 180 records, not the ~1,022 the prebuild pack claimed** (ADR-008).
  Verified three ways, including by the pack's own audit script.
- The ~2.58 GB Edexcel corpus in the whitepaper is absent from both repos.
- `shikhbo-ai/rag.py` already implements the target retrieval design — RRF at
  *k*=60 over FAISS + BM25, BGE-M3, BGE-Reranker-v2-M3, confidence gating. **Port
  it, do not rewrite it.**
- Ten legacy defects with file references (§C.2), including: a shipped `v1.0.0`
  with a বাংলা subject button and no corpus behind it; metadata filtering applied
  *after* a global top-k search; a `', '.join(str)` that corrupted every indexed
  chunk; and a prompt instructing the model never to cite its sources.
- No tests in either repo. No committed secrets in either repo.

### `0820f80` — LUMOS-004A, Curriculum Registry + Coverage Gates

- 7 tables, 1 view, 6 enums; reversible migration `0001`.
- **Availability is one SQL view** (`curriculum_availability`) returning
  `is_available` *and* machine-readable `blocked_reasons` (ADR-013).
  `require_available()` raises rather than returning a flag, so a forgotten `if`
  cannot become an ungrounded answer.
- Seed derives every number from `evidence/*.json`: 9 offerings, 42 source
  documents, 3 corpus snapshots.
- 19 private PDFs catalogued and checksummed; ingestion route determined **per
  document** by probing, not assumed (ADR-015).
- `.githooks/pre-commit` + CI guard for licensed material (ADR-017).

### `302ebb4` — LUMOS-004B, Canonical chunk model + normalisation

- `chunks` (35 columns, 11 CHECK constraints), `normalisation_runs`,
  `chunk_retrieval_context`; migration `0002`.
- **Identity is derived, not assigned** (ADR-018):
  `uuid5(namespace, "lumos:v1:<document sha256>:<locator>")`. Question 12 of
  WPH11 and question 12 of WPH12 cannot collide, and re-running an adapter
  updates rather than duplicates.
- **263 canonical chunks**: 180 `legacy_record` + 83 `exam_question`.
- **Provenance per chunk** (ADR-021): 165 `verbatim`, 83 `cleaned`, 15
  `normalized`. Every non-verbatim chunk keeps `text_raw`; the schema refuses one
  that does not.
- **Three counts, three meanings** (ADR-020): audited / canonical / indexed. Only
  *indexed* can make a subject available — which is why **0 of 9 offerings are
  available**, correctly.

### Verified numbers — treat these as ground truth

| | |
|---|---:|
| Legacy records (ICT / English / Physics) | 120 / 43 / 17 = **180** |
| Canonical chunks | **263** |
| Exam questions parsed, WPH11–16 | **83**, 440 marks |
| — AS demo scope (WPH11/12/13) | **41**, 210 marks |
| Tests passing | **120** |
| ADRs | **21** |
| Private source PDFs | 19, ~125 MB |
| Offerings available | **0 of 9** |
| Bangla-damaged ICT records | 73 of 120 |
| Legacy records with no keywords | 163 of 180 |

### Measured facts that shape everything downstream

- `(Total for Question N = M marks)` is a **100 % reliable** question boundary —
  19/19 in WPH11, no numbering gap in any of the six papers.
- **Zero explicit dependency cross-references** in any AS paper. `depends_on` has
  nothing to extract from; multi-part context comes from keeping a whole question
  in one chunk (ADR-016). LUMOS-016 is *unblocked*, not blocked.
- Examiner reports differ *within one session*: WPH11/13 decode to `(cid:N)` and
  need OCR; WPH12/15 parse; WPH14/16 are mixed.
- **Student Book 1 has no text layer on any of its 225 pages.** Full OCR.
  Tesseract at 250 DPI is good on prose; specification references (`1.3.1` →
  `131`) and equations degrade and need targeted handling.
- Mark schemes carry proper Unicode mathematics and are the **repair source** for
  equations lost to glyph failures in the question papers.

---

## 6. Known gaps and required fixes

**Do these first, as LUMOS-004B.1, in one commit, before starting 004C.** They
are small, and leaving them makes every later goal harder.

### 6.1 `ci.yml` may be missing locally — verify

`.github/workflows/ci.yml` exists in the bundle but could not be written to the
Mac by the previous environment (protected path). After cloning, confirm:

```bash
ls -la .github/workflows/ci.yml   # must exist, ~8 KB
```

If absent, restore it with `git checkout HEAD -- .github/workflows/ci.yml`.

### 6.2 CI has never actually run

Everything is verified locally; no GitHub Actions run has ever executed. The
first push will be the first real run. **Expect it to fail on something
environmental** and fix it — that is part of this work item, not a surprise.

### 6.3 Model policy is not yet reflected in the docs

These forward-looking files still name superseded models and must be updated to
the gemma4:e4b policy in §2.2:

- `.env.example` — `CHAT_MODEL` is blank. Set it to `gemma4:e4b`, document the
  provider mapping (`gemma4:e4b` on Ollama, `google/gemma-4-E4B-it` on HF), and
  state that no other generation model is permitted.
- `CONNECTORS.md` — the development-inference section still offers Qwen as a
  candidate.
- `MIGRATION_MAP.md` — the Models table still lists a Gemini provider as a port
  target. It becomes: **do not port**.
- `BLOCKERS.md` — BLOCK-005 is now partly decided (model chosen, remote hosting
  chosen). Record that; what remains open is the endpoint, the budget ceiling and
  the shutdown procedure.
- `ARCHITECTURE.md` and `CLAUDE.md` — add the model policy explicitly.

**Leave `RECONNAISSANCE_REPORT.md` alone.** It is a dated audit and its model
references are an accurate record of what the legacy system used.

### 6.4 The Model Gateway does not exist

`AI_PROVIDER=mock` is set in tests and CI, and **nothing reads it**. The gateway
(ADR-003) is referenced across the documents but unbuilt: `services/models/`
does not exist. That is honest and expected — but do not assume it is there.
Building it is LUMOS-004D (§7), and it must come before any generation work.

### 6.5 Smaller items

- `scripts/generate_inventory.py --check` compares the whole file; CI compares
  only the catalogue-independent sections. Fine, but the difference is worth a
  comment so nobody "fixes" one to match the other.
- `apps/api/main.py` has a `/tutor/ask` route that passes the coverage gate and
  then returns **501**. That is deliberate — it proves the gate runs before
  retrieval. Do not make it return a fabricated answer.

---

## 7. The goal register and the sequential rule

Full detail is in `GOALS.md`. **Work strictly top to bottom. One at a time.**

| Goal | Status |
|---|---|
| LUMOS-000 Reconnaissance | ✅ `efd4a18` |
| LUMOS-004A Curriculum registry + coverage gates | ✅ `0820f80` |
| LUMOS-004B Canonical chunk schema + legacy normalisation | ✅ `302ebb4` |
| **LUMOS-004B.1 Fixes and model policy** (§6) | ⬅ **do this first** |
| **LUMOS-004C Corpus cleaning and re-chunking** | ⬅ **then this** |
| LUMOS-004D Model Gateway + mock provider + gemma4:e4b | then this |
| LUMOS-004E Retrieval evaluation set (needs teacher review) | |
| LUMOS-008 Hybrid retrieval: pgvector + Postgres FTS + RRF | |
| LUMOS-009 BGE reranking + source-priority policy | |
| LUMOS-010 Tutor API + SSE streaming | |
| LUMOS-011 Citation + confidence validation | |
| LUMOS-005 Auth · LUMOS-006 Neon · LUMOS-012 Dashboard · LUMOS-013 Practice | |
| LUMOS-014–016 Multimodal · LUMOS-017–019 Experience · LUMOS-020–025 Trust & competition | |

**Do not reorder without recording why in `DECISIONS.md`.** The order is not
arbitrary: curriculum truth precedes retrieval, retrieval precedes generation,
generation precedes experience. Building the 3D homepage before the registry
produces a beautiful interface that lies about what it knows.

---

## 8. LUMOS-004C — the next real goal

**Depends on:** 004B (done) and 004B.1 (§6).
**Blocks:** LUMOS-008 — nothing should be indexed before it is clean.

Repair and re-chunk the normalised corpora, and extend ingestion to the source
types the past-paper adapter does not yet cover. `docs/INGESTION_DESIGN.md` §3–5
already describes the mechanics in detail; follow it.

### Acceptance criteria

- [ ] **Bangla repair** for the 73 damaged ICT records — the vowel-sign and
      conjunct corruption (`যযোগাযযোগ` for `যোগাযোগ`). Measure before and after,
      keep a reviewed sample, and record the repair rate. If repair proves
      inadequate, that is BLOCK-009 and the answer is re-extraction from source
      PDFs — say so rather than shipping half-repaired text.
- [ ] **English re-chunking** from ~2,000-token whole units to 400–600 tokens
      with 50-token overlap, split at real section boundaries.
- [ ] Bullet-glyph repair (`e` for `•`) and mid-word truncation repair.
- [ ] **Repaired chunks are `derived`, never `verbatim`**, and keep their original
      text in `text_raw`.
- [ ] **Mark-scheme adapter** with both strategies: terminator-bounded blocks for
      structured questions, and table extraction for the MCQ section the
      terminator does not cover (`Total for question N` appears 9/8/4 times
      against 19/18/4 questions). Capture the "B is incorrect because…"
      distractor explanations — they are teaching content, not table noise.
- [ ] **Examiner-report adapter**, honouring the per-document ingestion route and
      discarding handwritten candidate-script regions (they OCR to noise; the
      "Examiner Comments" prose after them is the valuable part).
- [ ] **Textbook OCR path**, 225 pages, with per-page confidence recorded and
      `ocr_uncertain` set where confidence is low. Re-OCR the
      specification-reference region at higher DPI with a digit allowlist.
      Render with `pypdfium2` at 250 DPI and OCR with Tesseract — the combination
      was measured during reconnaissance and produces good prose. Page-by-page
      with immediate cleanup if disk is tight (§3.1).
- [ ] **Linking**: question ↔ mark scheme ↔ examiner report by
      `(paper_code, question_number)`; textbook section ↔ specification reference.
      The columns exist; the linking pass does not.
- [ ] Every cleaning rule is a **separate, reversible stage with its own test**.
- [ ] Provenance survives: every derived chunk traces to its source page.
- [ ] Counts reconcile after re-chunking, with the change **explained** in the run
      report — re-chunking legitimately changes counts, so the reconciliation
      must compare against the new expected value, not silently pass.
- [ ] `scripts/check_registry_consistency.py` extended to cover the new invariants.
- [ ] Full suite green; migration up from empty and down; no source text in any
      committed file.

### Security and performance notes

Retrieved and extracted text is **untrusted input**. Strip instruction-like
patterns at ingest; no chunk may ever alter system instructions. OCR of 225 pages
is a batch job — never on the request path, and mind the disk (§3.1).

---

## 9. The standard verification gate

Run this before claiming any goal complete. Every step must pass.

```bash
# 0. clean database
docker rm -f lumos-pg 2>/dev/null; docker run -d --name lumos-pg \
  -e POSTGRES_USER=lumos -e POSTGRES_HOST_AUTH_METHOD=trust \
  -e POSTGRES_DB=lumos_dev -p 5432:5432 pgvector/pgvector:pg16
sleep 5
export DATABASE_URL=postgresql://lumos@localhost:5432/lumos_dev
export TEST_DATABASE_URL=$DATABASE_URL AI_PROVIDER=mock

# 1. the corpus audit still reproduces the committed evidence
git clone --depth 1 https://github.com/Shahriar290900/Shikhbo-Local-App /tmp/legacy
python scripts/audit_corpus.py /tmp/legacy/raw_data --quiet    # → 180 records

# 2. schema from empty
python packages/db/migrate.py up

# 3. seed from evidence
python packages/db/seed/curriculum_seed.py

# 4. normalise
python scripts/normalise_corpus.py legacy --corpus-root /tmp/legacy/raw_data \
    --output evidence/legacy_normalisation.json
python scripts/normalise_corpus.py papers \
    --sources-root private_source_materials \
    --output evidence/past_paper_structure.json

# 5. idempotency — a second run must write NOTHING
python scripts/normalise_corpus.py legacy --corpus-root /tmp/legacy/raw_data
# expect: created=0 updated=0 unchanged=180

# 6. registry agrees with its evidence
python scripts/check_registry_consistency.py

# 7. generated inventory is current
python scripts/generate_inventory.py --output CURRICULUM_INVENTORY.md
python scripts/generate_inventory.py --check

# 8. tests
pytest

# 9. migration reverses
python packages/db/migrate.py down
python packages/db/migrate.py down --to 0000
python packages/db/migrate.py status
```

Then the git safety check, every time, before committing:

```bash
git config --get core.hooksPath                       # → .githooks
git ls-files | grep -E 'private_source_materials|\.pdf$' | grep -v '^docs/'   # → empty
git add -A --dry-run | grep -iE 'private_source|\.pdf|\.bundle'               # → empty
```

---

## 10. The operating loop

1. Read `STATE.md`, `GOALS.md`, `BLOCKERS.md`.
2. Select **exactly one** unblocked goal — the topmost incomplete one.
3. Inspect the existing code before writing new code. **Prefer extending existing
   abstractions over introducing parallel systems.**
4. Plan the smallest coherent slice.
5. Implement.
6. Run the §9 gate.
7. Review your own diff as architect, QA, security, UX and performance engineer.
8. Fix every actionable defect inside the goal.
9. Re-run the gate.
10. Update `STATE.md`, `GOALS.md` (with evidence), `DECISIONS.md` (if a decision
    was made), and any document the change made wrong.
11. Commit — one goal, one atomic commit.
12. Report: files changed, migrations added, schema entities created, results,
    counts before/after, tests run, unresolved blockers, commit hash.
13. **Stop.** Confirm before starting the next goal.

### Failure behaviour

| Situation | Do |
|---|---|
| A service is unavailable | Say so. Never fake success. |
| A secret is missing | Record it in `BLOCKERS.md` and stop that thread. |
| A provider is unavailable | Use the mock. Never substitute another generation model. |
| Tests fail | The goal is **not** complete. |
| Architecture becomes inconsistent | Stop work in that area; update `ARCHITECTURE.md` and `DECISIONS.md`. |
| You find a defect outside the current goal | Record it. Fix it only if it blocks you. |

---

## 11. Things not to do

- Do not start the next goal before the current one is finished and reported.
- Do not use any generation model other than gemma4:e4b.
- Do not commit, force-add, or weaken the guards around
  `private_source_materials/`.
- Do not put source text in tests, fixtures, evidence files, README examples or
  commit messages.
- Do not hand-edit `CURRICULUM_INVENTORY.md` — regenerate it.
- Do not relitigate the 21 ADRs without a concrete implementation conflict.
- Do not add Elasticsearch, Pinecone, Weaviate or a separate BM25 service.
  Postgres + pgvector, until evaluation evidence says otherwise (ADR-001).
- Do not let a subject become available on anything but real indexed chunks and
  a passing evaluation.
- Do not present a design as an implementation. If it is not built and tested,
  `STATE.md` says so.

---

## 12. Competition context

BCOLBD 2026 final round, scored /100:

| Component | Points |
|---|---:|
| Technical documentation + code repository + inference model | 40 (20 documentation, 20 **code quality and reproducibility**) |
| Demo video, max 10 min, English or subtitled | 30 |
| Live presentation, 1-min intro per member | 30 |

The reproducibility half of that first 40 is why this project audits itself,
generates its inventory, and commits machine-readable evidence: an external
evaluator must be able to clone the repository and reproduce every number in it.
It is also why BLOCK-001A matters — the whitepaper describes a corpus the
repository does not contain, and an evaluator can check that in five minutes.

**Demo scope is Edexcel IAL AS Physics only** (WPH11/12/13 + *Student Book 1*).
Other subjects are placeholders that say so.

---

## 13. Start here

1. Run the bootstrap (§4) and confirm three commits, the hook, and a green §9
   gate against the current state.
2. Report what you found — especially anything that disagrees with §5.
3. Do **LUMOS-004B.1** (§6): the fixes and the model policy. Commit.
4. Then, and only then, begin **LUMOS-004C** (§8).

If anything in this document contradicts the repository, the repository wins —
tell me about the contradiction rather than working around it.
