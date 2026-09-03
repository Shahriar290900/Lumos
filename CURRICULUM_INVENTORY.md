# Lumos Curriculum Inventory — Verified Baseline

**Audit date:** 2026-09-04
**Method:** every JSONL file in both repositories parsed record by record.
**Reproduce:** `python scripts/audit_corpus.py <path>/Shikhbo-Local-App/raw_data`
**Machine-readable evidence:** `evidence/curriculum_audit_local.json`, `evidence/curriculum_audit_combined.json`

> **Supersedes the prebuild pack.** The Lumos prebuild pack stated 1,022 records
> (671 English / 253 ICT / 98 Physics). That figure is not supported by the
> repositories. The verified total is **180**. See ADR-008 in `DECISIONS.md`
> and §D.2 of `RECONNAISSANCE_REPORT.md`. The pack's own audit script, run
> unmodified against the real data, returns the corrected numbers below.

Repositories audited:

- `https://github.com/Shahriar290900/Shikhbo-Local-App` @ `b783680`
- `https://github.com/Shahriar290900/shikhbo-ai` @ `64b58c9`

---

## Verified inventory

`Shikhbo-Local-App/raw_data/` — 23 JSONL files, **180 records**, 0 parse errors, 0 duplicate `chunk_id`s.

| Corpus | Files | Records | Class | Curriculum | Median content | Bangla records |
|---|---:|---:|---|---|---:|---:|
| English (*English For Today*, Units 1–16) | 16 | **43** | SSC | NCTB | 7,900 chars | 0 / 43 |
| ICT (Chapters 1–6) | 6 | **120** | SSC | NCTB | 1,767 chars | 120 / 120 |
| Physics (Astrophysics & Cosmology, spec 5.6) | 1 | **17** | A-level | Edexcel IAL | 1,560 chars | 0 / 17 |
| **Total** | **23** | **180** | | | | **120 / 180** |

### English — per unit

| Unit | Records | | Unit | Records |
|---:|---:|---|---:|---:|
| 1 | 2 | | 9 | 2 |
| 2 | 3 | | 10 | 2 |
| 3 | 3 | | 11 | 4 |
| 4 | 2 | | 12 | 3 |
| 5 | 3 | | 13 | 2 |
| 6 | 4 | | 14 | 2 |
| 7 | 4 | | 15 | 2 |
| 8 | 2 | | 16 | 3 |
| | | | **Total** | **43** |

Filenames are inconsistently cased and spaced (`English Unit3.jsonl`, `English unit 1.jsonl`, `English unit10.jsonl`). Normalise at ingest; do not rely on filename parsing.

### ICT — per chapter

| Chapter | Records |
|---:|---:|
| C1 | 12 |
| C2 | 28 |
| C3 | 8 |
| C4 | 7 |
| C5 | 50 |
| C6 | 15 |
| **Total** | **120** |

### Physics

`Astrophysics_Cosmology_RAG.jsonl` — **17 records**, class `A-level`, subject `Physics`, chapter `5.6` ("Astrophysics and Cosmology"), with Edexcel IAL `spec_ref` values (e.g. `5.6.154, 5.6.155`). This is one specification area of revision notes. It is **not** A-level Physics coverage and must never be labelled as such.

### Cross-repository duplication

`shikhbo-ai` carries 7 JSONL files at its repository root (ICT C1–C6 + Astrophysics), **137 records**. All 137 are byte-identical duplicates of files in `Shikhbo-Local-App/raw_data`:

```
combined audit of both roots:
  JSONL files            : 30
  Total records          : 317
  Unique content blocks  : 180      ← the real number
  Duplicate content grps : 137
  Duplicate chunk_ids    : 137
```

Any pipeline that walks both repositories must deduplicate by content hash. The naive union (317) is double-counting.

