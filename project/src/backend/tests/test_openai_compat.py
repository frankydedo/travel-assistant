"""OpenAI-compatible provider against a simulated API (httpx.MockTransport): no network, no keys."""

import json

import httpx
import pytest
from pydantic import BaseModel

from app.llm.base import LLMError, LLMTask, RateLimited, TransientError, Unavailable
from app.llm.openai_compat import OpenAICompatibleProvider


class Answer(BaseModel):
    value: int


STRUCTURED = LLMTask(name="t", system="sys", user="user", output_schema=Answer)
TEXT = LLMTask(name="reply:x", system="sys", user="user")


def completion(content: str, usage: dict | None = None) -> httpx.Response:
    body = {
        "choices": [{"message": {"content": content}}],
        "usage": usage or {"prompt_tokens": 10, "completion_tokens": 3},
    }
    return httpx.Response(200, json=body)


def provider(handler, model: str = "m", key: str | None = "k"):
    return OpenAICompatibleProvider("GROQ", "https://api.test/v1", key, model, transport=httpx.MockTransport(handler))


def test_structured_output_with_json_schema_and_usage():
    seen = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body["response_format"]["type"])
        assert request.headers["Authorization"] == "Bearer k"
        return completion('{"value": 7}')

    result = provider(handler).generate(STRUCTURED)
    assert result.parsed == Answer(value=7) and seen == ["json_schema"]
    assert (result.input_tokens, result.output_tokens, result.provider) == (10, 3, "GROQ")


def test_rejected_format_is_downgraded_and_remembered():
    seen = []

    def handler(request):
        fmt = json.loads(request.content).get("response_format", {}).get("type", "prompt")
        seen.append(fmt)
        if fmt == "json_schema":
            return httpx.Response(400, json={"error": "This model does not support response format `json_schema`"})
        system = json.loads(request.content)["messages"][0]["content"]
        assert "schema" in system  # without native enforcement the schema travels in the prompt
        return completion('```json\n{"value": 1}\n```')  # fenced JSON is accepted too

    p = provider(handler)
    assert p.generate(STRUCTURED).parsed == Answer(value=1)
    assert p.generate(STRUCTURED).parsed == Answer(value=1)
    assert seen == ["json_schema", "json_object", "json_object"]  # the downgrade sticks


def test_invalid_json_gets_one_retry_with_feedback_then_fails():
    replies = iter(['{"value": "not a number"}', '{"value": 3}'])

    def handler(request):
        return completion(next(replies))

    assert provider(handler).generate(STRUCTURED).parsed == Answer(value=3)

    with pytest.raises(LLMError):
        provider(lambda request: completion("non è JSON")).generate(STRUCTURED)


@pytest.mark.parametrize(
    ("response", "error"),
    [
        (httpx.Response(429, text="quota"), RateLimited),
        (httpx.Response(503, text="overloaded"), TransientError),
        (httpx.Response(401, text="bad key"), Unavailable),
        (httpx.Response(404, text="model is no longer available"), Unavailable),
    ],
)
def test_http_errors_are_classified(response, error):
    with pytest.raises(error):
        provider(lambda request: response).generate(TEXT)


def test_connection_refused_means_unavailable():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(Unavailable):
        provider(handler).generate(TEXT)


def test_streaming_text_and_usage():
    chunks = [
        {"choices": [{"delta": {"content": "Ciao "}}]},
        {"choices": [{"delta": {"content": "viaggiatore"}}]},
        {"choices": [], "usage": {"prompt_tokens": 5, "completion_tokens": 2}},
    ]
    sse = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"

    def handler(request):
        assert json.loads(request.content)["stream"] is True
        return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})

    tokens = []
    result = provider(handler).generate(TEXT, on_token=tokens.append)
    assert tokens == ["Ciao ", "viaggiatore"] and result.text == "Ciao viaggiatore"
    assert result.output_tokens == 2


def test_providers_without_a_key_are_not_configured():
    assert provider(lambda request: completion("ok")).is_configured()
    assert not provider(lambda request: completion("ok"), key=None).is_configured()  # skipped by the gateway


def test_tool_history_from_another_provider_is_replayed_as_text():
    """A fallback in the middle of a tool loop: Gemini 3 rejects function calls without its own
    thought_signature, so calls made by Groq reach Gemini as plain text, while Groq gets them natively."""
    followups = [
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {"name": "search_activities", "arguments": '{"request": "terme"}'},
                    "_provider": "GROQ",
                    "_extra": {},
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": '{"attività": ["Terme Segestane"]}'},
    ]
    task = LLMTask(name="proposal_tools", system="sys", user="user", followups=followups)
    gemini = OpenAICompatibleProvider("GEMINI", "https://api.test/v1", "k", "m")
    replayed = gemini._messages(task)[2:]
    assert all("tool_calls" not in m and m["role"] != "tool" for m in replayed)
    assert "search_activities" in replayed[0]["content"] and "Terme Segestane" in replayed[1]["content"]
    groq = OpenAICompatibleProvider("GROQ", "https://api.test/v1", "k", "m")
    native = groq._messages(task)[2:]
    assert native[0]["tool_calls"][0]["id"] == "c1" and native[1]["role"] == "tool"
