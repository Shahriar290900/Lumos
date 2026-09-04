"""
The availability rule.

These tests build offerings directly and assert what `curriculum_availability`
says about them. They cover the rule itself, one clause at a time, plus the
schema constraints that stop an impossible row being written in the first place.

The regression case that matters most is `test_subject_with_zero_chunks_is_never_available`:
Shikhbo-Local-App v1.0.0 shipped a বাংলা subject button with no corpus behind it,
and selecting it produced ungrounded model output that looked like tutoring
(RECONNAISSANCE_REPORT.md §C.2.8). Nothing here may ever pass while that can happen.
"""

from __future__ import annotations

import uuid

import psycopg
import pytest


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — build a minimal, fully valid offering, then break one thing at a time
# ─────────────────────────────────────────────────────────────────────────────

FULLY_VALID = dict(
    publication_status="published",
    indexing_status="indexed",
    evaluation_status="passed",
    licence_status="permitted_public",
    indexed_chunk_count=42,
    languages=["en"],
    with_syllabus=True,
    with_source_document=True,
)


def make_offering(conn: psycopg.Connection, **overrides) -> str:
    """Create an offering with the given properties and return its slug."""
    spec = {**FULLY_VALID, **overrides}
    tag = uuid.uuid4().hex[:8]
    slug = f"test/{tag}"

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO curricula (code, name) VALUES (%s, %s) RETURNING id",
            (f"TEST_{tag.upper()}", f"Test curriculum {tag}"))
        curriculum_id = cur.fetchone()[0]

        cur.execute(
            "INSERT INTO subjects (curriculum_id, code, name_en) VALUES (%s, %s, %s) RETURNING id",
            (curriculum_id, "TESTSUBJ", "Test subject"))
        subject_id = cur.fetchone()[0]

        cur.execute(
            "INSERT INTO levels (curriculum_id, code, name) VALUES (%s, %s, %s) RETURNING id",
            (curriculum_id, "TESTLEVEL", "Test level"))
        level_id = cur.fetchone()[0]

        syllabus_id = None
        if spec["with_syllabus"]:
            cur.execute(
                "INSERT INTO syllabus_versions (curriculum_id, code, name) "
                "VALUES (%s, %s, %s) RETURNING id",
                (curriculum_id, f"SPEC_{tag.upper()}", "Test specification"))
            syllabus_id = cur.fetchone()[0]

        cur.execute(
            """
            INSERT INTO subject_offerings
                (curriculum_id, subject_id, level_id, syllabus_version_id, slug,
                 languages, publication_status, indexing_status, evaluation_status,
                 licence_status, indexed_chunk_count, display_note_en)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (curriculum_id, subject_id, level_id, syllabus_id, slug,
             spec["languages"], spec["publication_status"], spec["indexing_status"],
             spec["evaluation_status"], spec["licence_status"],
             spec["indexed_chunk_count"], "test note"))
        offering_id = cur.fetchone()[0]

        if spec["with_source_document"]:
            cur.execute(
                """
                INSERT INTO source_documents
                    (offering_id, document_type, source_priority, title)
                VALUES (%s, 'textbook', 2, 'Test source')
                """, (offering_id,))
    return slug


def availability(conn: psycopg.Connection, slug: str) -> tuple[bool, list[str]]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT is_available, blocked_reasons FROM curriculum_availability WHERE slug = %s",
            (slug,))
        row = cur.fetchone()
    assert row is not None, f"offering {slug} not found in the view"
    return bool(row[0]), list(row[1] or [])


# ─────────────────────────────────────────────────────────────────────────────
# The positive case — the rule must be satisfiable, or every test below is vacuous
# ─────────────────────────────────────────────────────────────────────────────

def test_fully_qualified_offering_is_available(conn):
    slug = make_offering(conn)
    ok, reasons = availability(conn, slug)
    assert ok is True
    assert reasons == []


# ─────────────────────────────────────────────────────────────────────────────
# The regression case
# ─────────────────────────────────────────────────────────────────────────────

def test_subject_with_zero_chunks_is_never_available(conn):
    """
    The বাংলা button. Everything else in order, no chunks — must be unavailable.

    Chunk count is checked independently of indexing_status precisely because a
    status field can be set by hand and a count cannot.
    """
    slug = make_offering(conn, indexed_chunk_count=0, indexing_status="normalising")
    ok, reasons = availability(conn, slug)
    assert ok is False
    assert "no_indexed_chunks" in reasons


def test_seeded_bangla_offering_is_unavailable(conn):
    """The real seeded row, not a synthetic one."""
    ok, reasons = availability(conn, "nctb/bangla/ssc")
    assert ok is False
    assert "no_indexed_chunks" in reasons
    assert "no_source_documents" in reasons


def test_indexed_status_cannot_be_set_without_chunks(conn):
    """The schema refuses the inconsistent row outright."""
    with pytest.raises(psycopg.errors.CheckViolation):
        make_offering(conn, indexing_status="indexed", indexed_chunk_count=0)


# ─────────────────────────────────────────────────────────────────────────────
# One clause at a time
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "overrides,expected_reason",
    [
        ({"publication_status": "planned"}, "publication_status=planned"),
        ({"publication_status": "in_preparation"}, "publication_status=in_preparation"),
        ({"publication_status": "hidden"}, "publication_status=hidden"),
        ({"indexing_status": "not_started", "indexed_chunk_count": 0}, "indexing_status=not_started"),
        ({"indexing_status": "ingesting", "indexed_chunk_count": 0}, "indexing_status=ingesting"),
        ({"evaluation_status": "none"}, "evaluation_status=none"),
        ({"evaluation_status": "failed"}, "evaluation_status=failed"),
        ({"indexed_chunk_count": 0, "indexing_status": "normalising"}, "no_indexed_chunks"),
        ({"with_syllabus": False}, "no_syllabus_version"),
        ({"with_source_document": False}, "no_source_documents"),
    ],
)
def test_each_clause_blocks_availability(conn, overrides, expected_reason):
    slug = make_offering(conn, **overrides)
    ok, reasons = availability(conn, slug)
    assert ok is False, f"{overrides} should have blocked availability"
    assert expected_reason in reasons, f"expected {expected_reason!r} in {reasons}"


def test_unknown_licence_blocks_publication_at_the_schema_level(conn):
    """A published offering on an unknown licence is not merely unavailable — it is unwritable."""
    with pytest.raises(psycopg.errors.CheckViolation):
        make_offering(conn, licence_status="unknown")


def test_restricted_licence_blocks_publication_at_the_schema_level(conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        make_offering(conn, licence_status="restricted")


def test_published_offering_requires_a_language(conn):
    with pytest.raises(psycopg.errors.CheckViolation):
        make_offering(conn, languages=[])


def test_visible_but_unavailable_offering_must_carry_a_note(conn):
    """
    A "coming soon" card with no copy forces the UI to invent an explanation.
    The schema refuses it.
    """
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO curricula (code, name) VALUES ('TEST_NONOTE', 'x') RETURNING id")
        cid = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO subjects (curriculum_id, code, name_en) "
            "VALUES (%s,'NONOTE_SUBJ','Subject') RETURNING id",
            (cid,))
        sid = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO levels (curriculum_id, code, name) "
            "VALUES (%s,'NONOTE_LEVEL','Level') RETURNING id",
            (cid,))
        lid = cur.fetchone()[0]
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                """
                INSERT INTO subject_offerings
                    (curriculum_id, subject_id, level_id, slug, publication_status)
                VALUES (%s, %s, %s, 'test/nonote', 'planned')
                """, (cid, sid, lid))


# ─────────────────────────────────────────────────────────────────────────────
# Data integrity
# ─────────────────────────────────────────────────────────────────────────────

def test_source_checksum_must_be_a_sha256(conn):
    slug = make_offering(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT offering_id FROM curriculum_availability WHERE slug = %s", (slug,))
        oid = cur.fetchone()[0]
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "INSERT INTO source_documents (offering_id, document_type, source_priority, "
                "title, sha256) VALUES (%s, 'textbook', 2, 't', 'not-a-checksum')", (oid,))


def test_same_document_cannot_be_catalogued_twice_under_one_offering(conn):
    slug = make_offering(conn)
    digest = "a" * 64
    with conn.cursor() as cur:
        cur.execute("SELECT offering_id FROM curriculum_availability WHERE slug = %s", (slug,))
        oid = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO source_documents (offering_id, document_type, source_priority, "
            "title, sha256) VALUES (%s, 'textbook', 2, 'first', %s)", (oid, digest))
        with pytest.raises(psycopg.errors.UniqueViolation):
            cur.execute(
                "INSERT INTO source_documents (offering_id, document_type, source_priority, "
                "title, sha256) VALUES (%s, 'textbook', 2, 'duplicate', %s)", (oid, digest))


def test_source_priority_must_be_in_range(conn):
    slug = make_offering(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT offering_id FROM curriculum_availability WHERE slug = %s", (slug,))
        oid = cur.fetchone()[0]
        with pytest.raises(psycopg.errors.CheckViolation):
            cur.execute(
                "INSERT INTO source_documents (offering_id, document_type, source_priority, title) "
                "VALUES (%s, 'textbook', 99, 't')", (oid,))


def test_blocked_reasons_is_empty_exactly_when_available(conn):
    """The two outputs of the view must never disagree."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT slug, is_available, coalesce(cardinality(blocked_reasons), 0) "
            "FROM curriculum_availability")
        rows = cur.fetchall()
    assert rows, "the view returned nothing — the seed did not run"
    for slug, available, n_reasons in rows:
        assert available == (n_reasons == 0), (
            f"{slug}: is_available={available} but {n_reasons} blocked reasons")
