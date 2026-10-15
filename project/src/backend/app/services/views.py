"""Rendering of planned itineraries into the API view (the JSON the frontend renders as cards)."""

from app.domain.planner import FlightOption, PlannedItinerary
from app.domain.schedule import describe_arrival, describe_departure


def _flight(f: FlightOption, travelers: int) -> dict:
    return {
        "id": f.id,
        "flight_number": f.flight_number,
        "carrier": f.carrier,
        "origin": f.origin,
        "destination": f.destination,
        "date": f.date.isoformat(),
        "departure_time": f.departure_time,
        "arrival_time": f.arrival_time,
        "price_per_person": f.price,
        "subtotal": f.price * travelers,
    }


def itinerary_view(plan: PlannedItinerary, country_name: str, destination: str) -> dict:
    nights = plan.nights
    return {
        "variant": plan.variant,
        "country_code": plan.country_code,
        "country_name": country_name,
        "destination": destination,
        "start_date": plan.start_date.isoformat(),
        "end_date": plan.end_date.isoformat(),
        "days": plan.days,
        "nights": nights,
        "travelers": plan.travelers,
        "rooms": plan.rooms,
        "total_price": plan.total_price,
        "budget_total": plan.budget,
        "cost_breakdown": {
            "flights": plan.flights_cost,
            "hotel": plan.hotel_cost,
            "activities": plan.activities_cost,
        },
        "flights": {
            "outbound": _flight(plan.outbound, plan.travelers),
            "return": _flight(plan.inbound, plan.travelers),
        },
        "hotel": {
            "id": plan.hotel.id,
            "name": plan.hotel.name,
            "stars": plan.hotel.stars,
            "neighborhood": plan.hotel.neighborhood,
            "nights": nights,
            "price_per_night_avg": round(plan.hotel_cost / plan.rooms / nights) if nights else 0,
            "subtotal": plan.hotel_cost,
        },
        "days_plan": [_day(d, plan) for d in plan.days_plan],
    }


def _day(d, plan: PlannedItinerary) -> dict:
    note = None  # first and last day: what the flights leave (ADR-0023)
    if d.day == 1:
        note = describe_arrival(plan.outbound.arrival_time)
    elif d.day == plan.days:
        note = describe_departure(plan.inbound.departure_time)
    activity = None
    if d.activity is not None:
        activity = {
            "id": d.activity.id,
            "name": d.activity.name,
            "category": d.activity.category,
            "description": d.activity.description,
            "description_ai_generated": d.activity.description_ai_generated,
            "duration_hours": d.activity.duration_hours,
            "price_per_person": d.activity.price,
            "subtotal": d.subtotal,
        }
    return {
        "day": d.day,
        "date": d.date.isoformat(),
        "travel_day": d.activity is None,
        "travel_note": note,
        "activity": activity,
    }
