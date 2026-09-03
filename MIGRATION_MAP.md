# Shikhbo → Lumos Migration Map

Updated after the 2026-09-04 reconnaissance. Every row is grounded in code that was read; file references are to the legacy repositories at `Shikhbo-Local-App@b783680` and `shikhbo-ai@64b58c9`.

Verdicts: **PORT** (move the logic, change the storage) · **LIFT** (nearly as-is) · **REBUILD** (new) · **RETIRE** (drop) · **DEFER** (later phase)

---

## Retrieval and RAG

| Area | Source | Verdict | Change required | Destination |
|---|---|---|---|---|
| RRF fusion | `shikhbo-ai/rag.py:66–82` | **LIFT** | Keep *k*=60 and the language-aware weights (en 0.6/0.4, bn 0.4/0.6) as the measured baseline. Fix the fusion key to always be `chunk_id`. | `services/rag/fusion.py` |
| Dense retrieval | `rag.py:262–267` (FAISS `IndexFlatIP`) | **PORT** | FAISS → pgvector; metadata filter moves into the SQL `WHERE`, evaluated **before** ranking | `services/rag/retrieval.py` |
| Sparse retrieval | `rag.py:269–277` (`BM25Okapi`) | **PORT** | `BM25Okapi` → Postgres FTS with a custom Bangla configuration built from the legacy tokeniser + stopword list | `services/rag/retrieval.py` |
| Reranking | `rag.py:107–127`, `219–243` | **LIFT** | Keep the lazy load, the lock, the `_reranker_failed` latch and the documented fallback to raw RRF order | `services/rag/rerank.py` |
| Confidence gate | `rag.py:199`, `230–231` | **PORT** | Keep `CONFIDENCE_THRESHOLD`; make it per-corpus and calibrate on the golden set | `services/rag/confidence.py` |
| Curriculum scoping | `rag.py:89–92` `KNOWN_CORPORA` (hardcoded set) | **REBUILD** | Replace with the curriculum registry, DB-driven | `services/curriculum/registry.py` |
| Post-retrieval filtering bug | `Shikhbo-Local-App/scripts/pipeline/retriever.py::_vector_search` | **RETIRE** | Filtering after a global top-*k* search is the defect (§C.2.3). SQL pre-filtering replaces it. | — |
| Source priority | *absent in both repos* | **REBUILD** | Layer membership carried through fusion and reranking as a feature; per-layer quota at context assembly | `services/rag/priority.py` |
| Multi-part dependency handling | *absent in both repos* | **REBUILD** | Question graph, topological ordering, per-question scratchpad. **No legacy data to build against** — see BLOCK-001 | `services/rag/context.py` |
| Citation validation | *absent in both repos* | **REBUILD** | Every reference in the answer must resolve to a retrieved chunk, or the answer is rejected | `services/rag/citations.py` |

## Ingestion and data

| Area | Source | Verdict | Change required | Destination |
|---|---|---|---|---|
| JSONL loaders | `shikhbo-ai/ingest.py:77–128` | **PORT** | Generalise; remove hardcoded filenames; add the 16 English files the cloud pipeline never loaded | `services/ingestion/loaders/` |
| Bangla tokeniser + stopwords | `ingest.py:32–72` | **LIFT** | Becomes the seed for the Postgres FTS Bangla configuration | `services/ingestion/lang/bn.py` |
| Keyword backfill | `ingest.py:57–72` | **PORT** | Extend to English; run for all corpora, not ICT only | `services/ingestion/enrich.py` |
| Character chunker | `ingest.py:131–141` | **PORT** | Keep as fallback; add a structure-aware chunker for documents with real boundaries | `services/ingestion/chunking.py` |
| PDF extraction | `ingest.py:144–190` (PyMuPDF) | **PORT** | Add cleaning stages; extract page images to R2; retain page manifest | `services/ingestion/pdf.py` |
| Chunk schema | 3 divergent legacy shapes | **REBUILD** | One canonical schema; legacy adapter maps all three onto it | `docs/CHUNK_SCHEMA.md`, `packages/contracts` |
| Deduplication | *absent* | **REBUILD** | Content-hash dedup — 137 records exist identically in both repos | `services/ingestion/dedup.py` |
| Cleaning / OCR repair | *absent* | **REBUILD** | NFC normalisation, Bangla repair (73 records), bullet-glyph repair, boundary repair | `services/ingestion/clean.py` |
| Corpus reports | *absent* | **REBUILD** | Per-corpus ingestion report, reviewed before publish | `services/ingestion/report.py` |
| Legacy corpus itself | `raw_data/*.jsonl` (180 records) | **PORT** | Input to the pipeline above. Never indexed raw. | `data/legacy/` |

## Models

