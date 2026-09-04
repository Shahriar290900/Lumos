"""
Normalisation against a real database.

Covers what only a database can show: that the schema refuses inconsistent
chunks, that writing is genuinely idempotent, that authority and session
metadata survive into the retrieval view, and that the legacy adapter converts a
corpus without losing or inventing records.

All fixtures are synthetic. The Pearson sources are licensed, and a committed
test suite is a published artifact.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import psycopg
import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

from services.ingestion.canonical import (  # noqa: E402
    INGESTION_VERSION, CanonicalChunk, ChunkWriter, record_run,
)
from services.ingestion.legacy_adapter import normalise_legacy_corpus  # noqa: E402
from services.ingestion.past_paper import parse_questions, questions_to_chunks  # noqa: E402


def make_chunk(sandbox, *, locator="q/1", text="A synthetic question about forces.",
               chunk_type="exam_question", **overrides) -> CanonicalChunk:
    base = dict(
        source_document_id=sandbox["document_id"],
        offering_id=sandbox["offering_id"],
        document_sha256=sandbox["document_sha256"],
        locator=locator,
        text=text,
        chunk_type=chunk_type,
        extraction_method="pdf_text_layer",
    )
    if chunk_type in ("exam_question", "mark_scheme_answer", "examiner_commentary"):
        base["question_number"] = overrides.pop("question_number", "1")
    if chunk_type == "legacy_record":
        base["legacy_chunk_id"] = overrides.pop("legacy_chunk_id", "LEG-1")
    base.update(overrides)
    return CanonicalChunk(**base)


def count_chunks(conn, offering_id: str) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM chunks WHERE offering_id = %s", (offering_id,))
        return cur.fetchone()[0]


# ─────────────────────────────────────────────────────────────────────────────
# Writing
# ─────────────────────────────────────────────────────────────────────────────

def test_a_chunk_round_trips_with_all_its_provenance(conn, sandbox):
    chunk = make_chunk(sandbox, page_number=4, page_number_end=5, marks=7,
                       sub_parts=[{"label": "(a)", "level": 1, "marks": 3}],
                       topic="Newton's laws", language="en")
    ChunkWriter(conn).write([chunk])

    with conn.cursor() as cur:
        cur.execute(
            "SELECT chunk_key, chunk_type, question_number, marks, page_number, "
            "page_number_end, sub_parts, extraction_method, provenance_status, "
            "ingestion_version, content_sha256, token_count, language "
            "FROM chunks WHERE id = %s", (chunk.id,))
        row = cur.fetchone()

    assert row[0] == chunk.chunk_key
    assert row[1] == "exam_question"
    assert (row[2], row[3], row[4], row[5]) == ("1", 7, 4, 5)
    assert row[6] == [{"label": "(a)", "level": 1, "marks": 3}]
    assert row[7] == "pdf_text_layer"
    assert row[8] in ("verbatim", "cleaned", "normalized")
    assert row[9] == INGESTION_VERSION
    assert row[10] == chunk.content_sha256
    assert row[11] == chunk.token_count
    assert row[12] == "en"


def test_writing_the_same_chunks_twice_changes_nothing(conn, sandbox):
    """Idempotency, measured rather than assumed."""
    chunks = [make_chunk(sandbox, locator=f"q/{n}", question_number=str(n),
                         text=f"Question {n} about motion.") for n in range(1, 6)]
    writer = ChunkWriter(conn)

    first = writer.write(chunks)
    assert (first.created, first.updated, first.unchanged) == (5, 0, 0)

    second = writer.write(chunks)
    assert (second.created, second.updated, second.unchanged) == (0, 0, 5)
    assert count_chunks(conn, sandbox["offering_id"]) == 5

    # And a third time, from freshly constructed objects.
    rebuilt = [make_chunk(sandbox, locator=f"q/{n}", question_number=str(n),
                          text=f"Question {n} about motion.") for n in range(1, 6)]
    third = writer.write(rebuilt)
    assert (third.created, third.updated, third.unchanged) == (0, 0, 5)


def test_changed_content_updates_in_place_rather_than_duplicating(conn, sandbox):
    writer = ChunkWriter(conn)
    writer.write([make_chunk(sandbox, text="Original wording.")])
    result = writer.write([make_chunk(sandbox, text="Corrected wording.")])

    assert (result.created, result.updated, result.unchanged) == (0, 1, 0)
    assert count_chunks(conn, sandbox["offering_id"]) == 1
    with conn.cursor() as cur:
        cur.execute("SELECT text FROM chunks WHERE offering_id = %s",
                    (sandbox["offering_id"],))
        assert cur.fetchone()[0] == "Corrected wording."


def test_a_duplicate_key_inside_one_batch_is_reported_not_written_twice(conn, sandbox):
    """Two chunks with one locator is an adapter bug, and must surface as one."""
    writer = ChunkWriter(conn)
    result = writer.write([
        make_chunk(sandbox, locator="q/1", text="First."),
        make_chunk(sandbox, locator="q/1", text="Second, same locator."),
    ])
    assert result.duplicates_seen == 1
    assert any("duplicate chunk_key" in w for w in result.warnings)
    assert count_chunks(conn, sandbox["offering_id"]) == 1


def test_the_same_question_number_in_two_documents_coexists(conn, sandbox):
    """
    Identity across documents, enforced by the database and not just the model.

    Both rows are "question 1"; they are different chunks because they came from
    different files.
    """
    with conn.cursor() as cur:
        other_sha = "c" * 64
        cur.execute(
            """
            INSERT INTO source_documents
                (offering_id, document_type, source_priority, title, filename,
                 sha256, ingestion_route, paper_code, session_year, session_series)
            VALUES (%s, 'past_paper', 1, 'Second paper', 'other.pdf', %s,
                    'text', 'SBX02', 2023, 'October November')
            RETURNING id
            """,
            (sandbox["offering_id"], other_sha))
        other_doc = str(cur.fetchone()[0])

    first = make_chunk(sandbox, locator="q/1", question_number="1")
    second = CanonicalChunk(
        source_document_id=other_doc, offering_id=sandbox["offering_id"],
        document_sha256=other_sha, locator="q/1",
        text="A different paper's question 1.", chunk_type="exam_question",
        question_number="1", extraction_method="pdf_text_layer")

    result = ChunkWriter(conn).write([first, second])
    assert result.created == 2
    assert first.id != second.id
    assert count_chunks(conn, sandbox["offering_id"]) == 2


# ─────────────────────────────────────────────────────────────────────────────
# Schema integrity
# ─────────────────────────────────────────────────────────────────────────────

def _insert_raw(conn, sandbox, **fields):
    """Insert straight into `chunks`, bypassing the model, to test the schema."""
    row = {
        "id": "33333333-3333-3333-3333-333333333333",
        "chunk_key": f"lumos:v1:{sandbox['document_sha256']}:raw/1",
        "source_document_id": sandbox["document_id"],
        "offering_id": sandbox["offering_id"],
        "chunk_type": "textbook_section",
        "text": "Some text.",
        "content_sha256": "d" * 64,
        "row_fingerprint": "e" * 64,
        "ingestion_version": INGESTION_VERSION,
    }
    row.update(fields)
    cols = ", ".join(row)
    ph = ", ".join(f"%({c})s" for c in row)
    with conn.cursor() as cur:
        cur.execute(f"INSERT INTO chunks ({cols}) VALUES ({ph})", row)


def test_a_question_chunk_without_a_question_number_is_refused(conn, sandbox):
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_raw(conn, sandbox, chunk_type="exam_question")


def test_a_legacy_chunk_without_its_legacy_identifier_is_refused(conn, sandbox):
    """Traceability is not optional for legacy material."""
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_raw(conn, sandbox, chunk_type="legacy_record")


def test_uncertainty_can_only_be_claimed_by_an_extractor_that_can_be_uncertain(conn, sandbox):
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_raw(conn, sandbox, provenance_status="ocr_uncertain",
                    extraction_method="structured_jsonl")


def test_transformed_text_without_its_original_is_refused(conn, sandbox):
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_raw(conn, sandbox, provenance_status="cleaned", text_raw=None)


def test_empty_text_is_refused(conn, sandbox):
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_raw(conn, sandbox, text="   ")


def test_a_malformed_chunk_key_is_refused(conn, sandbox):
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_raw(conn, sandbox, chunk_key="not-a-lumos-key")


def test_an_invented_language_code_is_refused(conn, sandbox):
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_raw(conn, sandbox, language="english")


def test_unknown_is_an_accepted_language(conn, sandbox):
    _insert_raw(conn, sandbox, language="unknown")
    with conn.cursor() as cur:
        cur.execute("SELECT language FROM chunks WHERE offering_id = %s",
                    (sandbox["offering_id"],))
        assert cur.fetchone()[0] == "unknown"


def test_negative_marks_are_refused(conn, sandbox):
    with pytest.raises(psycopg.errors.CheckViolation):
        _insert_raw(conn, sandbox, chunk_type="exam_question",
                    question_number="1", marks=-1)


def test_a_chunk_key_is_unique_across_the_table(conn, sandbox):
    _insert_raw(conn, sandbox)
    with pytest.raises(psycopg.errors.UniqueViolation):
        _insert_raw(conn, sandbox, id="44444444-4444-4444-4444-444444444444")


# ─────────────────────────────────────────────────────────────────────────────
# Retrieval context
# ─────────────────────────────────────────────────────────────────────────────

def test_authority_and_session_metadata_reach_the_retrieval_view(conn, sandbox):
    """
    Source priority, document type and exam session must be available to
    retrieval without re-deriving them from the chunk — that is how authority
    survives fusion and reranking as a feature (ADR-009).
    """
    chunk = make_chunk(sandbox, question_number="7", marks=9)
    ChunkWriter(conn).write([chunk])

    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT document_type, source_priority, paper_code, session_year,
                   session_series, curriculum_code, subject_code, level_code,
                   is_private, question_number, marks, extraction_method,
                   provenance_status, offering_slug
            FROM chunk_retrieval_context WHERE chunk_id = %s
            """, (chunk.id,))
        row = cur.fetchone()

    assert row[0] == "past_paper"
    assert row[1] == 1
    assert row[2] == "SBX01"
    assert (row[3], row[4]) == (2024, "May June")
    assert row[5].startswith("SBX_")
    assert row[6] == "SBX_SUBJECT"
    assert row[7] == "SBX_LEVEL"
    assert row[8] is True
    assert (row[9], row[10]) == ("7", 9)
    assert row[11] == "pdf_text_layer"
    assert row[12] in ("verbatim", "cleaned", "normalized")
    assert row[13] == sandbox["slug"]


