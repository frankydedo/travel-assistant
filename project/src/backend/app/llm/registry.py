"""Builds the fallback chain from configuration (ADR-0005)."""

import logging

from app.config import Settings
from app.llm.base import LLMProvider
from app.llm.gateway import Gateway
from app.llm.mock import MockProvider

log = logging.getLogger(__name__)


def build_providers(settings: Settings) -> list[LLMProvider]:
    factories = {"mock": MockProvider}
    providers: list[LLMProvider] = []
    for name in (n.strip().lower() for n in settings.llm_chain.split(",") if n.strip()):
        factory = factories.get(name)
        if factory is None:
            log.info("LLM provider %r not available yet, skipped", name)
            continue
        providers.append(factory())
    if not any(isinstance(p, MockProvider) for p in providers):
        providers.append(MockProvider())  # the chain always ends with the deterministic safety net
    return providers


def build_gateway(settings: Settings) -> Gateway:
    return Gateway(build_providers(settings))
