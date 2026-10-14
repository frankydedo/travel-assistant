import json
import logging
import uuid

from app.logging_setup import ContextFilter, JsonFormatter, event_fields, request_id_var
from tests.test_api import plan_trip, selected

SECRET_TEXT = "il mio codice segreto è ZEBRA-4242"


def test_json_formatter_carries_context_and_event_fields():
    token = request_id_var.set("req-123")
    try:
        record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "booking.confirmed", None, None)
        record.booking_id = "b-1"
        ContextFilter().filter(record)
        payload = json.loads(JsonFormatter().format(record))
    finally:
        request_id_var.reset(token)
    assert payload["event"] == "booking.confirmed"
    assert payload["request_id"] == "req-123" and payload["booking_id"] == "b-1"
    assert payload["level"] == "INFO" and "ts" in payload


def test_key_events_are_logged_without_user_text(client, caplog):
    caplog.set_level(logging.INFO)
    conv = selected(client, plan_trip(client))
    itinerary_id = conv["messages"][-1]["ui"]["itinerary_id"]
    client.post("/api/bookings", json={"itinerary_id": itinerary_id}, headers={"Idempotency-Key": str(uuid.uuid4())})
    client.post(f"/api/conversations/{conv['id']}/messages", json={"content": SECRET_TEXT})

    events = {r.getMessage() for r in caplog.records}
    for expected in (
        "llm.call",
        "conversation.phase_changed",
        "planner.completed",
        "booking.confirmed",
        "http.request",
    ):
        assert expected in events, expected

    # Logs describe what the system did, never what the user wrote (ADR-0017).
    for record in caplog.records:
        assert "ZEBRA-4242" not in record.getMessage()
        assert all("ZEBRA-4242" not in str(v) for v in event_fields(record).values())
