-- Reverse 0003_retrieval.
--
-- Order matters: the view reads the columns, so it goes first. 0002's down
-- migration had this exact bug — it dropped `chunks` before the view that reads
-- it, and reversal failed.

BEGIN;

DROP VIEW IF EXISTS offering_index_state;

DROP INDEX IF EXISTS chunks_embedding_idx;
DROP INDEX IF EXISTS chunks_search_vector_idx;
DROP INDEX IF EXISTS chunks_offering_type_idx;

ALTER TABLE chunks
    DROP CONSTRAINT IF EXISTS chunk_embedding_needs_model;

ALTER TABLE chunks
    DROP COLUMN IF EXISTS search_vector,
    DROP COLUMN IF EXISTS embedding,
    DROP COLUMN IF EXISTS embedding_model,
    DROP COLUMN IF EXISTS embedded_at;

ALTER TABLE source_documents
    DROP CONSTRAINT IF EXISTS document_served_needs_object_key;

ALTER TABLE source_documents
    DROP COLUMN IF EXISTS delivery,
    DROP COLUMN IF EXISTS object_key;

DROP TYPE IF EXISTS delivery_mode;

DELETE FROM schema_migrations WHERE version = '0003_retrieval';

COMMIT;
