"""LLM tracing with self-hosted Langfuse (ADR-0010).

- One trace per conversation turn, with user and conversation (as session) attached.
- One generation per provider *attempt*: fallbacks are visible, not hidden behind the final answer.
- Planner, retrieval, tools and guardrail are typed spans of the same trace.
- Best effort: without keys this is a no-op, and a Langfuse failure never breaks a request.

Content (prompts, replies) goes here and not to the operational logs (ADR-0017).
"""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache
from typing import Any

from app.config import get_settings

log = logging.getLogger(__name__)


class _NoopObservation:
    def update(self, **kwargs: Any) -> None:
        pass


NOOP = _NoopObservation()


class Observability:
    def __init__(self, client: Any | None):
        self.client = client

    @property
    def enabled(self) -> bool:
        return self.client is not None

    @contextmanager
    def turn(self, name: str, user_id: str, conversation_id: str, phase: str, version: str) -> Iterator[str | None]:
        """Root of a trace; yields the trace id (stored on the messages of the turn)."""
        if self.client is None:
            yield None
            return
        try:
            from langfuse import propagate_attributes

            observation = self.client.start_as_current_observation(name=name, as_type="agent")
            attributes = propagate_attributes(
                user_id=user_id, session_id=conversation_id, trace_name=name, tags=[phase], version=version
            )
            observation.__enter__()
            attributes.__enter__()
        except Exception:  # pragma: no cover - depends on the Langfuse client
            log.warning("tracing.unavailable", exc_info=True)
            yield None
            return
        try:
            yield self.client.get_current_trace_id()
        finally:
            for manager in (attributes, observation):
                try:
                    manager.__exit__(None, None, None)
                except Exception:  # pragma: no cover
                    log.warning("tracing.close_failed", exc_info=True)

    @contextmanager
    def observation(self, name: str, as_type: str = "span", **fields: Any) -> Iterator[Any]:
        """A child span or generation; yields an object with ``update(...)`` (a no-op when disabled)."""
        if self.client is None:
            yield NOOP
            return
        try:
            manager = self.client.start_as_current_observation(name=name, as_type=as_type, **fields)
            observation = manager.__enter__()
        except Exception:  # pragma: no cover
            log.warning("tracing.unavailable", exc_info=True)
            yield NOOP
            return
        try:
            yield _Safe(observation)
        finally:
            try:
                manager.__exit__(None, None, None)
            except Exception:  # pragma: no cover
                log.warning("tracing.close_failed", exc_info=True)

    def flush(self) -> None:
        if self.client is not None:
            try:
                self.client.flush()
            except Exception:  # pragma: no cover
                log.warning("tracing.flush_failed", exc_info=True)


class _Safe:
    """Wraps an observation so that a failing ``update`` cannot break the request."""

    def __init__(self, observation: Any):
        self._observation = observation

    def update(self, **kwargs: Any) -> None:
        try:
            self._observation.update(**kwargs)
        except Exception:  # pragma: no cover
            log.warning("tracing.update_failed", exc_info=True)


@lru_cache
def get_observability() -> Observability:
    settings = get_settings()
    if not (settings.langfuse_public_key and settings.langfuse_secret_key and settings.langfuse_host):
        return Observability(None)
    try:
        from langfuse import Langfuse

        client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            base_url=settings.langfuse_host,
            environment="local",
        )
        log.info("tracing.enabled", extra={"host": settings.langfuse_host})
        return Observability(client)
    except Exception:  # pragma: no cover
        log.warning("tracing.unavailable", exc_info=True)
        return Observability(None)
