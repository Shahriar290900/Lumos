"""
services.models.providers.base — what every provider must implement.

Three capabilities, deliberately separate, because no single model does all
three (ADR-022):

    embed    turn text into a vector                   BAAI/bge-m3
    rerank   score a query against candidate documents BAAI/bge-reranker-v2-m3
    generate produce an answer                         gemma4:e4b, and only that

A provider may implement any subset. The gateway asks for a capability, not for
a provider, and raises a typed error naming the missing piece when nobody can
serve it. That is the whole point of ADR-003: no product module imports a
provider SDK, and swapping a provider is a configuration change.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence, runtime_checkable


class ProviderError(RuntimeError):
    """A provider could not serve a request. Never swallowed into a fake answer."""


class CapabilityUnavailable(ProviderError):
    """
    The configured provider cannot do this job.

    Raised rather than falling back to a different model. An answer from an
    unevaluated model is indistinguishable to a student from an evaluated one,
    so a silent substitution turns a measured system into an unmeasured one at
    exactly the moment something is already going wrong (ADR-022).
    """


@dataclass(frozen=True)
class Embedding:
    """One vector, and the model that produced it."""

    vector: tuple[float, ...]
    model: str

    @property
    def dimensions(self) -> int:
        return len(self.vector)


@dataclass(frozen=True)
class RerankResult:
    """One candidate's relevance to a query, as a cross-encoder scored it."""

    index: int
    score: float


@dataclass(frozen=True)
class Completion:
    """A generated answer, and enough provenance to audit where it came from."""

    text: str
    model: str
    provider: str
    finish_reason: str = "stop"
    usage: dict[str, int] = field(default_factory=dict)

    @property
    def is_mock(self) -> bool:
        return self.provider == "mock"


@runtime_checkable
class Provider(Protocol):
    """A model backend. Every method is optional; the gateway checks first."""

    name: str

    def embed(self, texts: Sequence[str], *, model: str) -> list[Embedding]: ...

    def rerank(self, query: str, documents: Sequence[str], *,
               model: str) -> list[RerankResult]: ...

    def generate(self, prompt: str, *, model: str, max_tokens: int,
                 temperature: float, system: str | None) -> Completion: ...

    def health(self) -> dict[str, object]: ...
