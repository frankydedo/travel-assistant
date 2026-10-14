"""LLM gateway: fallback chain with retry, backoff and cooldown (ADR-0005)."""

import logging
import time
from collections.abc import Callable

from pydantic import ValidationError

from app.llm.base import Attempt, LLMError, LLMProvider, LLMResult, LLMTask, RateLimited, TransientError

log = logging.getLogger(__name__)


class AllProvidersFailed(LLMError):
    pass


class Gateway:
    def __init__(
        self,
        providers: list[LLMProvider],
        cooldown_seconds: float = 60.0,
        retries: int = 1,
        backoff_seconds: float = 0.5,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.providers = providers
        self.cooldown_seconds = cooldown_seconds
        self.retries = retries
        self.backoff_seconds = backoff_seconds
        self.clock = clock
        self.sleep = sleep
        self._cooldown_until: dict[str, float] = {}

    def generate(self, task: LLMTask) -> LLMResult:
        attempts: list[Attempt] = []
        for provider in self.providers:
            if not provider.is_configured():
                attempts.append(Attempt(provider.name, "skipped", "not configured"))
                continue
            if self._cooldown_until.get(provider.name, 0.0) > self.clock():
                attempts.append(Attempt(provider.name, "cooldown"))
                continue
            for attempt in range(self.retries + 1):
                try:
                    result = provider.generate(task)
                    self._check_schema(task, result)
                    attempts.append(Attempt(provider.name, "ok"))
                    result.attempts = attempts
                    log.info(
                        "llm.call",
                        extra={
                            "task": task.name,
                            "provider": result.provider,
                            "model": result.model,
                            "latency_ms": result.latency_ms,
                            "input_tokens": result.input_tokens,
                            "output_tokens": result.output_tokens,
                            "fell_back": result.fell_back,
                            "attempts": [f"{a.provider}:{a.outcome}" for a in attempts],
                        },
                    )
                    return result
                except RateLimited as exc:
                    self._cooldown_until[provider.name] = self.clock() + self.cooldown_seconds
                    attempts.append(Attempt(provider.name, "rate_limited", str(exc)[:200]))
                    break
                except TransientError as exc:
                    if attempt < self.retries:
                        self.sleep(self.backoff_seconds * (2**attempt))
                        continue
                    attempts.append(Attempt(provider.name, "error", str(exc)[:200]))
                except (LLMError, ValidationError) as exc:
                    attempts.append(Attempt(provider.name, "error", str(exc)[:200]))
                    break
            log.warning(
                "llm.provider_failed",
                extra={
                    "task": task.name,
                    "provider": provider.name,
                    "outcome": attempts[-1].outcome if attempts else None,
                },
            )
        raise AllProvidersFailed(f"no provider could run task {task.name}: {attempts}")

    @staticmethod
    def _check_schema(task: LLMTask, result: LLMResult) -> None:
        if task.output_schema is not None:
            if result.parsed is None:
                raise LLMError("structured output missing")
            task.output_schema.model_validate(result.parsed.model_dump())
