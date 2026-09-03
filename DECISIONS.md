# Lumos Architecture Decision Record

## ADR-001 — Neon PostgreSQL + pgvector as the single store
**Status:** Accepted
**Decision:** PostgreSQL is the relational source of truth and pgvector provides semantic retrieval; Postgres FTS provides lexical retrieval.
**Reason:** metadata filtering and vector search execute in one query rather than requiring application-side joins; referential integrity between curricula, sources, questions and chunks is enforced by the database; one system is less to operate for a small team.
**Consequence:** it also fixes the legacy defect where the FAISS search was global and the metadata filter ran afterwards on the top-k result (`Shikhbo-Local-App/scripts/pipeline/retriever.py::_vector_search`), which could return zero in-scope chunks.

## ADR-002 — Cloudflare at the edge, GPU-capable infrastructure for inference
**Status:** Accepted
**Decision:** do not force inference into an edge runtime.
**Reason:** separates latency-sensitive delivery from GPU and long-running Python workloads.

## ADR-003 — Model provider abstraction
**Status:** Accepted
**Decision:** all model access goes through an internal Model Gateway. No product module imports a provider SDK.
**Reason:** providers must be swappable without touching product code. The legacy system violates this in three places (`shikhbo-ai/app.py` calls `transformers` directly; `hf_client.py` and `gemini_client.py` are per-call-site HTTP clients with hand-rolled fallback).
**Consequence:** a deterministic mock provider is mandatory, not optional — it is what makes CI and credential-free development possible.

## ADR-004 — TanStack Start for the web application
**Status:** Accepted
**Decision:** TanStack Start + React + TypeScript.
**Reason:** typed server functions and routes, with a direct Cloudflare deployment path.

## ADR-005 — 3D is progressive enhancement
**Status:** Accepted
**Decision:** 3D may enhance identity and navigation but must never block core learning functionality.
**Reason:** accessibility, low-end Android performance, reduced-motion support, and Bangladesh connectivity conditions.

## ADR-006 — Curriculum isolation before retrieval
**Status:** Accepted
**Decision:** curriculum / syllabus version / subject / level filters are applied at the SQL boundary, before any similarity computation.
**Reason:** prevents cross-curriculum contamination, and makes isolation testable as a query property rather than a post-hoc filter.

## ADR-007 — RRF is the retrieval fusion baseline
**Status:** Accepted
**Decision:** fuse lexical and semantic rankings with Reciprocal Rank Fusion at k = 60, weighted (0.6 dense / 0.4 sparse) for English and (0.4 dense / 0.6 sparse) for Bangla — the constants the legacy implementation uses.
**Reason:** rank-based fusion needs no score normalisation between retrievers whose score scales are not comparable; it is one function with no infrastructure cost; and it already works in `shikhbo-ai/rag.py:66–82`.
**Consequence:** the language-aware weights are an untested hypothesis until a golden set exists. They are the baseline to beat, not a settled result. Any replacement — weighted score blending, learned fusion — must demonstrate improvement on measured evaluation data before it is adopted.

## ADR-008 — Corpus inventory corrected to 180 records
**Status:** Accepted · **Date:** 2026-09-04
**Decision:** the verified corpus baseline is **180 records** (SSC English 43, SSC ICT 120, Edexcel IAL Physics 5.6 17), superseding the ~1,022 figure stated in the Lumos prebuild pack.
**Reason:** three independent verifications — `scripts/audit_corpus.py`; the prebuild pack's own `audit_chunked_data.py` run unmodified against the real data; and per-file byte arithmetic. `git log -- raw_data` shows a single commit, so this is not drift.
**Consequence:** `CURRICULUM_INVENTORY.md`, `COVERAGE_MATRIX.md` and `CHUNKED_DATA_AUDIT.md` are rewritten. The prebuild pack is retained as a design reference; its data claims are not authoritative. Once the curriculum registry exists, the inventory becomes a generated artifact so it cannot drift again.

## ADR-009 — Source priority is a ranking feature, not a hard pre-filter
**Status:** Accepted
**Decision:** candidates from all source layers are reranked together, with layer membership retained as a feature that prevents authoritative context being displaced by a superficially similar lower-layer passage.
**Reason:** follows the whitepaper's §5.6 exactly. A hard pre-filter starves the context window whenever the top layer is thin — which, given the current corpus, is most of the time.
**Consequence:** the priority policy must be configurable and measurable, and its effect must appear in the evaluation metrics.

## ADR-010 — Citation validation is a required pipeline stage
**Status:** Accepted · **Date:** 2026-09-04
**Decision:** every generated answer passes a validation stage in which each source reference must resolve to a chunk that was actually retrieved for that turn. An answer that fails is rejected and regenerated, not shown.
**Reason:** the legacy system returns a `sources` array alongside an `answer` with no relationship enforced between them. A model that ignores its context and invents a page number produces a response that *looks* cited. This is the highest-value correctness gap found in the audit.

## ADR-011 — Availability is registry-driven
**Status:** Accepted · **Date:** 2026-09-04
**Decision:** subject availability is served from the curriculum registry, and a request naming an unavailable subject is rejected server-side before retrieval.
**Reason:** `Shikhbo-Local-App` ships a বাংলা subject button in a tagged `v1.0.0` release with no Bangla corpus behind it. Selecting it silently produces ungrounded model output. Availability expressed in markup is not availability.

## ADR-012 — Secrets fail closed
**Status:** Accepted · **Date:** 2026-09-04
**Decision:** no secret has a default value. A missing required secret aborts startup with a clear error.
**Reason:** `web/app.py:38` falls back to `"shikhbo_dev_secret_2024"` when `SECRET_KEY` is unset, so a deploy that forgets the variable silently gets a publicly known session-signing key.
