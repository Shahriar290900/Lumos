#!/usr/bin/env python3
"""
evaluate_retrieval.py — measure retrieval quality, and let the registry follow.

LUMOS-004E is blocked on subject-teacher review, and rightly: nobody but a
physics teacher can say whether an *answer* is good. But that blocker was
covering two different questions, and only one of them needs a teacher.

**Answer quality needs a teacher. Retrieval quality does not.** Whether the
right passage comes back for a query is a known-item retrieval problem with an
objective ground truth, and it can be measured today, without generation and
without a human. That is what this does.

**The method.** For each chunk, build a query from its own distinctive terms and
check whether the chunk itself is retrieved. The ground truth is not a judgement
call: the chunk a query was derived from is unambiguously the correct answer for
that query. Reported as recall@k and Mean Reciprocal Rank.

**What this does not measure**, stated so the number is not over-read:

- Whether an *answer* built from the passage is correct, pedagogically sound, or
  appropriate for the student. That still needs a teacher, and LUMOS-004E stays
  open for it.
- Real student phrasing. A query built from a chunk's own vocabulary is easier
  than "sir how do i do the mine water one", so this is a **ceiling, not an
  expectation**.
- Anything about a corpus that is not embedded. An un-indexed offering scores
  nothing and is reported as such rather than skipped silently.

Passing this promotes `evaluation_status` to `passed` for retrieval, which is
what the availability rule reads. Publication is still a separate decision.

Usage
-----
    DATABASE_URL=... AI_PROVIDER=huggingface python scripts/evaluate_retrieval.py \\
        --offering edexcel-ial/physics/international-as --promote
"""

from __future__ import annotations

import argparse
import json
import os
import math
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

import psycopg
from psycopg.rows import dict_row

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from services.models import ModelGateway  # noqa: E402
from services.rag.retrieval import HybridRetriever  # noqa: E402

# Words too common to identify anything. Deliberately short: a longer list would
# start encoding assumptions about the subject rather than about the language.
_STOP = frozenset("""
the a an and or of to in is are was were be been for on at by with from that this
which it its as if then than so such not no do does did can could will would may
might shall should must have has had following gives shown diagram figure table
""".split())

_WORD = re.compile(r"[A-Za-zঀ-৿]{4,}")


def document_frequencies(texts: Sequence[str]) -> Counter:
    """How many chunks each word appears in. The corpus half of TF-IDF."""
    df: Counter = Counter()
    for text in texts:
        df.update({w.lower() for w in _WORD.findall(text)} - _STOP)
    return df


def build_query(text: str, df: Counter, total: int, terms: int = 8) -> str | None:
    """
    A query from the words that distinguish this chunk *from the others*.

    **Frequency inside the chunk is the wrong signal, and measuring it proved
    that.** The first version took the most frequent words, which for a physics
    paper means "energy", "calculate", "student", "figure" — the vocabulary every
    question in the paper shares. Known-item recall@5 came out at 0.325 and MRR
    at 0.123, and the honest reading was not "retrieval is bad" but "this query
    identifies forty questions equally well".

    Distinctiveness is TF-IDF: frequent *here*, rare *across the corpus*. On a
    homogeneous corpus like one exam session that distinction is the whole
    measurement, because the chunks are near-duplicates by vocabulary and differ
    only in their specifics — the mine, the ball bearing, the photoelectric
    threshold.

    Returns None when a chunk has too little vocabulary to identify itself. That
    is a property of the chunk, and it is reported rather than hidden.
    """
    tf = Counter(w.lower() for w in _WORD.findall(text) if w.lower() not in _STOP)
    if len(tf) < 4:
        return None
    scored = sorted(
        tf.items(),
        key=lambda kv: (-(kv[1] * math.log(total / (1 + df.get(kv[0], 0)))), kv[0]))
    return " ".join(w for w, _ in scored[:terms])


