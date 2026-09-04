"""
Document delivery: what a student may open, and what they may not.

ADR-026 split the corpus. The 18 exam documents may be served; *Student Book 1*
may not, because it is a commercial textbook rather than freely published exam
material. That split is a database column, and these tests are the reason it
cannot quietly stop being enforced.
"""

from __future__ import annotations

import pytest

from services.delivery.documents import (
    DocumentNotServable,
    presigned_url,
    servable_documents,
)


def _register(conn, sandbox, *, title, doc_type, delivery, object_key):
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO source_documents
                (offering_id, document_type, source_priority, title, filename,
                 sha256, page_count, ingestion_route, language, is_private,
                 delivery, object_key)
            VALUES (%s, %s::document_type, 2, %s, %s, %s, 10, 'text', 'en', true,
                    %s::delivery_mode, %s)
            RETURNING id::text
            """,
            (sandbox["offering_id"], doc_type, title, f"{title}.pdf",
             "b" * 64, delivery, object_key))
        return cur.fetchone()[0]


def test_an_exam_document_is_listed_as_servable(conn, sandbox):
    _register(conn, sandbox, title="WPH11 question paper", doc_type="past_paper",
              delivery="in_app_pdf", object_key="Edexcel/wph11-que.pdf")
    docs = servable_documents(conn, sandbox["slug"])
    assert [d.title for d in docs] == ["WPH11 question paper"]


def test_the_textbook_is_not_listed(conn, sandbox):
    """
    Grounding an answer and being openable are different permissions.

    The textbook is in the same bucket as the exam papers and is embedded into
    the same index. Only the registry separates them.
    """
    _register(conn, sandbox, title="Student Book 1", doc_type="textbook",
              delivery="none", object_key="Edexcel/textbook.pdf")
    assert servable_documents(conn, sandbox["slug"]) == []


def test_requesting_the_textbook_is_refused_by_name(conn, sandbox):
    document_id = _register(conn, sandbox, title="Student Book 1",
                            doc_type="textbook", delivery="none",
                            object_key="Edexcel/textbook.pdf")
    with pytest.raises(DocumentNotServable) as exc:
        presigned_url(conn, document_id)
    assert "delivery=none" in str(exc.value)
    assert "grounding only" in str(exc.value)


def test_delivery_defaults_to_none(conn, sandbox):
    """
    Serving is the exception and has to be asserted.

    A document registered without an opinion about delivery must not become
    openable because someone forgot to say otherwise.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO source_documents
                (offering_id, document_type, source_priority, title, filename,
                 sha256, ingestion_route, language, is_private)
            VALUES (%s, 'past_paper', 2, 'Unconsidered', 'u.pdf', %s, 'text', 'en', true)
            RETURNING delivery::text
            """,
            (sandbox["offering_id"], "c" * 64))
        assert cur.fetchone()[0] == "none"


def test_a_servable_document_must_have_an_object_key(conn, sandbox):
    """The schema refuses "servable" without somewhere to serve it from."""
    import psycopg
    with pytest.raises(psycopg.errors.CheckViolation):
        _register(conn, sandbox, title="Nowhere", doc_type="past_paper",
                  delivery="in_app_pdf", object_key=None)


def test_an_unknown_document_is_refused(conn):
    import uuid
    with pytest.raises(DocumentNotServable):
        presigned_url(conn, str(uuid.uuid4()))
