"""Provider for OpenAI-compatible chat completions APIs: Gemini, Groq and LM Studio (ADR-0005).

Written on httpx rather than an SDK to keep full control over the parts the gateway depends on: error
classification (429 -> cooldown, 5xx/timeout -> retry, connection refused -> unavailable), streaming and
structured output.

Structured output is capability-adaptive, because support for ``json_schema`` differs between providers
and even between models of the same provider. The provider tries ``json_schema``, falls back to
``json_object`` and then to prompt-only JSON when the API rejects the format with a 400, and remembers the
mode that works. The reply is always validated with Pydantic; an invalid reply gets one retry with the
validation error fed back to the model.
"""

import json
import logging
import re
import time
from collections.abc import Callable

import httpx
from pydantic import BaseModel, ValidationError

from app.llm.base import LLMError, LLMResult, LLMTask, RateLimited, ToolCall, TransientError, Unavailable

log = logging.getLogger(__name__)

STRUCTURED_MODES = ("json_schema", "json_object", "prompt")
_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class OpenAICompatibleProvider:
    def __init__(
        self,
        name: str,
        base_url: str | None,
        api_key: str | None,
        model: str | None,
        timeout_seconds: float = 30.0,
        requires_key: bool = True,
        transport: httpx.BaseTransport | None = None,
        reasoning_effort: str | None = None,
    ):
        self.name = name
        self.base_url = (base_url or "").rstrip("/")
        self.api_key = api_key
        self._model = model
        self.requires_key = requires_key
        self.mode_index = 0  # index into STRUCTURED_MODES, lowered when the API rejects a format
        self.stream_usage = True  # some APIs reject stream_options
        self.reasoning_effort = reasoning_effort  # thinking models are slow: "low" keeps latency down
        self.served_model: str | None = None  # what the API reports: aliases like "-latest" resolve here
        self.client = httpx.Client(timeout=timeout_seconds, transport=transport)

    # --- Configuration ----------------------------------------------------------------

    @property
    def model(self) -> str:
        return self._model or "auto"

    def is_configured(self) -> bool:
        return bool(self.base_url) and (bool(self.api_key) or not self.requires_key)

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}

    def _resolve_model(self) -> str:
        """LM Studio serves whatever model is loaded: discover it when none is configured."""
        if self._model:
            return self._model
        data = self._request("GET", "/models").json()
        models = [m["id"] for m in data.get("data", [])]
        if not models:
            raise Unavailable(f"{self.name}: no model loaded")
        self._model = models[0]
        return self._model

    # --- HTTP and error classification -------------------------------------------------

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = self.client.request(method, self.base_url + path, headers=self._headers(), **kwargs)
        except httpx.ConnectError as exc:
            raise Unavailable(f"{self.name}: unreachable") from exc
        except httpx.TimeoutException as exc:
            raise TransientError(f"{self.name}: timeout") from exc
        except httpx.HTTPError as exc:
            raise TransientError(f"{self.name}: {type(exc).__name__}") from exc
        self._raise_for_status(response)
        return response

    def _raise_for_status(self, response: httpx.Response) -> None:
        if response.status_code < 400:
            return
        detail = response.text[:300]
        if response.status_code == 429:
            raise RateLimited(f"{self.name}: 429 {detail}")
        if response.status_code >= 500:
            raise TransientError(f"{self.name}: {response.status_code} {detail}")
        if response.status_code in (401, 403):
            raise Unavailable(f"{self.name}: {response.status_code} invalid credentials")
        if response.status_code == 404:  # unknown or retired model: a configuration error, not a format issue
            raise Unavailable(f"{self.name}: 404 {detail}")
        raise _BadRequest(response.status_code, detail)

    # --- Generation --------------------------------------------------------------------

    def generate(self, task: LLMTask, on_token: Callable[[str], None] | None = None) -> LLMResult:
        model = self._resolve_model()
        self.served_model = None
        started = time.perf_counter()
        tool_calls: list[ToolCall] = []
        if task.tools:
            text, tool_calls, usage = self._with_tools(task, model)
            parsed = None
        elif task.output_schema is not None:
            text, parsed, usage = self._structured(task, model)
        else:
            text, usage = self._text(task, model, on_token)
            parsed = None
        return LLMResult(
            text=text,
            parsed=parsed,
            provider=self.name,
            model=(self.served_model or model).removeprefix("models/"),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            latency_ms=round((time.perf_counter() - started) * 1000),
            tool_calls=tool_calls,
        )

    def _messages(self, task: LLMTask, extra_system: str = "") -> list[dict]:
        return [
            {"role": "system", "content": task.system + extra_system},
            {"role": "user", "content": task.user},
            *(self._followup(m) for m in task.followups),
        ]

    def _followup(self, message: dict) -> dict:
        """Tool-call turns carry provider-specific fields (Gemini 3 rejects a function call without its
        thought_signature). They go back only to the provider that produced them."""
        if message.get("role") != "assistant" or "tool_calls" not in message:
            return message
        calls = []
        for call in message["tool_calls"]:
            base = {k: v for k, v in call.items() if not k.startswith("_")}
            calls.append({**base, **(call.get("_extra") or {})} if call.get("_provider") == self.name else base)
        return {**message, "tool_calls": calls}

    def _with_tools(self, task: LLMTask, model: str) -> tuple[str, list[ToolCall], dict]:
        """Native function calling: the model either calls tools or answers in text."""
        assert task.tools
        body: dict = {
            "model": model,
            "messages": self._messages(task),
            "temperature": 0,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters.model_json_schema(),
                    },
                }
                for t in task.tools
            ],
            "tool_choice": "auto",
            **self._reasoning(),
        }
        try:
            data = self._request("POST", "/chat/completions", json=body).json()
        except _BadRequest as exc:
            if not self._drop_reasoning(exc, body):
                raise LLMError(f"{self.name}: tools rejected: {exc.detail}") from exc  # next provider
            data = self._request("POST", "/chat/completions", json=body).json()
        self.served_model = data.get("model") or self.served_model
        try:
            message = data["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("malformed completion response") from exc
        calls = []
        for raw in message.get("tool_calls") or []:
            function = raw.get("function") or {}
            try:
                arguments = json.loads(function.get("arguments") or "{}")
            except json.JSONDecodeError as exc:
                raise LLMError(f"{self.name}: tool arguments are not JSON") from exc
            calls.append(
                ToolCall(
                    id=raw.get("id") or function.get("name", "call"),
                    name=function.get("name", ""),
                    arguments=arguments if isinstance(arguments, dict) else {},
                    provider=self.name,
                    extra={k: v for k, v in raw.items() if k not in ("id", "type", "function")},
                )
            )
        text = (message.get("content") or "").strip()
        if not calls and not text:
            raise LLMError(f"{self.name}: empty response")
        return text, calls, data.get("usage") or {}

    def _structured(self, task: LLMTask, model: str) -> tuple[str, BaseModel, dict]:
        schema_model = task.output_schema
        assert schema_model is not None
        schema = schema_model.model_json_schema()
        messages = self._messages(task)
        last_error = ""
        for attempt in range(2):  # one retry with the validation error fed back
            body: dict = {"model": model, "messages": messages, "temperature": 0, **self._reasoning()}
            content, usage = self._complete_with_format(body, schema_model.__name__, schema)
            try:
                return content, schema_model.model_validate_json(_FENCE.sub("", content).strip()), usage
            except ValidationError as exc:
                last_error = str(exc)[:500]
                log.warning("llm.invalid_structured_output", extra={"provider": self.name, "attempt": attempt + 1})
                messages = [
                    *messages,
                    {"role": "assistant", "content": content},
                    {
                        "role": "user",
                        "content": f"Il JSON non è valido: {last_error}. Correggilo e rispondi solo con il JSON.",
                    },
                ]
        raise LLMError(f"{self.name}: invalid structured output: {last_error}")

    def _complete_with_format(self, body: dict, schema_name: str, schema: dict) -> tuple[str, dict]:
        while True:
            mode = STRUCTURED_MODES[self.mode_index]
            request = dict(body)
            if mode != "json_schema":
                # Without native schema enforcement the schema must travel in the prompt (more tokens).
                hint = f"\nRispondi SOLO con un oggetto JSON valido conforme a questo schema: {json.dumps(schema)}"
                system, *rest = request["messages"]
                request["messages"] = [{**system, "content": system["content"] + hint}, *rest]
            if mode == "json_schema":
                request["response_format"] = {
                    "type": "json_schema",
                    "json_schema": {"name": schema_name, "schema": schema, "strict": False},
                }
            elif mode == "json_object":
                request["response_format"] = {"type": "json_object"}
            try:
                data = self._request("POST", "/chat/completions", json=request).json()
                self.served_model = data.get("model") or self.served_model
                return _content(data), data.get("usage") or {}
            except _BadRequest as exc:
                if self._drop_reasoning(exc, body):
                    continue
                if mode == "prompt":
                    raise LLMError(f"{self.name}: 400 {exc.detail}") from exc
                self.mode_index += 1  # remember the downgrade for the next calls
                log.warning(
                    "llm.structured_mode_downgraded",
                    extra={"provider": self.name, "from_mode": mode, "to_mode": STRUCTURED_MODES[self.mode_index]},
                )

    def _text(self, task: LLMTask, model: str, on_token: Callable[[str], None] | None) -> tuple[str, dict]:
        body: dict = {"model": model, "messages": self._messages(task), "temperature": 0.4, **self._reasoning()}
        if on_token is None:
            try:
                data = self._request("POST", "/chat/completions", json=body).json()
            except _BadRequest as exc:
                if not self._drop_reasoning(exc, body):
                    raise LLMError(f"{self.name}: 400 {exc.detail}") from exc
                data = self._request("POST", "/chat/completions", json=body).json()
            self.served_model = data.get("model") or self.served_model
            return _content(data), data.get("usage") or {}
        return self._stream(body, on_token)

    def _reasoning(self) -> dict:
        return {"reasoning_effort": self.reasoning_effort} if self.reasoning_effort else {}

    def _drop_reasoning(self, exc: "_BadRequest", body: dict) -> bool:
        """The API rejected ``reasoning_effort``: stop sending it (remembered) and let the caller retry."""
        if "reasoning_effort" in body and "reason" in exc.detail.lower():
            body.pop("reasoning_effort")
            self.reasoning_effort = None
            log.warning("llm.reasoning_effort_unsupported", extra={"provider": self.name})
            return True
        return False

    def _stream(self, body: dict, on_token: Callable[[str], None]) -> tuple[str, dict]:
        request = {**body, "stream": True}
        if self.stream_usage:
            request["stream_options"] = {"include_usage": True}
        parts: list[str] = []
        usage: dict = {}
        try:
            with self.client.stream(
                "POST", self.base_url + "/chat/completions", headers=self._headers(), json=request
            ) as response:
                if response.status_code >= 400:
                    response.read()
                    self._raise_for_status(response)
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    chunk = json.loads(payload)
                    self.served_model = chunk.get("model") or self.served_model
                    usage = chunk.get("usage") or (chunk.get("x_groq") or {}).get("usage") or usage
                    for choice in chunk.get("choices") or []:
                        delta = (choice.get("delta") or {}).get("content")
                        if delta:
                            parts.append(delta)
                            on_token(delta)
        except _BadRequest as exc:
            if not parts and self._drop_reasoning(exc, body):
                return self._stream(body, on_token)
            if self.stream_usage and not parts:
                self.stream_usage = False  # retry once without stream_options
                return self._stream(body, on_token)
            raise LLMError(f"{self.name}: 400 {exc.detail}") from exc
        except httpx.ConnectError as exc:
            raise Unavailable(f"{self.name}: unreachable") from exc
        except httpx.TimeoutException as exc:
            raise TransientError(f"{self.name}: timeout") from exc
        except (httpx.HTTPError, json.JSONDecodeError) as exc:
            raise TransientError(f"{self.name}: stream interrupted ({type(exc).__name__})") from exc
        text = "".join(parts).strip()
        if not text:
            raise LLMError(f"{self.name}: empty response")
        return text, usage


class _BadRequest(LLMError):
    def __init__(self, status: int, detail: str):
        super().__init__(f"{status} {detail}")
        self.status = status
        self.detail = detail


def _content(data: dict) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMError("malformed completion response") from exc
    if not content:
        raise LLMError("empty response")
    return content.strip()
