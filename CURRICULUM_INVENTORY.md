# Lumos Curriculum Inventory

> **Generated file — do not edit by hand.**
> `DATABASE_URL=... python scripts/generate_inventory.py --output CURRICULUM_INVENTORY.md`
>
> Every number here is read from the curriculum registry and from the corpus
> auditor's evidence files. The prebuild pack's inventory stated 1,022 records
> against an actual 180 because it was prose nobody re-derived (ADR-008). CI
> re-runs `scripts/check_registry_consistency.py` so the two cannot drift again.

Generated: 2026-09-04

## Offerings and availability

| Offering | Curriculum | Subject | Level | Status | Sources | Canonical | Indexed | Available |
|---|---|---|---|---|---:|---:|---:|---|
| `edexcel-ial/physics/international-as` | EDEXCEL_IAL | Physics | International AS | in preparation | 10 | 41 | 0 | no |
| `edexcel-ial/physics/a2` | EDEXCEL_IAL | Physics | International A2 | planned — no corpus | 10 | 59 | 0 | no |
| `nctb/bangla/ssc` | NCTB | Bangla | Secondary School Certificate | planned — no corpus | 0 | 0 | 0 | no |
| `nctb/biology/ssc` | NCTB | Biology | Secondary School Certificate | planned — no corpus | 0 | 0 | 0 | no |
| `nctb/chemistry/ssc` | NCTB | Chemistry | Secondary School Certificate | planned — no corpus | 0 | 0 | 0 | no |
| `nctb/english/ssc` | NCTB | English | Secondary School Certificate | in preparation | 16 | 109 | 0 | no |
| `nctb/ict/ssc` | NCTB | ICT | Secondary School Certificate | in preparation | 6 | 164 | 0 | no |
| `nctb/mathematics/ssc` | NCTB | Mathematics | Secondary School Certificate | planned — no corpus | 0 | 0 | 0 | no |
| `nctb/physics/ssc` | NCTB | Physics | Secondary School Certificate | planned — no corpus | 0 | 0 | 0 | no |

Three counts, three different things (ADR-014, ADR-020): **audited** is what an auditor found in the source material, **canonical** is what normalisation produced, **indexed** is what is embedded and lexically searchable. Only the last one can make a subject available.

**No offering is currently available.** Nothing has been ingested, so nothing may be queried. The API refuses every offering above before retrieval runs.

### Why each offering is unavailable

| Offering | Blocked by |
|---|---|
| `edexcel-ial/physics/international-as` | publication_status=in_preparation, indexing_status=sources_catalogued, evaluation_status=none, no_indexed_chunks |
| `edexcel-ial/physics/a2` | publication_status=planned, indexing_status=sources_catalogued, evaluation_status=none, no_indexed_chunks |
| `nctb/bangla/ssc` | publication_status=planned, indexing_status=not_started, evaluation_status=none, no_indexed_chunks, licence_status=unknown, no_source_documents |
| `nctb/biology/ssc` | publication_status=planned, indexing_status=not_started, evaluation_status=none, no_indexed_chunks, licence_status=unknown, no_source_documents |
| `nctb/chemistry/ssc` | publication_status=planned, indexing_status=not_started, evaluation_status=none, no_indexed_chunks, licence_status=unknown, no_source_documents |
| `nctb/english/ssc` | publication_status=in_preparation, indexing_status=normalising, evaluation_status=none, no_indexed_chunks, licence_status=unknown |
| `nctb/ict/ssc` | publication_status=in_preparation, indexing_status=normalising, evaluation_status=none, no_indexed_chunks, licence_status=unknown |
| `nctb/mathematics/ssc` | publication_status=planned, indexing_status=not_started, evaluation_status=none, no_indexed_chunks, licence_status=unknown, no_source_documents |
| `nctb/physics/ssc` | publication_status=planned, indexing_status=not_started, evaluation_status=none, no_indexed_chunks, licence_status=unknown, no_source_documents |

## Audited legacy corpus

`scripts/audit_corpus.py` over `23` JSONL files: **180 records**, 180 unique content blocks, 0 parse errors.

| Subject | Files | Records | Class | Median content | Bangla records | Registered to |
|---|---:|---:|---|---:|---:|---|
| English | 16 | **43** | SSC | 7900 chars | 0 | `nctb/english/ssc` |
| ICT | 6 | **120** | SSC | 1766 chars | 120 | `nctb/ict/ssc` |
| Physics | 1 | **17** | A-level | 1560 chars | 0 | `edexcel-ial/physics/a2` |
| **Total** | **23** | **180** | | | | |

Registry snapshots, each carrying the method and evidence file it came from:

| Offering | Records | Method | Evidence |
|---|---:|---|---|
| `edexcel-ial/physics/a2` | 17 | `scripts/audit_corpus.py` | `evidence/curriculum_audit_local.json` |
| `nctb/english/ssc` | 43 | `scripts/audit_corpus.py` | `evidence/curriculum_audit_local.json` |
| `nctb/ict/ssc` | 120 | `scripts/audit_corpus.py` | `evidence/curriculum_audit_local.json` |

