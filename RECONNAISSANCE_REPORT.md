# Lumos — Reconnaissance Report

**Session type:** Reconnaissance only (per the operating contract, §27). No product code was written.
**Date:** 2026-09-04 (Asia/Dhaka)
**Auditor:** Claude (Cowork), acting as principal engineering agent for Lumos
**Repositories inspected:**

- `https://github.com/Shahriar290900/Shikhbo-Local-App` @ `b783680` (8 commits, tag `v1.0.0`)
- `https://github.com/Shahriar290900/shikhbo-ai` @ `64b58c9` (8 commits)
- `https://github.com/Shahriar290900/Lumos` — **empty repository**, no commits

**Local material inspected:** `Lumos_Prebuild_Pack`, `Lumos_Prebuild_Pack 2`, `Lumos_Whitepaper.pdf` (10 pp.), `BLOCKCHAIN OLYMPIAD BANGLADESH AI Guideline.pdf` (6 pp.), homepage start/end imagery, transition video (referenced, not decoded).

---

## Executive summary

The engineering substance in the legacy repositories is **better than the surrounding documentation suggests**, and the curriculum position is **materially worse**. Those are the two headline findings, and they point in opposite directions.

`shikhbo-ai/rag.py` already implements the exact retrieval architecture Lumos specifies — metadata-scoped corpora, dense + sparse retrieval, Reciprocal Rank Fusion at *k*=60, BGE-M3 embeddings, BGE-Reranker-v2-M3 cross-encoding with a confidence gate, and graceful degradation when the reranker fails to load. That is roughly 280 lines of directly reusable design, and it should be ported, not rewritten.

Against that, three documentation claims do not survive contact with the repositories:

| Claim | Source | Verified reality |
|---|---|---|
| ~1,022 curriculum chunks | Prebuild pack (`CURRICULUM_INVENTORY.md`, `CHUNKED_DATA_AUDIT.md`, `CLAUDE.md`) | **180** — a 5.7× overstatement |
| ~2.58 GB Edexcel Physics corpus, 2009–Jan 2026, "ingested", "Phase 1 implemented" | `Lumos_Whitepaper.pdf` §1, §4, §5.2 | **Not present in either repository.** 17 chunks of Astrophysics/Cosmology notes exist; no past papers, no mark schemes, no examiner reports |
| Multi-part question dependency graph, `depends_on`, sub-question parsing, mark-scheme linkage | `Lumos_Whitepaper.pdf` §5.3–§5.7 | **No implementation and no data.** Zero records in either repo carry a question, sub-question, marks, or dependency field |

These are recorded, not silently corrected. `BLOCKERS.md` carries them as decisions the human owner must make, because the whitepaper is a competition submission already filed and the gap between it and the repository is a reproducibility risk under the BCOLBD final-round criteria ("*complete code repository*", "*deployment-ready inference model demonstrating … reproducibility*", 20 points).

**Recommended first implementation goal: LUMOS-004A — Curriculum Registry + Coverage Gates.** Rationale in §M.

---

## A. Architecture comparison

### A.1 `Shikhbo-Local-App` — offline desktop tutor

```
pywebview window
  └── Flask (app.py, 16 KB)
        ├── scripts/pipeline/pipeline.py     orchestration, 5-turn memory
        ├── scripts/pipeline/retriever.py    LangChain FAISS + BM25 + RRF
        ├── scripts/pipeline/generator.py    Ollama streaming (qwen3.5:0.8b)
        ├── scripts/utils/prompts.py         4 tutoring modes, bilingual
        ├── scripts/utils/context_builder.py context assembly
        ├── scripts/db/sqlite_db.py          local chat history
        └── scripts/voice/{stt,tts}.py       faster-whisper + Piper
  └── raw_data/*.jsonl                       23 files, 180 records
  └── PyInstaller → .dmg / .exe (GitHub Actions, tag-triggered)
```

Everything runs on the user's machine. Embeddings and generation both go to a local Ollama at `127.0.0.1:11434`. There is no network dependency after model pull — a genuine strength for the "institution-owned hardware / unreliable connectivity" deployment target the whitepaper describes in §5.11, and worth preserving as a separate target rather than discarding.

### A.2 `shikhbo-ai` — cloud, three tiers

```
Browser
  └── Flask web app (web/app.py, Render)          sessions, auth, OTP, Google OAuth
        ├── Neon PostgreSQL (web/scripts/init_db.sql)
        ├── web/scripts/hf_client.py    ──►  HF Space (FastAPI, T4 GPU)
        │                                      ├── app.py   /chat /vision /health
        │                                      ├── rag.py   FAISS+BM25+RRF+reranker
        │                                      └── ingest.py bge-m3, per-corpus indices
        └── web/scripts/gemini_client.py ──►  Gemini API (gemma-4-31b-it) — fallback
  └── desktop/ (Electron)   android/ (Capacitor)  — thin shells over the web app
```

The inference tier is already **FastAPI**, which is the Lumos target. The user-facing tier is Flask + Jinja + vanilla JS, which is not. The two-tier routing (Space primary, Gemini fallback on 503/timeout) is a working, deliberate availability pattern and is the closest thing in either repo to the Model Gateway that ADR-003 requires — but it is hand-rolled inside a Flask blueprint rather than an abstraction.

### A.3 Lumos target vs. legacy — the actual deltas

| Concern | Legacy | Lumos target | Delta size |
|---|---|---|---|
| Retrieval algorithm | FAISS + rank_bm25 + RRF + BGE reranker | PostgreSQL FTS + pgvector + RRF + BGE reranker | **Small** — same algorithm, different storage |
| Vector storage | FAISS flat IP index, per-corpus `.index` files on disk | pgvector, one table, metadata-filtered in SQL | Medium |
| Lexical storage | `BM25Okapi` pickled per corpus, rebuilt at ingest | Postgres `tsvector` / FTS | Medium |
| Curriculum scoping | `KNOWN_CORPORA` set hardcoded in `rag.py` | Curriculum registry table, DB-driven | **Large** — the central gap |
| API layer | FastAPI (cloud) / Flask (local, web) | FastAPI | Small |
| Web UI | Jinja + vanilla JS, 59 KB `chat.html` | TanStack Start + React + TS | **Full rewrite** |
| Persistence | Neon (cloud), SQLite (local) | Neon + Drizzle migrations | Medium |
| Model access | Direct `transformers` calls + two ad-hoc HTTP clients | Model Gateway abstraction | Medium |
| Source priority | **Absent** | First-class ranking feature | **Full build** |
| Multi-part questions | **Absent** | Dependency graph + scratchpad | **Full build** |
| Citation validation | **Absent** (sources returned, never checked against answer text) | Mandatory validation stage | **Full build** |
| Tests | **None, in either repo** | Unit / integration / Playwright / RAG eval | **Full build** |

