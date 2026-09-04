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

## ADR-013 — Availability is a database view, not application code
**Status:** Accepted · **Date:** 2026-09-04
**Decision:** the rule that decides whether a subject may be queried lives in one SQL view, `curriculum_availability`, which also returns `blocked_reasons`. Application code reads the view; it does not restate the rule.
**Reason:** two copies of a rule are two rules. A Python check and a SQL check drift, and the one that drifts is the one nobody tested. Returning the reasons alongside the verdict means a refusal can be explained to a student instead of appearing arbitrary.
**Consequence:** `CurriculumRegistry.require_available()` raises rather than returning a boolean, so a forgotten `if` cannot become an ungrounded answer. A CI check asserts the view never reports available with blocked reasons present, or vice versa.

## ADR-014 — Audited counts are separate from indexed counts
**Status:** Accepted · **Date:** 2026-09-04
**Decision:** `corpus_snapshots` records what an auditor counted in the source material, with the method and evidence file that produced the number. `subject_offerings.indexed_chunk_count` records what is actually in the store. They are different columns in different tables and are never conflated.
**Reason:** the 180 legacy records exist; zero of them are indexed. A single "chunk count" would have to mean one or the other, and whichever it meant, the other would be misreported. The prebuild pack's 1,022 figure was exactly this kind of number — real-sounding, attached to nothing.
**Consequence:** every snapshot carries `method` and `evidence_ref`. `scripts/check_registry_consistency.py` fails the build when a snapshot disagrees with the auditor's current output, and `CURRICULUM_INVENTORY.md` is generated from both rather than written by hand.

## ADR-015 — Ingestion route is a per-document property
**Status:** Accepted · **Date:** 2026-09-04
**Decision:** each source document records its own `ingestion_route` — `text`, `ocr_required`, `mixed` or `structured` — determined by probing the file at catalogue time.
**Reason:** measured, not assumed. Within the 2024 May/June examiner reports, WPH11 and WPH13 decode to `(cid:N)` glyphs and need OCR, WPH12 and WPH15 extract cleanly, WPH14 and WPH16 are mixed. A corpus-level setting would be wrong for half of them. *Student Book 1* has no text layer on any of its 225 pages.
**Consequence:** `scripts/catalog_sources.py` probes and records; the pipeline dispatches on the recorded route; CI asserts the registry still matches the catalogue.

## ADR-016 — Multi-part context comes from chunk granularity, not parsed dependency edges
**Status:** Accepted · **Date:** 2026-09-04
**Decision:** one complete main question, with all its sub-parts, is one chunk. `depends_on` remains in the schema as an enhancement and is not a prerequisite for multi-part tutoring.
**Reason:** evidence. A scan of all three AS papers for explicit cross-references — "your answer to", "answer to part", "value calculated in", "use your", "obtained in" — returns **zero matches**. The whitepaper's dependency-extraction mechanism has nothing to operate on in this corpus. Chunking a whole question together gives the tutor every part's context whenever any part is retrieved, by construction rather than by parsing.
**Consequence:** LUMOS-016 is not blocked on dependency extraction. If a later session's papers do contain explicit references, `depends_on` is populated then and improves ordering; it does not gate the feature.

## ADR-017 — Licensed source material never enters version control
**Status:** Accepted · **Date:** 2026-09-04
**Decision:** `private_source_materials/` is gitignored, `.githooks/pre-commit` refuses any commit touching that path, any PDF outside `docs/`, any file over 10 MB, and any file matching a credential pattern; and a CI job fails the build if any of those are tracked.
**Reason:** the licensed material sits inside the repository working tree for convenience, which puts 125 MB of Pearson copyright one `git add -A` away from a public push. `.gitignore` alone does not survive `git add -f`.
**Consequence:** the hook needs `git config core.hooksPath .githooks` once per clone; CI is the backstop for anyone who has not run it. Derived chunk text is treated as licensed too — retrieval context only, never redistributed.

