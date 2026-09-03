# Canonical Lumos Chunk Schema

Legacy records are normalised into this representation before indexing. **No legacy record satisfies it today** — all 180 are missing every field beyond the common set, quantified under `canonical_schema_gaps` in `evidence/curriculum_audit_local.json`.

## Fields

### Identity and lineage
| Field | Type | Notes |
|---|---|---|
| `id` | uuid | Lumos-assigned |
| `legacy_chunk_id` | text | Preserved from the source, e.g. `SSC-ICT-C1-P1-CH1`. The legacy scheme encodes curriculum/subject/chapter/page/index and is worth keeping. |
| `source_document_id` | uuid | → `source_documents` |
| `provenance_hash` | text | SHA-256 of the original text. **The deduplication key** — 137 legacy records exist identically in two repositories. |
| `ingestion_version` | text | Which pipeline version produced this chunk |
| `created_at` / `updated_at` | timestamptz | |

### Curriculum identity
| Field | Type | Notes |
|---|---|---|
| `curriculum_id` | uuid | → `curricula` (NCTB, Edexcel IAL, …) |
| `syllabus_version_id` | uuid | → `syllabus_versions`. Spec drift is a stated risk; retrieval filters on this. |
| `subject_id` | uuid | → `subjects` |
| `level` | text | SSC, HSC, A-level |
| `language` | text | `bn` \| `en`. Absent from legacy files; injected at ingest. |
| `chapter_or_unit` | text | Reconciles the legacy `chapter_title` / `chapter_name` split (80/100 records) |
| `topic_id` / `topic_name` | uuid / text | |
| `syllabus_reference` | text | e.g. `5.6.154`. Present on 17 Physics records only. |

### Source and priority
| Field | Type | Notes |
|---|---|---|
| `source_type` | enum | `syllabus` \| `mark_scheme` \| `examiner_report` \| `textbook` \| `revision_guide` \| `topic_notes` \| `lab_guide` |
| `source_priority` | int | 1 official · 2 core textbook · 3 supplementary. Carried through fusion and reranking as a feature (ADR-009). |
| `source_uri` / `storage_key` | text | R2 key or origin URI |
| `page_number` | int | Populated on all 180 legacy records |
| `licence_status` | text | → licence registry. **No legacy source has one** (BLOCK-008). |

### Question structure — for past papers
| Field | Type | Notes |
|---|---|---|
| `question_number` | text | |
| `sub_question` | text | `(a)`, `(c)(ii)` |
| `marks` | int | |
| `parent_question_id` | uuid | |
| `depends_on` | uuid[] | Extracted from cross-references such as "using your answer from part (a)" |
| `mark_scheme_id` | uuid | |
| `examiner_report_id` | uuid | |

**No legacy record carries any of these.** A key-space scan across all 180 records found no field matching `*mark*` or `*question*`. Multi-part support (LUMOS-016) has no data to build against until BLOCK-001 is resolved.

### Content and retrieval
| Field | Type | Notes |
|---|---|---|
| `text` | text | Cleaned, canonical |
| `original_text` | text | Pre-cleaning, retained so provenance survives repair |
| `token_count` | int | **Recomputed with the real tokeniser.** Legacy values disagree with word counts on 134 of 180 records — do not trust them. |
| `quality_score` | float | From the cleaning pipeline: OCR damage, truncation, boundary quality |
| `keywords` | text[] | Empty in 163 of 180 legacy records |
| `prerequisite_ids` | uuid[] | Legacy has free-text prerequisites on every record — normalise, don't invent |
| `embedding` | vector(1024) | BGE-M3 |
| `search_document` | tsvector | Postgres FTS; Bangla needs a custom configuration built from the legacy tokeniser and stopword list |

## Chunking policy

| Document type | Unit | Target size |
|---|---|---|
| Question paper | one complete main question, all parts | whole question |
| Mark scheme | one main question, mirroring the paper | whole question |
| Textbook | section heading | 400–600 tokens, 50-token overlap |
| Revision guide / topic notes | topic | 200–400 tokens |

Legacy English chunks are ~2,000 tokens — whole textbook units — and **must be re-chunked** before use. ICT (~450 tokens) and Physics (~400 tokens) are closer to target.

## Purpose

RRF must be able to fuse lexical and semantic results without losing curriculum identity or source lineage, and every citation must be traceable to a page in a licensed document. Every field above serves one of those two ends.
