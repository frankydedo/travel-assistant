"""Builds the fallback chain from configuration (ADR-0005)."""

import logging

from app.config import Settings
from app.llm.base import LLMProvider
from app.llm.gateway import Gateway
from app.llm.mock import MockProvider
from app.llm.openai_compat import OpenAICompatibleProvider

log = logging.getLogger(__name__)

# Only these produce generative-AI text: MOCK is deterministic rules, SYSTEM is code.
AI_PROVIDERS = frozenset({"GEMINI", "GROQ"})


def build_providers(settings: Settings) -> list[LLMProvider]:
    timeout = settings.llm_timeout_seconds
    factories = {
        "gemini": lambda: OpenAICompatibleProvider(
            "GEMINI",
            settings.gemini_base_url,
            settings.gemini_api_key,
            settings.gemini_model,
            timeout,
            reasoning_effort=settings.gemini_reasoning_effort,
        ),
        "groq": lambda: OpenAICompatibleProvider(
            "GROQ",
            settings.groq_base_url,
            settings.groq_api_key,
            settings.groq_model,
            timeout,
            reasoning_effort=settings.groq_reasoning_effort,
        ),
        "mock": lambda: MockProvider(settings.mock_stream_delay_ms),
    }
    providers: list[LLMProvider] = []
    for name in (n.strip().lower() for n in settings.llm_chain.split(",") if n.strip()):
        factory = factories.get(name)
        if factory is None:
            log.warning("llm.unknown_provider", extra={"provider": name})
            continue
        providers.append(factory())
    if not any(isinstance(p, MockProvider) for p in providers):
        providers.append(MockProvider(settings.mock_stream_delay_ms))  # the deterministic safety net
    configured = [p.name for p in providers if p.is_configured()]
    log.info("llm.chain", extra={"chain": [p.name for p in providers], "configured": configured})
    return providers


def build_gateway(settings: Settings) -> Gateway:
    return Gateway(build_providers(settings), cooldown_seconds=settings.llm_cooldown_seconds)
