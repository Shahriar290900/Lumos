# Canonical Lumos Chunk Schema

**Implemented** in `packages/db/migrations/0002_canonical_chunks.up.sql` and
`services/ingestion/canonical.py`. Everything Lumos retrieves is a row in
`chunks`, whatever it came from. Adding a curriculum or a source type means
adding an adapter, never changing this table.

Status: the 180 legacy records and the 83 exam questions from the 2024 May/June
Edexcel IAL Physics papers are normalised into it. Nothing is embedded or
lexically indexed yet, so nothing is retrievable and no subject is available.

---

## Identity

```
id         uuid5(LUMOS_CHUNK_NAMESPACE, chunk_key)
chunk_key  lumos:v<n>:<source document sha256>:<locator>
```

Identity is **derived, not assigned** (ADR-018). Two consequences, both load-bearing:

- **Idempotency.** The same input always produces the same id, so re-running an
  adapter updates in place. A second run over unchanged input writes nothing and
  reports `unchanged`.
- **No collision across documents.** The document's checksum is inside the key,
  so question 12 of WPH11 and question 12 of WPH12 are different chunks. No
  adapter has to remember a paper-code or session convention for this to hold.

Locators by source type:

| Source | Locator | Example key |
|---|---|---|
| Legacy JSONL | `legacy/<original chunk_id>` | `lumos:v1:<sha>:legacy/SSC-ICT-C1-P1-CH1` |
| Exam question | `q/<question number>` | `lumos:v1:<sha>:q/12` |
| Mark scheme | `ms/<question number>` | `lumos:v1:<sha>:ms/12` |
| Examiner commentary | `er/<question number>` | `lumos:v1:<sha>:er/12` |
| Textbook section | `p<page>/<ordinal>` | `lumos:v1:<sha>:p45/3` |

`CHUNK_KEY_VERSION` changes only when the key *format* changes, because that
re-identifies every chunk. `INGESTION_VERSION` (currently `004b.1`) moves
independently and records which pipeline produced the text.

`row_fingerprint` hashes every persisted field, which is how a re-run
distinguishes *unchanged* from *updated* without a field-by-field comparison.

---

## Fields

### Lineage
| Column | Notes |
|---|---|
| `id`, `chunk_key` | derived identity, above |
| `source_document_id` | → `source_documents`; resolves to an exact file by SHA-256 |
| `offering_id` | → `subject_offerings`. **The isolation key**: retrieval filters on this before any ranking, so cross-curriculum contamination is structurally impossible (ADR-006) |
| `content_sha256` | of the stored text; cross-document duplicate detection |
| `row_fingerprint` | of every persisted field; idempotency |
| `ingestion_version` | which pipeline built this |
| `created_at`, `updated_at` | |

Curriculum, subject, level and syllabus version are reached through
`offering_id` rather than copied onto the chunk. One source of truth, nothing to
drift; `chunk_retrieval_context` joins them for retrieval.

### Location
`page_number`, `page_number_end`, `section_ref`, `topic`, `syllabus_reference`.

`section_ref` reconciles the legacy `chapter_title` / `chapter_name` split — 80
records used one, 100 the other, and reading only one is why both legacy apps
displayed `Chapter N: None` for 100 records.

### Exam structure
`question_number`, `sub_question`, `marks`, `sub_parts`, `parent_chunk_id`,
`depends_on`.

`sub_parts` records the detected structure **without splitting the chunk**:
`[{"label": "(b)(i)", "level": 2, "marks": 3}]`. On a whole-question chunk
`sub_question` is NULL, because the chunk is the whole question and claiming a
sub-part identifier would misrepresent what was stored.

`depends_on` is **optional and normally empty** (ADR-016). A scan of all three
audited AS papers for explicit cross-references — "your answer to", "value
calculated in", "use your" — returned zero matches. Ingestion never requires it.

### Content
| Column | Notes |
|---|---|
| `text` | the canonical text |
| `text_raw` | what extraction produced, when the stored text differs. NULL means `text` *is* the raw extraction |
| `language` | `en`, `bn`, or the explicit `unknown`. Derived from the script the text is written in, not from the filename |
| `token_count` | recomputed at normalisation |
| `legacy_token_count` | whatever the source claimed. Recorded, never trusted — it disagreed with any recomputation on 134 of 180 legacy records |
| `keywords`, `prerequisite_text` | as supplied; empty on 163 of 180 legacy records |

