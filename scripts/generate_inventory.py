#!/usr/bin/env python3
"""
generate_inventory.py — regenerate CURRICULUM_INVENTORY.md from the registry.

The inventory is a generated artifact, not a hand-maintained document. That is a
direct consequence of ADR-008: the prebuild pack's inventory said 1,022 records
against an actual 180, because it was prose that nobody re-derived. Prose drifts.
A generator cannot.

Every figure below is read from the database and from the corpus auditor's
evidence files. The narrative is templated here; the numbers never are.

Usage
-----
    DATABASE_URL=... python scripts/generate_inventory.py --output CURRICULUM_INVENTORY.md
    DATABASE_URL=... python scripts/generate_inventory.py --check    # CI: fail if stale
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import date
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parents[1]

STATUS_WORDS = {
    "published": "available",
    "in_preparation": "in preparation",
    "planned": "planned — no corpus",
    "hidden": "hidden",
}


def fetch(conn: psycopg.Connection) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            SELECT slug, curriculum_code, curriculum_name, subject_code,
                   subject_name_en, subject_name_bn, level_code, level_name,
                   level_sort_order, syllabus_version_code, languages,
                   publication_status, indexing_status, evaluation_status,
                   indexed_chunk_count, canonical_chunk_count,
                   source_document_count, is_available,
                   blocked_reasons, display_note_en
            FROM curriculum_availability o
            ORDER BY curriculum_code, level_sort_order, subject_code
            """)
        offerings = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT o.slug, c.chunk_type::text AS chunk_type,
                   c.extraction_method::text AS extraction_method,
                   c.provenance_status::text AS provenance_status,
                   count(*) AS n, round(avg(c.token_count)) AS avg_tokens
            FROM chunks c
            JOIN subject_offerings o ON o.id = c.offering_id
            GROUP BY 1, 2, 3, 4 ORDER BY 1, 2, 3
            """)
        chunks = [dict(r) for r in cur.fetchall()]

        # The most recent *batch* per (offering, adapter), summed.
        #
        # Two reasons this is not `DISTINCT ON ... ORDER BY started_at DESC`.
        # First, the past-paper adapter records one run per document, and every
        # run of a single invocation shares one `started_at` because `now()` is
        # transaction-scoped — so picking "the latest" was a three-way tie broken
        # arbitrarily, and reported one paper out of three. Second, ordering by
        # `offering_id` ordered by a `gen_random_uuid()` value, so the row order
        # of this table depended on which database instance generated it.
        #
        # Both made CURRICULUM_INVENTORY.md irreproducible across machines, which
        # is precisely the claim this file exists to support. Grouping by the
        # batch timestamp and ordering by slug is stable everywhere.
        cur.execute(
            """
            WITH latest AS (
                SELECT offering_id, adapter, max(started_at) AS started_at
                FROM normalisation_runs
                GROUP BY offering_id, adapter
            )
            SELECT o.slug, r.adapter,
                   max(r.ingestion_version)      AS ingestion_version,
                   count(*)                      AS documents,
                   sum(r.source_records)         AS source_records
            FROM normalisation_runs r
            JOIN latest l
              ON l.offering_id = r.offering_id
             AND l.adapter     = r.adapter
             AND l.started_at  = r.started_at
            JOIN subject_offerings o ON o.id = r.offering_id
            GROUP BY o.slug, r.adapter
            ORDER BY o.slug, r.adapter
            """)
        runs = [dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT DISTINCT ON (o.slug) o.slug, cs.record_count, cs.method, cs.evidence_ref
            FROM corpus_snapshots cs
            JOIN subject_offerings o ON o.id = cs.offering_id
            ORDER BY o.slug, cs.taken_at DESC
            """)
        snapshots = {r["slug"]: dict(r) for r in cur.fetchall()}

        cur.execute(
            """
            SELECT o.slug, sd.document_type::text AS document_type,
                   sd.source_priority, sd.ingestion_route::text AS ingestion_route,
                   count(*) AS n, sum(sd.page_count) AS pages
            FROM source_documents sd
            JOIN subject_offerings o ON o.id = sd.offering_id
            GROUP BY 1, 2, 3, 4
            ORDER BY 1, 3, 2
            """)
        documents = [dict(r) for r in cur.fetchall()]

    return {"offerings": offerings, "snapshots": snapshots,
            "documents": documents, "chunks": chunks, "runs": runs}


