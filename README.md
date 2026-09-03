# Lumos

**Lights the way to knowledge.**

Lumos is a curriculum-grounded AI educational assistant for Bangladeshi students — evidence-linked tutoring constrained by a student's declared curriculum, subject, level and syllabus version, in Bangla and English.

Successor to [Shikhbo-Local-App](https://github.com/Shahriar290900/Shikhbo-Local-App) and [shikhbo-ai](https://github.com/Shahriar290900/shikhbo-ai). BCOLBD 2026, Artificial Intelligence category.

---

## Status

**Reconnaissance complete. No product code yet.**

This repository currently contains the audit of the two legacy systems, the corrected curriculum inventory, the target architecture, the migration plan, and the goal register. Start with **[`RECONNAISSANCE_REPORT.md`](RECONNAISSANCE_REPORT.md)**.

**Next goal:** LUMOS-004A — Curriculum Registry + Coverage Gates.

## Verified corpus

| Corpus | Records | Curriculum | Level |
|---|---:|---|---|
| English — *English For Today*, Units 1–16 | 43 | NCTB | SSC |
| ICT — Chapters 1–6 (Bangla) | 120 | NCTB | SSC |
| Physics — Astrophysics & Cosmology, spec 5.6 | 17 | Edexcel IAL | A-level |
| **Total** | **180** | | |

No corpus is published. All three require normalisation, cleaning, re-chunking and evaluation first. Chemistry, Biology, Mathematics, Bangla and past papers are **not present** — see [`COVERAGE_MATRIX.md`](COVERAGE_MATRIX.md).

Reproduce the audit with no dependencies:

```bash
git clone https://github.com/Shahriar290900/Shikhbo-Local-App
python scripts/audit_corpus.py Shikhbo-Local-App/raw_data
```

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
| [`CURRICULUM_INVENTORY.md`](CURRICULUM_INVENTORY.md) | Verified corpus, per file |
| [`COVERAGE_MATRIX.md`](COVERAGE_MATRIX.md) | What is available, and the gates |
| [`CHUNKED_DATA_AUDIT.md`](CHUNKED_DATA_AUDIT.md) | Corpus quality findings |
| [`TEST_MATRIX.md`](TEST_MATRIX.md) | What must be tested |
| [`CONNECTORS.md`](CONNECTORS.md) | External services and their status |
| [`CLAUDE.md`](CLAUDE.md) | Engineering operating contract |
| `evidence/` | Machine-readable audit output |
| `scripts/audit_corpus.py` | The audit tool — stdlib only, reproducible |

## Principles

1. Never confuse UI availability with curriculum availability.
2. Never fabricate curriculum data.
3. Every citation resolves to a chunk that was actually retrieved.
4. Insufficient evidence produces a stated limitation, not an invented answer.
5. Model providers are replaceable and never reach the browser.
6. No secrets are committed, and none has a default.
7. A goal is complete when its acceptance criteria are met and the evidence is recorded — not when the build passes.
