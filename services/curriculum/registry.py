"""
services.curriculum.registry — the authority on what curriculum content Lumos holds.

Everything the product knows about availability comes from here, and this module
gets it from exactly one place: the `curriculum_availability` view. The rule is
not restated in Python, because two copies of a rule are two rules.

The guarantee this module exists to provide:

    An offering that is not available cannot reach the retrieval path.

`require_available()` is the gate. Call it before any retrieval, on the server,
every time. A client-side check is a courtesy to the user, not a control.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Iterable

import psycopg
from psycopg.rows import dict_row

# Columns the view exposes, in the order the API returns them.
# How a request's identifier is matched against a stored code.
#
# Case is folded, and hyphen and underscore are treated as one separator, so the
# slug segments `GET /curriculum` publishes (`edexcel-ial`, `international-as`)
# resolve to the codes the registry stores (`EDEXCEL_IAL`, `INTERNATIONAL_AS`).
# Defined once so every clause of every lookup normalises identically — two
# copies of a matching rule are two rules, and the one that drifts is the one
# nobody tested.
_CODE_MATCH = "upper(replace({column}, '-', '_')) = upper(replace(%s, '-', '_'))"

_SELECT = """
    offering_id, slug,
    curriculum_code, curriculum_name,
    subject_code, subject_name_en, subject_name_bn,
    level_code, level_name, level_sort_order,
    syllabus_version_code, specification_reference,
    languages,
    publication_status, indexing_status, evaluation_status, licence_status,
    indexed_chunk_count, source_document_count, source_priority_policy,
    display_note_en, display_note_bn,
    is_available, blocked_reasons
