-- LUMOS-004A — Curriculum Registry + Coverage Gates
--
-- Makes the database, not a document or a UI card, the authority on what
-- curriculum content Lumos actually holds.
--
-- Context (RECONNAISSANCE_REPORT.md §C.2.8): the legacy Shikhbo desktop app
-- shipped a বাংলা subject button in a tagged v1.0.0 release with no Bangla
-- corpus behind it. Selecting it produced ungrounded model output that looked
-- like tutoring. This schema exists so that cannot happen again: availability is
-- computed from evidence, in one place, and the API refuses anything the view
-- does not mark available.
--
-- ADR-006  curriculum isolation precedes retrieval
-- ADR-009  source priority is a ranking feature
-- ADR-011  availability is registry-driven
--
-- Requires: PostgreSQL 16+, pgvector (enabled here for later goals).

BEGIN;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()

-- ─────────────────────────────────────────────────────────────────────────────
-- Enumerations
-- ─────────────────────────────────────────────────────────────────────────────

-- How far a corpus has progressed through the ingestion pipeline.
CREATE TYPE indexing_status AS ENUM (
    'not_started',          -- nothing done
    'sources_catalogued',   -- documents identified and checksummed, not parsed
    'normalising',          -- legacy records being mapped to the canonical schema
    'ingesting',            -- extraction / chunking / embedding in progress
    'indexed',              -- chunks are in the store and searchable
    'failed'
);

-- Whether retrieval quality has been measured for this corpus.
CREATE TYPE evaluation_status AS ENUM (
    'none',
    'set_in_preparation',
    'in_progress',
    'passed',
    'failed'
);

-- What the product intends to do with this offering. Distinct from indexing:
-- a corpus can be fully indexed and still deliberately unpublished.
CREATE TYPE publication_status AS ENUM (
    'hidden',           -- not shown in the UI at all
    'planned',          -- shown as "coming soon"; no corpus exists
    'in_preparation',   -- shown as "in preparation"; a real corpus exists but is not ready
    'published'         -- shown as available; may be queried
);

-- Whether we are permitted to use the source, and how far.
-- Deliberately conservative: 'unknown' blocks publication.
CREATE TYPE licence_status AS ENUM (
    'unknown',              -- default; blocks publication
    'permitted_private',    -- may be ingested and used locally / for private evaluation
    'permitted_public',     -- may back a publicly available offering
    'restricted'            -- must not be ingested
);

-- Chosen from the document itself at catalogue time; decides the ingest route.
CREATE TYPE ingestion_route AS ENUM (
    'text',           -- usable text layer; parse directly
    'ocr_required',   -- scanned, or fonts with no ToUnicode map
    'mixed',          -- some pages parse, some need OCR
    'structured',     -- already-structured input, e.g. legacy JSONL
    'unknown'
);

