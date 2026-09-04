-- LUMOS-004B — Canonical chunk model
--
-- One representation that all curriculum content normalises into, whatever it
-- came from: legacy JSONL, a scanned textbook, an exam paper, a mark scheme, an
-- examiner report. Adding a curriculum or a source type must not require
-- changing this table.
--
-- Three things this schema refuses to lose:
--
--   provenance   every chunk resolves to source -> document -> location, and the
--                document resolves to an exact file by SHA-256
--   authority    mark schemes, examiner reports, past papers, specifications and
--                textbooks stay distinguishable, because they carry different
--                weight in retrieval (ADR-009)
--   uncertainty  OCR output is never presented as though it were exact
--
-- Depends on 0001_curriculum_registry.
--
-- ADR-006  curriculum isolation precedes retrieval
-- ADR-009  source priority is a ranking feature
-- ADR-014  audited / canonical / indexed counts are separate things
-- ADR-016  depends_on is optional; question grouping supplies multi-part context
-- ADR-018  deterministic chunk identity (this migration)
-- ADR-019  canonical document types (this migration)

BEGIN;

-- ─────────────────────────────────────────────────────────────────────────────
-- Canonical document types
-- ─────────────────────────────────────────────────────────────────────────────
--
-- 0001 used `question_paper`, `syllabus` and `legacy_jsonl`. The canonical names
-- are `past_paper`, `specification` and `legacy_corpus` — one name per concept,
-- matching how Pearson and NCTB actually refer to these documents. This is a
-- rename of existing values, not a new taxonomy: every 0001 row maps onto
-- exactly one new value and nothing is reclassified.

CREATE TYPE document_type_v2 AS ENUM (
    'specification',      -- the published syllabus / specification document
    'past_paper',         -- an examination question paper
    'mark_scheme',        -- the official answers and mark allocations
    'examiner_report',    -- examiner commentary on candidate performance
    'textbook',           -- core textbook
    'revision_guide',
    'topic_notes',
    'lab_guide',
    'legacy_corpus',      -- pre-Lumos JSONL, provenance partially unknown
    'unknown'
);

ALTER TABLE source_documents
    ALTER COLUMN document_type TYPE document_type_v2
    USING (
        CASE document_type::text
            WHEN 'question_paper' THEN 'past_paper'
            WHEN 'syllabus'       THEN 'specification'
            WHEN 'legacy_jsonl'   THEN 'legacy_corpus'
            ELSE document_type::text
        END
    )::document_type_v2;

DROP TYPE document_type;
ALTER TYPE document_type_v2 RENAME TO document_type;

COMMENT ON COLUMN source_documents.document_type IS
    'What kind of document this is. Mark schemes and examiner reports are never '
    'collapsed into a generic type: they carry different authority and answer '
    'different questions for a student.';

-- ─────────────────────────────────────────────────────────────────────────────
-- Chunk enumerations
-- ─────────────────────────────────────────────────────────────────────────────

-- What a chunk *is*, which is not the same as what document it came from: an
-- examiner report yields commentary chunks, a past paper yields question chunks.
CREATE TYPE chunk_type AS ENUM (
    'exam_question',        -- one complete main question, all sub-parts together
    'mark_scheme_answer',   -- the official answer to one question
    'examiner_commentary',  -- examiner remarks on one question
    'textbook_section',
    'specification_point',
    'legacy_record',        -- a legacy JSONL record, normalised but not re-chunked
    'unknown'
);

-- How the text was obtained. Recorded per chunk because it varies within a
-- single document, let alone within a corpus (ADR-015).
CREATE TYPE extraction_method AS ENUM (
    'pdf_text_layer',    -- parsed from an embedded text layer
    'ocr_tesseract',     -- rendered and OCR'd; not exact
    'structured_jsonl',  -- read from an already-structured record
    'manual',            -- entered or corrected by a person
    'unknown'
);

