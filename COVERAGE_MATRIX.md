# Lumos Coverage Matrix

Derived from `CURRICULUM_INVENTORY.md`. Verified 2026-09-04.
Once LUMOS-004A lands, this file is generated from the curriculum registry.

## Verified coverage

| Subject | Corpus | Board / curriculum | Level | Records | Status | MVP? |
|---|---|---|---|---:|---|---|
| ICT | Chapters 1–6 | NCTB (Bangla textbook) | SSC | 120 | Legacy corpus present, **not production-ready** | Yes — migration candidate |
| English | Units 1–16, *English For Today* | NCTB | SSC | 43 | Legacy corpus present, **must be re-chunked** | Yes — migration candidate |
| Physics | Astrophysics & Cosmology, spec 5.6 | Pearson Edexcel IAL | A-level | 17 | **Partial — one specification area only** | Yes — targeted demo / evaluation |
| Bangla | none | — | — | 0 | **UI-advertised, no corpus** | No — remove or gate |
| Chemistry | none | — | — | 0 | Not available | Future ingestion |
| Biology | none | — | — | 0 | Not available | Future ingestion |
| Mathematics | none | — | — | 0 | Not available | Future ingestion |
| NCTB Physics | none | — | — | 0 | Not available | Future ingestion |
| Past papers / mark schemes / examiner reports | none | — | — | 0 | **Not available in any subject** | See BLOCK-001 |

**No corpus is currently `published`.** All three present corpora require normalisation, cleaning, re-chunking and evaluation before a student may be told a subject is supported.

## Readiness gates per corpus

| Gate | ICT | English | Physics 5.6 |
|---|---|---|---|
| Records present | ✅ 120 | ✅ 43 | ✅ 17 |
| Parses cleanly | ✅ | ✅ | ✅ |
| Canonical schema | ❌ | ❌ | ❌ |
| Deduplicated | ❌ (137 cross-repo dupes) | ✅ | ❌ (duplicated in both repos) |
| OCR quality acceptable | ❌ 73 damaged records | ⚠️ bullet/truncation artefacts | ⚠️ mid-word truncation |
| Chunk size appropriate | ⚠️ ~1,800 chars | ❌ ~7,900 chars | ✅ ~1,560 chars |
| Keywords populated | ❌ backfilled at ingest only | ❌ empty | ✅ |
| Syllabus references | ❌ none | ❌ none | ✅ `spec_ref` |
| Source licence recorded | ❌ | ❌ | ❌ |
| Indexed in production | ❌ | ❌ (never indexed by `shikhbo-ai` at all) | ❌ |
| Evaluation set exists | ❌ | ❌ | ❌ |

## Product rule

A subject is `available` **only** when the curriculum registry records all of:

- curriculum / board
- syllabus version
- level / class
- source provenance and licence status
- indexed chunk count > 0
- a passing retrieval evaluation record

A UI tile, a route, a subject button, or a row in this table **never** means a subject is available. The Local app ships a বাংলা subject button with no corpus behind it; that is the failure this rule exists to prevent.

## Known UI/corpus mismatches to fix in the rebuild

| Mismatch | Where | Effect |
|---|---|---|
| `Bangla` subject button, no corpus | `Shikhbo-Local-App/templates/chat.html:53` | Retrieval returns nothing; the model answers ungrounded |
| Class pinned to `SSC`, Physics corpus is `A-level` | Local app `chipClass` | Selecting Physics returns nothing |
| English corpus never indexed | `shikhbo-ai/ingest.py` loads ICT + Astrophysics only | 43 records dead in the cloud deployment |
