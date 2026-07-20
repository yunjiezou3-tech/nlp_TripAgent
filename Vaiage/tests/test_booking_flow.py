import sys
import types
from pathlib import Path

import pytest


class AIMessage:
    def __init__(self, content):
        self.content = content


schema_module = types.ModuleType("langchain.schema")
schema_module.AIMessage = AIMessage
sys.modules.setdefault("langchain.schema", schema_module)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def register_agent_module(module_name, class_name, cls):
    module = types.ModuleType(module_name)
    setattr(module, class_name, cls)
    sys.modules[module_name] = module


class DummyChatAgent:
    def collect_info(self, user_input, state=None):
        return {
            "stream": iter([AIMessage(content="ok")]),
            "missing_fields": [],
            "complete": True,
            "state": state or {},
        }


class DummyInformationAgent:
    def city2geocode(self, city):
        return {"lat": 31.23, "lng": 121.47}

    def get_weather(self, lat, lng, start_date, days, summary=True):
        return {"summary": "天气晴朗"}

    def get_attractions(self, lat, lng, user_prefs, weather_summary=None, number=20, poi_type="tourist_attraction"):
        return [
            {
                "id": "a1",
                "name": "外滩",
                "location": {"lat": 31.24, "lng": 121.49},
                "estimated_duration": 2,
            }
        ]

    def search_nearby_places(self, lat, lng, radius=500):
        return {
            "restaurants": [],
            "hotels": [
                {
                    "name": "静安景观酒店",
                    "address": "上海静安区",
                    "rating": 4.7,
                    "price_level": 3,
                    "summary_overview": "地铁方便，适合亲子",
                    "photos": [],
                },
                {
                    "name": "外滩轻居酒店",
                    "address": "上海黄浦区",
                    "rating": 4.5,
                    "price_level": 2,
                    "summary_overview": "靠近景点，含早餐",
                    "photos": [],
                },
            ],
        }


class DummyRecommendAgent:
    def generate_map_data(self, attractions):
        return attractions

    def recommend_core_attractions(self, user_prefs, attractions):
        return attractions


class DummyStrategyAgent:
    def plan_remaining_time(self, selected_spots, total_days, all_attractions, user_prefs, weather_summary):
        return {
            "remaining_hours": 4,
            "additional_attractions": all_attractions,
            "daily_plan": {"day1": ["外滩"]},
        }

    def get_ai_recommendation(self, user_prefs, selected_spots, total_days, user_name=None):
        user_prefs["should_rent_car"] = False

        def gen():
            yield AIMessage(content="已为你生成行程建议。")

        return gen()


class DummyRouteAgent:
    def format_daily_plan_to_itinerary(self, daily_plan_name_dict, all_spots_object_map, start_date_str):
        return [
            {
                "day": 1,
                "date": start_date_str,
                "spots": [
                    {
                        "name": "外滩",
                        "start_time": "09:00",
                        "end_time": "11:00",
                    }
                ],
            }
        ]

    def estimate_budget(self, spots, user_prefs, should_rent_car=False, car_info=None, fuel_price=None):
        return {"total": 3200, "accommodation": 1200}


class DummyCommunicationAgent:
    def generate_booking_confirmation(self, itinerary, budget_estimate, car_rental=None, user_name=None):
        return "行程已生成，可以继续让我帮你预订机票或酒店。"


register_agent_module("agents.chat_agent", "ChatAgent", DummyChatAgent)
register_agent_module("agents.information_agent", "InformationAgent", DummyInformationAgent)
register_agent_module("agents.recommend_agent", "RecommendAgent", DummyRecommendAgent)
register_agent_module("agents.strategy_agent", "StrategyAgent", DummyStrategyAgent)
register_agent_module("agents.route_agent", "RouteAgent", DummyRouteAgent)
register_agent_module("agents.communication_agent", "CommunicationAgent", DummyCommunicationAgent)

from workflows import travel_graph as tg


