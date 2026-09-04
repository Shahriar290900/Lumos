# Source Manifest

Verified 2026-09-04. Metadata only — no source content appears in this repository.

- Legacy corpora: `scripts/audit_corpus.py` → `evidence/curriculum_audit_local.json`
- Private PDFs: `scripts/catalog_sources.py` → `evidence/source_catalog.json`
- Both are reconciled against the registry by `scripts/check_registry_consistency.py` in CI.

---

## Private source materials — never committed

`private_source_materials/Edexcel Physics/` — **19 PDFs, 125 MB**, licensed Pearson Edexcel material held for private ingestion only.

Protected by three independent controls (ADR-017): `.gitignore`, a `.githooks/pre-commit` hook that refuses the path, any PDF outside `docs/`, and any file over 10 MB, and a CI job that fails if any of those are tracked.

### 2024 May/June session — International AS (demo scope)

Registered to `edexcel-ial/physics/international-as`.

| Unit | Paper code | Question paper | Mark scheme | Examiner report |
|---|---|---|---|---|
| 1 — Mechanics and Materials | WPH11 | 28 pp, text | 18 pp, text | 39 pp, **OCR required** |
| 2 — Waves and Electricity | WPH12 | 28 pp, text | 16 pp, text | 82 pp, text |
| 3 — Practical Skills in Physics I | WPH13 | 20 pp, text | 11 pp, text | 45 pp, **OCR required** |

Measured content: 41 main questions, 210 marks (WPH11 19/80, WPH12 18/80, WPH13 4/50).

### 2024 May/June session — A2 (held, not indexed)

Registered to `edexcel-ial/physics/a2`.

| Unit | Paper code | Question paper | Mark scheme | Examiner report |
|---|---|---|---|---|
| 4 — Further Mechanics, Fields and Particles | WPH14 | 32 pp, text | 18 pp, text | 72 pp, mixed |
| 5 — Thermodynamics, Radiation, Oscillations and Cosmology | WPH15 | 32 pp, text | 18 pp, text | 49 pp, text |
| 6 — Practical Skills in Physics II | WPH16 | 24 pp, text | 12 pp, text | 49 pp, mixed |

### Textbook

`textbooks/Edexcel_AS_Physics.pdf` — *Pearson Edexcel International AS/A Level Physics Student Book 1*, 225 pages, 102 MB, © Pearson Education Limited 2018. **No text layer on any page** — full OCR required. Covers Topics 1–4 (Mechanics, Materials, Waves and the Particle Nature of Light, Electric Circuits) plus Practical Skills, Maths Skills, exam preparation, sample answers, command words, glossary and index. Registered to the International AS offering.

Every SHA-256 checksum is in `evidence/source_catalog.json`. Ingestion routes were determined by probing each file, not assumed from its type (ADR-015).

---

## Legacy corpora — public repositories

### `Shikhbo-Local-App/raw_data/`

`https://github.com/Shahriar290900/Shikhbo-Local-App/tree/main/raw_data` @ `b783680`

| Files | Records | Subject | Class | Curriculum | Registered to |
|---|---:|---|---|---|---|
| `English unit 1.jsonl` … `English unit 16.jsonl` | 43 | English | SSC | NCTB | `nctb/english/ssc` |
| `ICT_C1.jsonl` … `ICT_C6.jsonl` | 120 | ICT | SSC | NCTB | `nctb/ict/ssc` |
| `Astrophysics_Cosmology_RAG.jsonl` | 17 | Physics | A-level | Edexcel IAL 5.6 | `edexcel-ial/physics/a2` |
| **Total** | **180** | | | | |

`raw_data/` has one commit in its history (`f49cc6e`) — unchanged since it was added.

The Astrophysics chunks are registered to the A2 offering because specification area 5.6 (Astrophysics and Cosmology) sits in Unit 5, which is A2 content.

### `shikhbo-ai` repository root — duplicates

`ICT_C1.jsonl`–`ICT_C6.jsonl` and `Astrophysics_Cosmology_RAG.jsonl` — 7 files, 137 records, **all byte-identical** to the files above. Deduplicate by content hash before ingesting from both roots.

Also present: `Astrophysics_Cosmology_Notes.pdf` (79 KB), chunked at ingest time by `ingest.py::_load_pdf_chunks()`. A deployment-time artifact, not repository state.

---

## Not present

No past paper, mark scheme or examiner report for **any NCTB curriculum**. No Chemistry, Biology, Mathematics, Bangla or NCTB Physics corpus. No HSC content.

The ~2.58 GB Edexcel corpus (2009–Jan 2026) described in the whitepaper remains unlocated. See BLOCK-001 (decided) and BLOCK-001A (open).

---

## Licensing

`licence_status` is recorded per offering and per document, and the schema refuses to publish an offering whose licence is `unknown` or `restricted`.

| Material | Status | Meaning |
|---|---|---|
| Pearson Edexcel PDFs | `permitted_private` | Private ingestion only. Not committed, not redistributed, cannot back a public offering. |
| NCTB legacy JSONL | `unknown` | Blocks publication until BLOCK-008 is resolved. |

Derived chunk text is licensed material in another form. It is retrieval context: the tutor returns generated explanations with citations, never reproduced source text, and no page image is served to a student.

---

## Refreshing

```bash
python scripts/audit_corpus.py <path>/Shikhbo-Local-App/raw_data \
    --output evidence/curriculum_audit_local.json --quiet

python scripts/catalog_sources.py private_source_materials \
    --output evidence/source_catalog.json --quiet

DATABASE_URL=... python packages/db/seed/curriculum_seed.py
DATABASE_URL=... python scripts/check_registry_consistency.py
DATABASE_URL=... python scripts/generate_inventory.py --output CURRICULUM_INVENTORY.md
```
