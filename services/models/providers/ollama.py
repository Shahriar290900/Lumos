"""
services.models.providers.ollama — gemma4:e4b on a machine that can actually run it.

This is the provider that makes generation work. Hugging Face serves the
embeddings and the reranker but not `google/gemma-4-E4B-it`, so on a machine
with a capable GPU the shortest path to a working tutor is Ollama:

    ollama pull gemma4:e4b
    ollama serve                      # listens on 127.0.0.1:11434

    AI_PROVIDER=ollama
    OLLAMA_URL=http://127.0.0.1:11434

**Embeddings deliberately stay on Hugging Face.** Ollama can embed, but not with
`BAAI/bge-m3`, and an embedding from a different model is worse than none: the
corpus is already indexed with bge-m3 and mixing models would put query and
document vectors in different spaces, which ranks confidently and wrongly. So
this provider generates only, and the gateway keeps using Hugging Face for
`embed` and `rerank`. Set both:

    AI_PROVIDER=ollama
    HF_TOKEN=...                      # still needed, for embeddings

`ollama show gemma4:e4b` verifies the tag. If it resolves to something else,
record what it actually is in CONNECTORS.md rather than assuming (BLOCK-005).
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Sequence

from .base import CapabilityUnavailable, Completion, Embedding, ProviderError, RerankResult

DEFAULT_URL = "http://127.0.0.1:11434"


class OllamaProvider:
    """Local generation through Ollama's chat API."""

    name = "ollama"

    def __init__(self, url: str | None = None, timeout: float = 180.0) -> None:
        # Generous timeout: a cold model load on a consumer GPU can take a
        # minute, and failing at 30 seconds would look like a broken endpoint.
        self._url = (url or os.environ.get("OLLAMA_URL")
                     or os.environ.get("AI_API_URL") or DEFAULT_URL).rstrip("/")
        self._timeout = timeout

    def _post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self._url}{path}", data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")[:300]
            if exc.code == 404:
                raise CapabilityUnavailable(
                    f"Ollama has no such model. Run `ollama pull "
                    f"{payload.get('model')}` on the host running {self._url}."
                ) from None
            raise ProviderError(f"ollama HTTP {exc.code}: {body}") from None
        except Exception as exc:  # noqa: BLE001
            raise ProviderError(
                f"cannot reach Ollama at {self._url} ({type(exc).__name__}). "
                "Is `ollama serve` running, and is OLLAMA_URL correct?") from None

    # ── generation ───────────────────────────────────────────────────────────

    def generate(self, prompt: str, *, model: str, max_tokens: int = 512,
                 temperature: float = 0.2, system: str | None = None) -> Completion:
        messages = ([{"role": "system", "content": system}] if system else []) + \
                   [{"role": "user", "content": prompt}]
        body = self._post("/api/chat", {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": temperature, "num_predict": max_tokens},
        })
        return Completion(
            text=(body.get("message") or {}).get("content", ""),
            model=body.get("model", model),
            provider=self.name,
            finish_reason=body.get("done_reason", "stop"),
            usage={k: int(v) for k, v in body.items()
                   if k.endswith("_count") and isinstance(v, (int, float))},
        )

    # ── embedding and reranking are not this provider's job ──────────────────

    def embed(self, texts: Sequence[str], *, model: str) -> list[Embedding]:
        raise CapabilityUnavailable(
            f"the ollama provider does not embed. The corpus is indexed with "
            f"{model} via Hugging Face, and embedding queries with a different "
            "model would put query and document vectors in different spaces. "
            "Keep HF_TOKEN set; the gateway routes embeddings there.")

    def rerank(self, query: str, documents: Sequence[str], *,
               model: str) -> list[RerankResult]:
        raise CapabilityUnavailable(
            "the ollama provider does not rerank; use a cross-encoder endpoint")

    # ── health ───────────────────────────────────────────────────────────────

    def health(self) -> dict[str, object]:
        state: dict[str, object] = {"provider": self.name, "url": self._url}
        try:
            with urllib.request.urlopen(f"{self._url}/api/tags", timeout=10) as response:
                tags = json.loads(response.read().decode("utf-8"))
            state["reachable"] = True
            state["models"] = [m.get("name") for m in tags.get("models", [])][:12]
        except Exception as exc:  # noqa: BLE001
            state["reachable"] = False
            state["error"] = f"{type(exc).__name__}"
        return state
