"""LLM gateway: fallback chain with retry, backoff and cooldown (ADR-0005)."""

import logging
import time
from collections.abc import Callable

from pydantic import ValidationError

from app.llm.base import (
    Attempt,
    LLMError,
    LLMProvider,
    LLMResult,
    LLMTask,
    RateLimited,
    TransientError,
    Unavailable,
)
from app.llm.prices import estimate_cost
from app.observability import Observability

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
        tracer: Observability | None = None,
    ):
        self.providers = providers
        self.cooldown_seconds = cooldown_seconds
        self.retries = retries
        self.backoff_seconds = backoff_seconds
        self.clock = clock
        self.sleep = sleep
        self._cooldown_until: dict[str, float] = {}
        self.tracer = tracer or Observability(None)

    def generate(
        self,
        task: LLMTask,
        on_token: Callable[[str], None] | None = None,
        on_reset: Callable[[], None] | None = None,
        on_attempt: Callable[[str, str], None] | None = None,
    ) -> LLMResult:
        """Run the task on the first healthy provider. With streaming, a provider that fails after emitting
        tokens triggers ``on_reset`` so the client discards the partial text before the next provider."""
        attempts: list[Attempt] = []
        streamed = False

        def relay(chunk: str) -> None:
            nonlocal streamed
            streamed = True
            if on_token is not None:
                on_token(chunk)

        for provider in self.providers:
            if not provider.is_configured():
                attempts.append(Attempt(provider.name, "skipped", "not configured"))
                continue
            if self._cooldown_until.get(provider.name, 0.0) > self.clock():
                attempts.append(Attempt(provider.name, "cooldown"))
                continue
            for attempt in range(self.retries + 1):
                if streamed and on_reset is not None:
                    on_reset()
                streamed = False
                if on_attempt is not None:
                    on_attempt(provider.name, provider.model)
                # One generation per attempt: fallbacks and retries are visible in the trace.
                with self.tracer.observation(
                    task.name,
                    as_type="generation",
                    model=provider.model,
                    input=_trace_input(task),
                    version=task.prompt_version or None,
                    metadata={"provider": provider.name, "attempt": attempt + 1},
                ) as generation:
                    try:
                        result = provider.generate(task, relay if on_token is not None else None)
                        self._check_schema(task, result)
                    except (RateLimited, Unavailable) as exc:
                        self._cooldown_until[provider.name] = self.clock() + self.cooldown_seconds
                        outcome = "rate_limited" if isinstance(exc, RateLimited) else "unavailable"
                        attempts.append(Attempt(provider.name, outcome, str(exc)[:200]))
                        generation.update(
                            level="ERROR",
                            status_message=f"{outcome}: {str(exc)[:300]}",
                            metadata={"provider": provider.name, "outcome": outcome},
                        )
                        break
                    except TransientError as exc:
                        generation.update(
                            level="WARNING",
                            status_message=f"transient: {str(exc)[:300]}",
                            metadata={"provider": provider.name, "outcome": "transient"},
                        )
                        if attempt < self.retries:
                            self.sleep(self.backoff_seconds * (2**attempt))
                            continue
                        attempts.append(Attempt(provider.name, "error", str(exc)[:200]))
                        break
                    except (LLMError, ValidationError) as exc:
                        attempts.append(Attempt(provider.name, "error", str(exc)[:200]))
                        generation.update(
                            level="ERROR",
                            status_message=f"error: {str(exc)[:300]}",
                            metadata={"provider": provider.name, "outcome": "error"},
                        )
                        break
                    attempts.append(Attempt(provider.name, "ok"))
                    result.attempts = attempts
                    cost = estimate_cost(result.model, result.input_tokens, result.output_tokens)
                    generation.update(
                        model=result.model,
                        output=_trace_output(result),
                        usage_details={"input": result.input_tokens or 0, "output": result.output_tokens or 0},
                        cost_details=cost,
                        metadata={
                            "provider": result.provider,
                            "outcome": "ok",
                            "fell_back": result.fell_back,
                            "attempts": [f"{a.provider}:{a.outcome}" for a in attempts],
                        },
                    )
                    log.info(
                        "llm.call",
                        extra={
                            "task": task.name,
                            "provider": result.provider,
                            "model": result.model,
                            "latency_ms": result.latency_ms,
                            "input_tokens": result.input_tokens,
                            "output_tokens": result.output_tokens,
                            "cost_usd": cost["total"] if cost else None,
                            "fell_back": result.fell_back,
                            "attempts": [f"{a.provider}:{a.outcome}" for a in attempts],
                        },
                    )
                    return result
            log.warning(
                "llm.provider_failed",
                extra={
                    "task": task.name,
                    "provider": provider.name,
                    "outcome": attempts[-1].outcome if attempts else None,
                },
            )
        if streamed and on_reset is not None:
            on_reset()
        raise AllProvidersFailed(f"no provider could run task {task.name}: {attempts}")

    @staticmethod
    def _check_schema(task: LLMTask, result: LLMResult) -> None:
        if task.output_schema is not None:
            if result.parsed is None:
                raise LLMError("structured output missing")
            task.output_schema.model_validate(result.parsed.model_dump())


def _trace_input(task: LLMTask) -> dict:
    data: dict = {"system": task.system, "user": task.user}
    if task.followups:
        data["followups"] = task.followups
    if task.tools:
        data["tools"] = [t.name for t in task.tools]
    return data


def _trace_output(result: LLMResult) -> object:
    if result.tool_calls:
        return {"tool_calls": [{"name": c.name, "arguments": c.arguments} for c in result.tool_calls]}
    if result.parsed is not None:
        return result.parsed.model_dump(mode="json")
    return result.text