---

## B. Reusable Shikhbo components

Ranked by value. "Port" means move the logic and adapt the storage; "lift" means the code can move nearly as-is.

### B.1 High value — port deliberately

**1. `shikhbo-ai/rag.py` retrieval core.** The best asset in either repository.

```python
def _rrf(dense_ids, sparse_ids, w_dense, w_sparse, k=60):
    scores = {}
    for rank, cid in enumerate(dense_ids):
        scores[cid] = scores.get(cid, 0.0) + w_dense / (k + rank + 1)
    for rank, cid in enumerate(sparse_ids):
        scores[cid] = scores.get(cid, 0.0) + w_sparse / (k + rank + 1)
    return sorted(scores, key=lambda cid: scores[cid], reverse=True)
```

Correct RRF: rank-based, not score-based, so the two retrievers' incomparable score scales never need normalising. The weighting is language-aware — `(0.6, 0.4)` dense/sparse for English, `(0.4, 0.6)` for Bangla — a defensible choice given that BGE-M3's Bangla representation is weaker than its English one and lexical matching carries more of the load. **Keep the constants, and record them as the RRF baseline to beat once an evaluation set exists** (§K). Retrieve 30 per retriever → fuse → 20 candidates → rerank → top-*k*=5 is a sensible funnel.

**2. Reranker lifecycle handling (`rag.py:107–127`).** Lazy load behind a lock, a `_reranker_failed` latch so a failed load is not retried per request, and a documented fallback to raw RRF order. This is the kind of detail that is easy to omit and expensive to add later.

**3. Confidence gating.** `CONFIDENCE_THRESHOLD` (default 0.3) applied to the top reranker score, returning `([], False)` rather than a weak answer. `grounded` then flows into `_build_system_prompt()`, which switches to a prompt that forces the model to open with an explicit "I couldn't find this directly in your textbook" disclosure — in Bangla for NCTB, English otherwise. This is a working, if partial, implementation of the whitepaper's §5.9 safeguard, and the bilingual disclosure strings are worth keeping verbatim.

**4. Prompt library — `Shikhbo-Local-App/scripts/utils/prompts.py` and `shikhbo-ai/app.py:258–345`.** Four tutoring modes (normal / simple / quiz / step_by_step), each written in both Bangla and English, tuned for the audience. The `step_by_step` framing — *Formula → Substitution → Units → Final Answer* — is exactly right for Edexcel Physics working. This is pedagogical content, not code, and it is genuinely hard to reproduce. **Extract to versioned prompt templates rather than re-authoring.** One caveat in §C.

**5. Bilingual tokenisation.** `_tokenize_bengali` (`[ঀ-৿\w]+`, tokens ≥ 2 chars) plus a 60-word Bangla stopword list and a keyword-backfill routine in `ingest.py:48–72`. Crude, but it is real Bangla NLP work grounded in the actual corpus, and it is the starting point for the Postgres FTS configuration Lumos needs (Postgres ships no Bangla text-search dictionary, so this becomes custom).

**6. Neon schema (`web/scripts/init_db.sql`).** `users` / `otp_codes` / `chat_sessions` / `chat_messages`, with `sources JSONB` already on the message row and `class` + `curriculum` already on the user row. Small, correct, and the right shape. Port as the starting point for the Drizzle migration.

**7. Availability pattern.** Primary inference with automatic fallback on 503/timeout, and a `/health` endpoint reporting `rag_loaded` / `llm_loaded` / `llm_failed` separately. Keep the pattern; move it behind the Model Gateway.

**8. Voice modules.** `faster-whisper` STT and Piper TTS with a Bengali voice lookup, already written against a provider-ish interface. Phase 2, but no need to start from zero.

### B.2 Moderate value — lift with edits

- Ingestion loaders (`ingest.py:77–190`) — the per-corpus normalisation shape is right; the hardcoded filenames are not.
- `_chunk_text()` character chunker (1600/200 overlap) — a reasonable fallback for documents with no structural boundaries.
- The four tutoring modes' UI vocabulary and the Bangla/English label pairs in `chat.html` (`data-en` / `data-bn` attributes).
- Dockerfile HF-cache handling — the `/tmp/hf_cache` redirect off the 50 GB non-persistent root disk is hard-won operational knowledge, documented in-file.

### B.3 Not currently reusable

Nothing in either repo can be reused for: source priority, multi-part question handling, citation validation, curriculum registry, or evaluation. Those are new builds.

---

## C. Obsolete components and defects

### C.1 Architecture to retire

| Component | Reason |
|---|---|
| Flask + Jinja + vanilla JS front end | Replaced by TanStack Start + React + TS. `chat.html` is 59 KB of markup, inline script and styling. |
| SQLite chat history (`scripts/db/sqlite_db.py`) | Replaced by Neon. Retain only if the offline desktop target is kept alive. |
| LangChain `FAISS` + `allow_dangerous_deserialization=True` | pgvector replaces it, and loading a pickled index with that flag is an arbitrary-code-execution surface if the index file is ever attacker-influenced. |
| `KNOWN_CORPORA` hardcoded set | Replaced by the curriculum registry. |
| Ollama coupling (`OLLAMA_BASE = "http://127.0.0.1:11434"` hardcoded in two modules) | Violates the Model Gateway rule. Keep Ollama only as one gateway provider for the offline target. |
| Anaconda/PyInstaller/NSIS desktop packaging | Future target, not MVP. |
| Capacitor Android shell | Rebuild against a stable API later. |

### C.2 Defects found — all verified by reading the code

**C.2.1 — `build_index.py` corrupts every chunk's indexed text.** *(Shikhbo-Local-App, high severity)*

```python
f"Topics: {', '.join(item.get('topic', []))}",
```

`topic` is a **string** in all 180 records, never a list. `', '.join("Pastimes")` yields `"P, a, s, t, i, m, e, s"`. Verified:

```
topic type: str | value: 'Pastimes'
joined -> 'P, a, s, t, i, m, e, s'
```

Every document embedded and BM25-indexed by the local app therefore carries a line of character-separated noise, degrading both retrievers.