def test_document_types_stay_distinguishable(conn, sandbox):
    """
    Mark schemes and examiner reports are never collapsed into one type: they
    carry different authority and answer different questions for a student.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT unnest(enum_range(NULL::document_type))::text")
        values = {r[0] for r in cur.fetchall()}
    assert {"specification", "past_paper", "mark_scheme", "examiner_report",
            "textbook", "legacy_corpus"} <= values


def test_chunk_types_distinguish_what_a_chunk_is_from_where_it_came_from(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT unnest(enum_range(NULL::chunk_type))::text")
        values = {r[0] for r in cur.fetchall()}
    assert {"exam_question", "mark_scheme_answer", "examiner_commentary",
            "textbook_section", "legacy_record"} <= values


def test_availability_exposes_the_canonical_count_without_becoming_available(conn, sandbox):
    """
    Normalised is not indexed. Chunks existing must never flip a subject to
    available on their own — the availability rule is unchanged from 004A.
    """
    ChunkWriter(conn).write([make_chunk(sandbox)])
    with conn.cursor() as cur:
        cur.execute(
            "SELECT canonical_chunk_count, indexed_chunk_count, is_available, "
            "blocked_reasons FROM curriculum_availability WHERE slug = %s",
            (sandbox["slug"],))
        canonical, indexed, available, reasons = cur.fetchone()

    assert canonical == 1
    assert indexed == 0
    assert available is False
    assert "no_indexed_chunks" in reasons


def test_a_normalisation_run_is_recorded(conn, sandbox):
    writer = ChunkWriter(conn)
    result = writer.write([make_chunk(sandbox)])
    run_id = record_run(conn, offering_id=sandbox["offering_id"],
                        adapter="test", source_records=1, result=result)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT adapter, ingestion_version, source_records, chunks_created "
            "FROM normalisation_runs WHERE id = %s", (run_id,))
        assert cur.fetchone() == ("test", INGESTION_VERSION, 1, 1)


# ─────────────────────────────────────────────────────────────────────────────
# Legacy adapter, end to end against a synthetic corpus
# ─────────────────────────────────────────────────────────────────────────────

SYNTHETIC_RECORDS = [
    {"chunk_id": "SYN-1", "class": "SSC", "subject": "SYN", "chapter_no": "1",
     "chapter_title": "Chapter one", "page_no": 1, "topic": "Introduction",
     "prerequisite": "None", "keywords": [], "token_count": 999,
     "content": "The first synthetic record, written in English."},
    {"chunk_id": "SYN-2", "class": "SSC", "subject": "SYN", "chapter_no": "1",
     "chapter_name": "Chapter one", "page_no": 2, "topic": "Second topic",
     "prerequisite": "None", "keywords": ["alpha"], "token_count": 888,
     "content": "তথ্য ও যোগাযোগ প্রযুক্তি — a Bangla record."},
    {"chunk_id": "SYN-3", "page_no": 3,
     "content": "A sparse record with almost no metadata at all."},
]


@pytest.fixture
def synthetic_corpus(conn, sandbox, tmp_path):
    """A legacy JSONL file on disk, registered in the sandbox offering."""
    path = tmp_path / "SYN_C1.jsonl"
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in SYNTHETIC_RECORDS) + "\n",
        encoding="utf-8")
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO source_documents
                (offering_id, document_type, source_priority, title, filename,
                 relative_path, ingestion_route, language, is_private)
            VALUES (%s, 'legacy_corpus', 2, 'Synthetic legacy corpus',
                    'SYN_C1.jsonl', 'raw_data/SYN_C1.jsonl', 'structured', 'en', false)
            RETURNING id
            """, (sandbox["offering_id"],))
        document_id = str(cur.fetchone()[0])
    return {"root": tmp_path, "document_id": document_id}


