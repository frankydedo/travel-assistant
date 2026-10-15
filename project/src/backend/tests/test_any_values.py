"""Explicit "any" values (ADR-0021): unlimited budget, any departure airport, no activity preference."""

import uuid

from app.domain.requirements import RequirementsUpdate, keep_explicit_any
from tests.test_api import new_conversation, plan_trip, selected


def say(client, conv: dict, text: str) -> dict:
    return client.post(f"/api/conversations/{conv['id']}/messages", json={"content": text}).json()


def test_unlimited_budget(client):
    conv = plan_trip(
        client, "Siamo in due, budget illimitato, Spagna a maggio per 5 giorni, partenza da Roma, cultura e cibo"
    )
    assert conv["requirements"]["budget_total"] == "unlimited"
    variants = {i["variant"]: i for i in conv["itineraries"]}
    assert set(variants) >= {"economy", "premium"} and all(i["budget_total"] is None for i in variants.values())
    assert variants["economy"]["total_price"] <= variants["premium"]["total_price"]
    assert "budget illimitato" in conv["messages"][-1]["content"]
    booked = selected(client, conv, "premium")
    assert booked["phase"] == "AWAITING_CONFIRMATION"


def test_any_airport_compares_every_departure(client):
    conv = plan_trip(
        client,
        "Siamo in 2, budget 2500 euro, Grecia ad agosto per 5 giorni, parto da qualsiasi aeroporto, mare e relax",
    )
    assert conv["requirements"]["departure_airport"] == "ANY"
    origins = {i["flights"]["outbound"]["origin"] for i in conv["itineraries"]}
    assert origins <= {"FCO", "MXP", "NAP"} and origins
    for it in conv["itineraries"]:  # the return flight goes back to the same airport
        assert it["flights"]["return"]["destination"] == it["flights"]["outbound"]["origin"]


def test_no_preferences(client):
    conv = plan_trip(
        client, "Budget 2000 euro, da solo, Italia a giugno, 4 giorni, da Milano, nessuna preferenza sulle attività"
    )
    assert conv["requirements"]["preferences"]["categories"] == []
    assert conv["phase"] == "PROPOSING" and conv["itineraries"]


def test_a_bare_any_answers_only_the_pending_question(client):
    conv = new_conversation(client)
    conv = say(client, conv, "Grecia a luglio, 6 giorni, siamo in 3, budget 3000 euro, cultura")
    assert conv["requirements"]["departure_airport"] is None
    conv = say(client, conv, "indifferente")
    assert conv["requirements"]["departure_airport"] == "ANY"
    assert conv["requirements"]["destination"]["country_code"] == "GR"  # untouched
    assert conv["phase"] == "PROPOSING"


def test_any_values_need_an_explicit_expression():
    """An interpreter that fills a gap with "any" is a silent default: code drops what was not said."""
    update = RequirementsUpdate.model_validate(
        {"budget_total": "unlimited", "departure_airport": "ANY", "preferences": {"categories": []}, "month": 5}
    )
    kept = keep_explicit_any(update, "vorrei andare in Spagna a maggio", [])
    assert kept.model_dump(exclude_none=True) == {"month": 5}
    said = "nessun limite di budget, parto da qualsiasi aeroporto, non ho preferenze"
    assert keep_explicit_any(update, said, []) == update
    # A bare "indifferente" is accepted only for the one field still missing.
    assert keep_explicit_any(update, "indifferente", ["departure_airport"]).departure_airport == "ANY"
    assert keep_explicit_any(update, "indifferente", ["departure_airport", "budget_total"]).departure_airport is None


def test_impossible_requests_are_explained_not_dropped(client):
    conv = new_conversation(client)
    conv = say(client, conv, "Brasile a dicembre, partenza da Torino, siamo in 15, budget 5000 euro, 10 giorni, mare")
    reply = conv["messages"][-1]["content"]
    assert "non abbiamo offerte" in reply and "Roma Fiumicino, Milano Malpensa o Napoli" in reply
    assert "al massimo 9 persone" in reply
    req = conv["requirements"]
    assert req["destination"] is None and req["departure_airport"] is None and req["travelers"] is None


