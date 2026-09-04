"""
The model boundary, and the single-model policy it enforces.

These tests never touch the network. The mock provider is the point: the whole
suite runs with an empty `.env`, no credential and no GPU, which is a hard
requirement of ADR-003 and the reason CI has never needed a secret.
"""

from __future__ import annotations

import math

import pytest

from services.models import (
    DEFAULT_CHAT_MODEL,
    CapabilityUnavailable,
    GatewayConfig,
    ModelGateway,
    ModelPolicyViolation,
    ProviderError,
    build_provider,
)
from services.models.providers.mock import MOCK_DIMENSIONS, MockProvider


def gateway() -> ModelGateway:
    return ModelGateway(MockProvider())


# ── the single-model policy (ADR-022) ───────────────────────────────────────

@pytest.mark.parametrize("permitted", ["gemma4:e4b", "google/gemma-4-E4B-it"])
def test_the_two_spellings_of_the_permitted_model_are_accepted(permitted):
    """One model, two names: the Ollama tag and the Hugging Face repository id."""
    ModelGateway(MockProvider(), GatewayConfig(chat_model=permitted))


@pytest.mark.parametrize("forbidden", [
    "Qwen/Qwen3.5-4B", "gpt-4o", "gemini-1.5-pro", "meta-llama/Llama-3-8B", "gemma-2-2b-it",
])
def test_any_other_generation_model_is_refused_at_construction(forbidden):
    """
    The policy is enforced in code, not only in prose.

    Refused when the gateway is built rather than when it is used, so a
    misconfigured deployment fails at startup instead of on a student's first
    question.
    """
    with pytest.raises(ModelPolicyViolation) as exc:
        ModelGateway(MockProvider(), GatewayConfig(chat_model=forbidden))
    assert "ADR-022" in str(exc.value)


def test_the_embedding_model_is_exempt_but_still_pinned():
    """Exempt from the single-model rule, not from having a rule."""
    ModelGateway(MockProvider(), GatewayConfig(embedding_model="BAAI/bge-m3"))
    with pytest.raises(ModelPolicyViolation):
        ModelGateway(MockProvider(), GatewayConfig(embedding_model="text-embedding-3-small"))


def test_the_rerank_model_is_exempt_but_still_pinned():
    with pytest.raises(ModelPolicyViolation):
        ModelGateway(MockProvider(), GatewayConfig(rerank_model="cross-encoder/ms-marco"))


def test_an_unknown_provider_fails_closed():
    with pytest.raises(ProviderError) as exc:
        build_provider("openai")
    assert "mock" in str(exc.value), "the error should name the real options"


def test_config_reads_the_environment(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "mock")
    monkeypatch.setenv("CHAT_MODEL", "gemma4:e4b")
    config = GatewayConfig.from_env()
    assert config.provider == "mock" and config.chat_model == DEFAULT_CHAT_MODEL


def test_gateway_builds_from_an_empty_environment(monkeypatch):
    """The defaults must be the permitted ones, or CI needs configuration to pass."""
    for key in ("AI_PROVIDER", "CHAT_MODEL", "EMBEDDING_MODEL", "RERANK_MODEL"):
        monkeypatch.delenv(key, raising=False)
    assert ModelGateway.from_env().is_mock


# ── embedding ───────────────────────────────────────────────────────────────

def test_embeddings_match_the_real_model_dimensions():
    """
    1024, because the vector column is sized for BGE-M3.

    A mock of a different width would let a dimension mismatch stay hidden until
    the day a real provider is switched on.
    """
    assert gateway().embed_one("anything").dimensions == MOCK_DIMENSIONS == 1024


def test_embeddings_are_unit_vectors():
    vector = gateway().embed_one("তথ্য ও যোগাযোগ প্রযুক্তি").vector
    assert math.isclose(math.sqrt(sum(v * v for v in vector)), 1.0, rel_tol=1e-9)


def test_embeddings_are_deterministic():
    a = gateway().embed_one("the same text").vector
    b = gateway().embed_one("the same text").vector
    assert a == b, "a test cannot assert on a value that changes between runs"


def test_different_texts_embed_differently():
    g = gateway()
    assert g.embed_one("physics").vector != g.embed_one("chemistry").vector


def test_batching_preserves_order():
    g = gateway()
    texts = [f"chunk {i}" for i in range(37)]        # not a multiple of the batch size
    batched = g.embed(texts, batch_size=8)
    assert len(batched) == 37
    assert [e.vector for e in batched] == [g.embed_one(t).vector for t in texts]


def test_embedding_nothing_returns_nothing():
    assert gateway().embed([]) == []


# ── reranking ───────────────────────────────────────────────────────────────

def test_rerank_returns_every_candidate_best_first():
    results = gateway().rerank("query", ["a", "b", "c"])
    assert len(results) == 3
    assert {r.index for r in results} == {0, 1, 2}
    assert [r.score for r in results] == sorted((r.score for r in results), reverse=True)


def test_rerank_is_a_real_ranking_not_the_input_order():
    """
    The mock ranks by cosine over real vectors.

    A mock that returned the input order unchanged would let a broken reranker
    pass its tests, which is the opposite of what a test double is for.
    """
    documents = [f"candidate {i}" for i in range(12)]
    order = [r.index for r in gateway().rerank("a query", documents)]
    assert order != list(range(12))


def test_rerank_of_nothing_returns_nothing():
    assert gateway().rerank("query", []) == []


# ── generation ──────────────────────────────────────────────────────────────

def test_the_mock_answer_says_it_is_a_mock():
    """
    The most important test in this file.

    A mock that produced plausible tutoring prose would look like a working
    system in a demo, in a screenshot and in a competition video, and nobody
    would notice until a student was reading invented physics.
    """
    completion = gateway().generate("Explain gravitational potential energy.")
    assert completion.is_mock
    assert "mock" in completion.text.lower()
    assert "not a tutoring answer" in completion.text


def test_generation_is_deterministic():
    a = gateway().generate("same prompt").text
    b = gateway().generate("same prompt").text
    assert a == b


def test_the_gateway_admits_when_it_is_mocked():
    """The API surfaces this, so a client can tell a student the answer is not real."""
    assert gateway().is_mock is True
    assert gateway().health()["is_mock"] is True


def test_a_provider_that_cannot_generate_raises_rather_than_substituting():
    """
    ADR-022's real teeth: no fallback to a second generation model.

    An answer from an unevaluated model is indistinguishable to a student from
    an evaluated one, so the failure has to be visible.
    """
    class EmbedOnly:
        name = "embed-only"

        def embed(self, texts, *, model):
            return MockProvider().embed(texts, model=model)

        def health(self):
            return {"reachable": True}

    with pytest.raises(CapabilityUnavailable):
        ModelGateway(EmbedOnly()).generate("anything")


def test_health_reports_without_raising():
    state = gateway().health()
    assert state["provider"] == "mock"
    assert state["chat_model"] == DEFAULT_CHAT_MODEL
    assert state["reachable"] is True


def test_health_survives_a_provider_that_throws():
    class Broken:
        name = "broken"

        def health(self):
            raise RuntimeError("provider is down")

    state = ModelGateway(Broken()).health()
    assert state["reachable"] is False and "error" in state
