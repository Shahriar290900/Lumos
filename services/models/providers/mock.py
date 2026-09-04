"""
services.models.providers.mock — the deterministic, credential-free provider.

This is not a convenience. It is what lets the whole test suite run with an empty
`.env`, no credential, no network and no GPU, which is a hard requirement of
ADR-003 and the reason CI has never needed a secret.

**Deterministic, not random.** The same input always produces the same output,
so a test can assert on an embedding or an answer without pinning a seed and
without a snapshot that drifts. Embeddings come from a SHA-256 of the text,
expanded to the real dimensionality and L2-normalised, so they behave like
vectors — cosine similarity works, identical texts score 1.0, and unrelated
texts score near zero — without meaning anything semantically.

**It never pretends to be a tutor.** `generate` returns text that says plainly
it came from the mock. A mock that produced plausible tutoring prose would be
the single most dangerous component in this repository: it would look like a
working system in a demo and in a screenshot, and nobody would notice until a
student was reading invented physics.
"""

from __future__ import annotations

import hashlib
import math
import struct
from typing import Sequence

from .base import Completion, Embedding, RerankResult

# BGE-M3's dimensionality. The mock matches it so a vector column sized for the
# real model accepts mock vectors, and a dimension mismatch cannot hide until
# the day a real provider is switched on.
MOCK_DIMENSIONS = 1024

MOCK_NOTICE = (
    "[mock provider] No generation model is configured, so this is not a "
    "tutoring answer. Retrieval ran and the citations below are real; the "
    "explanation is not."
)


def _stream(text: str, count: int) -> list[float]:
    """`count` deterministic floats in [-1, 1], derived from the text."""
    out: list[float] = []
    counter = 0
    while len(out) < count:
        digest = hashlib.sha256(f"{text}\x00{counter}".encode()).digest()
        for offset in range(0, 32, 4):
            if len(out) >= count:
                break
            (raw,) = struct.unpack(">I", digest[offset:offset + 4])
            out.append((raw / 0xFFFFFFFF) * 2.0 - 1.0)
        counter += 1
    return out


def deterministic_embedding(text: str, dimensions: int = MOCK_DIMENSIONS) -> tuple[float, ...]:
    """
    A stable unit vector for `text`.

    L2-normalised so cosine similarity is the dot product and pgvector's
    distance operators behave the way they will with real embeddings.
    """
    raw = _stream(text, dimensions)
    norm = math.sqrt(sum(v * v for v in raw)) or 1.0
    return tuple(v / norm for v in raw)


class MockProvider:
    """Deterministic stand-in for every capability. Never reaches the network."""

    name = "mock"

    def __init__(self, dimensions: int = MOCK_DIMENSIONS) -> None:
        self.dimensions = dimensions

    # ── embedding ────────────────────────────────────────────────────────────

    def embed(self, texts: Sequence[str], *, model: str) -> list[Embedding]:
        return [Embedding(vector=deterministic_embedding(t, self.dimensions), model=model)
                for t in texts]

    # ── reranking ────────────────────────────────────────────────────────────

    def rerank(self, query: str, documents: Sequence[str], *,
               model: str) -> list[RerankResult]:
        """
        Cosine similarity between the mock embeddings, ordered.

        Not semantic — it cannot be — but it *is* a real ranking function over
        real vectors, so the fusion and reranking code downstream is exercised
        rather than bypassed. A mock that returned the input order unchanged
        would let a broken reranker pass its tests.
        """
        q = deterministic_embedding(query, self.dimensions)
        scored = []
        for index, document in enumerate(documents):
            d = deterministic_embedding(document, self.dimensions)
            scored.append(RerankResult(index=index, score=sum(a * b for a, b in zip(q, d))))
        return sorted(scored, key=lambda r: (-r.score, r.index))

    # ── generation ───────────────────────────────────────────────────────────

    def generate(self, prompt: str, *, model: str, max_tokens: int = 512,
                 temperature: float = 0.2, system: str | None = None) -> Completion:
        """
        A visibly-mock answer. Deterministic, and honest about what it is.

        The digest makes it stable per prompt so a test can assert equality, and
        the notice makes it impossible to mistake for a real answer in a demo,
        a screenshot or a video.
        """
        digest = hashlib.sha256(f"{system or ''}\x00{prompt}".encode()).hexdigest()[:12]
        return Completion(
            text=f"{MOCK_NOTICE}\n\n(deterministic mock response {digest})",
            model=model,
            provider=self.name,
            finish_reason="stop",
            usage={"prompt_chars": len(prompt), "completion_chars": len(MOCK_NOTICE)},
        )

    # ── health ───────────────────────────────────────────────────────────────

    def health(self) -> dict[str, object]:
        return {
            "provider": self.name,
            "reachable": True,
            "capabilities": ["embed", "rerank", "generate"],
            "dimensions": self.dimensions,
            "note": "deterministic; no network, no credential, no GPU",
        }