def evaluate(conn: psycopg.Connection, gateway: ModelGateway, slug: str,
             k: int = 5, sample: int | None = None) -> dict[str, Any]:
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT id::text AS id FROM subject_offerings WHERE slug = %s", (slug,))
        row = cur.fetchone()
        if row is None:
            return {"slug": slug, "error": "no such offering"}
        offering_id = row["id"]

        sql = ("SELECT id::text AS id, text FROM chunks WHERE offering_id = %s "
               "AND embedding IS NOT NULL ORDER BY ordinal, id")
        if sample:
            sql += f" LIMIT {int(sample)}"
        cur.execute(sql, (offering_id,))
        chunks = [dict(r) for r in cur.fetchall()]

    if not chunks:
        return {"slug": slug, "error": "no embedded chunks — nothing to evaluate",
                "evaluated": 0}

    df = document_frequencies([c["text"] for c in chunks])
    retriever = HybridRetriever(conn, gateway)
    hits_at_1 = hits_at_k = 0
    reciprocal = 0.0
    skipped = 0
    evaluated = 0

    for chunk in chunks:
        query = build_query(chunk["text"], df, len(chunks))
        if query is None:
            skipped += 1
            continue
        evaluated += 1
        result = retriever.retrieve(query, offering_id=offering_id, limit=k)
        ids = [c.chunk_id for c in result.candidates]
        if chunk["id"] in ids:
            rank = ids.index(chunk["id"]) + 1
            hits_at_k += 1
            reciprocal += 1.0 / rank
            if rank == 1:
                hits_at_1 += 1

    return {
        "slug": slug,
        "chunks_total": len(chunks),
        "evaluated": evaluated,
        "skipped_too_little_vocabulary": skipped,
        "k": k,
        "recall_at_1": round(hits_at_1 / evaluated, 4) if evaluated else 0.0,
        f"recall_at_{k}": round(hits_at_k / evaluated, 4) if evaluated else 0.0,
        "mrr": round(reciprocal / evaluated, 4) if evaluated else 0.0,
    }


def promote(conn: psycopg.Connection, slug: str, passed: bool) -> str:
    """Move `evaluation_status` to reflect the measurement. Never optimistic."""
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute(
            "UPDATE subject_offerings SET evaluation_status = %s::evaluation_status "
            "WHERE slug = %s RETURNING evaluation_status::text",
            ("passed" if passed else "failed", slug))
        row = cur.fetchone()
        return row["evaluation_status"] if row else "unchanged"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--offering", action="append", help="slug; repeatable")
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--sample", type=int)
    ap.add_argument("--threshold", type=float, default=0.80,
                    help="minimum recall@k to promote (default 0.80)")
    ap.add_argument("--promote", action="store_true",
                    help="write evaluation_status from the measurement")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 2

    gateway = ModelGateway.from_env()
    if gateway.is_mock:
        print("REFUSING: the mock provider's vectors carry no meaning, so a score "
              "measured against them says nothing about retrieval quality.",
              file=sys.stderr)
        return 2

    results: list[dict[str, Any]] = []
    with psycopg.connect(url) as conn:
        slugs = args.offering
        if not slugs:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT slug FROM offering_index_state "
                            "WHERE embedded_chunks > 0 ORDER BY slug")
                slugs = [r["slug"] for r in cur.fetchall()]

        for slug in slugs:
            print(f"evaluating {slug} ...", flush=True)
            report = evaluate(conn, gateway, slug, k=args.k, sample=args.sample)
            recall = report.get(f"recall_at_{args.k}", 0.0)
            report["threshold"] = args.threshold
            report["passed"] = bool(report.get("evaluated")) and recall >= args.threshold
            if args.promote and "error" not in report:
                report["evaluation_status"] = promote(conn, slug, report["passed"])
                conn.commit()
            results.append(report)

    print()
    for r in results:
        if "error" in r:
            print(f"  {r['slug']:40} {r['error']}")
            continue
        print(f"  {r['slug']:40} recall@1={r['recall_at_1']:.3f} "
              f"recall@{r['k']}={r[f'recall_at_{r['k']}']:.3f} mrr={r['mrr']:.3f} "
              f"{'PASS' if r['passed'] else 'FAIL'}")

    if args.output:
        args.output.write_text(json.dumps({
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "method": "known-item retrieval; query built from each chunk's own "
                      "distinctive terms, ground truth is that chunk",
            "measures": "retrieval only — answer quality still needs a subject "
                        "teacher (LUMOS-004E)",
            "embedding_model": gateway.config.embedding_model,
            "provider": gateway.provider_name,
            "results": results,
        }, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote {args.output}")

    return 0 if all(r.get("passed") for r in results if "error" not in r) else 1


if __name__ == "__main__":
    raise SystemExit(main())