-- How far the stored text has travelled from the source. The point of this
-- column is that a reader can tell whether they are looking at what the document
-- says or at what a pipeline made of it.
CREATE TYPE provenance_status AS ENUM (
    'verbatim',        -- byte-for-byte what extraction produced
    'cleaned',         -- boilerplate and layout noise removed; wording untouched
    'normalized',      -- Unicode / whitespace / spelling normalisation applied
    'derived',         -- assembled or repaired using another source
    'ocr_uncertain'    -- OCR output below confidence; explicitly not asserted exact
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Chunks
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE chunks (
    -- Deterministic: uuid5(LUMOS_CHUNK_NAMESPACE, chunk_key). Re-running
    -- normalisation over unchanged input produces the same id, which is what
    -- makes ingestion idempotent rather than merely re-runnable (ADR-018).
    id uuid PRIMARY KEY,

    -- The natural key the id is derived from. Stored so identity is auditable
    -- rather than opaque: 'lumos:v1:<document sha256>:<locator>'.
    -- The document checksum is inside the key, so the same logical question from
    -- a different paper or session cannot collide.
    chunk_key text NOT NULL UNIQUE,

    source_document_id uuid NOT NULL REFERENCES source_documents(id)  ON DELETE CASCADE,

    -- The isolation key. Retrieval filters on this before any ranking, so
    -- cross-curriculum contamination is structurally impossible rather than
    -- merely discouraged (ADR-006).
    offering_id        uuid NOT NULL REFERENCES subject_offerings(id) ON DELETE CASCADE,

    chunk_type chunk_type NOT NULL,
    ordinal    int NOT NULL DEFAULT 0,          -- order within the document

    -- ── location ─────────────────────────────────────────────────────────────
    page_number     int,
    page_number_end int,
    section_ref     text,        -- chapter, unit, or textbook section label
    topic           text,
    syllabus_reference text,     -- e.g. '5.6.154'; NULL when the source gives none

    -- ── exam structure ───────────────────────────────────────────────────────
    question_number text,        -- '12'
    sub_question    text,        -- '(c)(ii)'. NULL on a whole-question chunk.
    marks           int,

    -- Sub-parts detected inside a whole-question chunk, recorded WITHOUT
    -- splitting it. Keeping the parts together is what supplies multi-part
    -- context; this array is for display, navigation and evaluation (ADR-016).
    sub_parts jsonb NOT NULL DEFAULT '[]'::jsonb,

    parent_chunk_id uuid REFERENCES chunks(id) ON DELETE SET NULL,

    -- Optional, and deliberately so. No explicit dependency cross-reference was
    -- found in any audited AS paper, so ingestion must never require this
    -- (ADR-016). Empty is the normal case, not a gap.
    depends_on uuid[] NOT NULL DEFAULT '{}',

    -- ── content ──────────────────────────────────────────────────────────────
    text     text NOT NULL,
    -- What extraction produced, when the stored text differs from it. NULL means
    -- text IS the raw extraction. Never dropped: a transformation you cannot
    -- inspect is a transformation you cannot trust.
    text_raw text,
    content_sha256 text NOT NULL,   -- of `text`; cross-document duplicate detection

    -- Hash of every persisted field. Lets a re-run tell "unchanged" from
    -- "updated" without a field-by-field comparison, which is what makes
    -- idempotency measurable rather than merely asserted.
    row_fingerprint text NOT NULL,

    language text NOT NULL DEFAULT 'unknown',

    -- Recomputed at normalisation. legacy_token_count preserves whatever the
    -- source claimed, which disagreed with reality on 134 of 180 legacy records
    -- and is therefore recorded but never trusted.
    token_count        int,
    legacy_token_count int,

    keywords          text[] NOT NULL DEFAULT '{}',
    prerequisite_text text,      -- legacy free text; not yet resolved to IDs

    -- ── legacy traceability ──────────────────────────────────────────────────
    legacy_chunk_id text,        -- e.g. 'SSC-ICT-C1-P1-CH1'
    -- The original record, kept whole. Normalisation is then always reversible
    -- and reviewable, and no legacy field is lost because the canonical model
    -- had nowhere to put it.
    legacy_metadata jsonb,

    -- ── provenance ───────────────────────────────────────────────────────────
    extraction_method     extraction_method NOT NULL DEFAULT 'unknown',
    provenance_status     provenance_status NOT NULL DEFAULT 'verbatim',
    extraction_confidence numeric(5,4),   -- 0..1 where the extractor reports it
    ingestion_version     text NOT NULL,

    notes      text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    -- ── integrity ────────────────────────────────────────────────────────────
    CONSTRAINT chunk_text_not_empty       CHECK (length(btrim(text)) > 0),
    CONSTRAINT chunk_sha_shape            CHECK (content_sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chunk_fingerprint_shape    CHECK (row_fingerprint ~ '^[0-9a-f]{64}$'),
    CONSTRAINT chunk_key_shape            CHECK (chunk_key ~ '^lumos:v[0-9]+:[0-9a-f]{64}:.+$'),
    CONSTRAINT chunk_ordinal_non_negative CHECK (ordinal >= 0),
    CONSTRAINT chunk_marks_non_negative   CHECK (marks IS NULL OR marks >= 0),
    CONSTRAINT chunk_pages_ordered
        CHECK (page_number_end IS NULL OR page_number IS NULL OR page_number_end >= page_number),
    CONSTRAINT chunk_confidence_range
        CHECK (extraction_confidence IS NULL OR extraction_confidence BETWEEN 0 AND 1),
    -- 'unknown' is a legitimate, explicit value. Guessing is not.
    CONSTRAINT chunk_language_shape CHECK (language ~ '^([a-z]{2}|unknown)$'),
    CONSTRAINT chunk_not_own_parent CHECK (parent_chunk_id IS NULL OR parent_chunk_id <> id),

    -- A question chunk without a question number is not a question chunk.
    CONSTRAINT chunk_exam_needs_question_number
        CHECK (chunk_type NOT IN ('exam_question', 'mark_scheme_answer', 'examiner_commentary')
               OR question_number IS NOT NULL),

    -- Legacy records must stay traceable to the identifier they arrived with.
    CONSTRAINT chunk_legacy_needs_legacy_id
        CHECK (chunk_type <> 'legacy_record' OR legacy_chunk_id IS NOT NULL),

    -- Uncertainty may only be claimed by an extractor that can be uncertain.
    CONSTRAINT chunk_ocr_uncertainty_needs_ocr
        CHECK (provenance_status <> 'ocr_uncertain' OR extraction_method = 'ocr_tesseract'),

    -- If the text was transformed, the untransformed text must still be there.
    CONSTRAINT chunk_transformed_keeps_raw
        CHECK (provenance_status IN ('verbatim', 'ocr_uncertain') OR text_raw IS NOT NULL)
);

COMMENT ON TABLE chunks IS
    'The canonical content model. Every curriculum source normalises into this '
    'table; retrieval indexes are built from it and are never the source of truth.';

COMMENT ON COLUMN chunks.chunk_key IS
    'lumos:v<n>:<source document sha256>:<locator>. The document checksum makes '
    'identity collision across papers or sessions impossible.';

COMMENT ON COLUMN chunks.sub_parts IS
    'Sub-parts detected inside a whole-question chunk, recorded without splitting '
    'it. The parts stay together; this is metadata about them.';

COMMENT ON COLUMN chunks.depends_on IS
    'Optional. No explicit dependency cross-reference was found in any audited AS '
    'paper, so this is an enhancement and never a prerequisite for ingestion.';

COMMENT ON COLUMN chunks.text_raw IS
    'Extraction output before transformation, when the stored text differs. NULL '
    'means text is the raw extraction.';

-- The hot filter (ADR-006), then the shapes retrieval and evaluation ask for.
CREATE INDEX chunks_offering_idx          ON chunks (offering_id);
CREATE INDEX chunks_offering_type_idx     ON chunks (offering_id, chunk_type);
CREATE INDEX chunks_source_document_idx   ON chunks (source_document_id);
CREATE INDEX chunks_content_sha_idx       ON chunks (content_sha256);
CREATE INDEX chunks_question_idx          ON chunks (offering_id, question_number)
    WHERE question_number IS NOT NULL;
CREATE INDEX chunks_legacy_id_idx         ON chunks (legacy_chunk_id)
    WHERE legacy_chunk_id IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- Normalisation runs
-- ─────────────────────────────────────────────────────────────────────────────
--
-- Every run records what it processed and what it produced, so a count in a
-- document always has a run behind it. This is the same discipline as
-- corpus_snapshots, applied one stage later.

CREATE TABLE normalisation_runs (
    id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    offering_id       uuid REFERENCES subject_offerings(id) ON DELETE CASCADE,
    adapter           text NOT NULL,          -- 'legacy_jsonl', 'past_paper', ...
    ingestion_version text NOT NULL,
    source_records    int  NOT NULL DEFAULT 0,
    chunks_created    int  NOT NULL DEFAULT 0,
    chunks_updated    int  NOT NULL DEFAULT 0,
    chunks_unchanged  int  NOT NULL DEFAULT 0,
    duplicates_seen   int  NOT NULL DEFAULT 0,
    warnings          jsonb NOT NULL DEFAULT '[]'::jsonb,
    started_at        timestamptz NOT NULL DEFAULT now(),
    finished_at       timestamptz,
    CONSTRAINT run_counts_non_negative
        CHECK (source_records >= 0 AND chunks_created >= 0
               AND chunks_updated >= 0 AND chunks_unchanged >= 0
               AND duplicates_seen >= 0)
);

CREATE INDEX normalisation_runs_offering_idx
    ON normalisation_runs (offering_id, started_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- Retrieval context
-- ─────────────────────────────────────────────────────────────────────────────
--
-- Everything the retrieval layer needs about a chunk, in one place: curriculum
-- identity for the pre-ranking filter, document authority for source priority,
-- and provenance for citation. Retrieval reads this view; it never re-derives
-- authority from chunk fields, so ranking logic stays out of chunk identity.

CREATE VIEW chunk_retrieval_context AS
SELECT
    c.id                AS chunk_id,
    c.chunk_key,
    c.chunk_type,
    c.ordinal,
    c.text,
    c.content_sha256,
    c.language,
    c.token_count,
    c.keywords,

    -- location, for citation
    c.page_number,
    c.page_number_end,
    c.section_ref,
    c.topic,
    c.syllabus_reference,
    c.question_number,
    c.sub_question,
    c.marks,
    c.sub_parts,
    c.depends_on,

    -- provenance, for honesty about what the text is
    c.extraction_method,
    c.provenance_status,
    c.extraction_confidence,
    c.ingestion_version,
    c.legacy_chunk_id,

    -- document identity and authority
    sd.id               AS source_document_id,
    sd.document_type,
    sd.source_priority,
    sd.title            AS document_title,
    sd.filename         AS document_filename,
    sd.sha256           AS document_sha256,
    sd.paper_code,
    sd.unit_number,
    sd.session_year,
    sd.session_series,
    sd.is_private,
    sd.licence_status   AS document_licence_status,

    -- curriculum identity, for the pre-ranking filter
    o.id                AS offering_id,
    o.slug              AS offering_slug,
    o.publication_status,
    o.indexing_status,
    cur.code            AS curriculum_code,
    sub.code            AS subject_code,
    lvl.code            AS level_code,
    sv.code             AS syllabus_version_code

FROM chunks c
JOIN source_documents  sd  ON sd.id  = c.source_document_id
JOIN subject_offerings o   ON o.id   = c.offering_id
JOIN curricula         cur ON cur.id = o.curriculum_id
JOIN subjects          sub ON sub.id = o.subject_id
JOIN levels            lvl ON lvl.id = o.level_id
LEFT JOIN syllabus_versions sv ON sv.id = o.syllabus_version_id;

COMMENT ON VIEW chunk_retrieval_context IS
    'What retrieval reads. Carries source_priority so authority survives fusion '
    'and reranking as a feature, without ranking logic entering chunk identity.';

-- ─────────────────────────────────────────────────────────────────────────────
-- Availability, extended
-- ─────────────────────────────────────────────────────────────────────────────
--
-- Adds canonical_chunk_count, computed from the chunks table rather than stored,
-- so it cannot be set by hand and cannot drift. Three counts now exist and mean
-- three different things (ADR-014, extended by ADR-020):
--
--   audited   what an auditor counted in the source material  (corpus_snapshots)
--   canonical what normalisation produced                     (this column)
--   indexed   what is embedded and lexically searchable       (indexed_chunk_count)
--
-- The availability rule is unchanged: it still requires indexed_chunk_count > 0,
-- because normalised is not searchable.

DROP VIEW curriculum_availability;

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
    (SELECT count(*) FROM chunks ch WHERE ch.offering_id = o.id)
                        AS canonical_chunk_count,

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

INSERT INTO schema_migrations (version) VALUES ('0002_canonical_chunks')
ON CONFLICT (version) DO NOTHING;

COMMIT;
