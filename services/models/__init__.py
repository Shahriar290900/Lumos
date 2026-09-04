"""services.models — the model boundary (ADR-003) and the single-model policy (ADR-022)."""

from .gateway import (
    DEFAULT_CHAT_MODEL,
    PERMITTED_CHAT_MODELS,
    GatewayConfig,
    ModelGateway,
    ModelPolicyViolation,
    build_provider,
)
from .providers.base import (
    CapabilityUnavailable,
    Completion,
    Embedding,
    ProviderError,
    RerankResult,
)

__all__ = [
    "CapabilityUnavailable", "Completion", "DEFAULT_CHAT_MODEL", "Embedding",
    "GatewayConfig", "ModelGateway", "ModelPolicyViolation",
    "PERMITTED_CHAT_MODELS", "ProviderError", "RerankResult", "build_provider",
]