`shikhbo-ai` also holds `Astrophysics_Cosmology_Notes.pdf` (79 KB), chunked at ingest time by `ingest.py::_load_pdf_chunks()` at 1,600 chars / 200 overlap. Its chunk count is a deployment-time property, not repository state, and is excluded from the totals above.

---

## Not present — must never be shown as available

- Chemistry
- Biology
- Mathematics
- Bangla (**advertised by the Local app's UI; no corpus exists** — see `RECONNAISSANCE_REPORT.md` §C.2.8)
- NCTB Physics
- Complete Edexcel Physics beyond specification area 5.6
- Any HSC-level content
- **Any past paper, mark scheme or examiner report, for any subject**

The last item matters: the Lumos whitepaper describes a ~2.58 GB Edexcel Physics corpus of past papers, mark schemes and examiner reports (2009–Jan 2026) as ingested and Phase 1 implemented. **No such corpus exists in either repository.** See BLOCK-001 in `BLOCKERS.md`.

---

## Observed legacy schema

Not one schema. Common to all 180 records:

```
chunk_id  class  subject  chapter_no  page_no  topic
prerequisite  keywords  token_count  content
```

Divergences:

| Field | Records | Used by |
|---|---:|---|
| `chapter_title` | 80 | ICT C1–C2 |
| `chapter_name` | 100 | English, Physics, ICT C3–C6 |
| `spec_ref` | 17 | Physics only |

`curriculum` and `language` do **not** exist in the files; `shikhbo-ai/ingest.py` injects them at ingest time.

**Missing from all 180 records** — every field the canonical Lumos schema requires beyond the common set: `curriculum`, `curriculum_version`, `language`, `document_type`, `source_id`, `source_priority`, `provenance_hash`, `question_number`, `sub_question`, `marks`, `parent_question_id`, `depends_on`, `ingestion_version`. Quantified under `canonical_schema_gaps` in the evidence JSON.

---

## Data-quality findings

| Finding | Scale |
|---|---|
| Bangla vowel-sign / conjunct corruption (e.g. `যযোগাযযোগ` for `যোগাযোগ`) | 73 of 180 records — 61 % of the Bangla corpus |
| Broken word split across a line break | 66 of 180 |
| Bullet glyph OCR'd as the letter `e` | English records, e.g. `SSC-English-C3-P1-CH1` |
| Content truncated mid-word at chunk boundary | Observed in Physics and English |
| `keywords` empty | **163 of 180** (90.6 %) — only Physics has real keywords |
| `token_count` disagrees with word count by >50 % | 134 of 180 — treat as untrusted, recompute at ingest |
| English chunks ~2,000 tokens (whole textbook units) | All 43 — far above the 400–600 token target |

Positives: all files parse cleanly; all `chunk_id`s unique; the identifier scheme (`SSC-ICT-C1-P1-CH1`, `EDEXCEL-IAL-PHYS-5.6-P1-CH1`) encodes curriculum/subject/chapter/page/index and is worth keeping; `page_no` and `prerequisite` are populated on every record (the latter as free text, needing normalisation to IDs rather than invention).

---

## Production implications

1. Treat the current JSONL as a **legacy snapshot**, never as the production schema.
2. Normalise all three shapes into one canonical schema before indexing (`docs/CHUNK_SCHEMA.md`).
3. Deduplicate by content hash — 137 records exist twice across the two repos.
4. Re-chunk the English corpus. ~2,000-token units are unusable for retrieval and for citation.
5. Repair or re-extract the 73 damaged Bangla records; measure whether repair is mechanically sufficient before committing to it.
6. Preserve provenance and page references through every transformation; keep original text alongside cleaned text.
7. Keep Physics labelled as **Edexcel IAL spec 5.6 only**.
8. Gate subject availability on the curriculum registry, never on the presence of a UI card.
9. Record source licensing before any corpus is enabled for public or commercial use.
10. **This file should become a generated artifact** once the curriculum registry exists (LUMOS-004A), so it cannot drift from reality again.