**C.2.2 — `chapter_title` / `chapter_name` schema split.** 80 of 180 records use `chapter_title` (ICT C1–C2); 100 use `chapter_name` (English, Physics, ICT C3–C6). `build_index.py` reads only `chapter_title`, so 100 records index and display `Chapter N: None`. `shikhbo-ai/rag.py:245–254` `format_sources()` has the same bug — `c.get("chapter_title", "")` returns empty for the Astrophysics corpus, which uses `chapter_name`. `ingest.py:118` renames it for Astrophysics only, so the cloud path is partially patched and the local path is not.

**C.2.3 — metadata filtering happens *after* retrieval, not before.** *(Shikhbo-Local-App, high severity)*

```python
candidates = self.vector_store.similarity_search(query, k=TOP_K * 5)   # k=15, unfiltered
filtered  = [d for d in candidates if _matches_filter(d.metadata, ...)]
return filtered[:TOP_K]
```

The FAISS search is global. With 180 chunks across 3 subjects, a Physics query can consume all 15 slots with ICT chunks and return nothing. This directly violates ADR-006 (curriculum isolation before retrieval) and is the single strongest argument for moving retrieval into SQL, where the filter is a `WHERE` clause evaluated before the vector comparison.

**C.2.4 — RRF identity collision.** `uid = doc.metadata.get("source", str(id(doc)))` in `retriever.py::_fuse`. `source` falls back to `f"{filename}:{line_num}"` when `chunk_id` is absent, and `doc_map[uid] = doc` overwrites on collision. Low impact on the current corpus (all 180 `chunk_id`s are unique — verified), but unsafe as a fusion key.

**C.2.5 — the prompt forbids the citations the product requires.**

> "Use it to ground your answer, but **never quote or reference it directly** — teach as if the knowledge is your own." — `scripts/utils/prompts.py`

Directly contradicts the whitepaper's "100% of substantive answers" source-attribution objective and the operating contract's §13. The cloud prompts get this right ("Reference the chapter and page number in your answer"); the local ones invert it. Do not port `_BASE` unedited.

**C.2.6 — no citation validation anywhere.** `/chat` returns `sources` built from the retrieved chunks and `answer` generated by the model, with **no check that the answer's claims correspond to the sources**, and no check that any chapter/page the model names in prose matches a retrieved chunk. A model that ignores the context and states a wrong page number produces a response that looks cited and is not. This is the highest-value correctness gap in the legacy system.

**C.2.7 — English is in the corpus but not in the cloud index.** `ingest.py` loads ICT C1–C6, the Astrophysics JSONL and the Astrophysics PDF. It never loads the 16 English unit files, and `KNOWN_CORPORA` in `rag.py` lists only `(NCTB, ICT, SSC)` and `(Edexcel_IAL, Physics, A-level)`. The English corpus — 43 records, 24 % of the total — is dead weight in the cloud deployment. It is also the only corpus that exists solely in the *local* repository.

**C.2.8 — the UI advertises a subject with no corpus.** `templates/chat.html:50–59` offers four subject buttons:

```html
<button data-subject="ICT" ...>আইসিটি</button>
<button data-subject="Bangla" ...>বাংলা</button>
<button data-subject="Physics" ...>পদার্থ</button>
<button data-subject="English" ...>ইংরেজি</button>
```

There is no Bangla corpus. Selecting বাংলা passes `subject_filter="Bangla"`, every metadata filter fails, `docs` is empty, and the generator answers from model priors with no textbook grounding. This is precisely the failure the operating contract's §3 names: *"Never confuse UI availability with curriculum availability."* It is live in a shipped `v1.0.0` build.

A second instance: the local UI pins `class` to `SSC` (chip `chipClass`), but the Physics corpus is `class: "A-level"`. Selecting Physics therefore also returns nothing, for a different reason.

**C.2.9 — weak default secret.** `app.secret_key = os.getenv("SECRET_KEY", "shikhbo_dev_secret_2024")` (`web/app.py:38`). A deploy that forgets `SECRET_KEY` silently gets a publicly known session-signing key, which is a session-forgery path to any account. Must fail closed in Lumos.

**C.2.10 — `repetition_penalty=1.3` with `do_sample=False`.** (`app.py:373`) Aggressive for greedy decoding, and likely to distort Bangla output, where repeated conjunct forms are normal. Flagged for evaluation, not asserted as broken.

### C.3 Positive security finding

**No live credentials are committed in either repository.** A scan for OpenAI-style keys, `hf_*` tokens, Google `AIza*` keys, credentialed Postgres URLs and PEM private keys across all tracked files returned nothing but placeholders. `.env.example` files are clean and well-annotated. Good hygiene to carry forward.

---

## D. Curriculum inventory — verified

Full numbers in `CURRICULUM_INVENTORY.md`; machine-readable evidence in `evidence/curriculum_audit_local.json` and `evidence/curriculum_audit_combined.json`; reproduce with `python scripts/audit_corpus.py <path>/raw_data`.

### D.1 What exists

| Corpus | Files | **Records** | Class | Curriculum | Median content | Bangla |
|---|---:|---:|---|---|---:|---:|
| SSC English (*English For Today*, Units 1–16) | 16 | **43** | SSC | NCTB | 7,900 chars | 0 / 43 |
| SSC ICT (Chapters 1–6) | 6 | **120** | SSC | NCTB | 1,767 chars | 120 / 120 |
| Edexcel IAL Physics 5.6 (Astrophysics & Cosmology) | 1 | **17** | A-level | Edexcel_IAL | 1,560 chars | 0 / 17 |
| **Total unique** | **23** | **180** | | | | **120 / 180** |

`shikhbo-ai` additionally carries 7 JSONL files at its repository root (ICT C1–C6, Astrophysics) totalling 137 records. **All 137 are byte-identical duplicates** of files in `Shikhbo-Local-App/raw_data` — 137 duplicate content groups and 137 duplicate `chunk_id`s when the two roots are audited together, against 180 unique content blocks. The naive union of 317 records is therefore double-counting.

`shikhbo-ai` also holds `Astrophysics_Cosmology_Notes.pdf` (79 KB), chunked at ingest time by `_load_pdf_chunks()` at 1600 chars / 200 overlap. Its chunk count is deployment-time, not repository state, and is not counted above.

### D.2 The 1,022 discrepancy

