"""
services.rag.retrieval — hybrid retrieval: metadata filter, then lexical ‖ semantic, then RRF.

The shape is the one `shikhbo-ai/rag.py` already proved and ADR-007 adopted:
run a lexical and a semantic retriever independently, then fuse their *rankings*
with Reciprocal Rank Fusion at k = 60. Rank fusion needs no score normalisation
between retrievers whose scales are not comparable, which is why it survives a
corpus change that would invalidate any tuned score blend.

Three things this module does that the legacy implementation did not.

**The metadata filter runs first, inside SQL** (ADR-006). The legacy retriever
searched a global FAISS index and filtered the top-k afterwards, so a query
scoped to one subject could come back with zero in-scope chunks because all
twenty nearest neighbours belonged to another. Here the offering is a `WHERE`
clause on both retrievers, so out-of-scope chunks are never candidates.

**Language-aware fusion weights** (ADR-007). Bangla leans lexical and English
leans semantic, carried from the legacy constants. They are the *baseline to
beat* on a measured golden set, not a tuned result, and they are configuration
so LUMOS-004E can re-derive them.

**Nothing is invented on an empty result.** A query that matches nothing returns
nothing, and the caller is expected to say so rather than widen the search until
something comes back.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Sequence

import psycopg
from psycopg.rows import dict_row

from services.models import ModelGateway

RRF_K = int(os.environ.get("RRF_K", "60"))
RETRIEVAL_TOP_N = int(os.environ.get("RETRIEVAL_TOP_N", "30"))

# Carried from the legacy implementation. Baseline, not a result (ADR-007).
WEIGHTS = {
    "bn": {"dense": float(os.environ.get("RRF_WEIGHT_DENSE_BN", "0.4")),
           "sparse": float(os.environ.get("RRF_WEIGHT_SPARSE_BN", "0.6"))},
    "en": {"dense": float(os.environ.get("RRF_WEIGHT_DENSE_EN", "0.6")),
           "sparse": float(os.environ.get("RRF_WEIGHT_SPARSE_EN", "0.4"))},
}

BENGALI_RANGE = ("ঀ", "৿")

# Reranking is OFF by default, and that is a measurement, not a preference.
#
# ADR-009 puts a cross-encoder on the fused pool, and it should be there. But
# `BAAI/bge-reranker-v2-m3` is not reachable as a cross-encoder over Hugging
# Face serverless: the `text-classification` pipeline rejects a text pair, and
# the `sentence-similarity` pipeline answers — with bi-encoder cosine from the
# reranker's encoder, which is not what a cross-encoder computes. It returns
# ~0.9 for almost everything.
#
# Measured on 19 AS Physics questions by known-item retrieval:
#
#     rerank OFF   recall@1 = 1.000   recall@5 = 1.000
#     rerank ON    recall@1 = 0.053   recall@5 = 0.526
#
# The fusion is exact and the "reranker" was scrambling it. A stage that makes
# retrieval nineteen times worse at rank 1 must not run merely because the
# architecture diagram has a box for it. Set RERANK_ENABLED=1 once a real
# cross-encoder endpoint exists — a dedicated Inference Endpoint or a local
# sentence-transformers CrossEncoder — and re-measure before trusting it.
RERANK_ENABLED = os.environ.get("RERANK_ENABLED", "").strip().lower() in ("1", "true", "yes")


def detect_language(text: str) -> str:
    """Bangla if any Bengali codepoint appears. An English gloss inside a Bangla
    question is still a Bangla question, and the weights should follow the query
    the student actually typed."""
    return "bn" if any(BENGALI_RANGE[0] <= c <= BENGALI_RANGE[1] for c in text) else "en"


@dataclass
class Candidate:
    """One retrieved chunk, with where it came from and why it ranked."""

    chunk_id: str
    chunk_key: str
    text: str
    offering_slug: str
    chunk_type: str
    document_title: str | None = None
    paper_code: str | None = None
    question_number: str | None = None
    page_number: int | None = None
    section_ref: str | None = None
    source_priority: int | None = None
    language: str = "unknown"
    lexical_rank: int | None = None
    semantic_rank: int | None = None
    fused_score: float = 0.0
    rerank_score: float | None = None

    @property
    def retrievers(self) -> list[str]:
        found = []
        if self.lexical_rank is not None:
            found.append("lexical")
        if self.semantic_rank is not None:
            found.append("semantic")
        return found

    def citation(self) -> dict[str, Any]:
        """
        What a student sees, and what citation validation checks against.

        Deliberately not the text: a citation points at a place in a document,
        and the tutor explains rather than reproducing (ADR-026, BLOCK-008).
        """
        return {
            "chunk_id": self.chunk_id,
            "offering": self.offering_slug,
            "document": self.document_title,
            "paper_code": self.paper_code,
            "question_number": self.question_number,
            "page": self.page_number,
            "section": self.section_ref,
        }


@dataclass
class RetrievalResult:
    """The candidates, and enough about the run to explain an empty one."""

    candidates: list[Candidate] = field(default_factory=list)
    language: str = "en"
    lexical_found: int = 0
    semantic_found: int = 0
    embedded_chunks_available: int = 0
    reranked: bool = False
    notes: list[str] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.candidates

    def as_dict(self) -> dict[str, Any]:
        return {
            "language": self.language,
            "lexical_found": self.lexical_found,
            "semantic_found": self.semantic_found,
            "embedded_chunks_available": self.embedded_chunks_available,
            "reranked": self.reranked,
            "candidates": len(self.candidates),
            "notes": self.notes,
        }


_SELECT = """
    c.id::text        AS chunk_id,
    c.chunk_key,
    c.text,
    o.slug            AS offering_slug,
    c.chunk_type::text,
    sd.title          AS document_title,
    sd.paper_code,
    c.question_number,
    c.page_number,
    c.section_ref,
    sd.source_priority,
    c.language
