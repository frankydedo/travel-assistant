"""Proposal-phase tool calling (ADR-0001), driven by the mock's rule-based tool choice."""

from app.llm.base import ToolCall
from app.models import Conversation
from app.services.proposal_tools import ProposalToolbox
from tests.test_api import plan_trip, selected


def active(conv: dict) -> dict[str, dict]:
    return {i["variant"]: i for i in conv["itineraries"] if i["status"] in ("proposed", "selected")}


def say(client, conv: dict, text: str) -> dict:
    return client.post(f"/api/conversations/{conv['id']}/messages", json={"content": text}).json()


def test_swap_activity_creates_a_new_validated_itinerary(client):
    conv = plan_trip(client)
    before = active(conv)["balanced"]
    conv = say(client, conv, "Nella bilanciata, il giorno 2 vorrei qualcosa di più rilassante, magari al mare")
    after = active(conv)["balanced"]
    assert after["id"] != before["id"]  # never edited in place
    assert {i["id"]: i["status"] for i in conv["itineraries"]}[before["id"]] == "discarded"
    assert after["days_plan"][1]["activity"]["id"] != before["days_plan"][1]["activity"]["id"]
    assert [d["activity"]["id"] for d in after["days_plan"] if d["day"] != 2] == [
        d["activity"]["id"] for d in before["days_plan"] if d["day"] != 2
    ]
    assert after["total_price"] <= after["budget_total"]
    reply = conv["messages"][-1]
    assert reply["itinerary_ids"] == [after["id"]] and "giorno 2" in reply["content"]


def test_change_hotel(client):
    conv = plan_trip(client)
    before = active(conv)["economy"]
    conv = say(client, conv, "Per l'economica c'è un hotel migliore?")
    after = active(conv)["economy"]
    assert after["hotel"]["stars"] > before["hotel"]["stars"]
    assert after["total_price"] <= after["budget_total"]


def test_search_activities_is_read_only(client):
    conv = plan_trip(client)
    ids_before = {i["id"] for i in conv["itineraries"]}
    conv = say(client, conv, "Che attività ci sono per chi ama il cibo?")
    assert {i["id"] for i in conv["itineraries"]} == ids_before
    assert conv["phase"] == "PROPOSING" and "attività" in conv["messages"][-1]["content"]


def test_modifying_the_selected_variant_requires_a_new_choice(client):
    conv = selected(client, plan_trip(client))
    assert conv["phase"] == "AWAITING_CONFIRMATION"
    conv = say(client, conv, "Il giorno 1 preferirei un'attività diversa")
    assert conv["phase"] == "PROPOSING"
    assert all(i["status"] != "selected" for i in conv["itineraries"])


def test_tool_arguments_are_validated_and_ids_are_never_accepted(client, session):
    conv = plan_trip(client)
    toolbox = make_toolbox(session, conv["id"])
    bad_day = toolbox.execute(ToolCall("1", "swap_activity", {"variant": "balanced", "day": 99, "request": "mare"}))
    assert "errore" in bad_day.content and not bad_day.itinerary_ids
    unknown = toolbox.execute(ToolCall("2", "book_now", {}))
    assert "errore" in unknown.content  # there is no booking tool at all
    missing = toolbox.execute(ToolCall("3", "change_hotel", {"variant": "premium", "direction": "sideways"}))
    assert "errore" in missing.content


def make_toolbox(session, conversation_id: str) -> ProposalToolbox:
    from app.api.deps import get_interpreter, index_factory
    from app.config import get_settings
    from app.services.conversation import ConversationService

    service = ConversationService(session, get_interpreter(), index_factory, get_settings())
    return ProposalToolbox(service, session.get(Conversation, conversation_id))