The prebuild pack states 1,022 records (671 English / 253 ICT / 98 Physics), with a per-unit English breakdown and a per-chapter ICT breakdown. Every figure is wrong, and not by a constant factor (15.6× / 2.1× / 5.8×), which rules out a units confusion.

The pack's **own audit script**, run unmodified against the real `raw_data/`, returns the corrected numbers:

```
"English": { "files": 16, "records": 43,  "classes": ["SSC"] }
"ICT":     { "files": 6,  "records": 120, "classes": ["SSC"] }
"Physics": { "files": 1,  "records": 17,  "classes": ["A-level"] }
```

Independent confirmation by byte arithmetic: `English Unit3.jsonl` is 22,370 bytes and holds 21,543 characters of `content` — 96 % of the file. Three records of ~7,200 characters each. Fifty records would need roughly 360 KB. `raw_data/` has not been touched since the initial commit (`git log -- raw_data` → one commit, `f49cc6e`), so this is not drift.

**Conclusion:** the 1,022 figure was never true of these repositories. The corrected inventory is authoritative; the pack's figures are superseded and the discrepancy is logged in `DECISIONS.md` (ADR-008) rather than quietly overwritten.

### D.3 The 2.58 GB discrepancy

The whitepaper, §1 and §4:

> "the ingestion pipeline has processed a curriculum corpus of approximately 2.58 GB spanning examination sessions from 2009 to January 2026"
> "**Phase 1 (implemented).** Pearson Edexcel Physics, A-Level, sessions 2009 through January 2026 … question papers, mark schemes, examiner reports, textbooks, and revision guides, ingested into a linked, chunked, vector-indexed corpus."

Neither repository contains any of this. The complete Physics holding across both repos is one 36 KB JSONL of 17 revision-note chunks covering specification area 5.6, plus a 79 KB notes PDF. No question paper, mark scheme, examiner report, or textbook is present, and no ingestion code targets those document types.

Correspondingly, the architecture the whitepaper describes for that corpus — boundary-detection state machine keyed on "Total for Question *n*", sub-question hierarchy parsing, `depends_on` cross-reference extraction, Qwen2-VL figure alt-text, question↔mark-scheme↔examiner-report link fields — **has no implementation in either repository.** A field scan across all 180 records confirms no key matching `*mark*` or `*question*` exists anywhere in the corpus.

This is stated plainly because it is the single largest risk to the project, and it is a risk of a specific kind: the BCOLBD final round awards 20 points for "*a deployment-ready inference model demonstrating the AI model's functionality and **reproducibility***" and 20 for "*thorough documentation and complete code repository*". An evaluator reading the whitepaper and then opening the repository will find the gap. Three defensible paths, for the human owner to choose between, are set out in `BLOCKERS.md` (BLOCK-001).

### D.4 What is not present

Not available as chunked curriculum data, and must not be exposed as available: **Chemistry, Biology, Mathematics, Bangla, NCTB Physics, HSC-level content of any subject, any past paper, any mark scheme, any examiner report.**

---

## E. Chunk quality findings

Reproduce with `python scripts/audit_corpus.py <path>/raw_data`.

**E.1 — Chunk sizes are wildly inconsistent and mostly wrong.**

| Corpus | Median content | Min | Max | Whitepaper §5.4 target |
|---|---:|---:|---:|---|
| English | 7,900 chars | 177 | 9,595 | 400–600 tokens (textbook) |
| ICT | 1,767 chars | 1,101 | 2,569 | 400–600 tokens |
| Physics | 1,560 chars | 1,296 | 2,286 | 200–400 tokens (revision guide) |

The English chunks are roughly a **whole textbook unit each** — 2 to 4 records per unit. At ~2,000 tokens they are too coarse for retrieval (a query about one lesson retrieves the entire unit, drowning the reranker and the context window) and too coarse for citation (a page number spanning a unit is not a usable reference). ICT and Physics are closer to sane. **The English corpus must be re-chunked before it is usable**; ICT and Physics may survive re-chunking at a smaller granularity.

**E.2 — OCR and extraction artefacts are pervasive.**

| Artefact class | Records affected (of 180) |
|---|---:|
| Bangla duplicated vowel-sign / conjunct corruption | 73 |
| Broken word split across a line break | 66 |

Concrete Bangla example, from `SSC-ICT-C1-P1-CH1`:

> তথ্য ও **যযোগাযযোগ** প্রযুক্তি একুশ শতক এবং তথ্য ও **যযোগাযযোগ** প্রযুক্তি …

The correct form is যোগাযোগ. The extractor has duplicated the য and mis-ordered the ো vowel sign. This corrupts the token in both the embedding and the BM25 index, so a student typing the correct spelling may fail to match the chunk that answers their question. 73 of 120 ICT records — 61 % of the Bangla corpus — show this class of damage.

English example, from `SSC-English-C3-P1-CH1`:

> "Learning outcomes After we have studied the unit, we will be able to **e** narrate incidents and events … **e** participate in conversation …"

The bullet glyph (•) has been OCR'd as the letter `e`. Records also end mid-word (`… where the spacing between lines indicates the strength of the force: cl`), indicating hard truncation at the chunk boundary rather than a sentence or section boundary.

**E.3 — Metadata is thin and partly unreliable.**

- `keywords` is **empty in 163 of 180 records** (90.6 %). Only the 17 Physics records have real keywords. `ingest.py` backfills Bangla keywords by frequency at ingest time for ICT — English gets nothing.
- `spec_ref` exists **only** on the 17 Physics records. There is no syllabus reference for any NCTB content.
- `chapter_title` vs `chapter_name` split, 80/100 (see C.2.2).
- `token_count` is present on all 180 records but is not independently verifiable and disagrees with a whitespace word count by more than 50 % on 134 records. For Bangla this is partly expected (subword tokenisation inflates token counts relative to words), so this is flagged as **untrusted, to be recomputed at ingest with the actual tokeniser**, not asserted as wrong.
- No record carries: `curriculum`, `language`, `document_type`, `source_id`, `source_priority`, `provenance_hash`, `question_number`, `sub_question`, `marks`, `parent_question_id`, `depends_on`, or `ingestion_version`. `curriculum` and `language` are injected at ingest time by `shikhbo-ai/ingest.py`; the remaining ten fields have no source at all. **All 180 records are missing all 13 canonical fields** — quantified in `evidence/curriculum_audit_local.json` under `canonical_schema_gaps`.