def render(data: dict[str, Any], audit: dict[str, Any], catalog: dict[str, Any] | None) -> str:
    o = data["offerings"]
    snaps = data["snapshots"]
    docs = data["documents"]

    total_records = audit["total_records"]
    by_subject = audit["subjects"]
    artefacts = audit.get("ocr_artefact_hits", {})

    L: list[str] = []
    add = L.append

    add("# Lumos Curriculum Inventory")
    add("")
    add("> **Generated file — do not edit by hand.**")
    add("> `DATABASE_URL=... python scripts/generate_inventory.py --output CURRICULUM_INVENTORY.md`")
    add(">")
    add("> Every number here is read from the curriculum registry and from the corpus")
    add("> auditor's evidence files. The prebuild pack's inventory stated 1,022 records")
    add("> against an actual 180 because it was prose nobody re-derived (ADR-008). CI")
    add("> re-runs `scripts/check_registry_consistency.py` so the two cannot drift again.")
    add("")
    add(f"Generated: {date.today().isoformat()}")
    add("")

    # ── availability ─────────────────────────────────────────────────────────
    add("## Offerings and availability")
    add("")
    add("| Offering | Curriculum | Subject | Level | Status | Sources | Canonical | Indexed | Available |")
    add("|---|---|---|---|---|---:|---:|---:|---|")
    for r in o:
        add(f"| `{r['slug']}` | {r['curriculum_code']} | {r['subject_name_en']} | "
            f"{r['level_name']} | {STATUS_WORDS.get(r['publication_status'], r['publication_status'])} | "
            f"{r['source_document_count']} | {r['canonical_chunk_count']} | "
            f"{r['indexed_chunk_count']} | {'yes' if r['is_available'] else 'no'} |")
    add("")
    add("Three counts, three different things (ADR-014, ADR-020): **audited** is what "
        "an auditor found in the source material, **canonical** is what normalisation "
        "produced, **indexed** is what is embedded and lexically searchable. Only the "
        "last one can make a subject available.")
    add("")

    available = [r for r in o if r["is_available"]]
    if not available:
        add("**No offering is currently available.** Nothing has been ingested, so nothing "
            "may be queried. The API refuses every offering above before retrieval runs.")
    else:
        add(f"**{len(available)} offering(s) available.**")
    add("")

    add("### Why each offering is unavailable")
    add("")
    add("| Offering | Blocked by |")
    add("|---|---|")
    for r in o:
        if not r["is_available"]:
            add(f"| `{r['slug']}` | {', '.join(r['blocked_reasons'])} |")
    add("")

    # ── audited legacy corpus ────────────────────────────────────────────────
    add("## Audited legacy corpus")
    add("")
    add(f"`scripts/audit_corpus.py` over `{audit['jsonl_files']}` JSONL files: "
        f"**{total_records} records**, {audit['unique_content_blocks']} unique content blocks, "
        f"{len(audit['parse_errors'])} parse errors.")
    add("")
    add("| Subject | Files | Records | Class | Median content | Bangla records | Registered to |")
    add("|---|---:|---:|---|---:|---:|---|")
    slug_by_subject = {v: k for k, v in {
        "nctb/ict/ssc": "ICT", "nctb/english/ssc": "English",
        "edexcel-ial/physics/a2": "Physics"}.items()}
    for subject, s in sorted(by_subject.items()):
        slug = slug_by_subject.get(subject, "—")
        add(f"| {subject} | {s['files']} | **{s['records']}** | {', '.join(s['classes'])} | "
            f"{s['content_chars']['median']:.0f} chars | {s['records_containing_bangla']} | `{slug}` |")
    add(f"| **Total** | **{audit['jsonl_files']}** | **{total_records}** | | | | |")
    add("")

    add("Registry snapshots, each carrying the method and evidence file it came from:")
    add("")
    add("| Offering | Records | Method | Evidence |")
    add("|---|---:|---|---|")
    for slug, s in sorted(snaps.items()):
        add(f"| `{slug}` | {s['record_count']} | `{s['method']}` | `{s['evidence_ref']}` |")
    add("")
    add("These are **audited** counts of legacy source records, not indexed chunks. "
        "`indexed_chunk_count` stays 0 until the records are normalised, cleaned, "
        "re-chunked and written to the store — which is why no offering is available.")
    add("")

    # ── canonical chunks ─────────────────────────────────────────────────────
    if data["chunks"]:
        add("## Canonical chunks")
        add("")
        add("| Offering | Chunk type | Extraction | Provenance | Count | Median tokens |")
        add("|---|---|---|---|---:|---:|")
        for c in data["chunks"]:
            add(f"| `{c['slug']}` | {c['chunk_type']} | {c['extraction_method']} | "
                f"{c['provenance_status']} | {c['n']} | {c['avg_tokens'] or '—'} |")
        add("")
        add(f"**{sum(c['n'] for c in data['chunks'])} canonical chunks total.** "
            "Provenance is recorded per chunk, not per corpus: `verbatim` means the "
            "stored text is exactly what extraction produced, `cleaned` means layout "
            "furniture was removed, `normalized` means Unicode normalisation changed "
            "something. Anything other than verbatim keeps its untransformed text.")
        add("")

    if data["runs"]:
        add("### Normalisation runs")
        add("")
        add("| Offering | Adapter | Version | Documents | Source records |")
        add("|---|---|---|---:|---:|")
        for r in data["runs"]:
            add(f"| `{r['slug']}` | {r['adapter']} | {r['ingestion_version']} | "
                f"{r['documents']} | {r['source_records']} |")
        add("")
        add("The most recent normalisation batch per adapter, summed across the "
            "documents in that batch.")
        add("")
        add("Per-run `created` / `updated` / `unchanged` counts are deliberately "
            "**not** here. They describe what one run did, not what the corpus is, "
            "so the same corpus renders differently depending on whether the "
            "database was fresh — which would make this file report itself stale "
            "after a re-run that changed nothing. Those counts live in "
            "`evidence/*.json` and in the `normalisation_runs` table, where run "
            "history belongs. Idempotency is asserted by the test suite and by CI, "
            "not by a number in a document.")
        add("")

    # ── source documents ─────────────────────────────────────────────────────
    add("## Registered source documents")
    add("")
    if catalog:
        add(f"{catalog['document_count']} licensed PDFs "
            f"({catalog['total_bytes'] / 1024 / 1024:.0f} MB) catalogued by "
            "`scripts/catalog_sources.py`. The files themselves are private and are "
            "never committed; only their metadata appears here.")
    else:
        add("The source catalogue is not present on this machine, so PDF metadata is "
            "reported from the registry only.")
    add("")
    add("| Offering | Type | Priority | Count | Pages | Ingestion route |")
    add("|---|---|---:|---:|---:|---|")
    for d in docs:
        pages = d["pages"] if d["pages"] is not None else "—"
        add(f"| `{d['slug']}` | {d['document_type']} | {d['source_priority']} | "
            f"{d['n']} | {pages} | {d['ingestion_route']} |")
    add("")
    add("Priority 1 is official examination material, 2 core textbook, 3 supplementary "
        "(ADR-009). The ingestion route is recorded per document, not per corpus: within "
        "one session some examiner reports carry a usable text layer and others decode to "
        "`(cid:N)` glyphs and need OCR.")
    add("")

    # ── quality ──────────────────────────────────────────────────────────────
    add("## Legacy corpus quality")
    add("")
    add("| Finding | Records affected |")
    add("|---|---:|")
    labels = {
        "bangla_duplicated_vowel_sign": "Bangla vowel-sign / conjunct corruption",
        "broken_word_split": "Word broken across a line break",
        "bullet_ocr_as_letter_e": "Bullet glyph OCR'd as the letter `e`",
        "stray_control_chars": "Stray control characters",
        "repeated_whitespace_run": "Runs of repeated whitespace",
    }
    for key, info in artefacts.items():
        add(f"| {labels.get(key, key)} | {info['records']} / {total_records} |")
    gaps = audit.get("canonical_schema_gaps", {}).get("missing_counts", {})
    if gaps:
        worst = max(gaps.values())
        add(f"| Missing canonical schema fields | up to {worst} / {total_records} |")
    add("")
    add("No corpus is published until these are repaired and an evaluation passes "
        "(LUMOS-004C, LUMOS-004E).")
    add("")

    # ── not present ──────────────────────────────────────────────────────────
    add("## Not present")
    add("")
    empty = [r for r in o if r["source_document_count"] == 0]
    for r in empty:
        add(f"- **{r['subject_name_en']}** ({r['curriculum_code']} {r['level_code']}) — "
            f"{r['display_note_en']}")
    add("")
    add("Registered as known-but-unavailable so the interface can explain rather than omit, "
        "and so a request naming one is refused by the registry rather than falling through "
        "to an ungrounded answer (ADR-011).")
    add("")
    add("Also absent, in every subject: past papers, mark schemes and examiner reports for "
        "any NCTB curriculum. The ~2.58 GB Edexcel corpus described in the whitepaper "
        "remains unlocated — see BLOCK-001A in `BLOCKERS.md`.")
    return "\n".join(L) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--output", type=Path, default=REPO_ROOT / "CURRICULUM_INVENTORY.md")
    ap.add_argument("--audit", type=Path, default=REPO_ROOT / "evidence/curriculum_audit_local.json")
    ap.add_argument("--catalog", type=Path, default=REPO_ROOT / "evidence/source_catalog.json")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if the file on disk differs from what would be generated")
    args = ap.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2
    if not args.audit.exists():
        print(f"{args.audit} not found — run scripts/audit_corpus.py first", file=sys.stderr)
        return 2

    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    catalog = json.loads(args.catalog.read_text(encoding="utf-8")) if args.catalog.exists() else None

    with psycopg.connect(url) as conn:
        text = render(fetch(conn), audit, catalog)

    if args.check:
        current = args.output.read_text(encoding="utf-8") if args.output.exists() else ""
        # The generated-on date changes daily and is not a drift signal.
        #
        # This compares the WHOLE file, and deliberately differs from the CI
        # `inventory` job, which compares only the sections between "Offerings
        # and availability" and "Registered source documents". That is not an
        # oversight in either place: the licensed PDFs are not present in CI, so
        # the source-catalogue section legitimately differs there, while locally
        # the catalogue is present and the whole file must match. Do not "fix"
        # one to match the other — narrowing this check would stop it noticing
        # drift in the run and chunk tables, which is exactly where the
        # reproducibility defect fixed in LUMOS-004B.1 lived.
        strip = lambda s: "\n".join(l for l in s.splitlines() if not l.startswith("Generated: "))
        if strip(current) != strip(text):
            print(f"FAIL: {args.output.name} is stale — regenerate it", file=sys.stderr)
            return 1
        print(f"OK:      {args.output.name} matches the registry")
        return 0

    args.output.write_text(text, encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
