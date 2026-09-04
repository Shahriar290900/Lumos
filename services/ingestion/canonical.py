"""
services.ingestion.canonical — the canonical chunk model.

Everything Lumos ever retrieves is a `CanonicalChunk`, whatever it came from:
a legacy JSONL record, a scanned textbook page, an exam question, a mark scheme,
an examiner report. Adding a curriculum or a source type must not require
changing this model.

Three properties this module is responsible for.

**Deterministic identity.** A chunk's id is `uuid5(LUMOS_CHUNK_NAMESPACE,
chunk_key)`, and the key is `lumos:v1:<source document sha256>:<locator>`. The
same input always produces the same id, and — because the document's checksum is
inside the key — question 12 of WPH11 May 2024 cannot collide with question 12 of
WPH12, or of any other session, even though both are "question 12".

**Idempotency.** `ChunkWriter` compares a fingerprint of every persisted field
before writing, so re-running normalisation over unchanged input reports
`unchanged` rather than churning rows. Running the adapter twice is a no-op, not
a duplication risk.

**Honesty about provenance.** `extraction_method`, `provenance_status` and
`text_raw` travel with the chunk. OCR output is never stored as though it were
exact, and a transformed chunk always keeps the text it was transformed from.
Where a source does not supply a field, the value is an explicit `None` or
`'unknown'` — never an invented plausible value.
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Iterable, Sequence

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Json

# Fixed for the life of the project. Changing it re-identifies every chunk, so
# it is a constant, not configuration.
LUMOS_CHUNK_NAMESPACE = uuid.UUID("6c9d1f2a-3b4e-5d6f-8a7b-9c0d1e2f3a4b")

# Bumped when the key *format* changes, which is a re-identification event.
# Not the same as ingestion_version, which records which pipeline built the text.
CHUNK_KEY_VERSION = 1

# Bumped when the pipeline changes what it produces from the same input.
INGESTION_VERSION = "004c.1"

CHUNK_TYPES = frozenset({
    "exam_question", "mark_scheme_answer", "examiner_commentary",
    "textbook_section", "specification_point", "legacy_record", "unknown",
})
EXTRACTION_METHODS = frozenset({
    "pdf_text_layer", "ocr_tesseract", "structured_jsonl", "manual", "unknown",
})
PROVENANCE_STATUSES = frozenset({
    "verbatim", "cleaned", "normalized", "derived", "ocr_uncertain",
})

# Fields written to the database, in a fixed order. The order is part of the
# fingerprint, so it must not be shuffled casually.
PERSISTED_FIELDS: tuple[str, ...] = (
    "chunk_key", "source_document_id", "offering_id", "chunk_type", "ordinal",
    "page_number", "page_number_end", "section_ref", "topic", "syllabus_reference",
    "question_number", "sub_question", "marks", "sub_parts", "parent_chunk_id",
    "depends_on", "text", "text_raw", "content_sha256", "language",
    "token_count", "legacy_token_count", "keywords", "prerequisite_text",
    "legacy_chunk_id", "legacy_metadata", "extraction_method",
    "provenance_status", "extraction_confidence", "ingestion_version", "notes",
)


# ─────────────────────────────────────────────────────────────────────────────
# Identity
# ─────────────────────────────────────────────────────────────────────────────

def make_chunk_key(document_sha256: str, locator: str,
                   version: int = CHUNK_KEY_VERSION) -> str:
    """
    Build the natural key a chunk id is derived from.

    `document_sha256` is the checksum of the file the chunk came from. Putting it
    in the key is what prevents identity collision between the same logical
    question in different documents or sessions.

    `locator` says where in that document the chunk is — `q/12`, `p45/3`,
    `legacy/SSC-ICT-C1-P1-CH1`. It must be stable across runs; anything derived
    from iteration order or a timestamp would break determinism.
    """
    if not isinstance(document_sha256, str) or len(document_sha256) != 64:
        raise ValueError(
            f"document_sha256 must be a 64-character hex digest, got {document_sha256!r}. "
            "A chunk cannot be identified without knowing which file it came from."
        )
    digest = document_sha256.lower()
    if any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError(f"document_sha256 is not hexadecimal: {document_sha256!r}")
    locator = locator.strip()
    if not locator:
        raise ValueError("locator must not be empty")
    return f"lumos:v{version}:{digest}:{locator}"


def make_chunk_id(chunk_key: str) -> uuid.UUID:
    """Deterministic id for a chunk key. Same key in, same uuid out, forever."""
    return uuid.uuid5(LUMOS_CHUNK_NAMESPACE, chunk_key)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalise_text(raw: str) -> tuple[str, str]:
    """
    Apply the transformations every chunk gets, and say which one happened.

    Only Unicode NFC and trailing-whitespace tidying. No spelling repair, no
    boilerplate stripping, no OCR correction — those are separate, recorded
    pipeline stages, not something this function does silently.

    Returns (text, provenance_status). `provenance_status` is `verbatim` when
    nothing changed, so the label reflects what actually happened to this chunk
    rather than a blanket claim about the batch.
    """
    text = unicodedata.normalize("NFC", raw)
    text = "\n".join(line.rstrip() for line in text.split("\n")).strip()
    return text, ("verbatim" if text == raw else "normalized")


def count_tokens(text: str, language: str) -> int:
    """
    A deterministic, dependency-free token estimate.

    Not a model tokeniser. Bangla subword tokenisation inflates counts well above
    whitespace-word counts, so a single word-count heuristic would misreport one
    language or the other; this uses a per-script divisor instead.

    It exists so `token_count` is *recomputed and reproducible* rather than
    inherited from legacy values that disagreed with reality on 134 of 180
    records. It will be replaced by the real tokeniser when the Model Gateway
    exists — hence `ingestion_version`.
    """
    if not text:
        return 0
    bengali = sum(1 for ch in text if "ঀ" <= ch <= "৿")
    if bengali > len(text) * 0.3 or language == "bn":
        return max(1, len(text) // 3)      # Bangla: roughly 3 characters per token
    return max(1, len(text.split()))       # Latin script: roughly one word per token


# ─────────────────────────────────────────────────────────────────────────────
# The model
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CanonicalChunk:
    """
    One chunk, in the form every source normalises into.

    Required: what the chunk is, where it came from, and what it says. Everything
    else is optional and stays `None` when the source does not supply it.
    """

    # identity and lineage
    source_document_id: str
    offering_id: str
    document_sha256: str
    locator: str

    # content
    text: str
    chunk_type: str

    # provenance
    extraction_method: str = "unknown"
    ingestion_version: str = INGESTION_VERSION
    extraction_confidence: float | None = None
    provenance_status: str | None = None     # inferred from normalisation if None
    text_raw: str | None = None

    # location
    ordinal: int = 0
    page_number: int | None = None
    page_number_end: int | None = None
    section_ref: str | None = None
    topic: str | None = None
    syllabus_reference: str | None = None

    # exam structure
    question_number: str | None = None
    sub_question: str | None = None
    marks: int | None = None
    sub_parts: list[dict[str, Any]] = field(default_factory=list)
    parent_chunk_id: str | None = None
    depends_on: list[str] = field(default_factory=list)

    # descriptive
    language: str = "unknown"
    keywords: list[str] = field(default_factory=list)
    prerequisite_text: str | None = None
    legacy_token_count: int | None = None

    # legacy traceability
    legacy_chunk_id: str | None = None
    legacy_metadata: dict[str, Any] | None = None

    notes: str | None = None

    # derived, filled in __post_init__
    chunk_key: str = field(init=False)
    id: str = field(init=False)
    content_sha256: str = field(init=False)
    token_count: int = field(init=False)

    def __post_init__(self) -> None:
        if self.chunk_type not in CHUNK_TYPES:
            raise ValueError(f"unknown chunk_type {self.chunk_type!r}")
        if self.extraction_method not in EXTRACTION_METHODS:
            raise ValueError(f"unknown extraction_method {self.extraction_method!r}")

        raw = self.text
        text, inferred = normalise_text(raw)
        if not text:
            raise ValueError(
                f"chunk at {self.locator!r} has no text after normalisation — "
                "an empty chunk is a parsing failure, not a valid record"
            )
        self.text = text

        # An explicitly supplied status wins: an OCR adapter knows its output is
        # uncertain even when NFC happened to change nothing.
        if self.provenance_status is None:
            self.provenance_status = inferred
        if self.provenance_status not in PROVENANCE_STATUSES:
            raise ValueError(f"unknown provenance_status {self.provenance_status!r}")

        # A transformed chunk must keep what it was transformed from. The database
        # enforces this too; failing here gives a better message.
        if self.provenance_status not in ("verbatim", "ocr_uncertain") and self.text_raw is None:
            self.text_raw = raw

        self.chunk_key = make_chunk_key(self.document_sha256, self.locator)
        self.id = str(make_chunk_id(self.chunk_key))
        self.content_sha256 = sha256_text(self.text)
        self.token_count = count_tokens(self.text, self.language)

    # ── persistence shape ────────────────────────────────────────────────────

    def to_row(self) -> dict[str, Any]:
        """The row as the database stores it, minus the fingerprint."""
        return {
            "id": self.id,
            "chunk_key": self.chunk_key,
            "source_document_id": self.source_document_id,
            "offering_id": self.offering_id,
            "chunk_type": self.chunk_type,
            "ordinal": self.ordinal,
            "page_number": self.page_number,
            "page_number_end": self.page_number_end,
            "section_ref": self.section_ref,
            "topic": self.topic,
            "syllabus_reference": self.syllabus_reference,
            "question_number": self.question_number,
            "sub_question": self.sub_question,
            "marks": self.marks,
            "sub_parts": self.sub_parts,
            "parent_chunk_id": self.parent_chunk_id,
            "depends_on": self.depends_on,
            "text": self.text,
            "text_raw": self.text_raw,
            "content_sha256": self.content_sha256,
            "language": self.language,
            "token_count": self.token_count,
            "legacy_token_count": self.legacy_token_count,
            "keywords": self.keywords,
            "prerequisite_text": self.prerequisite_text,
            "legacy_chunk_id": self.legacy_chunk_id,
            "legacy_metadata": self.legacy_metadata,
            "extraction_method": self.extraction_method,
            "provenance_status": self.provenance_status,
            "extraction_confidence": self.extraction_confidence,
            "ingestion_version": self.ingestion_version,
            "notes": self.notes,
        }

    def fingerprint(self) -> str:
        """
        Hash of every persisted field.

        Deterministic across runs and processes: JSON with sorted keys, no
        floats formatted by locale, no object identity. Two chunks with the same
        fingerprint are the same row.
        """
        row = self.to_row()
        payload = [_stable(row.get(name)) for name in PERSISTED_FIELDS]
        blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _stable(value: Any) -> Any:
    """Coerce a value into something json.dumps renders identically every time."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, float):
        return format(value, ".6f")
    if isinstance(value, (list, tuple)):
        return [_stable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _stable(v) for k, v in sorted(value.items())}
    return value