def build_graph(monkeypatch):
    monkeypatch.setattr(tg, "ChatAgent", DummyChatAgent)
    monkeypatch.setattr(tg, "InformationAgent", DummyInformationAgent)
    monkeypatch.setattr(tg, "RecommendAgent", DummyRecommendAgent)
    monkeypatch.setattr(tg, "StrategyAgent", DummyStrategyAgent)
    monkeypatch.setattr(tg, "RouteAgent", DummyRouteAgent)
    monkeypatch.setattr(tg, "CommunicationAgent", DummyCommunicationAgent)
    return tg.TravelGraph()


def test_strategy_generates_structured_hotel_recommendations(monkeypatch):
    graph = build_graph(monkeypatch)
    graph.state.update(
        {
            "user_info": {
                "name": "小王",
                "city": "上海",
                "days": "2",
                "budget": "medium",
                "people": "2",
                "kids": "yes",
                "health": "good",
                "hobbies": "citywalk",
                "start_date": "2026-05-01",
                "accommodation_preference": "地铁方便、亲子友好、带早餐",
            },
            "selected_attractions": [{"id": "a1", "name": "外滩", "location": {"lat": 31.24, "lng": 121.49}}],
            "attractions": [{"id": "a1", "name": "外滩", "location": {"lat": 31.24, "lng": 121.49}}],
            "hotel_candidates": [
                {
                    "id": "h1",
                    "name": "静安景观酒店",
                    "address": "上海静安区",
                    "rating": 4.7,
                    "price_level": 3,
                    "summary": "地铁方便，适合亲子",
                    "photos": [],
                    "source": "mock",
                    "location": {"lat": 31.23, "lng": 121.45},
                }
            ],
        }
    )

    result = graph._process_strategy(user_input="here are my selected attractions")

    assert result["next_step"] == "route"
    assert result["state"]["hotel_recommendations"][0]["name"] == "静安景观酒店"
    assert result["state"]["recommended_hotel_id"] == "h1"


def test_complete_step_can_switch_to_booking_hotel_flow(monkeypatch):
    graph = build_graph(monkeypatch)
    graph.state.update(
        {
                "user_info": {
                    "name": "小王",
                    "city": "上海",
                    "days": "2",
                    "people": "2",
                    "start_date": "2026-05-01",
                    "contact_phone": "13800000000",
                    "accommodation_preference": "靠近地铁",
                },
            "itinerary": [{"day": 1, "date": "2026-05-01", "spots": [{"name": "外滩"}]}],
            "hotel_recommendations": [
                {"id": "h1", "name": "静安景观酒店", "address": "上海静安区", "source": "ctrip_mock"}
            ],
            "recommended_hotel_id": "h1",
        }
    )
    graph.session_states["session-1"] = graph.state.copy()

    result = graph.process_step("complete", session_id="session-1", user_input="帮我订酒店")

    assert result["next_step"] in {"booking_collect", "booking_confirm"}
    assert result["booking_mode"] == "hotel"
    assert "hotel_draft" in result["state"]["booking_drafts"]


def test_true_legacy_hotel_without_offer_fields_uses_computed_zero_tax_draft(monkeypatch):
    from services.booking_provider import CtripMockProvider

    provider = CtripMockProvider()
    draft = provider.create_hotel_draft(
        {
            "hotel": {"id": "h1", "name": "静安景观酒店", "address": "上海静安区"},
            "criteria": {
                "city": "上海",
                "check_in": "2026-05-01",
                "check_out": "2026-05-03",
                "rooms": 1,
                "guests": 2,
            },
            "traveler": {"contact_name": "小王", "contact_phone": "13800000000"},
        }
    )

    assert draft["status"] == "draft"
    assert draft["source_provider"] == "ctrip_mock"
    assert draft["selected_offer"]["hotel_name"] == "静安景观酒店"
    assert draft["selected_offer"]["offer_id"] is None
    assert draft["pricing_summary"] == {
        "currency": "CNY",
        "room_subtotal": 1376,
        "taxes_and_fees": 0,
        "total_price": 1376,
        "room_rate_total": 1376,
        "service_fee": 0,
        "taxes": 0,
        "total_amount": 1376,
    }
    assert draft["traveler_snapshot"]["contact_name"] == "小王"


