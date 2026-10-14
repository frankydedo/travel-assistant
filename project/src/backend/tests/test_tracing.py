"""Tracing page metrics against a simulated Langfuse v4 API (httpx.MockTransport)."""

import json

import httpx

from app.config import Settings
from app.services.tracing_metrics import LangfuseMetrics

SETTINGS = Settings(
    langfuse_host="http://langfuse:3000",
    langfuse_public_key="pk",
    langfuse_secret_key="sk",
    langfuse_ui_url="http://localhost:3001",
    langfuse_project_id="travel-assistant",
)


def fake_langfuse(seen: list):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/v2/observations"):
            seen.append(("observations", dict(request.url.params)))
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"name": "chat_turn", "traceId": "t1", "startTime": "x", "latency": 1.5, "level": "DEFAULT"}
                    ]
                },
            )
        query = json.loads(request.url.params["query"])
        seen.append(("metrics", query))
        dims = [d["field"] for d in query["dimensions"]]
        if dims == ["providedModelName", "level"]:
            data = [
                {
                    "providedModelName": "openai/gpt-oss-120b",
                    "level": "DEFAULT",
                    "count_count": 8,
                    "sum_totalCost": 0.002,
                    "sum_inputTokens": 9000,
                    "sum_outputTokens": 900,
                    "avg_latency": 900,
                    "p95_latency": 1500,
                },
                {
                    "providedModelName": "openai/gpt-oss-120b",
                    "level": "ERROR",
                    "count_count": 2,
                    "sum_totalCost": 0,
                    "sum_inputTokens": 0,
                    "sum_outputTokens": 0,
                    "avg_latency": 300,
                    "p95_latency": 400,
                },
                {
                    "providedModelName": "gemini-flash-lite-latest",
                    "level": "DEFAULT",
                    "count_count": 2,
                    "sum_totalCost": 0.001,
                    "sum_inputTokens": 2000,
                    "sum_outputTokens": 200,
                    "avg_latency": 4000,
                    "p95_latency": 5000,
                },
            ]
        elif dims == ["name"] and any(f["value"] == "AGENT" for f in query["filters"]):
            data = [{"name": "chat_turn", "count_count": 4, "avg_latency": 2500, "p95_latency": 6000}]
        elif dims == ["name"]:
            data = [{"name": "extract_requirements", "count_count": 4, "sum_totalCost": 0.001, "avg_latency": 800}]
        else:
            data = [{"time_dimension": "2026-01-01", "sum_totalCost": 0.003, "count_count": 12}]
        return httpx.Response(200, json={"data": data})

    return httpx.MockTransport(handler)


def test_summary_aggregates_per_model_and_filters_on_the_user():
    seen: list = []
    summary = LangfuseMetrics(SETTINGS, transport=fake_langfuse(seen)).summary("user-1", "7d")
    assert summary["available"] is True
    totals = summary["totals"]
    assert totals["llm_calls"] == 12 and totals["failed_attempts"] == 2 and totals["turns"] == 4
    assert totals["cost_usd"] == 0.003 and totals["avg_turn_latency_ms"] == 2500
    groq = next(r for r in summary["by_model"] if r["provider"] == "GROQ")
    assert groq["calls"] == 10 and groq["failed"] == 2 and groq["avg_latency_ms"] == 780
    assert next(r for r in summary["by_model"] if r["provider"] == "GEMINI")["p95_latency_ms"] == 5000
    assert summary["recent_turns"][0]["trace_url"] == "http://localhost:3001/project/travel-assistant/traces/t1"
    # Every query is restricted to the current user: nobody sees somebody else's traces.
    for kind, query in seen:
        if kind == "metrics":
            assert {"column": "userId", "operator": "=", "value": "user-1", "type": "string"} in query["filters"]
        else:
            assert query["userId"] == "user-1"


def test_unreachable_or_unconfigured_langfuse_degrades_gracefully():
    def down(request):
        raise httpx.ConnectError("refused")

    assert LangfuseMetrics(SETTINGS, transport=httpx.MockTransport(down)).summary("u", "24h")["available"] is False
    assert LangfuseMetrics(Settings(langfuse_host=None)).summary("u", "24h")["available"] is False


def test_tracing_endpoint_without_langfuse(client):
    response = client.get("/api/tracing/summary?period=7d")
    assert response.status_code == 200 and response.json()["available"] is False
    assert client.get("/api/tracing/summary?period=1y").status_code == 422
