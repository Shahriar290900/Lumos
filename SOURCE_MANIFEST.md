# Source Manifest

Verified 2026-09-04. Record counts are from `scripts/audit_corpus.py`.

## `Shikhbo-Local-App/raw_data/` — the authoritative legacy corpus

`https://github.com/Shahriar290900/Shikhbo-Local-App/tree/main/raw_data` @ `b783680`

| File pattern | Files | Records | Subject | Class | Curriculum |
|---|---:|---:|---|---|---|
| `English unit 1.jsonl` … `English unit 16.jsonl` (inconsistent casing/spacing) | 16 | 43 | English | SSC | NCTB |
| `ICT_C1.jsonl` … `ICT_C6.jsonl` | 6 | 120 | ICT | SSC | NCTB |
| `Astrophysics_Cosmology_RAG.jsonl` | 1 | 17 | Physics | A-level | Edexcel IAL (spec 5.6) |
| **Total** | **23** | **180** | | | |

`raw_data/` has one commit in its history (`f49cc6e`) — it has not changed since it was added.

## `shikhbo-ai` repository root — duplicates

`https://github.com/Shahriar290900/shikhbo-ai` @ `64b58c9`

`ICT_C1.jsonl`–`ICT_C6.jsonl` and `Astrophysics_Cosmology_RAG.jsonl` — 7 files, 137 records, **all byte-identical to the files above**. Deduplicate by content hash before ingesting from both roots.

Also present: `Astrophysics_Cosmology_Notes.pdf` (79 KB), chunked at ingest time by `ingest.py::_load_pdf_chunks()` at 1,600 chars / 200 overlap. Deployment-time artifact, not repository state.

## Not present in any repository

No past paper, mark scheme, examiner report or textbook, for any subject or curriculum. No Chemistry, Biology, Mathematics, Bangla or NCTB Physics corpus. No HSC-level content.

The ~2.58 GB Edexcel Physics corpus (2009–Jan 2026) described in `Lumos_Whitepaper.pdf` §1, §4 and §5.2 is **not in either repository**. See BLOCK-001.

## Licensing

**No licence, permission or provenance record exists for any source.** The corpus derives from NCTB textbook material and Pearson Edexcel material. This must be resolved before any corpus is published (BLOCK-008).

## Refreshing this manifest

The repositories are the source of truth. Re-run:

```
python scripts/audit_corpus.py <path>/Shikhbo-Local-App/raw_data <path>/shikhbo-ai \
    --output evidence/curriculum_audit_combined.json
```
