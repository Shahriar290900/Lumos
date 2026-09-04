"""
Hybrid retrieval: the metadata filter, the two retrievers, and the fusion.

Runs against the mock provider, so it needs no credential and no network. The
mock's embeddings are deterministic unit vectors, which means the SQL, the
fusion arithmetic and the curriculum isolation are all exercised for real — only
the *meaning* of the vectors is fake.
"""

from __future__ import annotations

import pytest

from services.models import ModelGateway
from services.models.providers.mock import MockProvider, deterministic_embedding
from services.rag.retrieval import RRF_K, HybridRetriever, detect_language


@pytest.fixture
def retriever(conn):
    return HybridRetriever(conn, ModelGateway(MockProvider()))


def _embed(conn, chunk_id: str, text: str) -> None:
    vector = "[" + ",".join(f"{v:.8f}" for v in deterministic_embedding(text)) + "]"
    with conn.cursor() as cur:
        cur.execute("UPDATE chunks SET embedding=%s::vector, embedding_model=%s, "
                    "embedded_at=now() WHERE id=%s::uuid",
                    (vector, "BAAI/bge-m3", chunk_id))


def _chunk(conn, sandbox, locator: str, text: str, *, embed: bool = True,
           priority: int | None = None) -> str:
    from services.ingestion.canonical import CanonicalChunk, ChunkWriter
    chunk = CanonicalChunk(
        source_document_id=sandbox["document_id"], offering_id=sandbox["offering_id"],
        document_sha256=sandbox["document_sha256"], locator=locator, text=text,
        chunk_type="exam_question", extraction_method="pdf_text_layer",
        question_number=locator.split("/")[-1], marks=3)
    ChunkWriter(conn).write([chunk])
    if embed:
        _embed(conn, chunk.id, text)
    return chunk.id


# ── language detection drives the fusion weights ────────────────────────────

def test_language_is_detected_from_the_script():
    assert detect_language("What is gravitational potential energy?") == "en"
    assert detect_language("অভিকর্ষজ বিভব শক্তি কী?") == "bn"


def test_an_english_gloss_inside_a_bangla_question_is_still_bangla():
    """The weights should follow the question the student actually typed."""
    assert detect_language("resistivity এর একক কী?") == "bn"


# ── curriculum isolation (ADR-006) ──────────────────────────────────────────

def test_retrieval_never_crosses_an_offering_boundary(conn, sandbox, retriever):
    """
    The filter is a WHERE clause on both retrievers, not a post-hoc filter.

    This is the legacy defect ADR-001 and ADR-006 exist to fix: FAISS searched
    globally and the metadata filter ran afterwards on the top-k, so a query
    scoped to one subject could return nothing in scope because every near
    neighbour belonged to another.
    """
    _chunk(conn, sandbox, "q/1", "Calculate the gravitational potential energy of the block.")

    with conn.cursor() as cur:
        cur.execute("SELECT id::text FROM subject_offerings WHERE id <> %s LIMIT 1",
                    (sandbox["offering_id"],))
        other = cur.fetchone()[0]

    result = retriever.retrieve("gravitational potential energy", offering_id=other)
    assert result.is_empty
    assert all(c.offering_slug != sandbox["slug"] for c in result.candidates)


def test_retrieval_finds_a_chunk_in_its_own_offering(conn, sandbox, retriever):
    _chunk(conn, sandbox, "q/1", "Calculate the gravitational potential energy of the block.")
    result = retriever.retrieve("gravitational potential energy",
                                offering_id=sandbox["offering_id"])
    assert not result.is_empty
    assert result.candidates[0].offering_slug == sandbox["slug"]


# ── the two retrievers ──────────────────────────────────────────────────────

def test_lexical_retrieval_ors_its_terms(conn, sandbox, retriever):
    """
    The bug this pins: `plainto_tsquery` ANDs every term.

    Under the `simple` configuration — chosen so Bangla is not mangled — nothing
    is a stopword, so "How do I calculate gravitational potential energy?"
    demanded all seven words in one chunk. On the real corpus that returned zero
    lexical matches while semantic returned thirty, and half the hybrid was
    silently contributing nothing.
    """
    _chunk(conn, sandbox, "q/1", "Calculate the gravitational potential energy.", embed=False)
    result = retriever.retrieve("How do I calculate gravitational potential energy?",
                                offering_id=sandbox["offering_id"])
    assert result.lexical_found >= 1, "an ORed query must match on the content words"


def test_semantic_retrieval_is_skipped_when_nothing_is_embedded(conn, sandbox, retriever):
    """And says so, rather than silently returning half a result."""
    _chunk(conn, sandbox, "q/1", "Calculate the work done by the force.", embed=False)
    result = retriever.retrieve("work done", offering_id=sandbox["offering_id"])
    assert result.semantic_found == 0
    assert result.embedded_chunks_available == 0
    assert any("not embedded" in n or "no chunks are embedded" in n for n in result.notes)