def test_complete_step_can_create_both_booking_drafts(monkeypatch):
    graph = build_graph(monkeypatch)
    graph.state.update(
        {
            "user_info": {
                "name": "小王",
                "city": "东京",
                "origin": "上海",
                "days": "3",
                "people": "2",
                "start_date": "2026-05-01",
                "contact_phone": "13800000000",
                "document_type": "护照",
                "document_last4": "1234",
                "accommodation_preference": "交通方便",
            },
            "itinerary": [{"day": 1, "date": "2026-05-01", "spots": [{"name": "浅草寺"}]}],
            "hotel_recommendations": [
                {"id": "h1", "name": "东京站优选酒店", "address": "东京站", "source": "ctrip_mock"}
            ],
            "recommended_hotel_id": "h1",
        }
    )
    graph.session_states["session-both"] = graph.state.copy()

    result = graph.process_step("complete", session_id="session-both", user_input="帮我订机票和酒店")

    assert result["next_step"] == "booking_confirm"
    assert "hotel_draft" in result["booking_drafts"]
    assert "flight_draft" in result["booking_drafts"]


def _room_search_criteria(**overrides):
    criteria = {
        "destination": "上海",
        "hotel_id": "google-hotel-1",
        "hotel_name": "静安景观酒店",
        "check_in": "2026-08-01",
        "check_out": "2026-08-04",
        "rooms": 2,
        "guests": 3,
    }
    criteria.update(overrides)
    return criteria


@pytest.mark.parametrize("missing_field", ["hotel_id", "hotel_name"])
def test_room_search_requires_hotel_identity_context(missing_field):
    from services.booking_provider import CtripMockProvider

    criteria = _room_search_criteria()
    criteria.pop(missing_field)

    with pytest.raises(ValueError, match=missing_field):
        CtripMockProvider().search_hotel_rooms(criteria)


@pytest.mark.parametrize(
    "criteria_update,error_match",
    [
        ({"check_in": None}, "check_in"),
        ({"check_out": None}, "check_out"),
        ({"check_in": "2026/08/01"}, "check_in.*YYYY-MM-DD"),
        ({"check_out": "2026-02-30"}, "check_out.*YYYY-MM-DD"),
        ({"check_out": "2026-08-01"}, "check_out.*after check_in"),
        ({"check_out": "2026-07-31"}, "check_out.*after check_in"),
    ],
)
def test_room_search_requires_explicit_valid_stay_dates(criteria_update, error_match):
    from services.booking_provider import CtripMockProvider

    with pytest.raises(ValueError, match=error_match):
        CtripMockProvider().search_hotel_rooms(
            _room_search_criteria(**criteria_update)
        )


@pytest.mark.parametrize(
    "field,value",
    [
        ("rooms", True),
        ("rooms", 0),
        ("rooms", -1),
        ("rooms", 1.5),
        ("rooms", "2"),
        ("rooms", None),
        ("guests", False),
        ("guests", 0),
        ("guests", -2),
        ("guests", 2.0),
        ("guests", "3"),
        ("guests", None),
    ],
)
def test_room_search_rejects_non_positive_or_non_integer_counts(field, value):
    from services.booking_provider import CtripMockProvider

    with pytest.raises(ValueError, match=field):
        CtripMockProvider().search_hotel_rooms(
            _room_search_criteria(**{field: value})
        )


def test_room_search_defaults_counts_only_when_omitted():
    from services.booking_provider import CtripMockProvider

    criteria = _room_search_criteria()
    criteria.pop("rooms")
    criteria.pop("guests")

    offers = CtripMockProvider().search_hotel_rooms(criteria)

    assert {offer["rooms"] for offer in offers} == {1}
    assert {offer["guests"] for offer in offers} == {1}