### Legacy traceability
`legacy_chunk_id` keeps the identifier the record arrived with.
`legacy_metadata` keeps the **complete original record**, so normalisation stays
reviewable and reversible and no legacy field is lost for want of a column.

### Provenance
| Column | Values |
|---|---|
| `extraction_method` | `pdf_text_layer` · `ocr_tesseract` · `structured_jsonl` · `manual` · `unknown` |
| `provenance_status` | `verbatim` · `cleaned` · `normalized` · `derived` · `ocr_uncertain` |
| `extraction_confidence` | 0–1 where the extractor reports it |

Per chunk, not per corpus (ADR-021). Of the 120 normalised ICT records, 105 are
`verbatim` and 15 are `normalized`, because Unicode normalisation changed only
those 15 — the label reflects what happened to *that* chunk.

The database enforces two rules the model also checks:

- a transformed chunk must keep `text_raw` — a transformation you cannot inspect
  is one you cannot trust;
- only an extractor that can be uncertain may claim `ocr_uncertain`.

---

## Chunk types

`chunk_type` says what a chunk **is**; `source_documents.document_type` says what
document it **came from**. They are not the same axis: an examiner report yields
commentary chunks, a past paper yields question chunks.

| `chunk_type` | Meaning |
|---|---|
| `exam_question` | one complete main question, all sub-parts together |
| `mark_scheme_answer` | the official answer to one question |
| `examiner_commentary` | examiner remarks on one question |
| `textbook_section` | a textbook section |
| `specification_point` | a syllabus point |
| `legacy_record` | a legacy JSONL record, normalised but **not re-chunked** |
| `unknown` | explicit, when the source does not say |

Legacy records are `legacy_record` and not `textbook_section` on purpose: the 43
English records are whole textbook units of roughly 2,000 tokens, and calling
them sections would assert a granularity they do not have. Re-chunking is
LUMOS-004C.

---

## Source types and authority

`document_type` (ADR-019): `specification`, `past_paper`, `mark_scheme`,
`examiner_report`, `textbook`, `revision_guide`, `topic_notes`, `lab_guide`,
`legacy_corpus`, `unknown`.

Mark schemes and examiner reports are never collapsed into a generic document.
They carry different authority and answer different questions: a mark scheme
says what earns the marks, an examiner report says what candidates actually got
wrong.

`source_priority` (1 official · 2 core textbook · 3 supplementary) lives on the
document, not the chunk, and reaches retrieval through
`chunk_retrieval_context`. Ranking logic stays out of chunk identity (ADR-009).

---

## Chunking policy

| Document type | Unit | Target size |
|---|---|---|
| Past paper | one complete main question, all parts | whole question |
| Mark scheme | one main question, mirroring the paper | whole question |
| Examiner report | one question-commentary block | whole block |
| Textbook | section heading | 400–600 tokens, 50-token overlap |
| Revision guide | topic | 200–400 tokens |
| Legacy corpus | as-is, pending re-chunking | — |

**The question boundary rule.** `(Total for Question N = M marks)` terminates
every main question — 19 of 19 in WPH11 — and carries the mark total, so
boundary detection and mark extraction come from one match. The terminator is the
anchor; the opening question number is validation. A gap in the numbering is
reported as a parse failure, not ignored.

**Keeping a question whole is the multi-part mechanism.** The context needed to
explain part (c) is present whenever part (c) is retrieved, by construction
rather than by a dependency graph.

---

## Normalisation runs

Every run records what it processed and produced in `normalisation_runs`:
adapter, ingestion version, source records, created / updated / unchanged,
duplicates, warnings. The same discipline as `corpus_snapshots`, one stage later
— a chunk count in a document always has a run behind it.

---

## What is not here yet

`embedding vector(1024)` and the lexical search document. They belong to
LUMOS-008 and are deliberately absent: canonical content storage is kept
separate from retrieval indexes, so lexical retrieval, vector retrieval, RRF,
reranking and source-priority filtering can all be built without changing this
model.
