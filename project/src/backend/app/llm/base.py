"""Provider-agnostic LLM abstraction (ADR-0005).

The unit of work is a *task*, not a raw prompt: a task carries the prompt for real LLMs and the
structured context the deterministic mock needs. This lets the rule-based mock sit in the same fallback
chain as the real providers.
"""

from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel


class LLMError(Exception):
    """A provider failed; the gateway moves on to the next one."""


class RateLimited(LLMError):
    """429 or exhausted quota: the provider goes into cooldown."""


class TransientError(LLMError):
    """Timeout or 5xx: worth a retry with backoff."""


@dataclass
class LLMTask:
    name: str
    system: str
    user: str
    output_schema: type[BaseModel] | None = None
    context: dict = field(default_factory=dict)  # structured inputs for the rule-based mock
    prompt_version: str = ""


@dataclass
class Attempt:
    provider: str
    outcome: str  # ok | skipped | cooldown | rate_limited | error
    detail: str = ""


@dataclass
class LLMResult:
    text: str
    parsed: BaseModel | None
    provider: str  # GEMINI | GROQ | LMSTUDIO | MOCK
    model: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    latency_ms: int = 0
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def fell_back(self) -> bool:
        return any(a.outcome not in ("ok", "skipped") for a in self.attempts)


class LLMProvider(Protocol):
    name: str
    model: str

    def is_configured(self) -> bool: ...

    def generate(self, task: LLMTask) -> LLMResult: ...