**E.4 — Cross-repo duplication.** 137 records exist identically in both repos with identical `chunk_id`s (§D.1). Any migration that walks both repositories will double-index them. Deduplication by content hash must be a pipeline stage, not a manual step.

**E.5 — Positive findings.** All 23 files parse cleanly (0 JSON errors). All 180 `chunk_id`s are unique within `raw_data/`, and the identifier scheme is well-designed and human-readable: `SSC-ICT-C1-P1-CH1`, `EDEXCEL-IAL-PHYS-5.6-P1-CH1` — it encodes curriculum, subject, chapter, page and chunk index. `page_no` is populated on every record. `prerequisite` is populated on every record, though as free text (`"Basic Computer Knowledge"`, `"Newton's Laws of Motion, Weight and Gravity"`) rather than as resolvable IDs — a genuine head start on the prerequisite graph, needing normalisation rather than invention.

---

## F. Migration strategy

Phased, evidence-gated. Full table in `MIGRATION_MAP.md`.

**Phase A — establish truth before moving anything.**
Build the curriculum registry and coverage gates *first*, before ingestion or retrieval. Until availability is DB-driven, every subsequent layer risks reproducing C.2.8. This is LUMOS-004A and it is the recommended next goal (§M).

**Phase B — canonical schema and normalisation.**
Define the canonical chunk schema (`docs/CHUNK_SCHEMA.md`), then write a legacy adapter that maps the three observed legacy shapes onto it, deduplicates by content hash, reconciles `chapter_title`/`chapter_name`, injects `curriculum` / `language` / `document_type` / `source_priority`, recomputes `token_count` with the real tokeniser, and emits a per-corpus ingestion report. Every transformation is a pure function with a test. Nothing is indexed until its report is reviewed.

**Phase C — cleaning and re-chunking.**
Bangla normalisation for the 73 damaged records (NFC normalisation, then targeted repair rules with a review sample), bullet-glyph repair for English, and re-chunking the English corpus from ~2,000-token units to 400–600-token sections with 50-token overlap at real section boundaries. Each rule is a separate, reversible pipeline stage; original text is retained alongside cleaned text so provenance survives.

**Phase D — retrieval on Postgres.**
Port `rag.py` verbatim in algorithm, changed in storage: FAISS → pgvector, `BM25Okapi` → Postgres FTS with a custom Bangla configuration built from the existing tokeniser and stopword list. **Keep RRF at *k*=60 and the language-aware weights as the baseline.** Add the two things the legacy has not got: metadata filter *before* retrieval (a `WHERE` clause, fixing C.2.3), and source priority as a retained feature through fusion and reranking.

**Phase E — generation, citation, safety.**
Port the prompt library with C.2.5 corrected. Build the citation validator that the legacy lacks: every chapter/page reference in the answer must resolve to a retrieved chunk, or the answer is rejected and regenerated. Then confidence gating, conflicting-source detection, and the refusal path.

**Phase F onward.** Tutor API + SSE, TanStack front end, practice, past papers, 3D homepage, evaluation harness, deployment. Ordered in `ROADMAP.md`.

**Explicitly deferred:** desktop packaging, Android, voice, vision. Each has working legacy code to return to.

**Migration rule:** legacy code is copied into the new tree only with a test, a normalised schema, and a recorded decision. Anything ported without those three is technical debt with a nicer filename.

---

## G. Target architecture

Confirmed as specified — the prebuild pack's `ARCHITECTURE.md` is sound and is carried forward with the corrections in this report folded in. Diagram sources in `docs/diagrams/`.

```
Student / Teacher
   │
   ▼
Cloudflare (DNS, CDN, Workers)
   │
   ▼
TanStack Start (React + TS + Tailwind + Motion + R3F/Drei)
   │  server functions · typed routes · SSR
   ▼
FastAPI (Python)  ──────────────► Model Gateway ──► HF endpoint / Render GPU / mock
   │  auth · orchestration · SSE                     (provider-agnostic, server-side only)
   ├── Curriculum Registry  ─┐
   ├── RAG Orchestrator      │
   ├── Practice Service      ├──► Neon PostgreSQL 16 + pgvector
   └── Ingestion Worker  ────┘         relational truth + vectors + FTS, one store
            │
            └──► Cloudflare R2   page images, assets, exports, uploads
```

Three architectural rules carried from the pack, all still correct after this audit:

1. **Cloudflare is not the model layer.** Edge for delivery; GPU work stays on GPU-capable infrastructure.
2. **One store.** Postgres + pgvector, so metadata filtering and vector search execute in a single query — which is also the fix for C.2.3. No Elasticsearch, Pinecone, Weaviate or separate BM25 service without evaluation evidence.
3. **No model provider reaches the browser.** The front end knows the Model Gateway URL and nothing else.

---

## H. Infrastructure requirements

| Layer | Choice | Status | Note |
|---|---|---|---|
| Source control | GitHub `Shahriar290900/Lumos` | **Exists, empty** | This report is its first commit |
| CI/CD | GitHub Actions | Not started | Legacy has a tag-triggered installer build only |
| Database | Neon PostgreSQL 16 + pgvector | **Not provisioned** | BLOCK-002 |
| Edge / DNS / CDN | Cloudflare | **Not provisioned** | BLOCK-003 |
| Object storage | Cloudflare R2 | **Not provisioned** | BLOCK-003 |
| API / workers | Render | **Not provisioned** | BLOCK-004 |
| Inference (dev) | HF Inference Endpoint or GPU Space | **Not provisioned** | BLOCK-005 |
| Observability | Sentry | Not configured | Connector available |
| Email | provider TBD | Not decided | Legacy used Gmail SMTP app passwords — not production-grade |
| Auth | TBD | **Not decided** | BLOCK-006. Legacy: bcrypt + Google OAuth + email OTP |

Connectors already authenticated in the engineering session: Hugging Face (`shahriarhameem`), Neon, Render, Cloudflare, Sentry, Google Drive. Provisioning is therefore a decision, not an access problem — which is why each blocker asks for a choice rather than a credential.

**Development machine constraint stands.** A 2017 MacBook Air is a client. No workflow may require local GPU inference, local BGE-M3 embedding of a full corpus, or a local vLLM. Ingestion runs against a remote embedding endpoint or as a batch job on remote infrastructure. A deterministic mock provider must make the whole app runnable with no credentials at all — this is also what makes CI possible.