"""


class HybridRetriever:
    """Lexical ‖ semantic over one offering, fused with RRF."""

    def __init__(self, conn: psycopg.Connection, gateway: ModelGateway) -> None:
        self._conn = conn
        self._gateway = gateway

    # ── the two retrievers ───────────────────────────────────────────────────

    def _lexical(self, query: str, offering_id: str, limit: int) -> list[dict[str, Any]]:
        """
        Postgres full-text search, scoped to the offering, ORing the query terms.

        **`plainto_tsquery` does not work here, and the reason is the `simple`
        configuration.** `plainto_tsquery` joins every term with AND. Under
        `english` that is survivable because stopwords are stripped first, but
        `simple` — chosen so Bangla is not mangled — keeps every token. So
        "How do I calculate gravitational potential energy?" became
        `how & do & i & calculate & gravitational & potential & energy`, and
        demanded all seven words in one chunk. Measured on the real corpus: zero
        lexical matches for both test queries, while semantic returned thirty.
        Half the hybrid was silently contributing nothing.

        ORing the terms makes lexical retrieval recall-oriented, which is the
        right division of labour: `ts_rank_cd` still ranks by how many terms
        matched and how close together, RRF weights it against the semantic
        list, and the cross-encoder supplies precision at the end. A lexical
        retriever tuned for precision inside a hybrid system is doing the
        reranker's job badly.

        The tokens are derived by `to_tsvector` with the same configuration used
        to build the index, so the query and the index can never disagree about
        what a token is.
        """
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                WITH q AS (
                    SELECT to_tsquery('simple',
                        array_to_string(
                            tsvector_to_array(to_tsvector('simple', %s)), ' | ')) AS tsq
                )
                SELECT {_SELECT},
                       ts_rank_cd(c.search_vector, q.tsq) AS score
                FROM chunks c
                CROSS JOIN q
                JOIN subject_offerings o ON o.id = c.offering_id
                LEFT JOIN source_documents sd ON sd.id = c.source_document_id
                WHERE c.offering_id = %s
                  AND q.tsq IS NOT NULL
                  AND c.search_vector @@ q.tsq
                ORDER BY score DESC, c.id
                LIMIT %s
                """,
                (query, offering_id, limit))
            return [dict(r) for r in cur.fetchall()]

    def _semantic(self, query: str, offering_id: str, limit: int) -> list[dict[str, Any]]:
        """Vector search over embedded chunks, scoped to the offering."""
        vector = self._gateway.embed_one(query).vector
        literal = "[" + ",".join(f"{v:.8f}" for v in vector) + "]"
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                f"""
                SELECT {_SELECT},
                       1 - (c.embedding <=> %s::vector) AS score
                FROM chunks c
                JOIN subject_offerings o ON o.id = c.offering_id
                LEFT JOIN source_documents sd ON sd.id = c.source_document_id
                WHERE c.offering_id = %s
                  AND c.embedding IS NOT NULL
                ORDER BY c.embedding <=> %s::vector, c.id
                LIMIT %s
                """,
                (literal, offering_id, literal, limit))
            return [dict(r) for r in cur.fetchall()]

    # ── fusion ───────────────────────────────────────────────────────────────

    def retrieve(self, query: str, *, offering_id: str, limit: int = 8,
                 top_n: int = RETRIEVAL_TOP_N,
                 rerank: bool = RERANK_ENABLED) -> RetrievalResult:
        """
        Retrieve, fuse and optionally rerank. Returns at most `limit` candidates.

        `top_n` is how many each retriever contributes *before* fusion. Fusing
        deeper lists then truncating finds documents that neither retriever
        ranked highly alone, which is the entire point of doing both.
        """
        language = detect_language(query)
        weights = WEIGHTS[language]
        result = RetrievalResult(language=language)

        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT count(embedding) AS n FROM chunks WHERE offering_id = %s",
                        (offering_id,))
            result.embedded_chunks_available = cur.fetchone()["n"]

        lexical = self._lexical(query, offering_id, top_n)
        result.lexical_found = len(lexical)

        semantic: list[dict[str, Any]] = []
        if result.embedded_chunks_available:
            semantic = self._semantic(query, offering_id, top_n)
            result.semantic_found = len(semantic)
        else:
            result.notes.append(
                "no chunks are embedded for this offering, so semantic retrieval "
                "was skipped and only lexical matches are returned")

        # Reciprocal Rank Fusion. Rank, not score: the two retrievers' scales are
        # not comparable, and normalising them would invent a relationship that
        # does not exist.
        fused: dict[str, Candidate] = {}
        for rows, kind, weight in ((lexical, "lexical", weights["sparse"]),
                                   (semantic, "semantic", weights["dense"])):
            for rank, row in enumerate(rows, start=1):
                key = row["chunk_id"]
                candidate = fused.get(key)
                if candidate is None:
                    candidate = Candidate(
                        chunk_id=row["chunk_id"], chunk_key=row["chunk_key"],
                        text=row["text"], offering_slug=row["offering_slug"],
                        chunk_type=row["chunk_type"], document_title=row["document_title"],
                        paper_code=row["paper_code"], question_number=row["question_number"],
                        page_number=row["page_number"], section_ref=row["section_ref"],
                        source_priority=row["source_priority"], language=row["language"])
                    fused[key] = candidate
                setattr(candidate, f"{kind}_rank", rank)
                candidate.fused_score += weight / (RRF_K + rank)

        ordered = sorted(fused.values(), key=lambda c: (-c.fused_score, c.chunk_id))

        if rerank and ordered:
            ordered = self._rerank(query, ordered)
            result.reranked = True

        result.candidates = ordered[:limit]
        if not result.candidates:
            result.notes.append("no chunk in this offering matched the query")
        return result

    def _rerank(self, query: str, candidates: list[Candidate]) -> list[Candidate]:
        """
        Cross-encoder rerank of the fused pool, with source priority as a feature.

        ADR-009: priority is a ranking feature, never a hard pre-filter. A hard
        filter starves the context window whenever the top layer is thin, which
        given this corpus is most of the time. The nudge is deliberately small —
        it breaks ties between comparable passages and cannot rescue an
        irrelevant one.
        """
        pool = candidates[:int(os.environ.get("RERANK_CANDIDATES", "20"))]
        scores = self._gateway.rerank(query, [c.text for c in pool])
        for scored in scores:
            pool[scored.index].rerank_score = scored.score

        def key(c: Candidate) -> tuple[float, str]:
            base = c.rerank_score if c.rerank_score is not None else -1.0
            # source_priority is 1 for the most authoritative layer.
            bonus = 0.02 * (4 - min(c.source_priority or 4, 4))
            return (-(base + bonus), c.chunk_id)

        return sorted(pool, key=key) + candidates[len(pool):]