def test_legacy_adapter_converts_every_record_and_loses_none(conn, sandbox, synthetic_corpus):
    report = normalise_legacy_corpus(conn, synthetic_corpus["root"])
    stats = report.by_offering[sandbox["offering_id"]]
    assert stats["source_records"] == len(SYNTHETIC_RECORDS)
    assert stats["chunks"] == len(SYNTHETIC_RECORDS)
    assert count_chunks(conn, sandbox["offering_id"]) == len(SYNTHETIC_RECORDS)


def test_legacy_adapter_is_idempotent(conn, sandbox, synthetic_corpus):
    normalise_legacy_corpus(conn, synthetic_corpus["root"])
    second = normalise_legacy_corpus(conn, synthetic_corpus["root"])
    stats = second.by_offering[sandbox["offering_id"]]
    assert stats["created"] == 0
    assert stats["updated"] == 0
    assert stats["unchanged"] == len(SYNTHETIC_RECORDS)
    assert count_chunks(conn, sandbox["offering_id"]) == len(SYNTHETIC_RECORDS)


def test_legacy_adapter_backfills_the_document_checksum(conn, sandbox, synthetic_corpus):
    """
    Chunk identity is derived from the document checksum, so a legacy document
    without one cannot produce a stable id. The adapter supplies it.
    """
    with conn.cursor() as cur:
        cur.execute("SELECT sha256 FROM source_documents WHERE id = %s",
                    (synthetic_corpus["document_id"],))
        assert cur.fetchone()[0] is None

    normalise_legacy_corpus(conn, synthetic_corpus["root"])

    with conn.cursor() as cur:
        cur.execute("SELECT sha256 FROM source_documents WHERE id = %s",
                    (synthetic_corpus["document_id"],))
        digest = cur.fetchone()[0]
    assert digest is not None and len(digest) == 64