## ADR-018 — Chunk identity is derived, not assigned
**Status:** Accepted · **Date:** 2026-09-04
**Decision:** a chunk's id is `uuid5(LUMOS_CHUNK_NAMESPACE, chunk_key)`, where the key is `lumos:v<n>:<source document sha256>:<locator>`. The key is stored alongside the id.
**Reason:** two properties fall out of it that an assigned id cannot give. Determinism — the same input always yields the same id, so re-running an adapter updates rather than duplicates, which is what makes ingestion idempotent rather than merely repeatable. And collision safety — because the document's checksum is inside the key, "question 12" of WPH11 and "question 12" of WPH12 are different chunks without any paper-code or session convention having to be remembered by every adapter.
**Consequence:** `CHUNK_KEY_VERSION` is bumped only when the key *format* changes, because that re-identifies every chunk; `INGESTION_VERSION` moves independently and records which pipeline produced the text. `scripts/check_registry_consistency.py` recomputes every stored id from its key and fails the build on a mismatch, so a chunk written outside the model is caught rather than silently trusted.

## ADR-019 — Canonical document type names
**Status:** Accepted · **Date:** 2026-09-04 · **Supersedes part of ADR-009's vocabulary
**Decision:** `document_type` uses `past_paper`, `specification` and `legacy_corpus` where 0001 used `question_paper`, `syllabus` and `legacy_jsonl`. Migration 0002 renames the values and maps every existing row; the down migration maps them back.
**Reason:** one name per concept, matching how Pearson and NCTB actually refer to these documents, and matching the source-type vocabulary the product specifies. `legacy_jsonl` also named a file format rather than a role, which would have aged badly the moment a legacy corpus arrived in another format.
**Consequence:** mark schemes and examiner reports remain separate types and are never collapsed into a generic document. They carry different authority and answer different questions for a student: a mark scheme says what earns the marks, an examiner report says what candidates actually got wrong.

## ADR-020 — Three chunk counts, three meanings
**Status:** Accepted · **Date:** 2026-09-04 · **Extends ADR-014
**Decision:** an offering carries three distinct counts. **Audited** (`corpus_snapshots.record_count`) is what an auditor found in the source material. **Canonical** (`curriculum_availability.canonical_chunk_count`, computed from the chunks table) is what normalisation produced. **Indexed** (`subject_offerings.indexed_chunk_count`) is what is embedded and lexically searchable. Only the third can make a subject available.
**Reason:** after 004B the legacy corpora have 180 canonical chunks and zero indexed chunks. A single count would have to mean one or the other, and either choice misreports the rest. This is the same failure mode as the prebuild pack's 1,022 — a real-sounding number attached to nothing in particular.
**Consequence:** `canonical_chunk_count` is a view subquery, not a stored column, so it cannot be set by hand and cannot drift. The availability rule is unchanged: normalised is not searchable, so chunks existing never flips a subject to available on their own.

## ADR-021 — Provenance is recorded per chunk, and transformations keep their input
**Status:** Accepted · **Date:** 2026-09-04
**Decision:** every chunk carries `extraction_method`, `provenance_status` and, whenever the stored text differs from what extraction produced, `text_raw`. `provenance_status` is `verbatim` only when nothing changed; a transformed chunk is `cleaned`, `normalized` or `derived`, and OCR output that is not asserted exact is `ocr_uncertain`. The database refuses a transformed chunk with no raw text, and refuses an uncertainty claim from an extractor that cannot be uncertain.
**Reason:** the corpus is heterogeneous in a way that makes a corpus-level label a lie. Within one examination session some examiner reports parse cleanly and others decode to `(cid:N)` glyphs; *Student Book 1* has no text layer at all on any of 225 pages. A reader must be able to tell, per chunk, whether they are looking at what the document says or at what a pipeline made of it.
**Consequence:** the status reflects what actually happened to that chunk, not a blanket claim about the batch — of the 120 normalised ICT records, 105 are `verbatim` and 15 are `normalized`, because Unicode normalisation changed only those 15. A transformation that cannot be inspected is a transformation that cannot be trusted, so `text_raw` is never dropped.

