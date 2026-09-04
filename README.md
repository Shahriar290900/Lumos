# Lumos

**Lights the way to knowledge.**

Lumos is a curriculum-grounded AI educational assistant for Bangladeshi students — evidence-linked tutoring constrained by a student's declared curriculum, subject, level and syllabus version, in Bangla and English.

Successor to [Shikhbo-Local-App](https://github.com/Shahriar290900/Shikhbo-Local-App) and [shikhbo-ai](https://github.com/Shahriar290900/shikhbo-ai). BCOLBD 2026, Artificial Intelligence category.

---

## Status

**Phase 0.5.** Reconnaissance complete; the curriculum registry is built and tested. No corpus is ingested yet, so **nothing is available and the API refuses every subject** — which is the correct state, not a defect.

- Start with [`RECONNAISSANCE_REPORT.md`](RECONNAISSANCE_REPORT.md) for the audit of the two legacy systems.
- [`CURRICULUM_INVENTORY.md`](CURRICULUM_INVENTORY.md) is generated from the registry and says exactly what exists.
- **Next goal:** LUMOS-004B — canonical chunk schema and legacy normalisation.

## What the registry knows

| Offering | Sources | Audited records | Indexed | Status |
|---|---:|---:|---:|---|
| Edexcel IAL Physics — International AS | 10 | — | 0 | in preparation (**demo scope**) |
| Edexcel IAL Physics — A2 | 10 | 17 | 0 | held, not indexed |
| NCTB ICT — SSC | 6 | 120 | 0 | in preparation |
| NCTB English — SSC | 16 | 43 | 0 | in preparation |
| NCTB Physics / Chemistry / Biology / Mathematics / Bangla — SSC | 0 | 0 | 0 | planned — no corpus |

"Audited records" is what an auditor counted in the source material; "Indexed" is what is actually in the store. Different things, different tables (ADR-014).

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
python scripts/check_registry_consistency.py
pytest                                       # 47 tests, no credentials, no GPU

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
| `scripts/check_registry_consistency.py` | CI gate: the registry must agree with its evidence |
| `packages/db/` · `services/curriculum/` · `apps/api/` | Migrations, registry domain logic, API |

## Principles

1. Never confuse UI availability with curriculum availability.
2. Never fabricate curriculum data.
3. Every citation resolves to a chunk that was actually retrieved.
4. Insufficient evidence produces a stated limitation, not an invented answer.
5. Model providers are replaceable and never reach the browser.
6. No secrets are committed, and none has a default.
7. A goal is complete when its acceptance criteria are met and the evidence is recorded — not when the build passes.