def test_legacy_conversion_preserves_identity_and_the_original_record(conn, sandbox,
                                                                     synthetic_corpus):
    normalise_legacy_corpus(conn, synthetic_corpus["root"])
    with conn.cursor() as cur:
        cur.execute(
            "SELECT legacy_chunk_id, legacy_metadata, chunk_type, extraction_method, "
            "section_ref, legacy_token_count, language "
            "FROM chunks WHERE offering_id = %s ORDER BY legacy_chunk_id",
            (sandbox["offering_id"],))
        rows = cur.fetchall()

    assert [r[0] for r in rows] == ["SYN-1", "SYN-2", "SYN-3"]
    assert rows[0][1]["record"] == SYNTHETIC_RECORDS[0]
    assert all(r[2] == "legacy_record" for r in rows)
    assert all(r[3] == "structured_jsonl" for r in rows)
    # chapter_title on the first, chapter_name on the second — both resolve.
    assert rows[0][4] == "Chapter one"
    assert rows[1][4] == "Chapter one"
    assert rows[0][5] == 999
    # Language is derived from the script, so the Bangla record is bn even though
    # the document declares en.
    assert rows[0][6] == "en"
    assert rows[1][6] == "bn"


def test_legacy_conversion_leaves_absent_fields_null(conn, sandbox, synthetic_corpus):
    """A sparse record produces explicit gaps, never invented values."""
    normalise_legacy_corpus(conn, synthetic_corpus["root"])
    with conn.cursor() as cur:
        cur.execute(
            "SELECT section_ref, topic, syllabus_reference, prerequisite_text, "
            "keywords, legacy_token_count FROM chunks WHERE legacy_chunk_id = 'SYN-3'")
        row = cur.fetchone()
    assert row[:4] == (None, None, None, None)
    assert row[4] == []
    assert row[5] is None