@pytest.mark.parametrize(
    "destination,hotel_id,hotel_name",
    [
        ("上海", "google-shanghai-1", "静安景观酒店"),
        ("Tokyo, Japan", "google-tokyo-1", "Tokyo Station Hotel"),
    ],
)
def test_room_search_returns_complete_provider_neutral_mock_offers(
    destination, hotel_id, hotel_name
):
    from services.booking_provider import CtripMockProvider

    offers = CtripMockProvider().search_hotel_rooms(
        _room_search_criteria(
            destination=destination,
            hotel_id=hotel_id,
            hotel_name=hotel_name,
        )
    )

    required_keys = {
        "offer_id",
        "hotel_id",
        "hotel_name",
        "room_type",
        "bed_type",
        "breakfast",
        "nightly_rate",
        "currency",
        "room_subtotal",
        "total_price",
        "taxes_and_fees",
        "cancellation_policy",
        "check_in",
        "check_out",
        "rooms",
        "guests",
        "inventory_status",
        "source_provider",
        "is_mock",
        "provider_trace_id",
        "raw_payload_ref",
    }
    assert len(offers) in {2, 3}
    assert all(required_keys <= offer.keys() for offer in offers)
    assert {offer["hotel_id"] for offer in offers} == {hotel_id}
    assert {offer["hotel_name"] for offer in offers} == {hotel_name}
    assert {offer["currency"] for offer in offers} == {"CNY"}
    assert {offer["source_provider"] for offer in offers} == {"ctrip_mock"}
    assert {offer["is_mock"] for offer in offers} == {True}
    assert len({offer["room_type"] for offer in offers}) > 1
    assert len({offer["breakfast"] for offer in offers}) > 1
    assert len({offer["cancellation_policy"] for offer in offers}) > 1
    assert all("payment" not in offer and "order" not in offer for offer in offers)


def test_room_offer_total_is_grand_total_for_all_nights_and_rooms():
    from services.booking_provider import CtripMockProvider

    offers = CtripMockProvider().search_hotel_rooms(_room_search_criteria())

    for offer in offers:
        assert offer["room_subtotal"] == offer["nightly_rate"] * 3 * 2
        assert offer["taxes_and_fees"] > 0
        assert offer["total_price"] == (
            offer["room_subtotal"] + offer["taxes_and_fees"]
        )


def test_room_offer_ids_are_stable_and_distinct_by_hotel_date_and_room():
    from services.booking_provider import CtripMockProvider

    provider = CtripMockProvider()
    baseline = provider.search_hotel_rooms(_room_search_criteria())
    repeated = provider.search_hotel_rooms(_room_search_criteria())
    other_hotel = provider.search_hotel_rooms(
        _room_search_criteria(hotel_id="google-hotel-2", hotel_name="外滩酒店")
    )
    other_dates = provider.search_hotel_rooms(
        _room_search_criteria(check_in="2026-08-02", check_out="2026-08-05")
    )

    baseline_ids = [offer["offer_id"] for offer in baseline]
    assert baseline == repeated
    assert len(set(baseline_ids)) == len(baseline_ids)
    assert set(baseline_ids).isdisjoint(offer["offer_id"] for offer in other_hotel)
    assert set(baseline_ids).isdisjoint(offer["offer_id"] for offer in other_dates)


def test_stable_ids_use_unambiguous_type_safe_sha256_serialization():
    from services.booking_provider import CtripMockProvider

    provider = CtripMockProvider()

    delimited_left = provider._stable_id("hotel|2026-08-01", "room")
    delimited_right = provider._stable_id("hotel", "2026-08-01|room")

    assert delimited_left != delimited_right
    assert provider._stable_id("1") != provider._stable_id(1)
    assert len(delimited_left) >= 24
    assert delimited_left == provider._stable_id("hotel|2026-08-01", "room")


def test_room_search_accepts_maximum_stay_room_and_guest_limits():
    from services.booking_provider import CtripMockProvider

    offers = CtripMockProvider().search_hotel_rooms(
        _room_search_criteria(
            check_in="2026-08-01",
            check_out="2026-08-31",
            rooms=10,
            guests=40,
        )
    )

    assert {offer["rooms"] for offer in offers} == {10}
    assert {offer["guests"] for offer in offers} == {40}
    assert all(
        offer["room_subtotal"] == offer["nightly_rate"] * 30 * 10
        for offer in offers
    )


@pytest.mark.parametrize(
    "criteria_update,error_match",
    [
        ({"check_out": "2026-09-01"}, "nights.*1.*30"),
        ({"rooms": 11}, "rooms.*1.*10"),
        ({"guests": 41}, "guests.*1.*40"),
    ],
)
def test_room_search_rejects_values_above_domain_limits(
    criteria_update, error_match
):
    from services.booking_provider import CtripMockProvider

    with pytest.raises(ValueError, match=error_match):
        CtripMockProvider().search_hotel_rooms(
            _room_search_criteria(**criteria_update)
        )