These are **audited** counts of legacy source records, not indexed chunks. `indexed_chunk_count` stays 0 until the records are normalised, cleaned, re-chunked and written to the store — which is why no offering is available.

## Canonical chunks

| Offering | Chunk type | Extraction | Provenance | Count | Median tokens |
|---|---|---|---|---:|---:|
| `edexcel-ial/physics/a2` | exam_question | pdf_text_layer | cleaned | 42 | 127 |
| `edexcel-ial/physics/a2` | legacy_record | structured_jsonl | verbatim | 17 | 278 |
| `edexcel-ial/physics/international-as` | exam_question | pdf_text_layer | cleaned | 41 | 133 |
| `nctb/english/ssc` | legacy_record | structured_jsonl | derived | 104 | 499 |
| `nctb/english/ssc` | legacy_record | structured_jsonl | verbatim | 5 | 308 |
| `nctb/ict/ssc` | legacy_record | structured_jsonl | derived | 164 | 447 |

**373 canonical chunks total.** Provenance is recorded per chunk, not per corpus: `verbatim` means the stored text is exactly what extraction produced, `cleaned` means layout furniture was removed, `normalized` means Unicode normalisation changed something. Anything other than verbatim keeps its untransformed text.

### Normalisation runs

| Offering | Adapter | Version | Documents | Source records |
|---|---|---|---:|---:|
| `edexcel-ial/physics/a2` | legacy_corpus | 004c.1 | 1 | 17 |
| `edexcel-ial/physics/a2` | past_paper | 004c.1 | 3 | 42 |
| `edexcel-ial/physics/international-as` | past_paper | 004c.1 | 3 | 41 |
| `nctb/english/ssc` | legacy_corpus | 004c.1 | 1 | 43 |
| `nctb/ict/ssc` | legacy_corpus | 004c.1 | 1 | 120 |

The most recent normalisation batch per adapter, summed across the documents in that batch.

Per-run `created` / `updated` / `unchanged` counts are deliberately **not** here. They describe what one run did, not what the corpus is, so the same corpus renders differently depending on whether the database was fresh — which would make this file report itself stale after a re-run that changed nothing. Those counts live in `evidence/*.json` and in the `normalisation_runs` table, where run history belongs. Idempotency is asserted by the test suite and by CI, not by a number in a document.

## Registered source documents

19 licensed PDFs (125 MB) catalogued by `scripts/catalog_sources.py`. The files themselves are private and are never committed; only their metadata appears here.

| Offering | Type | Priority | Count | Pages | Ingestion route |
|---|---|---:|---:|---:|---|
| `edexcel-ial/physics/a2` | examiner_report | 1 | 2 | 121 | mixed |
| `edexcel-ial/physics/a2` | examiner_report | 1 | 1 | 49 | text |
| `edexcel-ial/physics/a2` | mark_scheme | 1 | 3 | 48 | text |
| `edexcel-ial/physics/a2` | past_paper | 1 | 3 | 88 | text |
| `edexcel-ial/physics/a2` | legacy_corpus | 2 | 1 | — | structured |
| `edexcel-ial/physics/international-as` | examiner_report | 1 | 2 | 84 | ocr_required |
| `edexcel-ial/physics/international-as` | examiner_report | 1 | 1 | 82 | text |
| `edexcel-ial/physics/international-as` | mark_scheme | 1 | 3 | 45 | text |
| `edexcel-ial/physics/international-as` | past_paper | 1 | 3 | 76 | text |
| `edexcel-ial/physics/international-as` | textbook | 2 | 1 | 225 | ocr_required |
| `nctb/english/ssc` | legacy_corpus | 2 | 16 | — | structured |
| `nctb/ict/ssc` | legacy_corpus | 2 | 6 | — | structured |

Priority 1 is official examination material, 2 core textbook, 3 supplementary (ADR-009). The ingestion route is recorded per document, not per corpus: within one session some examiner reports carry a usable text layer and others decode to `(cid:N)` glyphs and need OCR.

## Legacy corpus quality

| Finding | Records affected |
|---|---:|
| Bangla vowel-sign / conjunct corruption | 73 / 180 |
| Word broken across a line break | 66 / 180 |
| Missing canonical schema fields | up to 180 / 180 |

No corpus is published until these are repaired and an evaluation passes (LUMOS-004C, LUMOS-004E).

## Not present

- **Bangla** (NCTB SSC) — Coming soon — no Bangla language corpus has been ingested yet.
- **Biology** (NCTB SSC) — Coming soon — no Biology corpus has been ingested yet.
- **Chemistry** (NCTB SSC) — Coming soon — no Chemistry corpus has been ingested yet.
- **Mathematics** (NCTB SSC) — Coming soon — no Mathematics corpus has been ingested yet.
- **Physics** (NCTB SSC) — Coming soon — no NCTB Physics corpus has been ingested yet.

Registered as known-but-unavailable so the interface can explain rather than omit, and so a request naming one is refused by the registry rather than falling through to an ungrounded answer (ADR-011).

Also absent, in every subject: past papers, mark schemes and examiner reports for any NCTB curriculum. The ~2.58 GB Edexcel corpus described in the whitepaper remains unlocated — see BLOCK-001A in `BLOCKERS.md`.