def test_a_registered_document_with_no_file_is_reported(conn, sandbox, synthetic_corpus):
    report = normalise_legacy_corpus(conn, synthetic_corpus["root"])
    # The seeded corpora are registered but their files are not under this root.
    assert report.missing_documents
    assert not any("SYN_C1" in m for m in report.missing_documents)


def test_field_gaps_are_counted(conn, sandbox, synthetic_corpus):
    report = normalise_legacy_corpus(conn, synthetic_corpus["root"])
    assert report.field_gaps["no_syllabus_reference"] == 3
    assert report.field_gaps["no_keywords"] == 2
    assert report.field_gaps["no_chapter_label"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# Past papers into the database
# ─────────────────────────────────────────────────────────────────────────────

SYNTHETIC_PAPER = [(1, """\
1 Which quantity is a vector?
A speed
B velocity
(Total for Question 1 = 1 mark)
2 A block of mass 4.0 kg rests on a surface.
(a) Calculate its weight.
(2)
(b) The block is pushed.
(i) Determine the resultant force.
(3)
(ii) Explain the acceleration.
(2)
(Total for Question 2 = 7 marks)
""")]


def test_a_whole_question_is_stored_and_retrieved_as_one_unit(conn, sandbox):
    """
    The acceptance criterion, end to end.

    A complete main question, all sub-parts included, is one row — and it comes
    back from the retrieval view as one row, with its structure intact.
    """
    questions, report = parse_questions(SYNTHETIC_PAPER)
    assert report.questions_found == 2

    chunks = questions_to_chunks(
        questions, source_document_id=sandbox["document_id"],
        offering_id=sandbox["offering_id"],
        document_sha256=sandbox["document_sha256"],
        extraction_method="pdf_text_layer")
    ChunkWriter(conn).write(chunks)

    with conn.cursor() as cur:
        cur.execute(
            "SELECT text, marks, sub_parts, sub_question, depends_on "
            "FROM chunk_retrieval_context "
            "WHERE offering_id = %s AND question_number = '2'",
            (sandbox["offering_id"],))
        rows = cur.fetchall()

    assert len(rows) == 1, "question 2 must be exactly one chunk"
    text, marks, sub_parts, sub_question, depends_on = rows[0]
    assert "Calculate its weight" in text
    assert "Determine the resultant force" in text
    assert "Explain the acceleration" in text
    assert marks == 7
    assert [p["label"] for p in sub_parts] == ["(a)", "(b)", "(b)(i)", "(b)(ii)"]
    assert sub_question is None
    # Multi-part context comes from grouping, not from a dependency graph.
    assert depends_on == []


# ─────────────────────────────────────────────────────────────────────────────
# Migration
# ─────────────────────────────────────────────────────────────────────────────

def test_canonical_chunk_migration_applies_and_reverses(empty_database_url):
    env = {**os.environ, "DATABASE_URL": empty_database_url}
    migrate = [sys.executable, str(REPO_ROOT / "packages/db/migrate.py")]

    def relations() -> tuple[set[str], set[str]]:
        with psycopg.connect(empty_database_url) as c, c.cursor() as cur:
            cur.execute(
                "SELECT table_name, table_type FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name <> 'schema_migrations'")
            rows = cur.fetchall()
        return ({n for n, t in rows if t == "BASE TABLE"},
                {n for n, t in rows if t == "VIEW"})

    subprocess.run(migrate + ["down", "--to", "0000"], env=env,
                   capture_output=True, text=True)
    subprocess.run(migrate + ["up"], env=env, check=True, capture_output=True, text=True)

    tables, views = relations()
    assert {"chunks", "normalisation_runs"} <= tables
    assert {"chunk_retrieval_context", "curriculum_availability"} <= views

    # Revert to 0001 explicitly rather than calling `down` once.
    #
    # A bare `down` reverts whichever migration is latest, so this test silently
    # changed meaning the moment 0003 was added: it reverted retrieval and then
    # asserted the chunks table was gone. Naming the target keeps the test about
    # 0002 however many migrations follow it.
    # The full version name, not the "0001" prefix: `--to` reverts everything
    # strictly greater as a string, and "0001_curriculum_registry" > "0001", so
    # the short form reverts the registry too.
    subprocess.run(migrate + ["down", "--to", "0001_curriculum_registry"], env=env,
                   check=True, capture_output=True, text=True)
    tables, views = relations()
    assert "chunks" not in tables and "normalisation_runs" not in tables
    assert "chunk_retrieval_context" not in views
    assert "curriculum_availability" in views, "reverting 0002 must not remove the registry"
    assert "subject_offerings" in tables

    # The 0001 document type names come back.
    with psycopg.connect(empty_database_url) as c, c.cursor() as cur:
        cur.execute("SELECT unnest(enum_range(NULL::document_type))::text")
        values = {r[0] for r in cur.fetchall()}
    assert "question_paper" in values and "past_paper" not in values

    subprocess.run(migrate + ["up"], env=env, check=True, capture_output=True, text=True)
    tables, _ = relations()
    assert "chunks" in tables


# ─────────────────────────────────────────────────────────────────────────────
# LUMOS-004C.1 — cleaning, re-chunking, and retiring what they replace
# ─────────────────────────────────────────────────────────────────────────────

def test_pruning_removes_a_chunk_the_rerun_no_longer_produces(conn, sandbox):
    """
    Re-chunking retires the whole-record chunk it replaces.

    When a record that was one chunk (`legacy/<id>`) becomes three
    (`legacy/<id>/part/0..2`), the original row still satisfies every constraint
    and would simply stay. The corpus would then hold both the whole record and
    its pieces, double-counting it in retrieval and in `canonical_chunk_count`.
    """
    from services.ingestion.canonical import CanonicalChunk, ChunkWriter
    from services.ingestion.legacy_adapter import prune_stale_chunks

    def chunk(locator: str) -> CanonicalChunk:
        return CanonicalChunk(
            source_document_id=sandbox["document_id"],
            offering_id=sandbox["offering_id"],
            document_sha256=sandbox["document_sha256"],
            locator=locator, text=f"content for {locator}",
            chunk_type="legacy_record", extraction_method="structured_jsonl",
            legacy_chunk_id="REC-1")

    writer = ChunkWriter(conn)
    stale = chunk("legacy/REC-1")
    fresh = [chunk("legacy/REC-1/part/0"), chunk("legacy/REC-1/part/1")]
    writer.write([stale, *fresh])

    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM chunks WHERE source_document_id = %s",
                    (sandbox["document_id"],))
        assert cur.fetchone()[0] == 3

    removed = prune_stale_chunks(
        conn, document_ids=[sandbox["document_id"]],
        keep_keys={c.chunk_key for c in fresh})

    assert removed == 1
    with conn.cursor() as cur:
        cur.execute("SELECT chunk_key FROM chunks WHERE source_document_id = %s "
                    "ORDER BY chunk_key", (sandbox["document_id"],))
        assert [r[0] for r in cur.fetchall()] == sorted(c.chunk_key for c in fresh)