def test_islanda_is_not_mangled_by_the_departure_rule(client):
    conv = plan_trip(client, "Islanda a febbraio, 4 giorni, da Milano, natura, da solo, 1800 euro")
    assert conv["requirements"]["destination"]["country_code"] == "IS"


def test_anywhere_with_unlimited_budget_explains_and_varies(client):
    conv = plan_trip(
        client,
        "Budget illimitato, vorrei andare ovunque a settembre per 6 giorni, siamo in 2, parto da qualsiasi "
        "aeroporto, nessuna preferenza sulle attività",
    )
    variants = {i["variant"]: i for i in conv["itineraries"]}
    assert len({i["country_code"] for i in variants.values()}) == 3  # ADR-0022: three different countries
    assert variants["economy"]["total_price"] < variants["balanced"]["total_price"] < variants["premium"]["total_price"]
    reply = conv["messages"][-1]["content"]
    assert "ho confrontato 5 paesi" in reply and "Budget illimitato" in reply


def test_an_amount_the_code_did_not_compute_never_reaches_the_user():
    """ADR-0025: '1 966 €' instead of 1963 € in a real conversation; the code text replaces the reply."""
    from app.llm.grounding import ungrounded_amounts

    facts = {"variants": [{"total_price": 508}, {"total_price": 729}, {"total_price": 1963}]}
    assert ungrounded_amounts("**Premium** a **1 966 €**", facts) == [1966]
    assert ungrounded_amounts("Premium a 1.963 €, 1.300 € in più dell'Economica (508 €)", facts) == [1300]
    assert ungrounded_amounts("La Bilanciata costa 221 € in più (729 €)", facts) == []  # 729 - 508


def test_cancelling_reopens_the_conversation(client):
    conv = plan_trip(client, "Siamo in due, budget 2500 euro, Spagna a maggio per 5 giorni, da Roma, cultura")
    conv = selected(client, conv)
    itinerary = next(i for i in conv["itineraries"] if i["status"] == "selected")
    booking = client.post(
        "/api/bookings", json={"itinerary_id": itinerary["id"]}, headers={"Idempotency-Key": str(uuid.uuid4())}
    ).json()
    client.post(f"/api/bookings/{booking['id']}/cancel")
    conv = client.get(f"/api/conversations/{conv['id']}").json()
    assert conv["phase"] == "PROPOSING"  # the other variants are still there
    assert conv["messages"][-1]["provider"] == "SYSTEM" and "Prenotazione annullata" in conv["messages"][-1]["content"]
    conv = say(client, conv, "ok, scelgo la economica")
    assert conv["phase"] == "AWAITING_CONFIRMATION"


def test_an_explicit_choice_selects_even_if_the_model_only_answers():
    import re

    from app.services.conversation import CHANGE_WORDS_IN_CHOICE, CHOICE_INTENT

    assert re.search(CHOICE_INTENT, "va bene, prenota tu la bilanciata, ti do carta bianca")
    assert re.search(CHANGE_WORDS_IN_CHOICE, "la bilanciata mi piace, ma cambia il giorno 3")


def test_review_findings_on_text_checks():
    from app.domain.requirements import Preferences, RequirementsUpdate, TripRequirements, clean_preference_notes
    from app.llm.grounding import strip_field_labels, ungrounded_amounts

    ctx = {"dal": "2026-11-08", "totale_euro": 1963, "prezzo_a_persona": 60, "giorno": 1}
    assert ungrounded_amounts("La Bilanciata costa 1 966 €", ctx) == [1966]  # 2026 - 60 must not vouch for it
    assert ungrounded_amounts("La Bilanciata costa 1,966 €", ctx) == [1966]  # comma as thousands separator
    assert ungrounded_amounts("giorno 2 150 €", {"prezzo": 150}) == []  # a day number before a price
    assert Preferences.model_validate({"categories": ["relax"], "notes": "spiagge tranquille " * 20}).notes
    assert clean_preference_notes("viaggio in coppia, romantico") == "viaggio in coppia, romantico"
    current = TripRequirements(preferences=Preferences(categories=["relax"], notes="mare"))
    cleared = current.merge(RequirementsUpdate(preferences=Preferences(categories=[])))
    assert cleared.preferences.none and cleared.preferences.notes is None
    assert strip_field_labels("Premium: *perché*: punta su hotel migliori") == "Premium: Punta su hotel migliori"