| Area | Source | Verdict | Change required | Destination |
|---|---|---|---|---|
| BGE-M3 embeddings | both repos | **LIFT** | Behind the gateway; vectors persisted in pgvector | `services/models/embeddings.py` |
| BGE-Reranker-v2-M3 | `shikhbo-ai` | **LIFT** | Behind the gateway | `services/models/rerank.py` |
| Direct `transformers` calls | `shikhbo-ai/app.py:54–160` | **RETIRE** | Violates ADR-003; becomes one gateway provider | `services/models/providers/` |
| HF Space client | `web/scripts/hf_client.py` | **PORT** | Becomes the `huggingface` provider | `services/models/providers/huggingface.py` |
| Gemini client | `web/scripts/gemini_client.py` | **PORT** | Becomes an optional provider; not a hardcoded fallback path | `services/models/providers/` |
| Fallback-on-503 pattern | `hf_client.py` | **LIFT** | Becomes gateway policy, not per-call-site `try/except` | `services/models/gateway.py` |
| Ollama coupling | `retriever.py:19`, `generator.py:12` | **PORT** | Hardcoded `127.0.0.1:11434` → one gateway provider, for the offline target only | `services/models/providers/ollama.py` |
| Mock provider | *absent* | **REBUILD** | Deterministic, credential-free. **Prerequisite for the whole test suite.** | `services/models/providers/mock.py` |

## Prompts and tutoring

| Area | Source | Verdict | Change required | Destination |
|---|---|---|---|---|
| 4 tutoring modes, bilingual | `scripts/utils/prompts.py`, `shikhbo-ai/app.py:258–345` | **LIFT** | Extract to versioned templates. **Fix the local `_BASE`**, which instructs the model never to reference sources — it contradicts the citation requirement | `packages/prompts/` |
| Ungrounded-answer disclosure | `app.py:260–274` | **LIFT** | Bangla and English strings kept verbatim; wire into the refusal path | `packages/prompts/` |
| Context assembly | `scripts/utils/context_builder.py` | **PORT** | Add source-priority ordering and dependency ordering; fix `chapter_title`/`chapter_name` | `services/rag/context.py` |
| `_format_chunk` topic join bug | `build_index.py:24–32` | **RETIRE** | `', '.join(str)` corrupts every indexed document. Do not port. | — |

## Application, data, infrastructure

| Area | Source | Verdict | Change required | Destination |
|---|---|---|---|---|
| FastAPI service | `shikhbo-ai/app.py` | **PORT** | Already the target framework. Restructure into routers + services. | `apps/api/` |
| Neon schema | `web/scripts/init_db.sql` | **PORT** | Right shape, small. Becomes the first Drizzle migration; extended with the registry. | `packages/db/migrations/` |
| Auth (bcrypt + Google OAuth + OTP) | `web/scripts/auth/` | **PORT** | Pending BLOCK-006. Remove the default `SECRET_KEY` fallback — fail closed. | `apps/api/auth/` |
| Streaming | `hf_client.chat_stream`, `generator.generate_stream` | **PORT** | Standardise on one SSE contract with clean close-under-error | `apps/api/routes/chat.py` |
| Flask web app | `web/app.py` + Jinja templates | **RETIRE** | Replaced by TanStack Start + React + TS | `apps/web/` |
| Vanilla JS / 59 KB `chat.html` | both repos | **RETIRE** | Replaced | `apps/web/` |
| SQLite chat history | `scripts/db/sqlite_db.py` | **RETIRE** | Replaced by Neon (retain only if the offline desktop target is revived) | — |
| LangChain FAISS + `allow_dangerous_deserialization` | `retriever.py` | **RETIRE** | pgvector replaces it; the flag is an RCE surface | — |
| Dockerfile HF-cache handling | `shikhbo-ai/Dockerfile` | **LIFT** | The `/tmp/hf_cache` redirect is hard-won operational knowledge | `deploy/` |
| Voice STT/TTS | `scripts/voice/` | **DEFER** | Phase 2, behind provider interfaces | `services/voice/` |
| Vision / OCR | `app.py` `/vision`, `ocr_client.py` | **DEFER** | Phase 2, behind the gateway | `services/vision/` |
| Desktop packaging | PyInstaller + NSIS + Actions | **DEFER** | Future target | `apps/desktop/` |
| Android (Capacitor) | `android/` | **DEFER** | Rebuild against stable APIs | `apps/android/` |
| Tests | *none in either repo* | **REBUILD** | Everything. See `TEST_MATRIX.md`. | `tests/` |

---

## Migration rule

Legacy code enters the Lumos tree only with three things attached: a test, a normalised schema, and a recorded decision. Code ported without them is technical debt with a nicer filename.