def test_pruning_refuses_to_empty_the_corpus(conn, sandbox):
    """An empty keep-set is a bug in the caller, not an instruction to delete all."""
    from services.ingestion.canonical import CanonicalChunk, ChunkWriter
    from services.ingestion.legacy_adapter import prune_stale_chunks

    ChunkWriter(conn).write([CanonicalChunk(
        source_document_id=sandbox["document_id"],
        offering_id=sandbox["offering_id"],
        document_sha256=sandbox["document_sha256"],
        locator="legacy/KEEP-ME", text="content",
        chunk_type="legacy_record", extraction_method="structured_jsonl",
        legacy_chunk_id="KEEP-ME")])

    assert prune_stale_chunks(conn, document_ids=[sandbox["document_id"]],
                              keep_keys=set()) == 0
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM chunks WHERE source_document_id = %s",
                    (sandbox["document_id"],))
        assert cur.fetchone()[0] == 1


def test_pruning_cannot_reach_another_adapters_chunks(conn, sandbox):
    """Scoped by document and by chunk type, so an exam question is untouchable."""
    from services.ingestion.canonical import CanonicalChunk, ChunkWriter
    from services.ingestion.legacy_adapter import prune_stale_chunks

    question = CanonicalChunk(
        source_document_id=sandbox["document_id"],
        offering_id=sandbox["offering_id"],
        document_sha256=sandbox["document_sha256"],
        locator="q/1", text="Calculate the weight.",
        chunk_type="exam_question", extraction_method="pdf_text_layer",
        question_number="1", marks=3)
    legacy = CanonicalChunk(
        source_document_id=sandbox["document_id"],
        offering_id=sandbox["offering_id"],
        document_sha256=sandbox["document_sha256"],
        locator="legacy/OLD", text="superseded",
        chunk_type="legacy_record", extraction_method="structured_jsonl",
        legacy_chunk_id="OLD")
    ChunkWriter(conn).write([question, legacy])

    prune_stale_chunks(conn, document_ids=[sandbox["document_id"]],
                       keep_keys={"lumos:v1:" + sandbox["document_sha256"] + ":legacy/NEW"})

    with conn.cursor() as cur:
        cur.execute("SELECT chunk_type::text FROM chunks WHERE source_document_id = %s",
                    (sandbox["document_id"],))
        remaining = [r[0] for r in cur.fetchall()]
    assert remaining == ["exam_question"], "the legacy chunk goes, the question stays"


