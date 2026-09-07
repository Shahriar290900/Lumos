"""
services.models.providers.gemini — Gemma 4 through the Gemini API.

This is the provider that finally makes generation work. `gemma-4-E4B-it` has no
inference host anywhere we can reach, but Google serves two larger Gemma 4
variants on the Gemini API, and a key for it costs nothing to try.

**Three things measured against the live API on 2026-09-07**, each of which
would have shipped a broken demo if assumed instead:

1. **Both models think, and thinking cannot be turned off.** Passing
   `thinkingConfig.thinkingBudget = 0` returns HTTP 400, *"Thinking budget is
   not supported for this model."* So the cost is unavoidable and has to be
   budgeted for rather than disabled.

2. **The reasoning scratchpad comes back inside `parts`.** Each part carries a
   `thought: true` flag, and the naive `"".join(p["text"] for p in parts)` —
   which is what every quickstart shows — hands the student the model's private
   notes:

       *   Topic: Gravitational potential energy.
       *   Constraint: Exactly two sentences.

   `_answer_text` keeps only the parts *not* marked as thought. That filter is
   the single most important line in this file.

3. **A small token budget yields no answer at all.** Thinking runs 400–730
   tokens before the answer starts, so `maxOutputTokens=80` returns one thought
   part, `finishReason=MAX_TOKENS`, and nothing to show. Anything under about
   1,200 is unusable; the floor below is 1,500.

**Model choice.** `gemma-4-26b-a4b-it` is a sparse mixture of experts — 26B
total, ~4B active — and answered in 11–13 s. The dense `gemma-4-31b-it` took
26–78 s for the same prompt. For a live demo that difference decides it, so the
26B is the default and the 31B is available for offline quality comparison.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Any, Sequence

from .base import CapabilityUnavailable, Completion, Embedding, ProviderError, RerankResult

DEFAULT_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta"

# Thinking runs 400–730 tokens before the answer begins. Below roughly 1,200 the
# budget is spent entirely on thought and the response carries no answer part —
# a silent empty answer rather than an error, which is the worst failure shape.
MIN_OUTPUT_TOKENS = 1500

_RETRY_STATUSES = frozenset({429, 500, 503, 504})


class GeminiProvider:
    """Gemma 4 generation over the Gemini API. Generation only."""

    name = "gemini"

    def __init__(self, api_key: str | None = None, *, endpoint: str | None = None,
                 timeout: float = 180.0, retries: int = 3) -> None:
        self._key = api_key or os.environ.get("GEMINI_API_KEY") or ""
        if not self._key:
            # ADR-012: fail closed, and name the variable.
            raise ProviderError(
                "GEMINI_API_KEY is not set. The gemini provider needs a key from "
                "https://aistudio.google.com/apikey; put it in .env, never in code.")
        self._endpoint = (endpoint or os.environ.get("AI_API_URL")
                          or DEFAULT_ENDPOINT).rstrip("/")
        self._timeout = timeout
        self._retries = retries

    # ── transport ────────────────────────────────────────────────────────────

    def _post(self, model: str, payload: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._endpoint}/models/{model}:generateContent"
        last = ""
        for attempt in range(self._retries):
            request = urllib.request.Request(
                url, data=json.dumps(payload).encode("utf-8"),
                headers={"x-goog-api-key": self._key,
                         "Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", "replace")[:300]
                last = f"HTTP {exc.code}: {body}"
                if exc.code in (401, 403):
                    raise ProviderError(
                        f"Gemini rejected the credential ({exc.code}). Check "
                        f"GEMINI_API_KEY. {body}") from None
                if exc.code == 404:
                    raise CapabilityUnavailable(
                        f"the Gemini API does not serve {model!r}. Supported Gemma 4 "
                        "models are gemma-4-26b-a4b-it and gemma-4-31b-it.") from None
                if exc.code in _RETRY_STATUSES and attempt < self._retries - 1:
                    time.sleep(2 ** attempt * 2)
                    continue
                raise ProviderError(f"{url} → {last}") from None
            except Exception as exc:   # noqa: BLE001 - network shape varies
                last = f"{type(exc).__name__}: {exc}"
                if attempt < self._retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise ProviderError(f"{url} → {last}") from None
        raise ProviderError(f"{url} → {last}")

    # ── generation ───────────────────────────────────────────────────────────

    @staticmethod
    def _answer_text(parts: Sequence[dict[str, Any]]) -> str:
        """
        The answer, with the model's private reasoning removed.

        Gemma 4 on this API returns its scratchpad as parts flagged
        `thought: true`, in the same list as the answer. Joining every part —
        what the quickstarts do — puts "* Constraint: Exactly two sentences"
        in front of a student. Only unflagged parts are the answer.
        """
        return "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()

    def generate(self, prompt: str, *, model: str, max_tokens: int = 512,
                 temperature: float = 0.2, system: str | None = None) -> Completion:
        # Raising the caller's budget rather than honouring it, because honouring
        # it produces an empty answer and no error. Documented above; the caller
        # asked for N tokens of *answer*, and thinking is overhead it cannot see.
        budget = max(max_tokens, MIN_OUTPUT_TOKENS)

        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {"maxOutputTokens": budget, "temperature": temperature},
        }
        if system:
            # Gemma on the Gemini API does not accept `systemInstruction`; the
            # instructions are prepended to the turn instead.
            payload["contents"][0]["parts"][0]["text"] = f"{system}\n\n{prompt}"

        body = self._post(model, payload)
        candidate = (body.get("candidates") or [{}])[0]
        parts = (candidate.get("content") or {}).get("parts") or []
        text = self._answer_text(parts)
        usage = body.get("usageMetadata") or {}
        finish = candidate.get("finishReason", "STOP")

        if not text:
            # An empty answer is reported, never returned as one. The usual cause
            # is the budget being spent entirely on thought.
            raise ProviderError(
                f"{model} returned no answer part (finish={finish}, "
                f"thought tokens={usage.get('thoughtsTokenCount')}, "
                f"budget={budget}). Thinking consumed the whole output budget.")

        return Completion(
            text=text,
            model=body.get("modelVersion", model),
            provider=self.name,
            finish_reason=str(finish),
            usage={k: int(v) for k, v in usage.items() if isinstance(v, (int, float))},
        )

    # ── not this provider's job ──────────────────────────────────────────────

    def embed(self, texts: Sequence[str], *, model: str) -> list[Embedding]:
        raise CapabilityUnavailable(
            f"the gemini provider does not embed. The corpus is indexed with "
            f"{model} via Hugging Face, and embedding queries with a different "
            "model would put query and document vectors in different spaces.")

    def rerank(self, query: str, documents: Sequence[str], *,
               model: str) -> list[RerankResult]:
        raise CapabilityUnavailable("the gemini provider does not rerank")

    # ── health ───────────────────────────────────────────────────────────────

    def health(self) -> dict[str, object]:
        state: dict[str, object] = {"provider": self.name, "endpoint": self._endpoint}
        try:
            request = urllib.request.Request(
                f"{self._endpoint}/models?pageSize=100",
                headers={"x-goog-api-key": self._key})
            with urllib.request.urlopen(request, timeout=30) as response:
                models = json.loads(response.read().decode()).get("models", [])
            available = [m["name"].split("/")[-1] for m in models
                         if "gemma" in m.get("name", "").lower()]
            state["reachable"] = True
            state["gemma_models"] = available
        except Exception as exc:   # noqa: BLE001 - a probe reports, never crashes
            state["reachable"] = False
            state["error"] = f"{type(exc).__name__}"
        return state