def test_hotel_draft_uses_matching_candidate_room_offer_totals_and_metadata():
    from services.booking_provider import CtripMockProvider

    provider = CtripMockProvider()
    search_criteria = _room_search_criteria()
    lowest_offer = provider.search_hotel_rooms(search_criteria)[0]
    hotel = {
        "id": search_criteria["hotel_id"],
        "name": search_criteria["hotel_name"],
        "address": "上海静安区",
        "selected_room_offer": lowest_offer,
        "room_offers": [lowest_offer],
    }

    draft = provider.create_hotel_draft(
        {
            "hotel": hotel,
            "criteria": {
                "city": "上海",
                "check_in": search_criteria["check_in"],
                "check_out": search_criteria["check_out"],
                "rooms": search_criteria["rooms"],
                "guests": search_criteria["guests"],
            },
            "traveler": {"contact_name": "小王"},
        }
    )

    assert draft["selected_offer"] == {
        "hotel_id": search_criteria["hotel_id"],
        "hotel_name": search_criteria["hotel_name"],
        "address": "上海静安区",
        "offer_id": lowest_offer["offer_id"],
        "room_type": lowest_offer["room_type"],
        "bed_type": lowest_offer["bed_type"],
        "breakfast": lowest_offer["breakfast"],
        "nightly_rate": lowest_offer["nightly_rate"],
        "source_provider": "ctrip_mock",
        "cancellation_policy": lowest_offer["cancellation_policy"],
    }
    assert draft["pricing_summary"]["room_subtotal"] == lowest_offer[
        "room_subtotal"
    ]
    assert draft["pricing_summary"]["taxes_and_fees"] == lowest_offer[
        "taxes_and_fees"
    ]
    assert draft["pricing_summary"]["total_price"] == lowest_offer["total_price"]
    assert draft["pricing_summary"]["total_amount"] == lowest_offer["total_price"]


def test_hotel_draft_explicit_matching_offer_takes_precedence_and_is_isolated():
    from services.booking_provider import CtripMockProvider

    provider = CtripMockProvider()
    criteria = _room_search_criteria()
    lowest_offer, explicit_offer = provider.search_hotel_rooms(criteria)[:2]
    hotel = {
        "id": criteria["hotel_id"],
        "name": criteria["hotel_name"],
        "selected_room_offer": lowest_offer,
        "room_offers": [lowest_offer, explicit_offer],
    }

    draft = provider.create_hotel_draft(
        {
            "hotel": hotel,
            "room_offer": explicit_offer,
            "criteria": {
                "check_in": criteria["check_in"],
                "check_out": criteria["check_out"],
                "rooms": criteria["rooms"],
                "guests": criteria["guests"],
            },
        }
    )
    explicit_offer["room_type"] = "mutated room"
    explicit_offer["total_price"] = 1

    assert draft["selected_offer"]["offer_id"] != lowest_offer["offer_id"]
    assert draft["selected_offer"]["room_type"] == "高级双床房"
    assert draft["pricing_summary"]["total_price"] > 1


@pytest.mark.parametrize(
    "criteria_update,error_match",
    [
        ({"check_in": "2026-08-01", "check_out": "2026-09-01"}, "nights.*1.*30"),
        ({"rooms": 11}, "rooms.*1.*10"),
        ({"guests": 41}, "guests.*1.*40"),
        ({"rooms": True}, "rooms.*integer"),
    ],
)
def test_hotel_draft_rejects_invalid_domain_counts(criteria_update, error_match):
    from services.booking_provider import CtripMockProvider

    criteria = {
        "check_in": "2026-08-01",
        "check_out": "2026-08-03",
        "rooms": 1,
        "guests": 1,
        **criteria_update,
    }

    with pytest.raises(ValueError, match=error_match):
        CtripMockProvider().create_hotel_draft(
            {"hotel": {"id": "hotel", "name": "酒店"}, "criteria": criteria}
        )