# ─────────────────────────────────────────────────────────────────────────────
# Writing
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class WriteResult:
    """What a normalisation run actually did. Reported, not estimated."""

    created: int = 0
    updated: int = 0
    unchanged: int = 0
    duplicates_seen: int = 0
    warnings: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.created + self.updated + self.unchanged

    def as_dict(self) -> dict[str, Any]:
        return {**asdict(self), "total": self.total}


class ChunkWriter:
    """
    Idempotent writer for canonical chunks.

    Re-running an adapter over unchanged input produces `unchanged` counts and no
    writes. That is what makes normalisation safe to run repeatedly — in CI, after
    a crash, or when only one document has changed.
    """

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def write(self, chunks: Sequence[CanonicalChunk]) -> WriteResult:
        result = WriteResult()
        if not chunks:
            return result

        # A duplicate key inside one batch means the adapter built two chunks with
        # the same locator — a bug in the adapter, not in the data. Surface it.
        seen: dict[str, CanonicalChunk] = {}
        for chunk in chunks:
            if chunk.chunk_key in seen:
                result.duplicates_seen += 1
                result.warnings.append(
                    f"duplicate chunk_key within one batch: {chunk.chunk_key}")
                continue
            seen[chunk.chunk_key] = chunk
        unique = list(seen.values())

        existing = self._existing_fingerprints([c.id for c in unique])

        to_write: list[tuple[CanonicalChunk, str]] = []
        for chunk in unique:
            fp = chunk.fingerprint()
            prior = existing.get(chunk.id)
            if prior is None:
                result.created += 1
                to_write.append((chunk, fp))
            elif prior != fp:
                result.updated += 1
                to_write.append((chunk, fp))
            else:
                result.unchanged += 1

        if to_write:
            self._upsert(to_write)
        return result

    # ── internals ────────────────────────────────────────────────────────────

    def _existing_fingerprints(self, ids: Iterable[str]) -> dict[str, str]:
        ids = list(ids)
        if not ids:
            return {}
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT id, row_fingerprint FROM chunks WHERE id = ANY(%s::uuid[])",
                (ids,))
            return {str(r["id"]): r["row_fingerprint"] for r in cur.fetchall()}

    def _upsert(self, rows: Sequence[tuple[CanonicalChunk, str]]) -> None:
        columns = ["id", *PERSISTED_FIELDS, "row_fingerprint"]
        placeholders = ", ".join(f"%({c})s" for c in columns)
        updates = ", ".join(f"{c} = EXCLUDED.{c}" for c in columns if c != "id")
        sql = (
            f"INSERT INTO chunks ({', '.join(columns)}) VALUES ({placeholders}) "
            f"ON CONFLICT (id) DO UPDATE SET {updates}, updated_at = now()"
        )
        payload = []
        for chunk, fp in rows:
            row = chunk.to_row()
            row["row_fingerprint"] = fp
            row["sub_parts"] = Json(row["sub_parts"])
            row["legacy_metadata"] = (
                Json(row["legacy_metadata"]) if row["legacy_metadata"] is not None else None)
            payload.append(row)
        with self._conn.cursor() as cur:
            cur.executemany(sql, payload)


def record_run(conn: psycopg.Connection, *, offering_id: str | None, adapter: str,
               source_records: int, result: WriteResult) -> str:
    """
    Persist what a run did, so a chunk count in a document always has a run behind it.

    The same discipline as `corpus_snapshots`, one pipeline stage later.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            INSERT INTO normalisation_runs
                (offering_id, adapter, ingestion_version, source_records,
                 chunks_created, chunks_updated, chunks_unchanged,
                 duplicates_seen, warnings, finished_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, now())
            RETURNING id
            """,
            (offering_id, adapter, INGESTION_VERSION, source_records,
             result.created, result.updated, result.unchanged,
             result.duplicates_seen, Json(result.warnings)))
        return str(cur.fetchone()["id"])