def test_both_retrievers_contribute_when_both_can(conn, sandbox, retriever):
    _chunk(conn, sandbox, "q/1", "Calculate the gravitational potential energy of the block.")
    result = retriever.retrieve("gravitational potential energy",
                                offering_id=sandbox["offering_id"])
    assert result.lexical_found >= 1 and result.semantic_found >= 1
    assert "lexical" in result.candidates[0].retrievers


# ── fusion ──────────────────────────────────────────────────────────────────

def test_a_chunk_found_by_both_retrievers_outranks_one_found_by_either(conn, sandbox, retriever):
    """The entire point of fusing two rankings rather than picking one."""
    both = _chunk(conn, sandbox, "q/1", "The gravitational potential energy of the block increases.")
    _chunk(conn, sandbox, "q/2", "An unrelated passage about circuits and resistance.")

    result = retriever.retrieve("gravitational potential energy",
                                offering_id=sandbox["offering_id"], rerank=False)
    top = result.candidates[0]
    assert top.chunk_id == both
    assert len(top.retrievers) == 2


def test_rrf_score_uses_the_rank_not_the_similarity(conn, sandbox, retriever):
    """
    Rank fusion needs no score normalisation between incomparable scales.

    A first-place finish contributes weight/(k+1) regardless of whether the
    underlying score was 0.99 or 0.4, which is what makes RRF survive a corpus
    change that would invalidate a tuned score blend.
    """
    _chunk(conn, sandbox, "q/1", "Gravitational potential energy is mgh.")
    result = retriever.retrieve("gravitational potential energy",
                                offering_id=sandbox["offering_id"], rerank=False)
    top = result.candidates[0]

    # English weights: 0.4 sparse, 0.6 dense. Whichever retrievers found it,
    # each contributes weight / (k + rank) and nothing else.
    expected = 0.0
    if top.lexical_rank is not None:
        expected += 0.4 / (RRF_K + top.lexical_rank)
    if top.semantic_rank is not None:
        expected += 0.6 / (RRF_K + top.semantic_rank)

    assert top.fused_score == pytest.approx(expected), (
        "the fused score must be the reciprocal-rank sum, with no similarity "
        "score leaking into it")
    assert 0 < top.fused_score < 1


def test_results_are_ordered_best_first(conn, sandbox, retriever):
    for i in range(5):
        _chunk(conn, sandbox, f"q/{i}", f"Passage {i} about energy and motion in physics.")
    result = retriever.retrieve("energy", offering_id=sandbox["offering_id"], rerank=False)
    scores = [c.fused_score for c in result.candidates]
    assert scores == sorted(scores, reverse=True)


def test_limit_is_respected(conn, sandbox, retriever):
    for i in range(9):
        _chunk(conn, sandbox, f"q/{i}", f"Passage {i} about energy and motion in physics.")
    assert len(retriever.retrieve("energy", offering_id=sandbox["offering_id"],
                                  limit=4).candidates) == 4


# ── honesty ─────────────────────────────────────────────────────────────────

def test_a_query_matching_nothing_returns_nothing(conn, sandbox, retriever):
    """
    No widening the search until something comes back.

    An empty result is a real answer, and the tutor is expected to state a
    limitation rather than ground an explanation in whatever was nearest.
    """
    _chunk(conn, sandbox, "q/1", "Calculate the gravitational potential energy.", embed=False)
    result = retriever.retrieve("zzzqqq nonexistent terminology",
                                offering_id=sandbox["offering_id"])
    assert result.is_empty
    assert result.notes


def test_every_candidate_carries_a_resolvable_citation(conn, sandbox, retriever):
    """ADR-010: a citation must point at a real place in a real document."""
    _chunk(conn, sandbox, "q/12", "Calculate the gravitational potential energy.")
    candidate = retriever.retrieve("gravitational potential energy",
                                   offering_id=sandbox["offering_id"]).candidates[0]
    citation = candidate.citation()
    assert citation["chunk_id"] == candidate.chunk_id
    assert citation["offering"] == sandbox["slug"]
    assert citation["question_number"] == "12"


def test_a_citation_never_carries_the_source_text(conn, sandbox, retriever):
    """
    The tutor explains and cites; it does not reproduce (ADR-026, BLOCK-008).

    A citation payload that included the chunk text would make every API
    response a redistribution of licensed material.
    """
    _chunk(conn, sandbox, "q/1", "Some licensed passage of Pearson material.")
    citation = retriever.retrieve("licensed passage",
                                  offering_id=sandbox["offering_id"]).candidates[0].citation()
    assert "text" not in citation
    assert not any(isinstance(v, str) and "Pearson" in v for v in citation.values())
