# Chunked Data Audit

**Date:** 2026-09-04
**Tool:** `scripts/audit_corpus.py` (stdlib only — an external evaluator can run it against a fresh clone with no installs)
**Evidence:** `evidence/curriculum_audit_local.json`, `evidence/curriculum_audit_combined.json`

```
python scripts/audit_corpus.py /path/to/Shikhbo-Local-App/raw_data
```

## Result

```
====================================================================
JSONL files            : 23
Total records          : 180
Unique content blocks  : 180
Duplicate content grps : 0
Duplicate chunk_ids    : 0
Parse errors           : 0
--------------------------------------------------------------------
English    files=16  records=43    classes=SSC        content_chars(med)=7900
ICT        files=6   records=120   classes=SSC        content_chars(med)=1766.5
Physics    files=1   records=17    classes=A-level    content_chars(med)=1560
--------------------------------------------------------------------
artefact bangla_duplicated_vowel_sign     records=73
artefact broken_word_split                records=66
====================================================================
```

Both repositories together:

```
JSONL files            : 30
Total records          : 317
Unique content blocks  : 180      ← 137 records are duplicates
Duplicate content grps : 137
Duplicate chunk_ids    : 137
```

## Correction to the prebuild pack

The pack recorded 1,022 records (671 English / 253 ICT / 98 Physics). Verified: **180** (43 / 120 / 17).

Three independent confirmations:

1. `scripts/audit_corpus.py` — 180.
2. The **prebuild pack's own** `scripts/audit_chunked_data.py`, run unmodified against the real `raw_data/`, returns `English: 43`, `ICT: 120`, `Physics: 17`.
3. Byte arithmetic: `English Unit3.jsonl` is 22,370 bytes and contains 21,543 characters of `content` — 96 % of the file, in 3 records of ~7,200 characters. The pack's claim of 50 records for that unit would require roughly 360 KB.

`git log -- raw_data` shows a single commit (`f49cc6e`), so the corpus has not changed since it was first added. The 1,022 figure was never true of these repositories. Recorded as ADR-008 in `DECISIONS.md`.

## Quality findings

| Finding | Records | Severity |
|---|---:|---|
| Bangla vowel-sign / conjunct corruption | 73 / 180 | High — corrupts both the embedding and the lexical index |
| Broken word split across line break | 66 / 180 | Medium |
| `keywords` empty | 163 / 180 | Medium — lexical retrieval loses a signal |
| `token_count` disagrees with word count by >50 % | 134 / 180 | Low — recompute at ingest, do not trust |
| English chunks are whole textbook units (~2,000 tokens) | 43 / 43 | High — unusable granularity for retrieval and citation |
| `chapter_title` vs `chapter_name` schema split | 80 / 100 | Medium — causes `None` chapter labels in both repos' source formatting |
| Missing every canonical Lumos field beyond the common set | 180 / 180 | Expected — this is the migration |
| Content truncated mid-word at chunk boundaries | observed | Medium |

Worked example of the Bangla damage, `SSC-ICT-C1-P1-CH1`:

> তথ্য ও **যযোগাযযোগ** প্রযুক্তি একুশ শতক …

Correct: যোগাযোগ. A student typing the correct spelling may fail to match the chunk that answers their question.

## Verdict

The legacy corpus is **usable as migration input and not usable as a production corpus.**

Required pipeline before any of it is indexed:

```
load → deduplicate (content hash) → normalise to canonical schema
     → clean (Unicode NFC, Bangla repair, bullet/glyph repair, boundary repair)
     → quality-score → re-chunk (400–600 tok textbook, 200–400 tok revision guide)
     → recompute token_count → embed (BGE-M3) → lexical index (Postgres FTS)
     → per-corpus ingestion report → human review → publish in registry
```

No corpus is marked `published` until its ingestion report is reviewed and its evaluation set passes.
