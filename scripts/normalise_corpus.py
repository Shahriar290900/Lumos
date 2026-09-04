#!/usr/bin/env python3
"""
normalise_corpus.py — run the normalisation adapters and record what they did.

Converts registered sources into canonical chunks and writes a metadata-only
report to `evidence/`. The report contains counts, checksummed identities,
structural facts and gap tallies — **never source text** — so it is safe to
commit while the documents it describes are not.

Two adapters:

    legacy    the registered legacy JSONL corpora  (always available)
    papers    Edexcel past papers                  (needs the private PDFs)

Both are deterministic and idempotent. Running either twice is a no-op: the
second run reports `unchanged` and writes nothing.

Usage
-----
    DATABASE_URL=... python scripts/normalise_corpus.py legacy \\
        --corpus-root /path/to/Shikhbo-Local-App/raw_data \\
        --output evidence/legacy_normalisation.json

    DATABASE_URL=... python scripts/normalise_corpus.py papers \\
        --sources-root private_source_materials \\
        --output evidence/past_paper_structure.json

    DATABASE_URL=... python scripts/normalise_corpus.py legacy --dry-run

Exit codes: 0 ran · 1 ran with reconciliation failures · 2 could not run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from services.ingestion.canonical import (  # noqa: E402
    INGESTION_VERSION, ChunkWriter, record_run,
)
from services.ingestion.legacy_adapter import normalise_legacy_corpus  # noqa: E402
from services.ingestion.past_paper import (  # noqa: E402
    extract_pages, parse_questions, questions_to_chunks,
)

# Which audited subject backs which offering, mirroring the consistency checker.
AUDIT_SUBJECT_BY_SLUG = {
    "nctb/ict/ssc": "ICT",
    "nctb/english/ssc": "English",
    "edexcel-ial/physics/a2": "Physics",
}


def _slugs(conn: psycopg.Connection) -> dict[str, str]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id, slug FROM subject_offerings")
        return {str(r["id"]): r["slug"] for r in cur.fetchall()}


def _chunk_counts(conn: psycopg.Connection, chunk_type: str | None = None) -> dict[str, int]:
    """
    Chunks per offering, optionally restricted to one chunk type.

    The restriction matters: one offering can hold chunks from several adapters.
    `edexcel-ial/physics/a2` carries 17 normalised legacy records *and* the
    questions parsed from its A2 papers, so reconciling the legacy adapter
    against a total count would compare it to a number it never produced.
    """
    sql = """
        SELECT o.slug, count(c.id) AS n
        FROM subject_offerings o
        LEFT JOIN chunks c ON c.offering_id = o.id
    """
    params: list[Any] = []
    if chunk_type is not None:
        sql += " AND c.chunk_type = %s"
        params.append(chunk_type)
    sql += " GROUP BY o.slug ORDER BY o.slug"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return {r["slug"]: r["n"] for r in cur.fetchall()}


def _source_record_counts(conn: psycopg.Connection) -> dict[str, int]:
    """
    Distinct legacy source records per offering, however many chunks each became.

    This is the invariant that survives LUMOS-004C.1. Before re-chunking, one
    audited record was one chunk and comparing chunk counts to the auditor was
    the same test. After re-chunking it is not: the 43 English records become
    110 chunks, and a chunk-count comparison would report that as normalisation
    inventing 67 records.

    What must still hold is that no record was lost and none invented, and
    `count(distinct legacy_chunk_id)` says exactly that regardless of how the
    text was divided. Chunk counts are still reported — they are just no longer
    the thing being reconciled.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT o.slug, count(DISTINCT c.legacy_chunk_id) AS n
            FROM subject_offerings o
            LEFT JOIN chunks c
              ON c.offering_id = o.id
             AND c.chunk_type = 'legacy_record'
             AND c.legacy_chunk_id IS NOT NULL
            GROUP BY o.slug ORDER BY o.slug
            """)
        return {r["slug"]: r["n"] for r in cur.fetchall()}


# ─────────────────────────────────────────────────────────────────────────────
# legacy
# ─────────────────────────────────────────────────────────────────────────────

def run_legacy(conn: psycopg.Connection, corpus_root: Path, audit_path: Path,
               dry_run: bool) -> tuple[dict[str, Any], list[str]]:
    # Legacy reconciliation counts legacy records only — see _chunk_counts.
    before = _chunk_counts(conn, "legacy_record")
    report = normalise_legacy_corpus(conn, corpus_root, dry_run=dry_run)
    if not dry_run:
        conn.commit()
    after = _chunk_counts(conn, "legacy_record")
    sources = _source_record_counts(conn)
    slugs = _slugs(conn)

    by_slug = {slugs.get(oid, oid): stats for oid, stats in report.by_offering.items()}

    # Reconcile against the corpus auditor. A canonical chunk count that does not
    # equal the audited record count means normalisation dropped or invented a
    # record, and that must fail loudly rather than appear in a summary.
    failures: list[str] = []
    reconciliation: dict[str, Any] = {}
    if audit_path.exists():
        audit = json.loads(audit_path.read_text(encoding="utf-8"))
        audited = {k: v["records"] for k, v in audit.get("subjects", {}).items()}
        for slug, subject in AUDIT_SUBJECT_BY_SLUG.items():
            expected = audited.get(subject)
            chunks = after.get(slug, 0) if not dry_run else \
                by_slug.get(slug, {}).get("chunks", 0)
            records = sources.get(slug, 0) if not dry_run else \
                by_slug.get(slug, {}).get("source_records", 0)
            reconciliation[slug] = {
                "audited_records": expected,
                "source_records_present": records,
                "canonical_chunks": chunks,
                "matches": expected == records,
            }
            if expected is not None and expected != records:
                failures.append(
                    f"{slug}: {records} source records present from {expected} audited "
                    "— normalisation lost or invented records")
            if expected is not None and chunks < records:
                failures.append(
                    f"{slug}: {chunks} chunks for {records} records — a record "
                    "must produce at least one chunk")
        total_expected = audit.get("total_records")
        total_records = sum(r["source_records_present"] for r in reconciliation.values())
        total_chunks = sum(r["canonical_chunks"] for r in reconciliation.values())
        reconciliation["_total"] = {
            "audited_records": total_expected,
            "source_records_present": total_records,
            "canonical_chunks": total_chunks,
            "matches": total_expected == total_records,
        }
        if total_expected is not None and total_expected != total_records:
            failures.append(
                f"total: {total_records} source records present from {total_expected} audited")
    else:
        failures.append(f"{audit_path} not found — cannot reconcile against the auditor")

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "adapter": "legacy_corpus",
        "ingestion_version": INGESTION_VERSION,
        "dry_run": dry_run,
        "note": (
            "Counts, identities and gap tallies only. No source text appears in "
            "this file."
        ),
        "documents": report.documents,
        "source_records": report.source_records,
        "write": report.write.as_dict(),
        "by_offering": by_slug,
        "legacy_chunk_counts_before": before,
        "legacy_chunk_counts_after": after,
        "reconciliation": reconciliation,
        # LUMOS-004C.1. Which repair fired how many times, and how many records
        # were split. Counts only — the stage names and tallies say what changed
        # without reproducing a character of source text.
        "cleaning": {
            "stages": report.cleaning_stages,
            "records_repaired": report.records_repaired,
            "records_split": report.records_split,
            "true_compound_prefixes": report.true_compound_prefixes,
            "pruned_stale_chunks": report.pruned_stale_chunks,
        },
        "field_gaps": report.field_gaps,
        "duplicate_content_groups": len(report.duplicate_content_groups),
        "duplicate_content_examples": {
            h[:16]: ids for h, ids in list(report.duplicate_content_groups.items())[:5]},
        "missing_documents": report.missing_documents,
    }
    return payload, failures


# ─────────────────────────────────────────────────────────────────────────────
# papers
# ─────────────────────────────────────────────────────────────────────────────

def run_papers(conn: psycopg.Connection, sources_root: Path,
               dry_run: bool) -> tuple[dict[str, Any], list[str]]:
    """
    Chunk the registered past papers whose text layer can be parsed.

    Only documents already in the registry are processed, and only those whose
    recorded ingestion route is `text` — a document needing OCR is skipped and
    reported, never guessed at.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT sd.id, sd.offering_id, sd.filename, sd.relative_path, sd.sha256,
                   sd.ingestion_route::text AS route, sd.paper_code,
                   sd.session_year, sd.session_series, o.slug
            FROM source_documents sd
            JOIN subject_offerings o ON o.id = sd.offering_id
            WHERE sd.document_type = 'past_paper'
            ORDER BY sd.paper_code
            """)
        documents = cur.fetchall()

    writer = ChunkWriter(conn)
    per_document: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    failures: list[str] = []
    before = _chunk_counts(conn)

    for doc in documents:
        path = sources_root / doc["relative_path"] if doc["relative_path"] else None
        if path is None or not path.exists():
            skipped.append({"filename": doc["filename"], "reason": "file not present"})
            continue
        if doc["route"] != "text":
            skipped.append({"filename": doc["filename"],
                            "reason": f"ingestion route is '{doc['route']}', not 'text'"})
            continue
        if not doc["sha256"]:
            skipped.append({"filename": doc["filename"], "reason": "no checksum recorded"})
            continue

        pages = extract_pages(path)
        questions, parse_report = parse_questions(pages)
        chunks = questions_to_chunks(
            questions,
            source_document_id=str(doc["id"]),
            offering_id=str(doc["offering_id"]),
            document_sha256=doc["sha256"],
            extraction_method="pdf_text_layer",
        )

        entry: dict[str, Any] = {
            "paper_code": doc["paper_code"],
            "offering": doc["slug"],
            "session": f"{doc['session_year']} {doc['session_series']}".strip(),
            "pages": len(pages),
            **parse_report.as_dict(),
            # Identity proof without content: the first eight chunk keys show that
            # the document checksum is embedded, so cross-paper collision is
            # impossible by construction.
            "chunk_key_sample": [c.chunk_key for c in chunks[:8]],
        }
        if not dry_run:
            result = writer.write(chunks)
            record_run(conn, offering_id=str(doc["offering_id"]), adapter="past_paper",
                       source_records=parse_report.questions_found, result=result)
            entry["write"] = result.as_dict()
        per_document.append(entry)
        for warning in parse_report.warnings:
            failures.append(f"{doc['paper_code']}: {warning}")

    if not dry_run:
        conn.commit()

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "adapter": "past_paper",
        "ingestion_version": INGESTION_VERSION,
        "dry_run": dry_run,
        "note": (
            "Structure and counts only. No question text, mark-scheme text or "
            "examiner commentary appears in this file — the source documents are "
            "licensed and are never redistributed."
        ),
        "documents_processed": len(per_document),
        "documents_skipped": skipped,
        "questions_total": sum(d["questions_found"] for d in per_document),
        "marks_total": sum(d["total_marks"] for d in per_document),
        "per_document": per_document,
        "chunk_counts_before": before,
        "chunk_counts_after": _chunk_counts(conn),
    }
    return payload, failures


# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("adapter", choices=["legacy", "papers"])
    ap.add_argument("--corpus-root", type=Path,
                    default=Path.home() / "recon/Shikhbo-Local-App/raw_data",
                    help="directory of legacy JSONL files")
    ap.add_argument("--sources-root", type=Path,
                    default=REPO_ROOT / "private_source_materials",
                    help="root of the private source materials")
    ap.add_argument("--audit", type=Path,
                    default=REPO_ROOT / "evidence/curriculum_audit_local.json")
    ap.add_argument("--output", type=Path, default=None)
    ap.add_argument("--dry-run", action="store_true",
                    help="parse and report without writing chunks")
    args = ap.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2

    with psycopg.connect(url) as conn:
        if args.adapter == "legacy":
            if not args.corpus_root.is_dir():
                print(f"corpus root not found: {args.corpus_root}", file=sys.stderr)
                return 2
            payload, failures = run_legacy(conn, args.corpus_root, args.audit, args.dry_run)
        else:
            payload, failures = run_papers(conn, args.sources_root, args.dry_run)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                               encoding="utf-8")

    print("=" * 74)
    print(f"adapter            : {payload['adapter']}"
          f"{'  (dry run)' if args.dry_run else ''}")
    print(f"ingestion version  : {payload['ingestion_version']}")
    if args.adapter == "legacy":
        print(f"documents          : {payload['documents']}")
        print(f"source records     : {payload['source_records']}")
        w = payload["write"]
        print(f"chunks             : created={w['created']} updated={w['updated']} "
              f"unchanged={w['unchanged']} total={w['total']}")
        print(f"duplicate content  : {payload['duplicate_content_groups']} group(s)")
        print("-" * 74)
        for slug, r in payload["reconciliation"].items():
            mark = "ok " if r["matches"] else "FAIL"
            print(f"  [{mark}] {slug:<40} audited={r['audited_records']} "
                  f"canonical={r['canonical_chunks']}")
        print("-" * 74)
        print("field gaps (explicit unknowns, not errors):")
        for name, n in sorted(payload["field_gaps"].items()):
            print(f"  {name:<26} {n}")
    else:
        print(f"documents processed: {payload['documents_processed']}")
        print(f"questions          : {payload['questions_total']}")
        print(f"marks              : {payload['marks_total']}")
        for d in payload["per_document"]:
            w = d.get("write", {})
            written = (f" created={w.get('created', 0)} unchanged={w.get('unchanged', 0)}"
                       if w else "")
            print(f"  {d['paper_code']:<8} questions={d['questions_found']:<4} "
                  f"marks={d['total_marks']:<4} pages={d['pages']}{written}")
        for s in payload["documents_skipped"]:
            print(f"  skipped {s['filename']}: {s['reason']}")
    print("=" * 74)

    if failures:
        print()
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print("OK: normalisation reconciles with the evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