def test_a_repaired_chunk_is_derived_and_keeps_its_raw_text(conn, sandbox):
    """ADR-021, applied to cleaning: a repair is not what the source said."""
    from services.ingestion.legacy_adapter import LegacyDocument, record_to_chunks

    doc = LegacyDocument(
        path=Path("sandbox.jsonl"), source_document_id=sandbox["document_id"],
        offering_id=sandbox["offering_id"], declared_language="bn",
        sha256=sandbox["document_sha256"])
    damaged = "তথ্য ও যযোগাযযোগ প্রযুক্তি ককোননো একটি বিষয়।"
    chunks = record_to_chunks({"chunk_id": "ICT-1", "content": damaged}, doc, 0)

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.provenance_status == "derived"
    assert chunk.text_raw == damaged, "the damaged text must survive the repair"
    assert "যযোগ" not in chunk.text and "যোগাযোগ" in chunk.text
    assert chunk.legacy_metadata["cleaning"]["by_stage"]["bangla_doubled_consonant"] > 0


def test_an_undamaged_record_stays_verbatim(conn, sandbox):
    """Only a chunk that actually changed loses `verbatim`."""
    from services.ingestion.legacy_adapter import LegacyDocument, record_to_chunks

    doc = LegacyDocument(
        path=Path("sandbox.jsonl"), source_document_id=sandbox["document_id"],
        offering_id=sandbox["offering_id"], declared_language="en",
        sha256=sandbox["document_sha256"])
    chunks = record_to_chunks(
        {"chunk_id": "EN-1", "content": "A clean English sentence."}, doc, 0)

    assert len(chunks) == 1
    assert chunks[0].provenance_status == "verbatim"
    assert chunks[0].text_raw is None
