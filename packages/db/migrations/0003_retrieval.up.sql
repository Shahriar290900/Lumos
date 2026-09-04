-- 0003_retrieval — semantic and lexical search over canonical chunks.
--
-- ADR-001: one store. The metadata filter, the vector search and the lexical
-- search all execute inside Postgres, in one query, so curriculum isolation
-- (ADR-006) happens at the SQL boundary and cannot be forgotten by a caller.
-- This is also the fix for the legacy defect where FAISS searched globally and
-- the metadata filter ran afterwards on the top-k result, which could return
-- zero in-scope chunks.
--
-- ADR-026 arrives here too: `source_documents.delivery` finally distinguishes a
-- document that may be served to a student from one that may only ground an
-- answer. Until now the textbook and the exam papers were indistinguishable at
-- `licence_status = 'permitted_private'`, and that distinction is load-bearing.

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. Embeddings
-- ─────────────────────────────────────────────────────────────────────────────

-- 1024 dimensions, because BAAI/bge-m3 produces 1024 and the mock provider
-- matches it. A column sized for anything else would let a dimension mismatch
-- stay hidden until the day a real provider is switched on.
ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS embedding vector(1024),
    ADD COLUMN IF NOT EXISTS embedding_model text,
    ADD COLUMN IF NOT EXISTS embedded_at timestamptz;

-- An embedding without the model that produced it cannot be invalidated when
-- the model changes, and an embedding from a different model is worse than none:
-- it ranks confidently and wrongly.
ALTER TABLE chunks
    DROP CONSTRAINT IF EXISTS chunk_embedding_needs_model;
ALTER TABLE chunks
    ADD CONSTRAINT chunk_embedding_needs_model
        CHECK (embedding IS NULL OR (embedding_model IS NOT NULL AND embedded_at IS NOT NULL));

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. Lexical search
-- ─────────────────────────────────────────────────────────────────────────────
--
-- `simple` rather than `english`, deliberately. The corpus is bilingual, and
-- Postgres has no Bangla stemmer; the `english` configuration would stem English
-- and mangle nothing in Bangla, but it would also strip English stopwords that
-- carry meaning in a physics question ("no", "not", "between"). `simple` keeps
-- every token, which costs some English recall and keeps Bangla honest. The
-- reranker recovers the precision.
ALTER TABLE chunks
    ADD COLUMN IF NOT EXISTS search_vector tsvector
    GENERATED ALWAYS AS (
        setweight(to_tsvector('simple', coalesce(topic, '')), 'A') ||
        setweight(to_tsvector('simple', coalesce(section_ref, '')), 'B') ||
        setweight(to_tsvector('simple', text), 'C')
    ) STORED;

CREATE INDEX IF NOT EXISTS chunks_search_vector_idx ON chunks USING gin (search_vector);

-- HNSW over cosine distance. Built unconditionally: at a few hundred chunks a
-- sequential scan would be faster, but the index has to exist and be correct
-- before the corpus grows, and a missing index is discovered at the worst time.
CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops);

-- The metadata filter runs first, so it needs its own index (ADR-006).
CREATE INDEX IF NOT EXISTS chunks_offering_type_idx
    ON chunks (offering_id, chunk_type);

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. Document delivery (ADR-026)
-- ─────────────────────────────────────────────────────────────────────────────

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'delivery_mode') THEN
        CREATE TYPE delivery_mode AS ENUM (
            'none',        -- never served: grounding only. Student Book 1.
            'in_app_pdf'   -- served to a student as a PDF. The 18 exam documents.
        );
    END IF;
END$$;

ALTER TABLE source_documents
    ADD COLUMN IF NOT EXISTS delivery delivery_mode NOT NULL DEFAULT 'none',
    ADD COLUMN IF NOT EXISTS object_key text;

COMMENT ON COLUMN source_documents.delivery IS
    'ADR-026. in_app_pdf may be served to a student; none is retrieval grounding '
    'only. Defaults to none so a newly registered document is never servable by '
    'accident — serving is the exception and has to be asserted.';

COMMENT ON COLUMN source_documents.object_key IS
    'Key in the R2 bucket. Null until uploaded. Never a public URL: delivery is '
    'by short-lived presigned URL, so access can be withdrawn.';

-- A document cannot be served if nobody knows where it is.
ALTER TABLE source_documents
    DROP CONSTRAINT IF EXISTS document_served_needs_object_key;
ALTER TABLE source_documents
    ADD CONSTRAINT document_served_needs_object_key
        CHECK (delivery <> 'in_app_pdf' OR object_key IS NOT NULL);

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. Indexed counts follow the embeddings
-- ─────────────────────────────────────────────────────────────────────────────
--
-- ADR-020 keeps three counts with three meanings, and `indexed_chunk_count` is
-- the only one that can make a subject available. It is now derived from what is
-- actually embedded, so it cannot be set by hand to something optimistic.
CREATE OR REPLACE VIEW offering_index_state AS
SELECT
    o.id                                   AS offering_id,
    o.slug,
    count(c.id)                            AS canonical_chunks,
    count(c.embedding)                     AS embedded_chunks,
    count(*) FILTER (WHERE c.search_vector IS NOT NULL) AS lexical_chunks,
    min(c.embedded_at)                     AS first_embedded_at,
    max(c.embedded_at)                     AS last_embedded_at,
    count(DISTINCT c.embedding_model)      AS embedding_models_used
FROM subject_offerings o
LEFT JOIN chunks c ON c.offering_id = o.id
GROUP BY o.id, o.slug;

COMMENT ON VIEW offering_index_state IS
    'What is actually searchable per offering. embedded_chunks is the number '
    'that matters: a chunk without an embedding is invisible to semantic '
    'retrieval however good its text is.';

INSERT INTO schema_migrations (version) VALUES ('0003_retrieval')
ON CONFLICT (version) DO NOTHING;

COMMIT;