## ADR-022 — `gemma4:e4b` is the only generation model
**Status:** Accepted · **Date:** 2026-09-04 · **Refines ADR-003**
**Decision:** Lumos generates text with `gemma4:e4b` and nothing else — `google/gemma-4-E4B-it` (Apache-2.0) on Hugging Face, `gemma4:e4b` as the Ollama tag. No Qwen, no Gemini, no GPT, and no fallback chain to a second generation model. When the model is unavailable the gateway retries and backs off against the same model, then raises. Inference is always remote; the gateway always ships a deterministic mock provider.

**Exempt — three jobs a decoder LLM cannot do:** `BAAI/bge-m3` (embeddings), `BAAI/bge-reranker-v2-m3` (cross-encoder reranking), and — **added 2026-09-04** — a document-reading model where `gemma4:e4b`'s own multimodal capability proves insufficient for OCR or page understanding. The third exemption is bounded: such a model **reads** documents and never **writes** an answer to a student. A small Qwen-VL-class or dedicated OCR model in the 0.5–4B range is permitted for extraction; the text a student reads still comes from `gemma4:e4b`. Model size across the whole system stays within roughly 0–4B parameters, which `gemma4:e4b` already satisfies.
**Reason:** a fallback to a different generation model is invisible to a student and to an evaluator. An answer produced by an unevaluated model is indistinguishable from an evaluated one, so a silent substitution converts a measured system into an unmeasured one at exactly the moment something is already going wrong. The exemptions are not a loophole: a decoder model exposes no embedding endpoint, and reranking scores a query–document *pair*, which a decoder scoring loop would do slowly, non-deterministically and without evaluation. The development machine is a 2017 MacBook Air with no GPU and 8 GB RAM, so local inference would compete with Postgres and OCR for the same memory at a few tokens per second.
**Consequence:** the legacy `Qwen2.5-VL-7B` / `gemma-4-31b-it` stack and the whitepaper §5.10 Qwen/DeepSeek stack are superseded. The Gemini client is **not ported** (`MIGRATION_MAP.md`). Model references in `RECONNAISSANCE_REPORT.md` are left alone as a dated record of what the legacy system did. Vision (Phase 2) uses gemma4:e4b's own multimodal capability rather than a separate vision model. The exact Ollama tag is still unverified — `ollama show gemma4:e4b` has not been run — and remains open under BLOCK-005.

## ADR-023 — Neon is the development database; CI keeps a container
**Status:** Accepted · **Date:** 2026-09-04 · **Refines ADR-001**
**Decision:** development runs against the provisioned Neon project (`ap-southeast-1`, PostgreSQL 18.6, pgvector 0.8.6), using the **unpooled** endpoint for migrations and for the test harness. CI continues to run against a `pgvector/pgvector:pg16` service container. The two are deliberately not the same.
**Reason:** the development machine had 3.2 GB of free disk, and Docker Desktop plus its VM disk image needs roughly 4 GB, so the documented local-container path was not available. Neon costs no local disk. Keeping CI on a container keeps the gate fast and hermetic: the suite runs in 3.9 s there against 93 s over the network to Singapore, and CI must not depend on a credential or on a third party being up.
**Consequence:** local and CI now differ in Postgres major version, 18 against 16. That is a real divergence and is accepted because the schema targets 16+ and uses no version-specific feature; a defect that appears in only one of the two is a finding, not noise, and the gate runs in both. No application or test code changed to make Neon work: this project's Neon instance has a `postgres` maintenance database, permits `pg_terminate_backend` for the owner role, and accepts `CREATE DATABASE` on both endpoints — so the planned `TEST_ADMIN_DATABASE` indirection was dropped as speculative rather than added unused.

