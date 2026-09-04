"""
services.models.providers.huggingface — embeddings and reranking over HF Inference.

**What was verified on 2026-09-04**, against the real endpoint with a real token,
rather than assumed from documentation:

    BAAI/bge-m3               feature-extraction     WORKS — 1024 dims, Bangla input
    BAAI/bge-reranker-v2-m3   sentence-similarity    WORKS — 0.975 relevant / 0.451 not
    google/gemma-4-E4B-it     chat/completions       NOT AVAILABLE

The generation gap is not a bug here and is not worked around. The repository
exists and is ungated, but its pipeline tag is `any-to-any` and the router
reports no inference provider serving it: *"The requested model
'google/gemma-4-E4B-it' is not a chat model."* Serving it needs a dedicated
Inference Endpoint or a rented GPU running Ollama, which is a spending decision
and is BLOCK-005.

So `generate` raises `CapabilityUnavailable` with that explanation. It does not
quietly substitute a model the router *will* serve, because ADR-022 forbids
exactly that, and because a demo that silently answered from some other model
would be worse than one that plainly says generation is not wired up.

Reranking uses the `sentence-similarity` pipeline rather than a raw
cross-encoder call. The text-classification form returns HTTP 400 for a text
pair on this endpoint; sentence-similarity accepts one source against many
candidates in a single request, which is also fewer round trips.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Sequence

from .base import (
    CapabilityUnavailable,
    Completion,
    Embedding,
    ProviderError,
    RerankResult,
)

DEFAULT_ROUTER = "https://router.huggingface.co"

# The same model has two names, and only one of them means anything here.
# `gemma4:e4b` is the Ollama tag; Hugging Face wants the repository id. Passing
# the Ollama tag through unmapped makes the router read `e4b` after the colon as
# a provider name and reject it as *"the provider or policy you attempted to
# specify 'e4b' is not valid"* — an error that says nothing about the real
# problem. Translating here keeps `CHAT_MODEL` provider-agnostic, which is what
# .env.example documents.
_MODEL_ALIASES = {
    "gemma4:e4b": "google/gemma-4-E4B-it",
}

# The endpoint returns 503 while a model loads onto a worker. That is expected
# on a cold model, not a failure, so it is retried with a backoff. Every other
# status is surfaced immediately.
_RETRY_STATUSES = frozenset({503, 529})


class HuggingFaceProvider:
    """Embeddings and reranking over the HF Inference router."""

    name = "huggingface"

    def __init__(self, token: str | None = None, *, router: str | None = None,
                 timeout: float = 60.0, retries: int = 3) -> None:
        self._token = token or os.environ.get("HF_TOKEN") or ""
        if not self._token:
            # ADR-012: a missing credential fails closed, and says which one.
            raise ProviderError(
                "HF_TOKEN is not set. The huggingface provider needs a token with "
                "the 'inference.serverless.write' scope; set it in .env, never in code.")
        self._router = (router or os.environ.get("AI_API_URL") or DEFAULT_ROUTER).rstrip("/")
        self._timeout = timeout
        self._retries = retries

    # ── transport ────────────────────────────────────────────────────────────

    def _post(self, url: str, payload: dict[str, Any]) -> Any:
        last: str = ""
        for attempt in range(self._retries):
            request = urllib.request.Request(
                url, data=json.dumps(payload).encode("utf-8"),
                headers={"Authorization": f"Bearer {self._token}",
                         "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", "replace")[:300]
                last = f"HTTP {exc.code}: {body}"
                if exc.code in _RETRY_STATUSES and attempt < self._retries - 1:
                    time.sleep(2 ** attempt * 5)   # model is loading; wait and retry
                    continue
                raise ProviderError(f"{url} → {last}") from None
            except Exception as exc:   # noqa: BLE001 - network shape varies
                last = f"{type(exc).__name__}: {exc}"
                if attempt < self._retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise ProviderError(f"{url} → {last}") from None
        raise ProviderError(f"{url} → {last}")

    def _model_url(self, model: str, pipeline: str) -> str:
        return f"{self._router}/hf-inference/models/{model}/pipeline/{pipeline}"

    # ── embedding ────────────────────────────────────────────────────────────

    def embed(self, texts: Sequence[str], *, model: str) -> list[Embedding]:
        """
        Embed one batch. Returns vectors in the order given.

        The endpoint returns either a flat vector for a single string or a list
        of vectors for a list, so both shapes are normalised here rather than
        left for every caller to rediscover.
        """
        if not texts:
            return []
        raw = self._post(self._model_url(model, "feature-extraction"),
                         {"inputs": list(texts)})

        vectors = [raw] if raw and isinstance(raw[0], (int, float)) else raw
        if len(vectors) != len(texts):
            raise ProviderError(
                f"{model} returned {len(vectors)} vectors for {len(texts)} inputs")

        out: list[Embedding] = []
        for vector in vectors:
            # Some pipelines return token-level vectors; take the pooled row.
            if vector and isinstance(vector[0], list):
                vector = vector[0]
            out.append(Embedding(vector=tuple(float(v) for v in vector), model=model))
        return out

    # ── reranking ────────────────────────────────────────────────────────────

    def rerank(self, query: str, documents: Sequence[str], *,
               model: str) -> list[RerankResult]:
        if not documents:
            return []
        scores = self._post(
            self._model_url(model, "sentence-similarity"),
            {"inputs": {"source_sentence": query, "sentences": list(documents)}})
        if not isinstance(scores, list) or len(scores) != len(documents):
            raise ProviderError(
                f"{model} returned {type(scores).__name__} for {len(documents)} documents")
        ranked = [RerankResult(index=i, score=float(s)) for i, s in enumerate(scores)]
        return sorted(ranked, key=lambda r: (-r.score, r.index))

    # ── generation ───────────────────────────────────────────────────────────

    def generate(self, prompt: str, *, model: str, max_tokens: int = 512,
                 temperature: float = 0.2, system: str | None = None) -> Completion:
        """
        Chat completion. Currently unavailable for the only permitted model.

        Kept as a real implementation rather than a stub, because the moment an
        Inference Endpoint exists this is the code that will call it, and a stub
        would have to be written and reviewed under time pressure instead.
        """
        repo = _MODEL_ALIASES.get(model, model)
        messages = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": prompt}]
        try:
            body = self._post(f"{self._router}/v1/chat/completions", {
                "model": repo, "messages": messages,
                "max_tokens": max_tokens, "temperature": temperature})
        except ProviderError as exc:
            text = str(exc)
            if any(s in text for s in ("not a chat model", "not supported by any provider",
                                       "is not valid", "model_not_supported")):
                raise CapabilityUnavailable(
                    f"{model} (repo {repo}) is not served by any enabled HF inference "
                    "provider. "
                    "The repository exists and is ungated, but its pipeline is "
                    "'any-to-any' and no provider hosts it, so serving it needs a "
                    "dedicated Inference Endpoint or a GPU running Ollama (BLOCK-005). "
                    "Set AI_PROVIDER=mock until one exists. Substituting a different "
                    "generation model is forbidden by ADR-022."
                ) from None
            raise

        choice = (body.get("choices") or [{}])[0]
        return Completion(
            text=(choice.get("message") or {}).get("content", ""),
            model=body.get("model", repo),
            provider=self.name,
            finish_reason=choice.get("finish_reason", "stop"),
            usage={k: int(v) for k, v in (body.get("usage") or {}).items()
                   if isinstance(v, (int, float))},
        )

    # ── health ───────────────────────────────────────────────────────────────

    def health(self) -> dict[str, object]:
        """Report what actually answers, without asserting anything untested."""
        state: dict[str, object] = {"provider": self.name, "router": self._router}
        try:
            vectors = self.embed(["health check"],
                                 model=os.environ.get("EMBEDDING_MODEL", "BAAI/bge-m3"))
            state["embed"] = "ok"
            state["dimensions"] = vectors[0].dimensions
            state["reachable"] = True
        except Exception as exc:   # noqa: BLE001 - a probe reports, never crashes
            state["embed"] = f"failed: {type(exc).__name__}"
            state["reachable"] = False
        state["generate"] = "unavailable: no provider serves the permitted model (BLOCK-005)"
        return state