**Cost note.** The whitepaper's §5.11 figures (T4 ≈ $0.50/hr, prototype on free tier, pilot $150–350/mo) and the pack's `HUGGINGFACE_DEV_MODE.md` figures are quoted from mid-2026 list prices. They are **not re-verified in this session** and should be re-checked at provisioning time, per BLOCK-005.

---

## I. Model-serving strategy

### I.1 Model IDs — checked against the live Hugging Face Hub

Every model named across the whitepaper, the prebuild pack and the legacy code was verified to exist. All do:

| Model | Params | Licence | Named in |
|---|---:|---|---|
| `Qwen/Qwen2.5-VL-7B-Instruct` | 8.3 B | Apache-2.0 | `shikhbo-ai/app.py` default |
| `Qwen/Qwen2.5-VL-3B-Instruct` | 3.8 B | — | `shikhbo-ai/app.py` fallback |
| `Qwen/Qwen2.5-7B-Instruct` | 7.6 B | Apache-2.0 | Whitepaper §5.10 |
| `Qwen/Qwen3.5-0.8B` | 0.8 B | Apache-2.0 | Local-App Ollama default (`qwen3.5:0.8b`) |
| `Qwen/Qwen3.5-4B` | 4 B | Apache-2.0 | Candidate |
| `google/gemma-4-31B-it` | 31 B | Apache-2.0 | `web/scripts/gemini_client.py` |
| `google/gemma-4-E4B-it` | 4 B (effective) | Apache-2.0 | Candidate |
| `BAAI/bge-m3` | XLM-R | **MIT** | Embeddings, both repos |
| `BAAI/bge-reranker-v2-m3` | 568 M | **Apache-2.0** | Reranker, `shikhbo-ai` |

Two observations, neither a defect:

- The whitepaper's §5.10 stack (Qwen2.5-7B, Qwen2-VL-7B, Gemma-2-2B) is now a generation behind both what the code actually runs and what is available. Qwen3.5 and Gemma 4 are current. The retrieval models — BGE-M3 and BGE-Reranker-v2-M3 — are unchanged and remain the right choice for Bangla/English, which is fortunate: they are the models the whole retrieval design depends on.
- The whitepaper's licence table lists Gemma under "Gemma Terms". `google/gemma-4-31B-it` is tagged **Apache-2.0** on the Hub, which is more permissive than the whitepaper assumes. Worth re-reading the model card before relying on it, but it does not weaken the open-weight argument.

### I.2 Gateway design

```
Application code
      │  ChatRequest / EmbedRequest / RerankRequest / VisionRequest  (typed, provider-neutral)
      ▼
Model Gateway  ── selects provider by config, never by caller
      ├── mock          deterministic, no credentials, CI + offline dev default
      ├── huggingface   Inference Endpoint or GPU Space   (development default)
      ├── render        self-hosted vLLM / SGLang         (production target)
      └── ollama        local, for the offline desktop target
```

Rules:

1. No product module imports `transformers`, `google.genai`, `huggingface_hub` or `requests`-to-a-model-URL. Only gateway providers do. `shikhbo-ai` violates this in three places today (`app.py`, `hf_client.py`, `gemini_client.py`).
2. Every provider implements the same interface and the same error taxonomy, so fallback is gateway policy rather than per-call-site `try/except` — replacing the ad-hoc pattern in `hf_client.py`.
3. The **mock provider is not optional**. It is what makes the test suite runnable, CI possible, and the app startable on the 2017 MacBook Air with an empty `.env`.
4. Credentials live server-side only. `AI_API_KEY` never appears in a client bundle, and a build-time check should assert that.
5. Model IDs are configuration (`CHAT_MODEL`, `EMBEDDING_MODEL`, `RERANKER_MODEL`), never literals in product code.

**Recommended development sequence:** mock first (unblocks everything), then a T4-class HF endpoint with a 4B-class model, measure latency and Bangla quality against a real evaluation set, and only then consider Render GPU. Pause the endpoint between sessions.

---

## J. RRF retrieval design

The legacy implementation is the baseline. The Lumos design changes storage and adds two stages; it does not change the fusion algorithm.

```
student query
      ▼
1. intent + curriculum identification        subject / class / curriculum / syllabus version
      ▼
2. registry check ─── subject unavailable ──► explicit "not covered" response, no retrieval
      ▼
3. metadata filter                            SQL WHERE, evaluated BEFORE any ranking   ← fixes C.2.3
      ▼
   ┌──────────────────────┬──────────────────────┐
   │ lexical              │ semantic             │
   │ Postgres FTS         │ pgvector + BGE-M3    │
   │ (custom bn config)   │ cosine, top 30       │
   │ top 30               │                      │
   └──────────┬───────────┴──────────┬───────────┘
              ▼                      ▼
4.            Reciprocal Rank Fusion, k = 60
              score(d) = Σ  w_r / (k + rank_r(d) + 1)
              w = (0.6 dense, 0.4 sparse) for en
              w = (0.4 dense, 0.6 sparse) for bn        ← legacy baseline, to be re-tuned on evidence
              ▼
5. source priority policy                     official/mark scheme > textbook > revision guide
      ▼                                        layer retained as a FEATURE, not a hard pre-filter
6. BGE-Reranker-v2-M3 cross-encoder            top 20 candidates → scored
      ▼
7. confidence gate                             max score < threshold → refuse, do not answer
      ▼
8. dependency-aware context assembly           topological order over depends_on; scratchpad
      ▼
9. generation via Model Gateway
      ▼
10. citation validation                        every reference resolves to a retrieved chunk  ← new
      ▼
    answer + sources + confidence
```

**Why RRF stays.** Rank-based fusion needs no score normalisation between two retrievers whose scores are not comparable (cosine similarity vs. BM25). It is one function, it has no infrastructure cost, and it already works in the legacy code. Replacing it with weighted score blending would require calibration the project cannot yet justify — there is no evaluation set. **RRF is the baseline; any replacement must beat it on a measured golden set, per the operating contract's §7.**

**Source priority as a feature, not a filter (stage 5).** The whitepaper's §5.6 is precise about this and the phrasing matters: candidates from all layers are re-scored by the reranker, but layer membership is *retained* so that official curriculum context cannot be displaced by a superficially similar textbook passage. A hard pre-filter would starve the context window when the top layer is thin. Implementation: carry `source_priority` through fusion, apply a bounded boost or a per-layer quota at context assembly, and make the policy configurable and measurable rather than baked in.

