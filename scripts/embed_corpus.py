#!/usr/bin/env python3
"""
embed_corpus.py — embed canonical chunks, and let the registry follow.

Embedding is the step that turns a normalised corpus into a searchable one, and
it is the *only* step that can make a subject available (ADR-020): a chunk
without an embedding is invisible to semantic retrieval however good its text.

Resumable and idempotent. Only chunks with no embedding, or embedded by a
different model, are sent — so a run interrupted halfway costs nothing, and
re-running after a model change re-embeds exactly what is stale rather than
everything. That matters because embedding is the one pipeline stage with a
per-call cost attached.

`indexed_chunk_count` is written from what is actually embedded, never by hand.
Publication still needs `evaluation_status = 'passed'`, so this makes a subject
*indexable*, not *available* — LUMOS-004E remains a separate gate.

Usage
-----
    DATABASE_URL=... AI_PROVIDER=huggingface python scripts/embed_corpus.py
    ... --offering edexcel-ial/physics/international-as
    ... --dry-run
    ... --limit 50
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psycopg
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from services.models import ModelGateway  # noqa: E402


def pending(conn: psycopg.Connection, model: str, offering: str | None,
            limit: int | None) -> list[dict[str, Any]]:
    """Chunks needing an embedding: never embedded, or embedded by another model."""
    sql = """
        SELECT c.id::text AS id, c.text, o.slug
        FROM chunks c
        JOIN subject_offerings o ON o.id = c.offering_id
        WHERE (c.embedding IS NULL OR c.embedding_model IS DISTINCT FROM %s)
    """
    params: list[Any] = [model]
    if offering:
        sql += " AND o.slug = %s"
        params.append(offering)
    sql += " ORDER BY o.slug, c.ordinal, c.id"
    if limit:
        sql += f" LIMIT {int(limit)}"
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]


def write_embeddings(conn: psycopg.Connection, rows: list[tuple[str, str, str]]) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "UPDATE chunks SET embedding = %s::vector, embedding_model = %s, "
            "embedded_at = now() WHERE id = %s::uuid",
            rows)


def refresh_indexed_counts(conn: psycopg.Connection) -> dict[str, int]:
    """
    Set `indexed_chunk_count` from what is actually embedded.

    Derived, never asserted. The legacy failure this guards against is a count
    that says a subject is ready because someone typed a number.
    """
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            """
            UPDATE subject_offerings o
               SET indexed_chunk_count = s.embedded_chunks,
                   indexing_status = CASE
                       WHEN s.embedded_chunks = 0 THEN indexing_status
                       WHEN s.embedded_chunks = s.canonical_chunks THEN 'indexed'::indexing_status
                       ELSE 'ingesting'::indexing_status
                   END
              FROM offering_index_state s
             WHERE s.offering_id = o.id
               AND o.indexed_chunk_count IS DISTINCT FROM s.embedded_chunks
            RETURNING o.slug, o.indexed_chunk_count
            """)
        return {r["slug"]: r["indexed_chunk_count"] for r in cur.fetchall()}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offering", help="restrict to one offering slug")
    ap.add_argument("--batch-size", type=int, default=16)
    ap.add_argument("--limit", type=int, help="stop after this many chunks")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--output", type=Path, default=None)
    args = ap.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2

    gateway = ModelGateway.from_env()
    model = gateway.config.embedding_model

    with psycopg.connect(url) as conn:
        todo = pending(conn, model, args.offering, args.limit)
        print(f"provider          : {gateway.provider_name}")
        print(f"embedding model   : {model}")
        print(f"chunks to embed   : {len(todo)}")
        if gateway.is_mock:
            print("NOTE: the mock provider produces deterministic vectors that carry "
                  "no meaning. Useful for exercising the pipeline; useless for "
                  "measuring retrieval quality.")
        if not todo:
            print("nothing to do — every chunk is embedded with this model")
            return 0
        if args.dry_run:
            return 0

        started = time.monotonic()
        done = 0
        for start in range(0, len(todo), args.batch_size):
            batch = todo[start:start + args.batch_size]
            vectors = gateway.embed([c["text"] for c in batch], batch_size=args.batch_size)
            write_embeddings(conn, [
                ("[" + ",".join(f"{v:.8f}" for v in emb.vector) + "]", model, chunk["id"])
                for chunk, emb in zip(batch, vectors)])
            conn.commit()
            done += len(batch)
            print(f"  {done}/{len(todo)}  ({time.monotonic() - started:.0f}s)", flush=True)

        changed = refresh_indexed_counts(conn)
        conn.commit()

        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT slug, canonical_chunks, embedded_chunks "
                        "FROM offering_index_state WHERE canonical_chunks > 0 ORDER BY slug")
            state = [dict(r) for r in cur.fetchall()]

    print("\nindex state:")
    for row in state:
        print(f"   {row['slug']:40} {row['embedded_chunks']:4}/{row['canonical_chunks']:4} embedded")
    if changed:
        print("\nindexed_chunk_count updated:", changed)

    if args.output:
        args.output.write_text(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "provider": gateway.provider_name,
            "embedding_model": model,
            "is_mock": gateway.is_mock,
            "chunks_embedded": done,
            "index_state": state,
            "note": "Counts only. No source text appears in this file.",
        }, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
