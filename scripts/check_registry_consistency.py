#!/usr/bin/env python3
"""
check_registry_consistency.py — CI gate: the registry must agree with the evidence.

The Lumos prebuild pack recorded 1,022 curriculum chunks. The repositories held
180 (ADR-008). Nobody lied; a hand-maintained figure simply drifted away from
the data it described, and nothing in the system was positioned to notice.

This is the thing positioned to notice. It fails the build when:

  * an audited record count in `corpus_snapshots` disagrees with the corpus
    auditor's current output,
  * a source document in the registry is missing from the source catalogue,
    or its checksum has changed,
  * an offering claims to be indexed with no chunks, or available with no
    evidence behind it,
  * the availability view contradicts itself (available, yet blocked),
  * a canonical chunk's identity does not derive from its own chunk key,
  * a chunk's key does not embed the checksum of the document it came from,
  * a chunk sits in a different offering from its source document,
  * a normalised legacy corpus has a different chunk count from the audited
    record count.

Usage
-----
    DATABASE_URL=... python scripts/check_registry_consistency.py \
        --audit evidence/curriculum_audit_local.json \
        --catalog evidence/source_catalog.json

`--catalog` is optional. On a machine without the licensed material, source
checksums are reported as unverifiable rather than treated as failures — the
absence of private files is a normal state, not a broken build.

Exit codes: 0 consistent · 1 inconsistent · 2 could not run
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from services.ingestion.canonical import make_chunk_id  # noqa: E402

# Which audited subject in the corpus auditor's output backs which offering.
SNAPSHOT_SUBJECT_BY_SLUG = {
    "nctb/ict/ssc": "ICT",
    "nctb/english/ssc": "English",
    "edexcel-ial/physics/a2": "Physics",
}


def load(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def check(conn: psycopg.Connection, audit: dict, catalog: dict | None
          ) -> tuple[list[str], list[str]]:
    failures: list[str] = []
    notes: list[str] = []

    with conn.cursor(row_factory=dict_row) as cur:

        # ── 1. audited counts ────────────────────────────────────────────────
        cur.execute(
            """
            SELECT DISTINCT ON (o.slug) o.slug, cs.record_count, cs.evidence_ref
            FROM corpus_snapshots cs
            JOIN subject_offerings o ON o.id = cs.offering_id
            ORDER BY o.slug, cs.taken_at DESC
            """)
        snapshots = {r["slug"]: r for r in cur.fetchall()}
        audited = {k: v["records"] for k, v in audit.get("subjects", {}).items()}

        for slug, subject in SNAPSHOT_SUBJECT_BY_SLUG.items():
            expected = audited.get(subject)
            row = snapshots.get(slug)
            if expected is None:
                notes.append(f"auditor has no subject '{subject}' — no snapshot to compare for {slug}")
                continue
            if row is None:
                failures.append(f"{slug}: no corpus snapshot, but the auditor reports {expected} records")
                continue
            if row["record_count"] != expected:
                failures.append(
                    f"{slug}: registry snapshot says {row['record_count']} records, "
                    f"auditor says {expected} — the registry has drifted from the data")

        total_snapshotted = sum(r["record_count"] for r in snapshots.values())
        if total_snapshotted != audit.get("total_records"):
            failures.append(
                f"snapshot total {total_snapshotted} != auditor total {audit.get('total_records')}")

        # ── 2. private source documents against the catalogue ────────────────
        #
        # Scoped to private material because that is what the catalogue
        # describes. Legacy JSONL checksums are backfilled by the normalisation
        # adapter from the files themselves and are reconciled against the corpus
        # auditor in check 7, not against this catalogue.
        cur.execute(
            """
            SELECT o.slug, sd.filename, sd.sha256, sd.page_count,
                   sd.ingestion_route::text AS ingestion_route, sd.is_private
            FROM source_documents sd
            JOIN subject_offerings o ON o.id = sd.offering_id
            WHERE sd.sha256 IS NOT NULL AND sd.is_private = true
            """)
        registry_docs = cur.fetchall()

        if catalog is None:
            if registry_docs:
                notes.append(
                    f"{len(registry_docs)} checksummed source documents could not be "
                    "verified: no source catalogue on this machine (the licensed "
                    "material is not present, which is expected in CI)")
        else:
            by_sha = {d["sha256"]: d for d in catalog.get("documents", [])}
            for doc in registry_docs:
                cat = by_sha.get(doc["sha256"])
                if cat is None:
                    failures.append(
                        f"{doc['slug']}: '{doc['filename']}' has checksum "
                        f"{doc['sha256'][:12]}… which is not in the source catalogue")
                    continue
                cat_pages = cat.get("text_layer", {}).get("pages")
                if doc["page_count"] is not None and cat_pages != doc["page_count"]:
                    failures.append(
                        f"{doc['slug']}: '{doc['filename']}' page count "
                        f"{doc['page_count']} != catalogue {cat_pages}")
                cat_route = cat.get("text_layer", {}).get("verdict")
                if cat_route and cat_route != doc["ingestion_route"]:
                    failures.append(
                        f"{doc['slug']}: '{doc['filename']}' ingestion route "
                        f"{doc['ingestion_route']} != catalogue {cat_route}")

        # ── 3. licensed material must be marked private ──────────────────────
        cur.execute(
            """
            SELECT o.slug, sd.filename
            FROM source_documents sd
            JOIN subject_offerings o ON o.id = sd.offering_id
            WHERE sd.is_private = false AND sd.document_type <> 'legacy_corpus'
            """)
        for row in cur.fetchall():
            failures.append(
                f"{row['slug']}: '{row['filename']}' is a licensed document type but "
                "is not marked private")

        # ── 4. the view must not contradict itself ───────────────────────────
        cur.execute(
            """
            SELECT slug, is_available, coalesce(cardinality(blocked_reasons), 0) AS n
            FROM curriculum_availability
            """)
        for row in cur.fetchall():
            if row["is_available"] != (row["n"] == 0):
                failures.append(
                    f"{row['slug']}: is_available={row['is_available']} with "
                    f"{row['n']} blocked reasons — the view contradicts itself")

        # ── 5. availability must rest on evidence ────────────────────────────
        cur.execute(
            """
            SELECT slug, indexed_chunk_count, source_document_count
            FROM curriculum_availability WHERE is_available
            """)
        for row in cur.fetchall():
            if row["indexed_chunk_count"] <= 0:
                failures.append(f"{row['slug']}: available with zero indexed chunks")
            if row["source_document_count"] <= 0:
                failures.append(f"{row['slug']}: available with no source documents")

        # ── 6. canonical chunk identity ──────────────────────────────────────
        #
        # Identity is derived, not assigned. If a stored id does not match the
        # uuid5 of its own key, something wrote a chunk outside the model and
        # idempotency can no longer be relied on.
        cur.execute("SELECT id, chunk_key FROM chunks")
        for row in cur.fetchall():
            expected = str(make_chunk_id(row["chunk_key"]))
            if str(row["id"]) != expected:
                failures.append(
                    f"chunk {row['id']}: id does not derive from its chunk_key "
                    f"(expected {expected})")

        # The document checksum inside the key is what prevents identity
        # collision between the same question in different papers.
        cur.execute(
            """
            SELECT c.id, c.chunk_key, sd.sha256, sd.filename
            FROM chunks c JOIN source_documents sd ON sd.id = c.source_document_id
            WHERE sd.sha256 IS NOT NULL
              AND position(sd.sha256 in c.chunk_key) = 0
            """)
        for row in cur.fetchall():
            failures.append(
                f"chunk {row['id']}: key does not embed the checksum of "
                f"'{row['filename']}' — identity is not anchored to a document")

        cur.execute(
            """
            SELECT c.id FROM chunks c
            JOIN source_documents sd ON sd.id = c.source_document_id
            WHERE c.offering_id <> sd.offering_id
            """)
        for row in cur.fetchall():
            failures.append(
                f"chunk {row['id']}: offering differs from its source document's "
                "— curriculum isolation would be violated")

        # ── 7. normalised legacy corpora must match the auditor ──────────────
        cur.execute(
            """
            SELECT o.slug, count(*) AS n
            FROM chunks c
            JOIN subject_offerings o ON o.id = c.offering_id
            WHERE c.chunk_type = 'legacy_record'
            GROUP BY o.slug
            """)
        legacy_counts = {r["slug"]: r["n"] for r in cur.fetchall()}
        for slug, subject in SNAPSHOT_SUBJECT_BY_SLUG.items():
            actual = legacy_counts.get(slug)
            expected = audited.get(subject)
            if actual is None:
                notes.append(f"{slug}: legacy corpus not yet normalised")
                continue
            if expected is not None and actual != expected:
                failures.append(
                    f"{slug}: {actual} legacy chunks from {expected} audited records "
                    "— normalisation lost or invented records")

        # ── 8. anything visible but unusable must explain itself ─────────────
        cur.execute(
            """
            SELECT slug FROM curriculum_availability
            WHERE NOT is_available
              AND publication_status IN ('planned', 'in_preparation')
              AND (display_note_en IS NULL OR display_note_en = '')
            """)
        for row in cur.fetchall():
            failures.append(
                f"{row['slug']}: shown to students as unavailable with no explanation")

    return failures, notes


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--audit", type=Path, default=REPO_ROOT / "evidence/curriculum_audit_local.json")
    ap.add_argument("--catalog", type=Path, default=REPO_ROOT / "evidence/source_catalog.json")
    args = ap.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2

    audit = load(args.audit)
    if audit is None:
        print(f"{args.audit} not found — run scripts/audit_corpus.py first", file=sys.stderr)
        return 2
    catalog = load(args.catalog)

    with psycopg.connect(url) as conn:
        failures, notes = check(conn, audit, catalog)

    for n in notes:
        print(f"note:    {n}")
    if failures:
        print()
        for f in failures:
            print(f"FAIL:    {f}")
        print(f"\n{len(failures)} inconsistenc{'y' if len(failures) == 1 else 'ies'} "
              f"between the registry and its evidence.")
        return 1

    print("OK:      registry and evidence agree")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