"""


class OfferingNotFound(LookupError):
    """No offering matches the identifiers given."""


@dataclass(frozen=True)
class OfferingUnavailable(Exception):
    """
    An offering exists but may not be queried.

    `reasons` comes straight from the view, so the caller can explain the refusal
    instead of returning a bare 403. `display_note` is the student-facing copy the
    registry holds for exactly this moment.
    """

    slug: str
    reasons: tuple[str, ...] = ()
    display_note_en: str | None = None
    display_note_bn: str | None = None
    publication_status: str | None = None

    def __str__(self) -> str:
        why = ", ".join(self.reasons) or "unknown"
        return f"offering '{self.slug}' is not available ({why})"


@dataclass(frozen=True)
class Offering:
    """One (curriculum, subject, level, syllabus version) as the registry sees it."""

    offering_id: str
    slug: str
    curriculum_code: str
    curriculum_name: str
    subject_code: str
    subject_name_en: str
    subject_name_bn: str | None
    level_code: str
    level_name: str
    syllabus_version_code: str | None
    specification_reference: str | None
    languages: tuple[str, ...]
    publication_status: str
    indexing_status: str
    evaluation_status: str
    licence_status: str
    indexed_chunk_count: int
    source_document_count: int
    source_priority_policy: tuple[str, ...]
    display_note_en: str | None
    display_note_bn: str | None
    is_available: bool
    blocked_reasons: tuple[str, ...] = field(default=())

    @classmethod
    def from_row(cls, row: dict[str, Any]) -> "Offering":
        return cls(
            offering_id=str(row["offering_id"]),
            slug=row["slug"],
            curriculum_code=row["curriculum_code"],
            curriculum_name=row["curriculum_name"],
            subject_code=row["subject_code"],
            subject_name_en=row["subject_name_en"],
            subject_name_bn=row["subject_name_bn"],
            level_code=row["level_code"],
            level_name=row["level_name"],
            syllabus_version_code=row["syllabus_version_code"],
            specification_reference=row["specification_reference"],
            languages=tuple(row["languages"] or ()),
            publication_status=row["publication_status"],
            indexing_status=row["indexing_status"],
            evaluation_status=row["evaluation_status"],
            licence_status=row["licence_status"],
            indexed_chunk_count=row["indexed_chunk_count"],
            source_document_count=row["source_document_count"],
            source_priority_policy=tuple(row["source_priority_policy"] or ()),
            display_note_en=row["display_note_en"],
            display_note_bn=row["display_note_bn"],
            is_available=bool(row["is_available"]),
            blocked_reasons=tuple(row["blocked_reasons"] or ()),
        )

    def as_dict(self) -> dict[str, Any]:
        d = self.__dict__.copy()
        for k in ("languages", "source_priority_policy", "blocked_reasons"):
            d[k] = list(d[k])
        return d


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError(
            "DATABASE_URL is not set. Lumos does not fall back to a default "
            "connection string (ADR-012)."
        )
    return url


class CurriculumRegistry:
    """
    Read access to the registry.

    Holds no connection of its own: a `psycopg.Connection` is passed in, so the
    caller owns pooling and transaction scope. Every method is a read.
    """

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    # ── queries ──────────────────────────────────────────────────────────────

    def list_offerings(self, *, include_hidden: bool = False) -> list[Offering]:
        """All offerings, in the order a subject list should render."""
        sql = f"SELECT {_SELECT} FROM curriculum_availability"
        if not include_hidden:
            sql += " WHERE publication_status <> 'hidden'"
        sql += " ORDER BY curriculum_code, level_sort_order, subject_code"
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql)
            return [Offering.from_row(r) for r in cur.fetchall()]

    def get_by_slug(self, slug: str) -> Offering:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(f"SELECT {_SELECT} FROM curriculum_availability WHERE slug = %s", (slug,))
            row = cur.fetchone()
        if row is None:
            raise OfferingNotFound(f"no offering with slug '{slug}'")
        return Offering.from_row(row)

    def resolve(self, *, curriculum: str, subject: str, level: str,
                syllabus_version: str | None = None) -> Offering:
        """
        Look an offering up the way a request names it.

        Codes are matched case-insensitively, because a student-facing client
        should not be able to cause a 404 with `physics` instead of `PHYSICS`.

        Hyphens and underscores are also treated as the same separator, for the
        same reason and a sharper one: `GET /curriculum` publishes the slug
        `edexcel-ial/physics/international-as`, while the stored codes are
        `EDEXCEL_IAL` / `INTERNATIONAL_AS`. Feeding those published segments
        straight back to this method used to raise `OfferingNotFound`, so a
        client that did exactly what the API told it would be informed that the
        one offering in demo scope does not exist. A 404 that contradicts the
        listing endpoint is worse than a strict match is valuable.

        Widening the match cannot make a lookup ambiguous on its own: no stored
        code contains a hyphen, and the multi-row guard below still catches any
        genuine ambiguity.
        """
        sql = f"""
            SELECT {_SELECT} FROM curriculum_availability
            WHERE {_CODE_MATCH.format(column='curriculum_code')}
              AND {_CODE_MATCH.format(column='subject_code')}
              AND {_CODE_MATCH.format(column='level_code')}
        """
        params: list[Any] = [curriculum, subject, level]
        if syllabus_version is not None:
            sql += f" AND {_CODE_MATCH.format(column='syllabus_version_code')}"
            params.append(syllabus_version)
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        if not rows:
            raise OfferingNotFound(
                f"no offering for curriculum={curriculum!r} subject={subject!r} level={level!r}"
            )
        if len(rows) > 1 and syllabus_version is None:
            raise OfferingNotFound(
                f"{len(rows)} offerings match curriculum={curriculum!r} subject={subject!r} "
                f"level={level!r}; specify a syllabus version"
            )
        return Offering.from_row(rows[0])

    def available_offerings(self) -> list[Offering]:
        return [o for o in self.list_offerings() if o.is_available]

    # ── the gate ─────────────────────────────────────────────────────────────

    def require_available(self, *, slug: str | None = None,
                          curriculum: str | None = None, subject: str | None = None,
                          level: str | None = None,
                          syllabus_version: str | None = None) -> Offering:
        """
        Resolve an offering and refuse it unless the registry says it is available.

        Call this before retrieval. It raises rather than returning a flag, so a
        forgotten `if` cannot become an ungrounded answer.

        Name the offering by `slug` — the identifier `GET /curriculum` publishes —
        or by the `curriculum` / `subject` / `level` code triple. Slug is
        preferred: it is what a client that read the listing actually holds, and
        it is not derivable from the codes (`edexcel-ial/physics/a2` against a
        stored level code of `IAL_A2`).

        Raises:
            OfferingNotFound:    nothing matches those identifiers
            OfferingUnavailable: it exists but is not available, with reasons
        """
        if slug:
            offering = self.get_by_slug(slug)
        else:
            if not (curriculum and subject and level):
                raise OfferingNotFound(
                    "name the offering by slug, or by curriculum + subject + level")
            offering = self.resolve(curriculum=curriculum, subject=subject,
                                    level=level, syllabus_version=syllabus_version)
        if not offering.is_available:
            raise OfferingUnavailable(
                slug=offering.slug,
                reasons=offering.blocked_reasons,
                display_note_en=offering.display_note_en,
                display_note_bn=offering.display_note_bn,
                publication_status=offering.publication_status,
            )
        return offering

    # ── source documents ─────────────────────────────────────────────────────

    def source_documents(self, offering_id: str, *, include_private: bool = False
                         ) -> list[dict[str, Any]]:
        """
        Documents backing an offering, most authoritative first.

        Private (licensed) documents are excluded by default: their filenames and
        paths are not student-facing, and nothing outside ingestion needs them.
        """
        sql = """
            SELECT id, document_type, source_priority, title, filename,
                   page_count, ingestion_route, paper_code, unit_number,
                   session_year, session_series, language, licence_status,
                   is_private, sha256, bytes
            FROM source_documents
            WHERE offering_id = %s
        """
        params: list[Any] = [offering_id]
        if not include_private:
            sql += " AND is_private = false"
        sql += " ORDER BY source_priority, document_type, paper_code NULLS LAST, filename"
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(sql, params)
            return [dict(r) | {"id": str(r["id"])} for r in cur.fetchall()]

    def corpus_snapshots(self, offering_id: str) -> list[dict[str, Any]]:
        """Audited record counts with their provenance, newest first."""
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT method, evidence_ref, record_count, notes, taken_at
                FROM corpus_snapshots WHERE offering_id = %s
                ORDER BY taken_at DESC
                """, (offering_id,))
            return [dict(r) for r in cur.fetchall()]

    # ── consistency ──────────────────────────────────────────────────────────

    def audited_record_counts(self) -> dict[str, int]:
        """
        Latest audited record count per offering slug.

        Used by `scripts/check_registry_consistency.py` to assert that the
        registry and the corpus auditor still agree — the guard against a
        documented figure drifting away from the data again (ADR-008).
        """
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (o.slug) o.slug, cs.record_count
                FROM corpus_snapshots cs
                JOIN subject_offerings o ON o.id = cs.offering_id
                ORDER BY o.slug, cs.taken_at DESC
                """)
            return {r["slug"]: r["record_count"] for r in cur.fetchall()}


def connect() -> psycopg.Connection:
    """Open a connection using DATABASE_URL. The caller closes it."""
    return psycopg.connect(database_url())


def offerings_to_public_dicts(offerings: Iterable[Offering]) -> list[dict[str, Any]]:
    """
    Shape offerings for a client.

    Deliberately omits `licence_status` and source filenames — licensing terms
    and the names of licensed files are internal, and a student-facing payload
    has no use for either.
    """
    out = []
    for o in offerings:
        d = o.as_dict()
        d.pop("licence_status", None)
        out.append(d)
    return out
