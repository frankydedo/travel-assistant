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
    conv = say(client, conv, "Nella bilanciata, il giorno 2 vorrei fare qualcosa di diverso")
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


def test_swap_respects_the_requested_category(client):
    conv = plan_trip(client)
    before = active(conv)["balanced"]
    used_relax = sum(d["activity"]["category"] == "relax" for d in before["days_plan"])
    conv = say(client, conv, "Nella bilanciata, il giorno 2 vorrei qualcosa di rilassante")
    after = active(conv)["balanced"]
    if after["id"] == before["id"]:  # no relax option left: explained, nothing silently replaced
        assert used_relax > 0 and "Non posso sostituire il giorno 2" in conv["messages"][-1]["content"]
    else:
        assert after["days_plan"][1]["activity"]["category"] == "relax"


def test_exact_dates_are_detected():
    from app.domain.requirements import mentions_exact_date

    for text in ["voglio partire esattamente il 4 febbraio", "dal 3 al 10 marzo", "partenza il 10/03", "il 1° maggio"]:
        assert mentions_exact_date(text), text
    for text in ["5-7 giorni a febbraio", "1500 euro, 4 giorni a marzo", "siamo in 2 ad agosto", "7 giorni"]:
        assert not mentions_exact_date(text), text


def test_an_exact_date_is_explained_not_silently_dropped(client):
    from app.services.conversation import EXACT_DATE_NOTICE

    conv = plan_trip(client)
    conv = say(client, conv, "ho cambiato idea, voglio partire esattamente il 4 febbraio")
    last = conv["messages"][-1]
    assert last["provider"] == "SYSTEM" and last["content"] == EXACT_DATE_NOTICE
    assert not any("chiedi all'utente" in m["content"] for m in conv["messages"])  # LLM-facing text never leaks
    assert active(conv)  # proposals still there
