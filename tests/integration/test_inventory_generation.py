"""
CURRICULUM_INVENTORY.md must be reproducible.

The whole point of generating the inventory is that an external reviewer can
clone the repository, run the generator, and get the committed file back. That
claim is worth 20 of BCOLBD's 100 points and it is the reason ADR-008 exists at
all — the prebuild pack's hand-written inventory said 1,022 records against an
actual 180 because nobody could re-derive it.

The normalisation-runs table broke that guarantee in two ways at once, both
found by running the generator on a second machine:

1. It ordered by `offering_id`, a `gen_random_uuid()` value. Row order therefore
   depended on which database instance produced the file, so two correct
   machines disagreed.
2. It took the "latest" run per (offering, adapter) with `DISTINCT ON` ordered
   by `started_at`. The past-paper adapter records one run per document and
   every run of one invocation shares a timestamp, because `now()` is
   transaction-scoped. That is a three-way tie broken arbitrarily, and it
   reported one paper of three: 18 questions where the offering actually holds
   41.

These tests pin both properties.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from generate_inventory import fetch  # noqa: E402


def _offering_ids(conn) -> list[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM subject_offerings ORDER BY slug LIMIT 2")
        return [str(r[0]) for r in cur.fetchall()]


def _record_batch(conn, offering_id: str, adapter: str, per_document: list[int]) -> None:
    """
    Write one batch of runs the way an adapter does: several documents, one row
    each, all sharing a `started_at` because they are one transaction.
    """
    with conn.cursor() as cur:
        for records in per_document:
            cur.execute(
                """
                INSERT INTO normalisation_runs
                    (offering_id, adapter, ingestion_version, source_records,
                     chunks_created, chunks_updated, chunks_unchanged,
                     duplicates_seen, warnings, finished_at)
                VALUES (%s, %s, '004b.1', %s, %s, 0, 0, 0, '[]'::jsonb, now())
                """,
                (offering_id, adapter, records, records))


def test_run_rows_are_ordered_by_slug_not_by_a_random_uuid(conn):
    """Row order must not depend on which database generated the file."""
    for offering_id in _offering_ids(conn):
        _record_batch(conn, offering_id, "past_paper", [19, 18, 4])

    rows = fetch(conn)["runs"]
    slugs = [r["slug"] for r in rows]

    assert slugs == sorted(slugs), (
        f"normalisation-run rows are not in slug order: {slugs}. "
        "Ordering by offering_id sorts by gen_random_uuid(), so the committed "
        "inventory would differ per machine.")


def test_a_multi_document_batch_is_summed_not_sampled(conn):
    """
    Three documents in one batch report as one row of three, not one of them.

    This is the WPH11/12/13 case: 19 + 18 + 4 = 41 questions in the AS demo
    scope. Reporting 18, or 4, is not a rounding difference — it is the wrong
    number in a document whose purpose is to state the right one.
    """
    offering_id = _offering_ids(conn)[0]
    _record_batch(conn, offering_id, "past_paper", [19, 18, 4])

    row = next(r for r in fetch(conn)["runs"] if r["adapter"] == "past_paper")

    assert row["documents"] == 3, "each document in the batch should be counted"
    assert row["source_records"] == 41, (
        f"expected the batch summed to 41, got {row['source_records']} — "
        "a tie on started_at was broken by picking one document")
    assert row["chunks_created"] == 41


def test_only_the_most_recent_batch_is_reported(conn):
    """An older batch must not be added to the current one."""
    offering_id = _offering_ids(conn)[0]

    _record_batch(conn, offering_id, "past_paper", [19, 18, 4])
    # A second, later batch. `started_at` defaults to the transaction clock, so
    # advance it explicitly rather than relying on wall time inside one
    # transaction — which is exactly the tie that caused the original defect.
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO normalisation_runs
                (offering_id, adapter, ingestion_version, source_records,
                 chunks_created, chunks_updated, chunks_unchanged,
                 duplicates_seen, warnings, started_at, finished_at)
            VALUES (%s, 'past_paper', '004b.1', 7, 0, 0, 7, 0, '[]'::jsonb,
                    now() + interval '1 hour', now() + interval '1 hour')
            """,
            (offering_id,))

    row = next(r for r in fetch(conn)["runs"] if r["adapter"] == "past_paper")

    assert row["documents"] == 1 and row["source_records"] == 7, (
        "the newest batch replaces the previous one; totals must not accumulate")
    assert row["chunks_unchanged"] == 7


def test_fetch_is_stable_across_repeated_calls(conn):
    """The same database must render the same rows every time."""
    for offering_id in _offering_ids(conn):
        _record_batch(conn, offering_id, "past_paper", [19, 18, 4])
        _record_batch(conn, offering_id, "legacy_corpus", [120])

    first = fetch(conn)["runs"]
    for _ in range(3):
        assert fetch(conn)["runs"] == first, "generator output varies between calls"
