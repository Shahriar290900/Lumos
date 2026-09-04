-- Reverse of 0001_curriculum_registry.up.sql.
-- Drops everything the up migration created, in dependency order.
-- Extensions (vector, pgcrypto) are intentionally left in place: other things
-- may depend on them, and dropping an extension is not this migration's business.

BEGIN;

DROP VIEW  IF EXISTS curriculum_availability;

DROP TABLE IF EXISTS corpus_snapshots;
DROP TABLE IF EXISTS source_documents;
DROP TABLE IF EXISTS subject_offerings;
DROP TABLE IF EXISTS levels;
DROP TABLE IF EXISTS subjects;
DROP TABLE IF EXISTS syllabus_versions;
DROP TABLE IF EXISTS curricula;

DROP TYPE IF EXISTS document_type;
DROP TYPE IF EXISTS ingestion_route;
DROP TYPE IF EXISTS licence_status;
DROP TYPE IF EXISTS publication_status;
DROP TYPE IF EXISTS evaluation_status;
DROP TYPE IF EXISTS indexing_status;

DELETE FROM schema_migrations WHERE version = '0001_curriculum_registry';

COMMIT;
