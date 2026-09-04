"""
services.ingestion.legacy_adapter — legacy JSONL to canonical chunks.

Converts the 180 verified legacy records into the canonical model without
destroying what they already are. Three rules govern every decision here:

**Nothing is invented.** The legacy files carry no curriculum, no language, no
document type, no source priority, no question structure. Where a value can be
derived from evidence — language from the script the text is written in — it is
derived and the derivation is recorded. Where it cannot, the value is `None` or
`'unknown'`. A plausible guess in a provenance field is worse than a blank one,
because a blank one is visibly a gap.

**Nothing is lost.** The complete original record is stored in
`legacy_metadata`, and `legacy_chunk_id` keeps the identifier the record arrived
with (`SSC-ICT-C1-P1-CH1`). Normalisation stays reviewable and reversible.

**Nothing is re-chunked.** These become `legacy_record` chunks, not
`textbook_section` chunks, because they have not been re-chunked yet: the 43
English records are whole textbook units of roughly 2,000 tokens. Calling them
sections would assert a granularity they do not have. Re-chunking is LUMOS-004C.

The adapter is deterministic and idempotent: same files in, same chunk ids out,
and a second run writes nothing.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

import psycopg
from psycopg.rows import dict_row

from .canonical import CanonicalChunk, ChunkWriter, WriteResult, record_run

BANGLA_RE = re.compile(r"[ঀ-৿]")

# The legacy corpora split on this: 80 records use `chapter_title`, 100 use
# `chapter_name`, and both mean the same thing. Reading only one of them is why
# both legacy repositories displayed `Chapter N: None` for 100 records.
CHAPTER_FIELDS = ("chapter_title", "chapter_name")


@dataclass
class LegacyDocument:
    """A legacy JSONL file, paired with the registry row that describes it."""

    path: Path
    source_document_id: str
    offering_id: str
    declared_language: str
    sha256: str


@dataclass
class LegacyNormalisationReport:
    """What the run saw and did, per offering. Counts only — never source text."""

    documents: int = 0
    source_records: int = 0
    write: WriteResult = field(default_factory=WriteResult)
    by_offering: dict[str, dict[str, int]] = field(default_factory=dict)
    duplicate_content_groups: dict[str, list[str]] = field(default_factory=dict)
    missing_documents: list[str] = field(default_factory=list)
    field_gaps: dict[str, int] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "documents": self.documents,
            "source_records": self.source_records,
            "write": self.write.as_dict(),
            "by_offering": self.by_offering,
            "duplicate_content_groups": {
                h: locs for h, locs in self.duplicate_content_groups.items()},
            "missing_documents": self.missing_documents,
            "field_gaps": self.field_gaps,
        }


def sha256_file(path: Path, block: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(block):
            h.update(chunk)
    return h.hexdigest()


def detect_language(text: str, declared: str | None) -> str:
    """
    Derive the language from the script the text is actually written in.

    The legacy files carry no language field; `shikhbo-ai/ingest.py` injected one
    at ingest time by hardcoding it per corpus. Deriving it from the content is
    both more honest and more robust — an English gloss inside a Bangla chapter
    is still Bangla text, and a mislabelled file cannot mislead us.

    Falls back to whatever the registry declared, then to `'unknown'`.
    """
    if BANGLA_RE.search(text):
        return "bn"
    if declared in ("bn", "en"):
        return declared
    return "en" if text.strip() else "unknown"


def reconcile_chapter(record: dict[str, Any]) -> tuple[str | None, str | None]:
    """
    Resolve the `chapter_title` / `chapter_name` split.

    Returns (value, field_it_came_from) so the choice is recorded rather than
    silently made.
    """
    for name in CHAPTER_FIELDS:
        value = record.get(name)
        if isinstance(value, str) and value.strip():
            return value.strip(), name
    return None, None


def _clean_optional(value: Any) -> str | None:
    """Empty strings and blanks become None. An empty string is not a value."""
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def record_to_chunk(record: dict[str, Any], doc: LegacyDocument,
                    ordinal: int) -> CanonicalChunk:
    """
    Map one legacy JSONL record onto the canonical model.

    Every field the legacy record does not supply becomes an explicit `None`.
    """
    legacy_id = _clean_optional(record.get("chunk_id"))
    if legacy_id is None:
        raise ValueError(
            f"legacy record {ordinal} in {doc.path.name} has no chunk_id — "
            "traceability cannot be reconstructed, so it is not ingested"
        )

    content = record.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError(f"legacy record {legacy_id} has no content")

    chapter, chapter_field = reconcile_chapter(record)
    keywords = record.get("keywords")
    keywords = [k for k in keywords if isinstance(k, str) and k.strip()] \
        if isinstance(keywords, list) else []

    return CanonicalChunk(
        source_document_id=doc.source_document_id,
        offering_id=doc.offering_id,
        document_sha256=doc.sha256,
        locator=f"legacy/{legacy_id}",
        text=content,
        chunk_type="legacy_record",
        extraction_method="structured_jsonl",
        ordinal=ordinal,
        page_number=_int_or_none(record.get("page_no")),
        section_ref=chapter,
        topic=_clean_optional(record.get("topic")),
        # Present on the 17 Physics records only; None everywhere else, and that
        # absence is real information about the corpus.
        syllabus_reference=_clean_optional(record.get("spec_ref")),
        language=detect_language(content, doc.declared_language),
        keywords=keywords,
        prerequisite_text=_clean_optional(record.get("prerequisite")),
        # Recorded, never trusted: legacy token counts disagree with any
        # recomputation on 134 of 180 records.
        legacy_token_count=_int_or_none(record.get("token_count")),
        legacy_chunk_id=legacy_id,
        # The original record, whole. Normalisation stays reviewable, and no
        # legacy field is lost because the canonical model had nowhere for it.
        legacy_metadata={
            "record": record,
            "source_file": doc.path.name,
            "chapter_field_used": chapter_field,
        },
        notes=(
            "Legacy corpus record, normalised but not re-chunked (LUMOS-004C). "
            f"Chapter label read from '{chapter_field}'."
            if chapter_field else
            "Legacy corpus record, normalised but not re-chunked (LUMOS-004C). "
            "No chapter label in the source."
        ),
    )


def iter_records(path: Path) -> Iterator[tuple[int, dict[str, Any]]]:
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if line:
                yield lineno, json.loads(line)


# ─────────────────────────────────────────────────────────────────────────────
# Run
# ─────────────────────────────────────────────────────────────────────────────

def resolve_documents(conn: psycopg.Connection, corpus_root: Path
                      ) -> tuple[list[LegacyDocument], list[str]]:
    """
    Pair each registered legacy document with the file on disk.

    A registry row with no file is reported, not skipped silently: it means the
    registry and the corpus have diverged, which is exactly the class of drift
    this project keeps finding.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT id, offering_id, filename, relative_path, language, sha256
            FROM source_documents
            WHERE document_type = 'legacy_corpus'
            ORDER BY relative_path
            """)
        rows = cur.fetchall()

    documents: list[LegacyDocument] = []
    missing: list[str] = []
    for row in rows:
        path = corpus_root / row["filename"]
        if not path.exists():
            missing.append(row["relative_path"] or row["filename"])
            continue
        documents.append(LegacyDocument(
            path=path,
            source_document_id=str(row["id"]),
            offering_id=str(row["offering_id"]),
            declared_language=row["language"],
            sha256=row["sha256"] or sha256_file(path),
        ))
    return documents, missing


def backfill_checksums(conn: psycopg.Connection, documents: list[LegacyDocument]) -> int:
    """
    Store the file checksum on any legacy document that lacks one.

    Chunk identity is derived from the document checksum, so a document without
    one cannot produce a stable chunk id. The registry seed could not compute
    these because it runs from an audit summary rather than the files themselves.
    """
    updated = 0
    with conn.cursor() as cur:
        for doc in documents:
            cur.execute(
                "UPDATE source_documents SET sha256 = %s "
                "WHERE id = %s AND sha256 IS DISTINCT FROM %s",
                (doc.sha256, doc.source_document_id, doc.sha256))
            updated += cur.rowcount
    return updated


def normalise_legacy_corpus(conn: psycopg.Connection, corpus_root: Path,
                            *, dry_run: bool = False) -> LegacyNormalisationReport:
    """
    Convert every registered legacy document into canonical chunks.

    Deterministic and idempotent. Returns a report of counts and gaps; it never
    returns source text, so the report is safe to write to disk and commit.
    """
    report = LegacyNormalisationReport()
    documents, missing = resolve_documents(conn, corpus_root)
    report.missing_documents = missing
    report.documents = len(documents)

    if not documents:
        report.write.warnings.append(
            f"no legacy documents found under {corpus_root} — nothing to normalise")
        return report

    backfill_checksums(conn, documents)

    writer = ChunkWriter(conn)
    content_seen: dict[str, list[str]] = {}
    gaps = {
        "no_chapter_label": 0, "no_topic": 0, "no_keywords": 0,
        "no_syllabus_reference": 0, "no_page_number": 0, "no_prerequisite": 0,
        "language_unknown": 0,
    }

    per_offering_chunks: dict[str, list[CanonicalChunk]] = {}
    per_offering_records: dict[str, int] = {}

    for doc in documents:
        for ordinal, (_, record) in enumerate(iter_records(doc.path)):
            chunk = record_to_chunk(record, doc, ordinal)
            report.source_records += 1
            per_offering_records[doc.offering_id] = \
                per_offering_records.get(doc.offering_id, 0) + 1
            per_offering_chunks.setdefault(doc.offering_id, []).append(chunk)

            content_seen.setdefault(chunk.content_sha256, []).append(chunk.legacy_chunk_id or "")

            if chunk.section_ref is None:
                gaps["no_chapter_label"] += 1
            if chunk.topic is None:
                gaps["no_topic"] += 1
            if not chunk.keywords:
                gaps["no_keywords"] += 1
            if chunk.syllabus_reference is None:
                gaps["no_syllabus_reference"] += 1
            if chunk.page_number is None:
                gaps["no_page_number"] += 1
            if chunk.prerequisite_text is None:
                gaps["no_prerequisite"] += 1
            if chunk.language == "unknown":
                gaps["language_unknown"] += 1

    report.field_gaps = gaps
    report.duplicate_content_groups = {
        h: ids for h, ids in content_seen.items() if len(ids) > 1}

    if dry_run:
        for offering_id, chunks in per_offering_chunks.items():
            report.by_offering[offering_id] = {
                "source_records": per_offering_records[offering_id],
                "chunks": len(chunks),
            }
        return report

    for offering_id, chunks in per_offering_chunks.items():
        result = writer.write(chunks)
        record_run(conn, offering_id=offering_id, adapter="legacy_corpus",
                   source_records=per_offering_records[offering_id], result=result)
        report.by_offering[offering_id] = {
            "source_records": per_offering_records[offering_id],
            "chunks": result.total,
            "created": result.created,
            "updated": result.updated,
            "unchanged": result.unchanged,
        }
        report.write.created += result.created
        report.write.updated += result.updated
        report.write.unchanged += result.unchanged
        report.write.duplicates_seen += result.duplicates_seen
        report.write.warnings.extend(result.warnings)

    return report
