-- Reverse of 0002_canonical_chunks.up.sql.
--
-- Restores the schema to exactly its 0001 state: the canonical chunk model is
-- removed, curriculum_availability is rebuilt without canonical_chunk_count, and
-- document_type is mapped back to the 0001 value names.
--
-- Chunk rows are dropped. That is correct — they are derived from source
-- documents by a deterministic, idempotent adapter, so re-running normalisation
-- reproduces them exactly. Nothing unrecoverable is lost.

BEGIN;

-- Both views must go before the table they read. The 0002 availability view
-- counts chunks, so dropping `chunks` first fails on the dependency.
DROP VIEW  IF EXISTS chunk_retrieval_context;
DROP VIEW  IF EXISTS curriculum_availability;

DROP TABLE IF EXISTS normalisation_runs;
DROP TABLE IF EXISTS chunks;

DROP TYPE IF EXISTS provenance_status;
DROP TYPE IF EXISTS extraction_method;
DROP TYPE IF EXISTS chunk_type;

-- ── restore the 0001 availability view ───────────────────────────────────────

CREATE VIEW curriculum_availability AS
SELECT
    o.id                AS offering_id,
    o.slug,
    c.code              AS curriculum_code,
    c.name              AS curriculum_name,
    s.code              AS subject_code,
    s.name_en           AS subject_name_en,
    s.name_bn           AS subject_name_bn,
    l.code              AS level_code,
    l.name              AS level_name,
    l.sort_order        AS level_sort_order,
    sv.code             AS syllabus_version_code,
    sv.specification_reference,
    o.languages,
    o.publication_status,
    o.indexing_status,
    o.evaluation_status,
    o.licence_status,
    o.indexed_chunk_count,
    o.source_priority_policy,
    o.display_note_en,
    o.display_note_bn,
    (SELECT count(*) FROM source_documents sd WHERE sd.offering_id = o.id)
                        AS source_document_count,

    (
        o.publication_status = 'published'
        AND o.indexing_status   = 'indexed'
        AND o.evaluation_status = 'passed'
        AND o.indexed_chunk_count > 0
        AND o.licence_status IN ('permitted_private', 'permitted_public')
        AND o.syllabus_version_id IS NOT NULL
        AND cardinality(o.languages) > 0
        AND EXISTS (SELECT 1 FROM source_documents sd WHERE sd.offering_id = o.id)
    )                   AS is_available,

    ARRAY_REMOVE(ARRAY[
        CASE WHEN o.publication_status <> 'published'
             THEN 'publication_status=' || o.publication_status::text END,
        CASE WHEN o.indexing_status <> 'indexed'
             THEN 'indexing_status=' || o.indexing_status::text END,
        CASE WHEN o.evaluation_status <> 'passed'
             THEN 'evaluation_status=' || o.evaluation_status::text END,
        CASE WHEN o.indexed_chunk_count <= 0
             THEN 'no_indexed_chunks' END,
        CASE WHEN o.licence_status NOT IN ('permitted_private', 'permitted_public')
             THEN 'licence_status=' || o.licence_status::text END,
        CASE WHEN o.syllabus_version_id IS NULL
             THEN 'no_syllabus_version' END,
        CASE WHEN cardinality(o.languages) = 0
             THEN 'no_languages' END,
        CASE WHEN NOT EXISTS (SELECT 1 FROM source_documents sd WHERE sd.offering_id = o.id)
             THEN 'no_source_documents' END
    ], NULL)            AS blocked_reasons

FROM subject_offerings o
JOIN curricula c ON c.id = o.curriculum_id
JOIN subjects  s ON s.id = o.subject_id
JOIN levels    l ON l.id = o.level_id
LEFT JOIN syllabus_versions sv ON sv.id = o.syllabus_version_id;

COMMENT ON VIEW curriculum_availability IS
    'The single definition of subject availability. The API rejects any request '
    'for an offering where is_available is false, before retrieval runs.';

-- ── restore the 0001 document_type names ─────────────────────────────────────

CREATE TYPE document_type_v1 AS ENUM (
    'syllabus',
    'mark_scheme',
    'examiner_report',
    'question_paper',
    'textbook',
    'revision_guide',
    'topic_notes',
    'lab_guide',
    'legacy_jsonl',
    'unknown'
);

ALTER TABLE source_documents
    ALTER COLUMN document_type TYPE document_type_v1
    USING (
        CASE document_type::text
            WHEN 'past_paper'    THEN 'question_paper'
            WHEN 'specification' THEN 'syllabus'
            WHEN 'legacy_corpus' THEN 'legacy_jsonl'
            ELSE document_type::text
        END
    )::document_type_v1;

DROP TYPE document_type;
ALTER TYPE document_type_v1 RENAME TO document_type;

DELETE FROM schema_migrations WHERE version = '0002_canonical_chunks';

COMMIT;