## ADR-024 — LUMOS-004D stays the licence registry; the Model Gateway is LUMOS-004F
**Status:** Accepted · **Date:** 2026-09-04
**Decision:** `LUMOS-004D` keeps its registered meaning, the licence and provenance registry. The Model Gateway, mock provider and `gemma4:e4b` wiring are registered as a new **`LUMOS-004F`**, sequenced after LUMOS-004C and before LUMOS-008.
**Reason:** the bootstrap prompt for this session reassigned 004D to the Model Gateway, but `GOALS.md` and BLOCK-008 already used 004D for the licence registry. Two documents naming the same identifier differently is precisely the drift this project's evidence discipline exists to prevent, and the repository is the authority when a document disagrees with it. Renumbering the goal that a blocker already points at would have broken that reference silently.
**Consequence:** goal order is unchanged in substance — curriculum truth, then retrieval, then generation. `GOALS.md` now carries both 004D and 004F, and BLOCK-008's "Blocks: LUMOS-004D" reference remains correct.

## ADR-025 — LUMOS-004C is delivered in three sub-goals
**Status:** Accepted · **Date:** 2026-09-04
**Decision:** LUMOS-004C ships as `004C.1` (legacy text repair: Bangla, English re-chunking, glyph and truncation repair), `004C.2` (mark-scheme and examiner-report adapters, plus cross-document linking) and `004C.3` (textbook OCR). Each has its own acceptance criteria, its own gate run and its own commit. The published acceptance criteria are unchanged, only staged.
**Reason:** as written, 004C covers five subsystems and a 225-page OCR batch — several times the scope of 004A or 004B, each of which was one commit. Delivering it as a single commit would mean a long stretch with nothing verified, against a prime directive that exists to prevent exactly that. Splitting is not reordering: the sequence and the dependency on LUMOS-008 are untouched.
**Consequence:** three gate runs instead of one, and three points at which the corpus is provably clean rather than one. If Bangla repair fails its quality bar (BLOCK-009), 004C.1 stops there and 004C.2 and 004C.3 still proceed, instead of one large goal blocking on its hardest part.

## ADR-026 — Exam PDFs are served in the app; the textbook is not
**Status:** Accepted · **Date:** 2026-09-04 · **Owner decision** · **Supersedes** part of `docs/INGESTION_DESIGN.md` §7 rule 2
**Decision:** the 18 Edexcel exam documents — question papers, mark schemes and examiner reports for WPH11–16 — are delivered to the student as PDFs inside the application, served from Lumos's own storage. **Student Book 1 is not served**, in whole or in part, and remains retrieval grounding only: the tutor cites it and explains from it, but never reproduces its text and never serves its pages.
**Reason:** the owner's decision, taken for the BCOLBD demo, and recorded here because it reverses a standing prohibition rather than merely extending one. Two facts shaped the options put to them. Pearson publishes past papers and mark schemes openly on `qualifications.pearson.com`, restricting only the most recent twelve months to registered centres; the corpus is the June 2024 session, roughly 27 months old at the time of writing, so these specific documents are outside that restriction and are publicly obtainable. *Student Book 1* is not comparable — it is a commercial textbook sold by Pearson, not free courseware, which is why it is excluded rather than treated the same way.
**Consequence:** three things follow. First, `docs/INGESTION_DESIGN.md` §7 rule 2 no longer holds unqualified: "no page image is served to a student" now applies to the textbook and to any future commercial source, not to the exam documents. Second, the registry cannot currently express this — the textbook and the exam papers both sit at `licence_status = 'permitted_private'`, and nothing distinguishes "servable in the app" from "grounding only". That distinction is now load-bearing and needs a column; it lands as a migration in LUMOS-004C.2, not before. Third, serving files needs storage, so BLOCK-003 (R2) moves onto the critical path for the demo, where it previously was not.

**The alternative that was not chosen** is recorded because it may become preferable: linking to Pearson's own hosted URLs rather than serving copies distributes nothing at all, costs no storage, and is easier to defend to an evaluator. It was declined in favour of controlling the in-app viewing experience and working offline. If the licensing question is ever raised, that is the fallback.