def test_graph_booking_draft_preserves_attached_room_offer_grand_total(monkeypatch):
    graph = build_graph(monkeypatch)
    criteria = _room_search_criteria(rooms=1, guests=2)
    offer = graph.booking_provider.search_hotel_rooms(criteria)[0]
    hotel = {
        "id": criteria["hotel_id"],
        "name": criteria["hotel_name"],
        "rating": 4.8,
        "selected_room_offer": offer,
        "room_offers": [offer],
        "nightly_rate": offer["nightly_rate"],
        "match_reasons": [],
    }
    graph.state.update(
        {
            "booking_mode": "hotel",
            "booking_context": {
                "destination": criteria["destination"],
                "check_in": criteria["check_in"],
                "check_out": criteria["check_out"],
                "rooms": criteria["rooms"],
                "guests": criteria["guests"],
            },
            "hotel_candidates": [hotel],
            "recommended_hotel_id": criteria["hotel_id"],
        }
    )

    graph._process_booking_draft()

    draft = graph.state["booking_drafts"]["hotel_draft"]
    assert draft["selected_offer"]["offer_id"] == offer["offer_id"]
    assert draft["pricing_summary"]["total_amount"] == offer["total_price"]


@pytest.mark.parametrize(
    "offer_update",
    [
        {"hotel_id": "another-hotel"},
        {"check_in": "2026-07-31"},
        {"check_out": "2026-08-05"},
        {"rooms": 1},
        {"guests": 4},
        {"guests": True},
    ],
)
def test_attached_room_offers_require_exact_typed_booking_match(offer_update):
    from services.booking_provider import CtripMockProvider

    provider = CtripMockProvider()
    criteria = _room_search_criteria()
    stale_offer = provider.search_hotel_rooms(criteria)[0]
    stale_offer.update(offer_update)
    hotel = {
        "id": criteria["hotel_id"],
        "name": criteria["hotel_name"],
        "nightly_rate": 9999,
        "selected_room_offer": stale_offer,
        "room_offers": [stale_offer],
    }

    with pytest.raises(ValueError, match="room_offer_requote_required"):
        provider.create_hotel_draft(
            {
                "hotel": hotel,
                "criteria": {
                    "check_in": criteria["check_in"],
                    "check_out": criteria["check_out"],
                    "rooms": criteria["rooms"],
                    "guests": criteria["guests"],
                },
            }
        )


@pytest.mark.parametrize(
    "explicit_update",
    [
        {"hotel_id": "another-hotel"},
        {"check_in": "2026-07-31"},
        {"check_out": "2026-08-05"},
        {"rooms": 1},
        {"guests": 4},
    ],
)
def test_invalid_explicit_room_offer_is_rejected_even_with_valid_attached_offer(
    explicit_update,
):
    from services.booking_provider import CtripMockProvider

    provider = CtripMockProvider()
    criteria = _room_search_criteria()
    valid_offer = provider.search_hotel_rooms(criteria)[0]
    explicit_offer = dict(valid_offer)
    explicit_offer.update(explicit_update)
    hotel = {
        "id": criteria["hotel_id"],
        "name": criteria["hotel_name"],
        "selected_room_offer": valid_offer,
        "room_offers": [valid_offer],
    }

    with pytest.raises(ValueError, match="room_offer_requote_required"):
        provider.create_hotel_draft(
            {
                "hotel": hotel,
                "room_offer": explicit_offer,
                "criteria": {
                    "check_in": criteria["check_in"],
                    "check_out": criteria["check_out"],
                    "rooms": criteria["rooms"],
                    "guests": criteria["guests"],
                },
            }
        )


@pytest.mark.parametrize(
    "hotel",
    [
        {"id": "hotel", "name": "酒店", "room_offers": []},
        {"id": "hotel", "name": "酒店", "selected_room_offer": None},
        {
            "id": "hotel",
            "name": "酒店",
            "room_offers": [],
            "nightly_rate": 9999,
            "room_type": "stale alias",
        },
    ],
)
def test_offer_aware_hotel_without_matching_offer_never_uses_alias_fallback(hotel):
    from services.booking_provider import CtripMockProvider

    with pytest.raises(ValueError, match="room_offer_requote_required"):
        CtripMockProvider().create_hotel_draft(
            {
                "hotel": hotel,
                "criteria": {
                    "check_in": "2026-08-01",
                    "check_out": "2026-08-03",
                    "rooms": 1,
                    "guests": 1,
                },
            }
        )
