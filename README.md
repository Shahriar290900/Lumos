# Lumos

**Lights the way to knowledge.**

Lumos is a curriculum-grounded AI educational assistant for Bangladeshi students — evidence-linked tutoring constrained by a student's declared curriculum, subject, level and syllabus version, in Bangla and English.

Successor to [Shikhbo-Local-App](https://github.com/Shahriar290900/Shikhbo-Local-App) and [shikhbo-ai](https://github.com/Shahriar290900/shikhbo-ai). BCOLBD 2026, Artificial Intelligence category.

---

## Status

**Phase 0.5.** The curriculum registry and the canonical chunk model are built, tested and populated: **263 canonical chunks** — 180 normalised legacy records and 83 exam questions from the 2024 May/June Edexcel IAL Physics papers. Nothing is embedded or lexically indexed yet, so **nothing is retrievable, nothing is available, and the API refuses every subject** — the correct state, not a defect.

- Start with [`RECONNAISSANCE_REPORT.md`](RECONNAISSANCE_REPORT.md) for the audit of the two legacy systems.
- [`CURRICULUM_INVENTORY.md`](CURRICULUM_INVENTORY.md) is generated from the registry and says exactly what exists.
- [`docs/CHUNK_SCHEMA.md`](docs/CHUNK_SCHEMA.md) describes the canonical model everything normalises into.
- **Next goal:** LUMOS-004C — corpus cleaning and re-chunking.

## What the registry knows

| Offering | Sources | Audited | Canonical | Indexed | Status |
|---|---:|---:|---:|---:|---|
| Edexcel IAL Physics — International AS | 10 | — | 41 | 0 | in preparation (**demo scope**) |
| Edexcel IAL Physics — A2 | 10 | 17 | 59 | 0 | held, not published |
| NCTB ICT — SSC | 6 | 120 | 120 | 0 | in preparation |
| NCTB English — SSC | 16 | 43 | 43 | 0 | in preparation |
| NCTB Physics / Chemistry / Biology / Mathematics / Bangla — SSC | 0 | 0 | 0 | 0 | planned — no corpus |

Three counts, three meanings (ADR-014, ADR-020). **Audited** is what an auditor found in the source material; **canonical** is what normalisation produced; **indexed** is what is embedded and searchable. Only the last one can make a subject available.

The demo corpus is Edexcel IAL **AS** Physics: units WPH11/12/13 for 2024 May/June — question papers, mark schemes and examiner reports — plus *Student Book 1*, whose Topics 1–4 cover the same AS content. 41 main questions, 210 marks. Those source PDFs are licensed and are never committed.

Reproduce the corpus audit with no dependencies at all:

```bash
git clone https://github.com/Shahriar290900/Shikhbo-Local-App
python scripts/audit_corpus.py Shikhbo-Local-App/raw_data     # → 180 records
```

## Running it

```bash
pip install -r requirements-dev.txt
export DATABASE_URL=postgresql://...        # PostgreSQL 16 + pgvector

python packages/db/migrate.py up
python packages/db/seed/curriculum_seed.py

# normalise the legacy corpora into canonical chunks (deterministic, idempotent)
git clone https://github.com/Shahriar290900/Shikhbo-Local-App /tmp/legacy
python scripts/normalise_corpus.py legacy --corpus-root /tmp/legacy/raw_data

python scripts/check_registry_consistency.py
pytest                                       # 120 tests, no credentials, no GPU

uvicorn apps.api.main:app --reload
curl localhost:8000/curriculum
```

The whole suite runs with an empty `.env` and `AI_PROVIDER=mock`. If a test ever needs a GPU or an API key, that test is wrong.

**Before your first commit:** `git config core.hooksPath .githooks` — the hook refuses licensed source material, PDFs outside `docs/`, files over 10 MB, and credential patterns.

## Architecture

```
Cloudflare edge
   └── TanStack Start (React · TypeScript · Tailwind · Motion · R3F)
         └── FastAPI ──► Model Gateway ──► HF / Render GPU / mock / Ollama
               ├── Curriculum Registry
               ├── RAG Orchestrator   hybrid retrieval → RRF → source priority
               │                      → BGE rerank → citation validation
               └── Ingestion Worker
                     └── Neon PostgreSQL 16 + pgvector + FTS
                     └── Cloudflare R2
```

Details in [`ARCHITECTURE.md`](ARCHITECTURE.md); decisions and their reasons in [`DECISIONS.md`](DECISIONS.md).

## Documents

| File | What it is |
|---|---|
| [`RECONNAISSANCE_REPORT.md`](RECONNAISSANCE_REPORT.md) | The full audit — start here |
| [`BLOCKERS.md`](BLOCKERS.md) | Decisions and provisioning needed from a human |
| [`GOALS.md`](GOALS.md) | Goal register with acceptance criteria |
| [`STATE.md`](STATE.md) | Where the project actually is |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | Target architecture and rules |
| [`DECISIONS.md`](DECISIONS.md) | ADRs |
| [`MIGRATION_MAP.md`](MIGRATION_MAP.md) | What is ported, lifted, rebuilt, retired |
| [`CURRICULUM_INVENTORY.md`](CURRICULUM_INVENTORY.md) | **Generated** from the registry — what exists, per offering |
| [`docs/INGESTION_DESIGN.md`](docs/INGESTION_DESIGN.md) | How the Edexcel sources are actually structured, and how to ingest them |
| [`COVERAGE_MATRIX.md`](COVERAGE_MATRIX.md) | What is available, and the gates |
| [`CHUNKED_DATA_AUDIT.md`](CHUNKED_DATA_AUDIT.md) | Corpus quality findings |
| [`TEST_MATRIX.md`](TEST_MATRIX.md) | What must be tested |
| [`CONNECTORS.md`](CONNECTORS.md) | External services and their status |
| [`CLAUDE.md`](CLAUDE.md) | Engineering operating contract |
| `evidence/` | Machine-readable audit output |
| `scripts/audit_corpus.py` | Corpus auditor — stdlib only, reproducible |
| `scripts/catalog_sources.py` | Checksums and routes private source PDFs; emits metadata only |
| `scripts/normalise_corpus.py` | Runs the normalisation adapters; writes metadata-only reports |
| `scripts/check_registry_consistency.py` | CI gate: the registry must agree with its evidence |
| `packages/db/` · `services/curriculum/` · `services/ingestion/` · `apps/api/` | Migrations, registry logic, normalisation adapters, API |

## Principles

1. Never confuse UI availability with curriculum availability.
2. Never fabricate curriculum data.
3. Every citation resolves to a chunk that was actually retrieved.
4. Insufficient evidence produces a stated limitation, not an invented answer.
5. Model providers are replaceable and never reach the browser.
6. No secrets are committed, and none has a default.
7. A goal is complete when its acceptance criteria are met and the evidence is recorded — not when the build passes.
