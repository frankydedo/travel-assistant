import pytest
from pydantic import BaseModel

from app.llm.base import LLMError, LLMResult, LLMTask, RateLimited, TransientError
from app.llm.gateway import AllProvidersFailed, Gateway
from app.llm.mock import MockProvider


class Out(BaseModel):
    value: int


class Fake:
    def __init__(self, name, behaviour, configured=True):
        self.name, self.model, self.behaviour, self.configured, self.calls = name, "fake", behaviour, configured, 0

    def is_configured(self):
        return self.configured

    def generate(self, task, on_token=None):
        self.calls += 1
        outcome = self.behaviour[min(self.calls, len(self.behaviour)) - 1]
        if isinstance(outcome, Exception):
            raise outcome
        return LLMResult(text="ok", parsed=outcome, provider=self.name, model="fake")


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


TASK = LLMTask(name="t", system="", user="", output_schema=Out)


def gateway(*providers, clock=None):
    return Gateway(list(providers), cooldown_seconds=60, retries=1, clock=clock or Clock(), sleep=lambda s: None)


def test_first_healthy_provider_answers():
    result = gateway(Fake("GEMINI", [Out(value=1)]), Fake("GROQ", [Out(value=2)])).generate(TASK)
    assert result.provider == "GEMINI" and not result.fell_back


def test_rate_limited_provider_goes_into_cooldown():
    clock = Clock()
    gemini, groq = Fake("GEMINI", [RateLimited("429")]), Fake("GROQ", [Out(value=2)])
    gw = gateway(gemini, groq, clock=clock)
    first = gw.generate(TASK)
    assert first.provider == "GROQ" and first.fell_back
    gw.generate(TASK)
    assert gemini.calls == 1  # skipped while cooling down
    clock.now = 61
    gw.generate(TASK)
    assert gemini.calls == 2


def test_transient_errors_are_retried_then_fall_back():
    flaky = Fake("GEMINI", [TransientError("timeout"), Out(value=1)])
    assert gateway(flaky).generate(TASK).provider == "GEMINI" and flaky.calls == 2
    broken = Fake("GEMINI", [TransientError("timeout")])
    assert gateway(broken, Fake("GROQ", [Out(value=2)])).generate(TASK).provider == "GROQ"
    assert broken.calls == 2


def test_missing_structured_output_falls_back_and_unconfigured_are_skipped():
    no_json = Fake("GEMINI", [None])
    skipped = Fake("GROQ", [Out(value=1)], configured=False)
    result = gateway(no_json, skipped, Fake("LMSTUDIO", [Out(value=3)])).generate(TASK)
    assert result.provider == "LMSTUDIO" and skipped.calls == 0
    assert [a.outcome for a in result.attempts] == ["error", "skipped", "ok"]


def test_all_failing_raises():
    with pytest.raises(AllProvidersFailed):
        gateway(Fake("GEMINI", [LLMError("boom")])).generate(TASK)


def test_mock_always_answers_as_last_link():
    task = LLMTask(
        name="extract_requirements", system="", user="", context={"message": "budget 900 euro", "missing": []}
    )
    result = gateway(Fake("GEMINI", [RateLimited("quota")]), MockProvider()).generate(task)
    assert result.provider == "MOCK" and result.parsed.requirements.budget_total == 900
