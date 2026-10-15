"""Read-only catalog tools (ADR-0026), driven by the mock's rule-based tool choice."""

from sqlalchemy import func, select

from app.llm.base import ToolCall
from app.models import Country, Flight
from tests.test_api import new_conversation, plan_trip
from tests.test_tools import make_toolbox


def say(client, conv: dict, text: str) -> dict:
    return client.post(f"/api/conversations/{conv['id']}/messages", json={"content": text}).json()


def test_a_question_about_destinations_is_answered_not_refused(client, session):
    conv = say(client, new_conversation(client), "mi dici quali sono le destinazioni disponibili?")
    reply = conv["messages"][-1]
    assert reply["provider"] == "MOCK" and conv["phase"] == "COLLECTING_REQUIREMENTS"
    for name in session.scalars(select(Country.name)):
        assert name in reply["content"]


def test_a_question_with_requirements_records_them_and_answers_with_real_availability(client, session):
    conv = say(client, new_conversation(client), "Siamo in due da Napoli: ci sono voli per l'Islanda a febbraio?")
    req = conv["requirements"]
    assert (req["travelers"], req["departure_airport"], req["destination"]["country_code"], req["month"]) == (
        2,
        "NAP",
        "IS",
        2,
    )
    reply = conv["messages"][-1]["content"]
    assert "febbraio 2027" in reply and "voli" in reply  # the year is said: the catalog window decides it
    assert "dimmi anche" in reply  # and it still asks for what is missing


def test_check_availability_counts_what_the_database_has(client, session):
    conv = new_conversation(client)
    toolbox = make_toolbox(session, conv["id"])
    from app.services.catalog_tools import CatalogToolbox

    catalog = CatalogToolbox(toolbox.service, toolbox.conv)
    out = catalog.execute(ToolCall("1", "check_availability", {"country": "IS", "month": 2, "travelers": 2}))
    nap = next(f for f in out.content["voli"] if f["partenza"] == "NAP")
    days, price = session.execute(
        select(func.count(func.distinct(Flight.date)), func.min(Flight.price)).where(
            Flight.origin == "NAP",
            Flight.destination == "KEF",
            func.extract("month", Flight.date) == 2,
            Flight.seats_left >= 2,
        )
    ).one()
    assert (nap["giorni_con_voli_andata"], nap["prezzo_minimo_andata_a_persona"]) == (days, price)
    unknown = catalog.execute(ToolCall("2", "get_hotels", {"country": "Brasile"}))
    assert "errore" in unknown.content and "Islanda" in unknown.summary


def test_catalog_tools_are_available_while_looking_at_proposals(client):
    conv = plan_trip(client)
    conv = say(client, conv, "Che hotel ci sono in Grecia?")
    reply = conv["messages"][-1]["content"]
    assert conv["phase"] == "PROPOSING" and "hotel" in reply and "Atene" in reply


def test_hotel_prices_are_those_of_the_requested_month(client, session):
    from app.catalog import resolve_month
    from app.models import Hotel, HotelAvailability
    from app.services.catalog_tools import CatalogToolbox

    conv = new_conversation(client)
    toolbox = make_toolbox(session, conv["id"])
    out = CatalogToolbox(toolbox.service, toolbox.conv).execute(
        ToolCall("1", "get_hotels", {"country": "Islanda", "month": 2})
    )
    days = resolve_month(session, 2)
    first = out.content["hotel"][0]
    expected = session.scalar(
        select(func.min(HotelAvailability.price))
        .join(Hotel, Hotel.id == HotelAvailability.hotel_id)
        .where(Hotel.name == first["hotel"], HotelAvailability.rooms_left > 0)
        .where(HotelAvailability.date.between(days[0], days[-1]))
    )
    assert first["prezzo_camera_notte_da"] == expected and out.content["periodo_prezzi"].startswith("febbraio")
