"""
services.models.gateway — the only way product code reaches a model.

ADR-003: no product module imports a provider SDK. Retrieval asks the gateway to
embed; the tutor asks it to generate. Neither knows whether that is Hugging
Face, a Render GPU, Ollama, or the deterministic mock, and swapping between them
is one environment variable.

**The single-model rule (ADR-022) lives here**, because a policy enforced only
in prose is not enforced. `CHAT_MODEL` is validated against the one permitted
generation model, and a gateway configured with anything else refuses to
construct rather than quietly serving the wrong model. Embedding and reranking
models are exempt and validated separately: a decoder LLM has no embedding
endpoint, and reranking scores a query-document pair.

**Failure is loud.** When the configured provider cannot generate, the gateway
raises `CapabilityUnavailable`. It does not fall back to a second generation
model, because an answer from an unevaluated model is indistinguishable to a
student from an evaluated one.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Sequence

from .providers.base import (
    CapabilityUnavailable,
    Completion,
    Embedding,
    Provider,
    ProviderError,
    RerankResult,
)
from .providers.mock import MockProvider

# ADR-022. The Ollama tag and the Hugging Face repository id are the same model;
# both are accepted so a provider swap does not need a config edit.
PERMITTED_CHAT_MODELS = frozenset({"gemma4:e4b", "google/gemma-4-E4B-it"})

# Exempt from the single-model rule — the two jobs a decoder LLM cannot do.
PERMITTED_EMBEDDING_MODELS = frozenset({"BAAI/bge-m3"})
PERMITTED_RERANK_MODELS = frozenset({"BAAI/bge-reranker-v2-m3"})

DEFAULT_CHAT_MODEL = "gemma4:e4b"
DEFAULT_EMBEDDING_MODEL = "BAAI/bge-m3"
DEFAULT_RERANK_MODEL = "BAAI/bge-reranker-v2-m3"


class ModelPolicyViolation(ValueError):
    """A configured model is not permitted. Raised at construction, not at use."""


@dataclass(frozen=True)
class GatewayConfig:
    """Resolved model configuration. Validated once, at the boundary."""

    provider: str = "mock"
    chat_model: str = DEFAULT_CHAT_MODEL
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    rerank_model: str = DEFAULT_RERANK_MODEL

    @classmethod
    def from_env(cls) -> "GatewayConfig":
        return cls(
            provider=os.environ.get("AI_PROVIDER", "mock").strip().lower(),
            chat_model=os.environ.get("CHAT_MODEL", DEFAULT_CHAT_MODEL).strip(),
            embedding_model=os.environ.get("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL).strip(),
            rerank_model=os.environ.get("RERANK_MODEL", DEFAULT_RERANK_MODEL).strip(),
        )

    def validate(self) -> None:
        if self.chat_model not in PERMITTED_CHAT_MODELS:
            raise ModelPolicyViolation(
                f"CHAT_MODEL={self.chat_model!r} is not permitted. Lumos generates "
                f"with {DEFAULT_CHAT_MODEL} and nothing else (ADR-022). Permitted "
                f"spellings: {sorted(PERMITTED_CHAT_MODELS)}. Changing this is a "
                "decision that belongs in DECISIONS.md, not in an environment file."
            )
        if self.embedding_model not in PERMITTED_EMBEDDING_MODELS:
            raise ModelPolicyViolation(
                f"EMBEDDING_MODEL={self.embedding_model!r} is not permitted. The "
                "bilingual retrieval design depends on BAAI/bge-m3 and its 1024 "
                "dimensions; the vector column is sized for it.")
        if self.rerank_model not in PERMITTED_RERANK_MODELS:
            raise ModelPolicyViolation(
                f"RERANK_MODEL={self.rerank_model!r} is not permitted. "
                "Reranking uses BAAI/bge-reranker-v2-m3.")


class SplitProvider:
    """
    One provider generates, another embeds and reranks.

    This is not an abstraction for its own sake — it is the only configuration
    in which the whole system works today. Hugging Face serves `BAAI/bge-m3` but
    not `gemma4:e4b`; Ollama serves `gemma4:e4b` but cannot produce bge-m3
    vectors. The corpus is already indexed with bge-m3, so embedding queries
    with anything else would place query and document vectors in different
    spaces and rank confidently wrong.

    It is emphatically **not** a fallback chain. Each capability has exactly one
    provider, chosen because it is the only one that can do that job. Nothing
    here ever answers a generation request from a second generation model
    (ADR-022).
    """

    def __init__(self, generator: Provider, retriever: Provider) -> None:
        self._generator = generator
        self._retriever = retriever
        self.name = f"{getattr(generator, 'name', '?')}+{getattr(retriever, 'name', '?')}"

    def generate(self, prompt: str, **kwargs: Any) -> Completion:
        return self._generator.generate(prompt, **kwargs)

    def embed(self, texts: Sequence[str], *, model: str) -> list[Embedding]:
        return self._retriever.embed(texts, model=model)

    def rerank(self, query: str, documents: Sequence[str], *, model: str) -> list[RerankResult]:
        return self._retriever.rerank(query, documents, model=model)

    def health(self) -> dict[str, Any]:
        return {
            "generation": self._generator.health(),
            "retrieval": self._retriever.health(),
            "reachable": bool(self._generator.health().get("reachable")),
        }


def build_provider(name: str) -> Provider:
    """Construct a provider by name. Unknown names fail closed, listing the real ones."""
    if name == "mock":
        return MockProvider()
    if name in ("huggingface", "hf"):
        from .providers.huggingface import HuggingFaceProvider
        return HuggingFaceProvider()
    if name == "ollama":
        # Generation locally, embeddings on Hugging Face — see SplitProvider.
        from .providers.ollama import OllamaProvider
        try:
            from .providers.huggingface import HuggingFaceProvider
            return SplitProvider(OllamaProvider(), HuggingFaceProvider())
        except ProviderError:
            # No HF token: generation still works, retrieval will say why.
            return OllamaProvider()
    raise ProviderError(
        f"unknown AI_PROVIDER={name!r}. Available: mock, huggingface, ollama. "
        "An unrecognised provider is a configuration error, not a reason to "
        "guess at a default.")


class ModelGateway:
    """
    The model boundary. Product code holds one of these and nothing else.

    Construct with `ModelGateway.from_env()` in application code; pass an
    explicit provider in tests.
    """

    def __init__(self, provider: Provider, config: GatewayConfig | None = None) -> None:
        self.config = config or GatewayConfig()
        self.config.validate()
        self._provider = provider

    @classmethod
    def from_env(cls) -> "ModelGateway":
        config = GatewayConfig.from_env()
        config.validate()
        return cls(build_provider(config.provider), config)

    @property
    def provider_name(self) -> str:
        return getattr(self._provider, "name", "unknown")

    @property
    def is_mock(self) -> bool:
        """
        Whether answers come from the mock.

        Exposed so the API can tell a client — and therefore a student — that an
        answer is not from a real model. A demo that hides this is the failure
        mode this project exists to avoid.
        """
        return self.provider_name == "mock"

    # ── capabilities ─────────────────────────────────────────────────────────

    def embed(self, texts: Sequence[str], *, batch_size: int = 16) -> list[Embedding]:
        """Embed texts in batches, preserving order."""
        if not texts:
            return []
        if not hasattr(self._provider, "embed"):
            raise CapabilityUnavailable(
                f"provider {self.provider_name!r} cannot embed; retrieval needs "
                f"{self.config.embedding_model}")
        out: list[Embedding] = []
        for start in range(0, len(texts), batch_size):
            out.extend(self._provider.embed(
                texts[start:start + batch_size], model=self.config.embedding_model))
        return out

    def embed_one(self, text: str) -> Embedding:
        return self.embed([text])[0]

    def rerank(self, query: str, documents: Sequence[str]) -> list[RerankResult]:
        """Score documents against a query, best first."""
        if not documents:
            return []
        if not hasattr(self._provider, "rerank"):
            raise CapabilityUnavailable(
                f"provider {self.provider_name!r} cannot rerank; "
                f"ranking needs {self.config.rerank_model}")
        return self._provider.rerank(query, documents, model=self.config.rerank_model)

    def generate(self, prompt: str, *, system: str | None = None,
                 max_tokens: int = 512, temperature: float = 0.2) -> Completion:
        """
        Generate an answer with the one permitted model.

        Raises `CapabilityUnavailable` when it cannot. Callers must surface that
        as a stated limitation, never as an answer from something else.
        """
        if not hasattr(self._provider, "generate"):
            raise CapabilityUnavailable(
                f"provider {self.provider_name!r} cannot generate")
        return self._provider.generate(
            prompt, model=self.config.chat_model, max_tokens=max_tokens,
            temperature=temperature, system=system)

    # ── health ───────────────────────────────────────────────────────────────

    def health(self) -> dict[str, object]:
        state: dict[str, object] = {
            "provider": self.provider_name,
            "is_mock": self.is_mock,
            "chat_model": self.config.chat_model,
            "embedding_model": self.config.embedding_model,
            "rerank_model": self.config.rerank_model,
        }
        try:
            state.update(self._provider.health())
        except Exception as exc:   # noqa: BLE001 - a probe reports, never crashes
            state["reachable"] = False
            state["error"] = f"{type(exc).__name__}"
        return state
