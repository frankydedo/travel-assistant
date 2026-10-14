"""Metrics for the UI Tracing page, read from Langfuse through the backend (ADR-0010).

The Langfuse keys never reach the browser, and every query is filtered on the current user: nobody sees
somebody else's traces. Langfuse v4 serves aggregates through the Metrics API v2 and single observations
through the Observations API v2. If Langfuse is unreachable the page shows "non disponibile" instead of
failing.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

import httpx

from app.config import Settings

log = logging.getLogger(__name__)

PERIODS = {"24h": timedelta(hours=24), "7d": timedelta(days=7), "30d": timedelta(days=30)}


def provider_of(model: str | None) -> str:
    if not model:
        return "—"
    if model.startswith("gemini"):
        return "GEMINI"
    if model == "rules-v1":
        return "MOCK"
    return "GROQ"


class LangfuseMetrics:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self.client = httpx.Client(
            base_url=(settings.langfuse_host or "").rstrip("/") + "/api/public",
            auth=(settings.langfuse_public_key or "", settings.langfuse_secret_key or ""),
            timeout=8.0,
            transport=transport,
        )

    @property
    def configured(self) -> bool:
        s = self.settings
        return bool(s.langfuse_host and s.langfuse_public_key and s.langfuse_secret_key)

    def trace_url(self, trace_id: str | None) -> str | None:
        if not trace_id or not self.configured:
            return None
        return (
            f"{self.settings.langfuse_ui_url.rstrip('/')}/project/{self.settings.langfuse_project_id}/traces/{trace_id}"
        )

    def summary(self, user_id: str, period: str) -> dict:
        if not self.configured:
            return {"available": False, "reason": "Langfuse non configurato"}
        now = datetime.now(UTC)
        start = now - PERIODS[period]
        window = {"fromTimestamp": _iso(start), "toTimestamp": _iso(now)}
        user = {"column": "userId", "operator": "=", "value": user_id, "type": "string"}
        generations = {"column": "type", "operator": "=", "value": "GENERATION", "type": "string"}
        try:
            by_model = self._metrics(
                window,
                [user, generations],
                [{"field": "providedModelName"}, {"field": "level"}],
                [
                    ("count", "count"),
                    ("totalCost", "sum"),
                    ("inputTokens", "sum"),
                    ("outputTokens", "sum"),
                    ("latency", "avg"),
                    ("latency", "p95"),
                ],
            )
            by_task = self._metrics(
                window,
                [user, generations],
                [{"field": "name"}],
                [("count", "count"), ("totalCost", "sum"), ("latency", "avg")],
            )
            turns = self._metrics(
                window,
                [user, {"column": "type", "operator": "=", "value": "AGENT", "type": "string"}],
                [{"field": "name"}],
                [("count", "count"), ("latency", "avg"), ("latency", "p95")],
            )
            daily = self._metrics(
                window,
                [user, generations],
                [],
                [("totalCost", "sum"), ("count", "count")],
                time_dimension={"granularity": "hour" if period == "24h" else "day"},
            )
            recent = self.client.get(
                "/v2/observations",
                params={"userId": user_id, "type": "AGENT", "limit": 10, "fromStartTime": _iso(start)},
            )
            recent.raise_for_status()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("tracing.metrics_unavailable", extra={"reason": type(exc).__name__})
            return {"available": False, "reason": "Langfuse non raggiungibile"}
        return _shape(period, by_model, by_task, turns, daily, recent.json().get("data", []), self.trace_url)

    def _metrics(self, window, filters, dimensions, metrics, time_dimension=None) -> list[dict]:
        query = {
            "view": "observations",
            "metrics": [{"measure": m, "aggregation": a} for m, a in metrics],
            "dimensions": dimensions,
            "filters": filters,
            **window,
        }
        if time_dimension:
            query["timeDimension"] = time_dimension
        response = self.client.get("/v2/metrics", params={"query": json.dumps(query)})
        response.raise_for_status()
        return response.json().get("data", [])


def _iso(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _num(value) -> float:
    return float(value) if value is not None else 0.0


def _shape(period, by_model, by_task, turns, daily, recent, trace_url) -> dict:
    models: dict[str, dict] = {}
    for row in by_model:
        model = row.get("providedModelName") or "—"
        entry = models.setdefault(
            model,
            {
                "provider": provider_of(row.get("providedModelName")),
                "model": model,
                "calls": 0,
                "failed": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_usd": 0.0,
                "latency_weighted": 0.0,
                "p95_latency_ms": 0.0,
            },
        )
        count = int(_num(row.get("count_count")))
        entry["calls"] += count
        if row.get("level") in ("WARNING", "ERROR"):
            entry["failed"] += count  # failed attempts: the chain fell back or retried
        entry["input_tokens"] += int(_num(row.get("sum_inputTokens")))
        entry["output_tokens"] += int(_num(row.get("sum_outputTokens")))
        entry["cost_usd"] += _num(row.get("sum_totalCost"))
        entry["latency_weighted"] += _num(row.get("avg_latency")) * count
        entry["p95_latency_ms"] = max(entry["p95_latency_ms"], _num(row.get("p95_latency")))
    model_rows = []
    for entry in models.values():
        calls = entry.pop("calls")
        weighted = entry.pop("latency_weighted")
        model_rows.append(
            {
                **entry,
                "calls": calls,
                "avg_latency_ms": round(weighted / calls) if calls else 0,
                "p95_latency_ms": round(entry["p95_latency_ms"]),
                "cost_usd": round(entry["cost_usd"], 6),
            }
        )
    model_rows.sort(key=lambda r: -r["calls"])

    calls = sum(r["calls"] for r in model_rows)
    failed = sum(r["failed"] for r in model_rows)
    turn_count = sum(int(_num(r.get("count_count"))) for r in turns)
    turn_latency = sum(_num(r.get("avg_latency")) * _num(r.get("count_count")) for r in turns)
    totals = {
        "turns": turn_count,
        "llm_calls": calls,
        "failed_attempts": failed,
        "failure_rate": round(failed / calls, 4) if calls else 0.0,
        "input_tokens": sum(r["input_tokens"] for r in model_rows),
        "output_tokens": sum(r["output_tokens"] for r in model_rows),
        "cost_usd": round(sum(r["cost_usd"] for r in model_rows), 6),
        "avg_turn_latency_ms": round(turn_latency / turn_count) if turn_count else 0,
        "p95_turn_latency_ms": round(max((_num(r.get("p95_latency")) for r in turns), default=0)),
    }
    return {
        "available": True,
        "period": period,
        "note": (
            "Costi stimati a listino (i free tier non costano nulla). I dati arrivano con qualche secondo di ritardo."
        ),
        "totals": totals,
        "by_model": model_rows,
        "by_task": sorted(
            (
                {
                    "task": r.get("name"),
                    "calls": int(_num(r.get("count_count"))),
                    "cost_usd": round(_num(r.get("sum_totalCost")), 6),
                    "avg_latency_ms": round(_num(r.get("avg_latency"))),
                }
                for r in by_task
            ),
            key=lambda r: -r["calls"],
        ),
        "series": [
            {
                "bucket": r.get("time_dimension"),
                "cost_usd": round(_num(r.get("sum_totalCost")), 6),
                "calls": int(_num(r.get("count_count"))),
            }
            for r in daily
        ],
        "recent_turns": [
            {
                "name": o.get("name"),
                "started_at": o.get("startTime"),
                "latency_ms": round(_num(o.get("latency")) * 1000),
                "level": o.get("level"),
                "trace_url": trace_url(o.get("traceId")),
            }
            for o in recent
        ],
    }