**Metrics to instrument from day one:** Recall@K, Precision@K, MRR, reranker lift over raw RRF order, citation accuracy, refusal correctness, and per-language breakdowns for every one of them. Bangla and English must be measured separately — the language-aware RRF weights are an untested hypothesis until they are.

---

## K. Security risks

| # | Risk | Severity | Evidence | Mitigation |
|---|---|---|---|---|
| K-1 | RAG documents are untrusted input; a poisoned chunk can carry prompt injection into the context window | **High** | No sanitisation in either repo | Treat retrieved text as data: delimit it structurally, strip instruction-like patterns at ingest, never let a chunk alter system instructions, validate citations against retrieved IDs |
| K-2 | Weak default session secret | **High** | `web/app.py:38` — `"shikhbo_dev_secret_2024"` | Fail closed if `AUTH_SECRET` is unset; no defaults for any secret |
| K-3 | Model endpoint exposure | **High** | Bearer-token auth only on the HF Space; a leaked token is an open GPU | Gateway-only access, server-side credentials, per-user rate limiting, request-size caps |
| K-4 | Minors' academic data | **High** | Users declare class/curriculum; whitepaper targets SSC students | Data minimisation, no assessment profiles, encryption in transit and at rest, deletion + retention policy, parental-consent path — BLOCK-007 |
| K-5 | Unsafe deserialisation | Medium | `allow_dangerous_deserialization=True` (`retriever.py`), `pickle.load` on BM25 (`rag.py:167`) | Eliminated by moving indices into Postgres |
| K-6 | File-upload handling | Medium | Vision endpoint accepts base64 images; local app accepts file paths | Type/size validation, no path traversal, scan before processing, cap decoded size |
| K-7 | SSRF via model/OCR endpoint config | Medium | Endpoint URLs come from env and are fetched server-side | Allowlist provider hosts; never let a request body choose the endpoint |
| K-8 | Missing rate limiting | Medium | None in either repo | Per-user and per-IP limits at the API boundary before any GPU call |
| K-9 | Authorization | Medium | Flask `login_required` checks session presence only — no ownership check visible on `/api/sessions/<sid>/messages` | Enforce row-level ownership server-side on every resource |
| K-10 | Copyright / licensing of curriculum sources | **High (legal)** | NCTB textbook and Edexcel material, no licence record anywhere | Provenance + licence registry per source; whitepaper's "retrieval context only, no redistribution" position must be implemented, not just asserted — BLOCK-008 |
| K-11 | Dependency vulnerabilities | Medium | `Werkzeug==3.0.6`, `psycopg2-binary==2.9.9`, `faiss-cpu==1.9.0` pinned in 2025 | Dependabot + `pip-audit` / `npm audit` in CI |

**Positive:** no committed secrets (§C.3), and `.env.example` files are complete and well-annotated.

---

## L. Testing strategy

**Current state: there are no tests in either repository.** No `test_*.py`, no `conftest.py`, no `*.spec.js`, no `pytest.ini`, no Playwright or Vitest configuration. The only CI is a tag-triggered installer build in `Shikhbo-Local-App/.github/workflows/build.yml`, which builds artifacts and asserts nothing about behaviour.

This makes "does not regress" unprovable today, and it is the reason the mock model provider (§I.2) is a prerequisite rather than a convenience: no test suite can depend on a GPU.

Layers, in build order:

1. **Unit** — chunk normalisation, dedup, RRF fusion (fixed rank lists → known fused order), tokenisers, citation validator, curriculum registry rules. Pure functions, no I/O, fast.
2. **Integration (API)** — FastAPI TestClient against a seeded ephemeral Postgres with pgvector and the mock provider. Curriculum isolation, source priority, refusal on thin evidence, SSE close-under-error, migration-from-empty.
3. **Browser (Playwright)** — the journeys in `TEST_MATRIX.md`: auth, subject selection, tutor turn with visible citations, error states, responsive layout, keyboard navigation, reduced motion, WebGL-absent fallback. *A feature is not complete if it works through direct function calls while the user workflow is broken* (operating contract §22).
4. **RAG evaluation (golden set)** — the one that decides whether the product is any good:
   - factual correctness against curriculum sources
   - curriculum alignment (no cross-curriculum leakage)
   - citation correctness (every reference resolves)
   - source priority (official material is not displaced)
   - Bangla quality and English quality, **scored separately**
   - multi-part continuity
   - **refusal when evidence is insufficient**
   - hallucination resistance under adversarial and out-of-corpus prompts

   Metrics: Recall@K, Precision@K, MRR, reranker lift over RRF, citation accuracy — tracked per language and per corpus, committed as versioned JSON so regressions are diffable.
5. **Security** — no secrets in the client bundle (build-time assertion), server-side authorization on every resource, upload validation, prompt-injection corpus.
6. **Performance** — query latency budget measured on a low-end Android profile and a throttled network, per the operating contract's §23.

**Sizing note.** With 180 chunks in 3 corpora, a golden set of ~40–60 questions (roughly 20 ICT/Bangla, 15 English, 15 Physics, plus 10 deliberately out-of-corpus to test refusal) is proportionate. It must be built with subject-teacher review, as the whitepaper's §6.1 commits to — a golden set written by the system's own authors measures self-consistency, not correctness.

---

## M. Immediate next goal

### LUMOS-004A — Curriculum Registry + Coverage Gates

**Why this first, ahead of ingestion, retrieval and UI.** Three independent lines of evidence converge on it:

- **The defect that most damages trust is a registry defect.** C.2.8 — a shipped `v1.0.0` build offers a বাংলা subject button backed by no corpus, silently answering from model priors. No amount of retrieval quality fixes that; only a registry does.
- **The documentation gap is a registry gap.** §D.2 and §D.3 exist because nothing in the system was the authority on what the corpus contains. A registry makes the corpus self-describing, so `CURRICULUM_INVENTORY.md` becomes a generated artifact rather than a claim that can drift by 5.7×.
- **Every downstream goal depends on it.** Ingestion needs somewhere to record indexing status. Retrieval needs the metadata filter (C.2.3) to be DB-driven, not a hardcoded `KNOWN_CORPORA` set. The UI needs availability from an API. Building any of those first means building them twice.

It is also small, testable without a GPU, and needs no provisioned infrastructure beyond a database — so it is not blocked by BLOCK-002 through BLOCK-006.