-- Source hierarchy. Lower number = more authoritative (ADR-009).
CREATE TYPE document_type AS ENUM (
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

-- ─────────────────────────────────────────────────────────────────────────────
-- Curriculum hierarchy
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE curricula (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    code        text NOT NULL UNIQUE,          -- 'NCTB', 'EDEXCEL_IAL'
    name        text NOT NULL,
    awarding_body text,
    region      text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT curricula_code_shape CHECK (code ~ '^[A-Z][A-Z0-9_]{1,31}$')
);

COMMENT ON TABLE curricula IS
    'Awarding bodies / national curricula. The outermost isolation boundary: no '
    'retrieval may cross a curriculum.';

CREATE TABLE syllabus_versions (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    curriculum_id  uuid NOT NULL REFERENCES curricula(id) ON DELETE CASCADE,
    code           text NOT NULL,              -- 'IAL_PHYSICS_2018'
    name           text NOT NULL,
    effective_from date,
    effective_to   date,
    -- Free-text reference to the specification document. NULL means we have not
    -- verified which specification edition this corpus follows, which is itself
    -- a publication blocker.
    specification_reference text,
    notes          text,
    created_at     timestamptz NOT NULL DEFAULT now(),
    UNIQUE (curriculum_id, code),
    CONSTRAINT syllabus_dates_ordered
        CHECK (effective_to IS NULL OR effective_from IS NULL OR effective_to >= effective_from)
);

COMMENT ON COLUMN syllabus_versions.specification_reference IS
    'Which published specification this corpus is aligned to. Spec drift is a '
    'stated product risk; retrieval filters on syllabus_version_id.';

CREATE TABLE subjects (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    curriculum_id uuid NOT NULL REFERENCES curricula(id) ON DELETE CASCADE,
    code          text NOT NULL,               -- 'PHYSICS', 'ICT', 'BANGLA'
    name_en       text NOT NULL,
    name_bn       text,
    created_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (curriculum_id, code),
    CONSTRAINT subjects_code_shape CHECK (code ~ '^[A-Z][A-Z0-9_]{1,31}$')
);

CREATE TABLE levels (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    curriculum_id uuid NOT NULL REFERENCES curricula(id) ON DELETE CASCADE,
    code          text NOT NULL,               -- 'SSC', 'HSC', 'INTERNATIONAL_AS', 'IAL_A2'
    name          text NOT NULL,
    sort_order    int  NOT NULL DEFAULT 0,
    UNIQUE (curriculum_id, code)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- Offerings — the unit of availability
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE subject_offerings (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    curriculum_id       uuid NOT NULL REFERENCES curricula(id)         ON DELETE CASCADE,
    subject_id          uuid NOT NULL REFERENCES subjects(id)          ON DELETE CASCADE,
    level_id            uuid NOT NULL REFERENCES levels(id)            ON DELETE CASCADE,
    syllabus_version_id uuid          REFERENCES syllabus_versions(id) ON DELETE SET NULL,

    slug                text NOT NULL UNIQUE,  -- 'edexcel-ial/physics/international-as'

    languages           text[] NOT NULL DEFAULT '{}',   -- ISO 639-1: {'en'}, {'bn','en'}

    publication_status  publication_status NOT NULL DEFAULT 'hidden',
    indexing_status     indexing_status    NOT NULL DEFAULT 'not_started',
    evaluation_status   evaluation_status  NOT NULL DEFAULT 'none',
    licence_status      licence_status     NOT NULL DEFAULT 'unknown',

    -- Maintained by the ingestion pipeline; 0 until chunks actually exist.
    indexed_chunk_count int NOT NULL DEFAULT 0,

    -- Ordered document_type list, most authoritative first (ADR-009).
    source_priority_policy jsonb NOT NULL DEFAULT '[]'::jsonb,

    -- Shown to the student when the offering is not available. Required for
    -- anything visible-but-unavailable, so the UI never has to invent copy.
    display_note_en text,
    display_note_bn text,

    notes       text,
    created_at  timestamptz NOT NULL DEFAULT now(),
    updated_at  timestamptz NOT NULL DEFAULT now(),

    UNIQUE (curriculum_id, subject_id, level_id, syllabus_version_id),

    CONSTRAINT offering_chunk_count_non_negative CHECK (indexed_chunk_count >= 0),

    -- An offering claiming to be indexed must have chunks to show for it.
    CONSTRAINT offering_indexed_implies_chunks
        CHECK (indexing_status <> 'indexed' OR indexed_chunk_count > 0),

    -- Anything the student can see but not use must explain itself.
    CONSTRAINT offering_visible_unavailable_needs_note
        CHECK (publication_status NOT IN ('planned', 'in_preparation')
               OR display_note_en IS NOT NULL),

    -- Nothing is published on an unknown or restricted licence.
    CONSTRAINT offering_published_needs_licence
        CHECK (publication_status <> 'published'
               OR licence_status IN ('permitted_private', 'permitted_public')),

    CONSTRAINT offering_languages_not_empty
        CHECK (publication_status <> 'published' OR cardinality(languages) > 0)
);

COMMENT ON TABLE subject_offerings IS
    'One row per (curriculum, subject, level, syllabus version). This is the unit '
    'a student selects and the unit availability is computed over.';

COMMENT ON COLUMN subject_offerings.source_priority_policy IS
    'Ordered JSON array of document_type values, most authoritative first. '
    'Carried into retrieval as a ranking feature, never as a hard pre-filter.';

-- The hot path: the metadata filter applied before any ranking (ADR-006).
CREATE INDEX subject_offerings_lookup_idx
    ON subject_offerings (curriculum_id, subject_id, level_id);
CREATE INDEX subject_offerings_publication_idx
    ON subject_offerings (publication_status)
    WHERE publication_status <> 'hidden';

-- ─────────────────────────────────────────────────────────────────────────────
-- Source documents
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE source_documents (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    offering_id   uuid NOT NULL REFERENCES subject_offerings(id) ON DELETE CASCADE,

    document_type   document_type NOT NULL,
    source_priority int NOT NULL,             -- 1 official, 2 core textbook, 3 supplementary

    title          text NOT NULL,
    filename       text,
    -- Path relative to the private materials root, or a repo-relative path for
    -- legacy JSONL. Never an absolute path from anyone's machine.
    relative_path  text,
    -- Object-storage key once the document is uploaded to R2. NULL while the
    -- document exists only on a local disk.
    storage_key    text,

    sha256         text,
    bytes          bigint,
    page_count     int,
    ingestion_route ingestion_route NOT NULL DEFAULT 'unknown',

    -- Exam-paper provenance. NULL for textbooks and legacy corpora.
    paper_code     text,                      -- 'WPH11'
    unit_number    int,
    session_year   int,
    session_series text,                      -- 'May June'

    language       text NOT NULL DEFAULT 'en',
    licence_status licence_status NOT NULL DEFAULT 'unknown',

    -- True for licensed material that must never enter the public repository or
    -- be redistributed. Enforced in the pipeline and by .githooks/pre-commit.
    is_private     boolean NOT NULL DEFAULT true,

    ingestion_version text,
    catalogued_at  timestamptz NOT NULL DEFAULT now(),
    ingested_at    timestamptz,

    CONSTRAINT source_priority_range CHECK (source_priority BETWEEN 1 AND 5),
    CONSTRAINT source_sha256_shape CHECK (sha256 IS NULL OR sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT source_bytes_non_negative CHECK (bytes IS NULL OR bytes >= 0),
    CONSTRAINT source_session_year_sane
        CHECK (session_year IS NULL OR session_year BETWEEN 1990 AND 2100)
);

COMMENT ON COLUMN source_documents.sha256 IS
    'Checksum of the source file. Deduplication key and provenance anchor: a '
    'chunk''s lineage resolves through here to an exact file.';

-- The same file must not be catalogued twice under one offering.
CREATE UNIQUE INDEX source_documents_offering_sha_idx
    ON source_documents (offering_id, sha256)
    WHERE sha256 IS NOT NULL;
CREATE INDEX source_documents_offering_idx ON source_documents (offering_id);
CREATE INDEX source_documents_priority_idx ON source_documents (offering_id, source_priority);

-- ─────────────────────────────────────────────────────────────────────────────
-- Corpus snapshots — audited chunk counts with provenance
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE corpus_snapshots (
    id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    offering_id uuid NOT NULL REFERENCES subject_offerings(id) ON DELETE CASCADE,
    -- How this number was arrived at, so a figure can never again float free of
    -- its evidence (see ADR-008 — a documented 1,022 against an actual 180).
    method      text NOT NULL,                -- 'scripts/audit_corpus.py'
    evidence_ref text,                        -- 'evidence/curriculum_audit_local.json'
    record_count int NOT NULL,
    notes       text,
    taken_at    timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT snapshot_count_non_negative CHECK (record_count >= 0)
);

CREATE INDEX corpus_snapshots_offering_idx ON corpus_snapshots (offering_id, taken_at DESC);

-- ─────────────────────────────────────────────────────────────────────────────
-- Availability — computed in exactly one place
-- ─────────────────────────────────────────────────────────────────────────────
--
-- Both the API and the UI read this view. There is no second definition of
-- "available" anywhere in the system, and blocked_reasons makes a refusal
-- explainable rather than mysterious.

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

    -- The availability rule. Every clause is evidence, not intention.
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

    -- Why not, in the order a reader would ask.
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

-- ─────────────────────────────────────────────────────────────────────────────
-- Migration bookkeeping
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS schema_migrations (
    version    text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO schema_migrations (version) VALUES ('0001_curriculum_registry')
ON CONFLICT (version) DO NOTHING;

COMMIT;
