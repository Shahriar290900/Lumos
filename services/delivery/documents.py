"""
services.delivery.documents — serving exam PDFs, and refusing to serve the rest.

ADR-026 split the corpus in two. The 18 Edexcel exam documents may be shown to a
student; *Student Book 1* may not, in whole or in part, because it is a
commercial textbook rather than the freely published exam material. That
distinction lives in `source_documents.delivery` and it is enforced here.

**Presigned, short-lived, never public.** The bucket stays private and every URL
expires. A public bucket URL cannot be withdrawn once it is shared; a presigned
URL stops working. If the licensing position changes, the fix is a database
update rather than an attempt to un-share a link.

**The registry decides, not the caller.** `delivery` defaults to `'none'`, so a
newly registered document is never servable by accident — serving is the
exception and has to be asserted. A request for a document the registry has not
cleared raises rather than returning a URL.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

import psycopg
from psycopg.rows import dict_row

# Long enough to open and read a paper, short enough that a leaked link dies.
DEFAULT_EXPIRY_SECONDS = 900


class DocumentNotServable(PermissionError):
    """The registry has not cleared this document for delivery. Never a URL."""


class DeliveryUnavailable(RuntimeError):
    """Object storage is not configured. Says which variable is missing."""


@dataclass(frozen=True)
class ServableDocument:
    """A document the registry permits a student to open."""

    document_id: str
    title: str
    document_type: str
    paper_code: str | None
    page_count: int | None
    object_key: str
    offering_slug: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "type": self.document_type,
            "paper_code": self.paper_code,
            "pages": self.page_count,
            "offering": self.offering_slug,
        }


def _client():
    """Build the S3 client, or explain exactly what is missing (ADR-012)."""
    missing = [k for k in ("R2_ENDPOINT", "R2_ACCESS_KEY_ID",
                           "R2_SECRET_ACCESS_KEY", "R2_BUCKET_NAME")
               if not os.environ.get(k)]
    if missing:
        raise DeliveryUnavailable(
            f"object storage is not configured: {', '.join(missing)} unset. "
            "PDF delivery needs the R2 bucket (BLOCK-003).")
    try:
        import boto3
        from botocore.config import Config
    except ImportError:
        raise DeliveryUnavailable("boto3 is not installed") from None

    return boto3.client(
        "s3", endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4", region_name="auto"))


def servable_documents(conn: psycopg.Connection, offering_slug: str
                       ) -> list[ServableDocument]:
    """Every document this offering may show a student. Often none, and that is fine."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT sd.id::text AS document_id, sd.title, sd.document_type::text AS dt,
                   sd.paper_code, sd.page_count, sd.object_key, o.slug
            FROM source_documents sd
            JOIN subject_offerings o ON o.id = sd.offering_id
            WHERE o.slug = %s
              AND sd.delivery = 'in_app_pdf'
              AND sd.object_key IS NOT NULL
            ORDER BY sd.paper_code NULLS LAST, sd.document_type, sd.title
            """,
            (offering_slug,))
        return [ServableDocument(
            document_id=r["document_id"], title=r["title"], document_type=r["dt"],
            paper_code=r["paper_code"], page_count=r["page_count"],
            object_key=r["object_key"], offering_slug=r["slug"])
            for r in cur.fetchall()]


def presigned_url(conn: psycopg.Connection, document_id: str,
                  expires: int = DEFAULT_EXPIRY_SECONDS) -> tuple[str, ServableDocument]:
    """
    A short-lived URL for one document — but only if the registry permits it.

    The delivery check is a `WHERE` clause, not an `if` in application code, for
    the same reason the availability gate is a SQL view: two copies of a rule are
    two rules, and the one that drifts is the one nobody tested.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT sd.id::text AS document_id, sd.title, sd.document_type::text AS dt,
                   sd.paper_code, sd.page_count, sd.object_key,
                   sd.delivery::text AS delivery, o.slug
            FROM source_documents sd
            JOIN subject_offerings o ON o.id = sd.offering_id
            WHERE sd.id = %s::uuid
            """,
            (document_id,))
        row = cur.fetchone()

    if row is None:
        raise DocumentNotServable(f"no document {document_id}")
    if row["delivery"] != "in_app_pdf":
        raise DocumentNotServable(
            f"{row['title']!r} is registered as delivery={row['delivery']} and is "
            "not served to students. It is retrieval grounding only (ADR-026).")
    if not row["object_key"]:
        raise DocumentNotServable(
            f"{row['title']!r} is marked servable but has no object key — it has "
            "not been uploaded")

    document = ServableDocument(
        document_id=row["document_id"], title=row["title"], document_type=row["dt"],
        paper_code=row["paper_code"], page_count=row["page_count"],
        object_key=row["object_key"], offering_slug=row["slug"])

    url = _client().generate_presigned_url(
        "get_object",
        Params={"Bucket": os.environ["R2_BUCKET_NAME"], "Key": document.object_key,
                "ResponseContentDisposition": f'inline; filename="{document.title}.pdf"',
                "ResponseContentType": "application/pdf"},
        ExpiresIn=expires)
    return url, document