**Scope.** Registry schema and migration (`curriculum → syllabus_version → subject → level → unit → source_document → chunk`), with per-subject `indexing_status`, `evaluation_status`, `source_priority` policy, supported languages, licence/provenance reference, and a `published` flag that is **false by default**. A seed derived from the verified 180-record inventory, not from the pack's numbers. A read API the front end consumes for availability. A rule enforced server-side: an unavailable subject cannot reach the retrieval path at all.

**Acceptance criteria.**

- [ ] Migration creates the registry tables from an empty database and is reversible
- [ ] Seed reflects the verified inventory exactly: English 43 / ICT 120 / Physics 17, `published = false` for all three until indexed and evaluated
- [ ] `Bangla`, `Chemistry`, `Biology`, `Mathematics` are representable as *known but unavailable* — not absent, so the UI can explain rather than omit
- [ ] A subject is `available` only when it has: curriculum + syllabus version + level + source provenance + indexed chunk count > 0 + a passing evaluation record
- [ ] `GET /curriculum` returns availability; the front end has no other source of it
- [ ] A request naming an unavailable subject is rejected before retrieval, with a clear message, and is covered by a test
- [ ] Unit tests for the availability rule, including the C.2.8 regression case (subject exists in UI, zero chunks → unavailable)
- [ ] Integration test: migration from empty DB → seed → API returns the expected availability set
- [ ] `scripts/audit_corpus.py` output and the registry seed agree; a CI check asserts it
- [ ] `CURRICULUM_INVENTORY.md` is regenerated from the registry, not hand-maintained
- [ ] No secret introduced; no model provider called; runs with an empty `.env` against a local Postgres

**Security considerations.** Registry contents are public-ish metadata, but licence and provenance fields may carry contractual terms — treat as internal. The availability check must be server-side; a client-side gate is not a gate.

**Performance considerations.** Trivial data volume. Index on `(curriculum, subject, level)` because it becomes the hot metadata filter in stage 3 of the retrieval pipeline.

**Blocked by.** Nothing that requires a decision. Needs a Postgres instance — a local container suffices for development, so it does not wait on BLOCK-002.

**Follows.** LUMOS-004B (canonical chunk schema + legacy normalisation), then LUMOS-004C (cleaning / OCR repair / re-chunking), then LUMOS-008 (hybrid retrieval with RRF on pgvector).

---

## Reconnaissance completion evidence

**What was inspected.** Both legacy repositories cloned and read at the file level: `rag.py` (278 lines), `ingest.py` (301), `shikhbo-ai/app.py` (routes, prompts, generation, health), `web/app.py` (routes, auth, session config), `hf_client.py`, `gemini_client.py`, `init_db.sql`, `Dockerfile`, `startup.sh`, `requirements.txt` (×3), `.env.example` (×2); `Shikhbo-Local-App`'s `build_index.py`, `retriever.py`, `generator.py`, `pipeline.py`, `prompts.py`, `context_builder.py`, `stt.py`, `tts.py`, `chat.html`, and the Actions workflow. All 23 JSONL corpus files parsed record by record. Both prebuild packs read in full (20 documents), the whitepaper (10 pages) and the competition guideline (6 pages) extracted and read.

**What was verified, and how.**

| Claim | Method |
|---|---|
| 180 unique records, 43/120/17 by subject | `scripts/audit_corpus.py`, plus the prebuild pack's own audit script run unmodified — both agree |
| 137 cross-repo duplicates | SHA-256 content hashing across both roots; 137 duplicate groups, 137 duplicate `chunk_id`s, 180 unique content blocks |
| 1,022 figure is unsupported | Independent byte arithmetic per file; `git log -- raw_data` shows one commit, so no drift |
| 2.58 GB Edexcel corpus absent | Full file inventory of both repos; no past paper, mark scheme or examiner report present |
| No question/marks/dependency metadata | Key-space scan across all 180 records |
| `topic` join bug | Executed against a real record: `', '.join("Pastimes")` → `"P, a, s, t, i, m, e, s"` |
| `chapter_title`/`chapter_name` split | Field counts — 80 vs 100 of 180 |
| OCR artefacts | Pattern scan: 73 Bangla-corruption records, 66 broken-word-split records, with cited examples |
| `keywords` empty | 163 of 180 |
| No tests | Filesystem scan for all common test-file conventions across both repos |
| No committed secrets | Regex scan for API-key, token, credentialed-URL and PEM patterns; placeholders only |
| All model IDs exist | Live Hugging Face Hub lookup for all 9 named models |
| Bangla subject has no corpus | `chat.html:50–59` cross-referenced against the subject field values in the corpus |

**What is missing.** The 2.58 GB Edexcel corpus, all past papers / mark schemes / examiner reports, every subject beyond English / ICT / Physics-5.6, all question-structure metadata, all tests, all provisioned infrastructure, and any licence record for the curriculum sources.

**What remains uncertain.**

- Whether the 2.58 GB corpus exists outside these repositories (BLOCK-001) — resolvable only by the human owner.
- Whether `token_count` is trustworthy for Bangla; recompute at ingest rather than assume.
- Deployment-time PDF chunk count for `Astrophysics_Cosmology_Notes.pdf` — computable only by running ingestion.
- Current pricing for HF endpoints, Neon, Render and R2; quoted figures are from the source documents and are not re-verified.
- Whether the Bangla OCR damage is mechanically repairable or requires re-extraction from source PDFs — needs a sample study in LUMOS-004C.
- Licensing status of NCTB and Edexcel material (BLOCK-008).

**Artifacts produced.** `RECONNAISSANCE_REPORT.md` (this document), `ARCHITECTURE.md`, `MIGRATION_MAP.md`, `CURRICULUM_INVENTORY.md`, `COVERAGE_MATRIX.md`, `CHUNKED_DATA_AUDIT.md`, `SOURCE_MANIFEST.md`, `SOURCES.md`, `CONNECTORS.md`, `DECISIONS.md`, `ROADMAP.md`, `GOALS.md`, `STATE.md`, `CHECKLIST.md`, `TEST_MATRIX.md`, `BLOCKERS.md`, `PROJECT.md`, `CLAUDE.md`, `README.md`, `.env.example`, `.gitignore`, `docs/CHUNK_SCHEMA.md`, `docs/diagrams/*.mmd`, `scripts/audit_corpus.py`, `evidence/curriculum_audit_local.json`, `evidence/curriculum_audit_combined.json`.

**Not done, deliberately.** No product code, no dependencies installed, no infrastructure provisioned, no legacy repository modified, no migration executed, no data transformed. Reconnaissance only, per §27.
