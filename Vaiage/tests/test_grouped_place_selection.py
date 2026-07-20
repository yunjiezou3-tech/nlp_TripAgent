import importlib.util
import sys
import types
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock

import pytest


ROOT = Path(__file__).resolve().parents[1]


class AIMessage:
    def __init__(self, content):
        self.content = content


def _load_module(module_name, relative_path):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _install_chat_stubs(monkeypatch):
    class ChatOpenAI:
        pass

    langchain_openai = types.ModuleType("langchain_openai")
    langchain_openai.ChatOpenAI = ChatOpenAI
    messages = types.ModuleType("langchain_core.messages")
    messages.SystemMessage = AIMessage
    messages.HumanMessage = AIMessage
    messages.AIMessage = AIMessage
    monkeypatch.setitem(sys.modules, "langchain_openai", langchain_openai)
    monkeypatch.setitem(sys.modules, "langchain_core.messages", messages)


def _install_information_stubs(monkeypatch):
    _install_chat_stubs(monkeypatch)
    googlemaps = types.ModuleType("googlemaps")
    googlemaps.Client = object
    monkeypatch.setitem(sys.modules, "googlemaps", googlemaps)

    dotenv = types.ModuleType("dotenv")
    dotenv.load_dotenv = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "dotenv", dotenv)

    maps_api = types.ModuleType("services.maps_api")
    maps_api.POIApi = object
    weather_api = types.ModuleType("services.weather_api")
    weather_api.WeatherService = object
    car_rental_api = types.ModuleType("services.car_rental_api")
    car_rental_api.CarRentalService = object
    fuel_price_api = types.ModuleType("services.fuel_price_api")
    fuel_price_api.get_gas_price = lambda *args, **kwargs: None
    monkeypatch.setitem(sys.modules, "services.maps_api", maps_api)
    monkeypatch.setitem(sys.modules, "services.weather_api", weather_api)
    monkeypatch.setitem(sys.modules, "services.car_rental_api", car_rental_api)
    monkeypatch.setitem(sys.modules, "services.fuel_price_api", fuel_price_api)


def test_chat_parses_structured_accommodation_preferences(monkeypatch):
    _install_chat_stubs(monkeypatch)
    chat_module = _load_module("chat_agent_under_test", "agents/chat_agent.py")

    extracted = chat_module.parse_accommodation_preferences(
        "住新宿站附近，预算中等，评分 4.2 以上，要早餐和健身房"
    )

    assert extracted["area"] == "新宿站附近"
    assert extracted["min_rating"] == 4.2
    assert extracted["amenities"] == ["早餐", "健身房"]


def test_lodging_candidates_use_google_lodging_type(monkeypatch):
    _install_information_stubs(monkeypatch)
    info_module = _load_module("information_agent_under_test", "agents/information_agent.py")
    info_agent = info_module.InformationAgent.__new__(info_module.InformationAgent)
    info_agent.maps_api_key = "test-key"
    info_agent.llm = None
    info_agent.poi_api = MagicMock()
    info_agent.poi_api.get_nearby_places.return_value = {
        "results": [
            {
                "place_id": "h1",
                "name": "新宿站酒店",
                "vicinity": "东京新宿",
                "rating": 4.5,
                "price_level": 3,
                "types": ["lodging"],
                "geometry": {"location": {"lat": 35.69, "lng": 139.7}},
            }
        ]
    }

    hotels = info_agent.get_hotel_candidates(35.68, 139.69, {"min_rating": 4.2})

    info_agent.poi_api.get_nearby_places.assert_called_once_with(
        location=(35.68, 139.69), type="lodging", radius=10000, language="zh-CN"
    )
    assert hotels[0]["kind"] == "hotel"
    assert hotels[0]["id"] == "h1"
    assert "满足评分 4.2 以上" in hotels[0]["recommendation_reasons"]
    assert hotels[0]["recommendation_rank"] == 1


def test_restaurant_candidates_exclude_lodging_results(monkeypatch):
    _install_information_stubs(monkeypatch)
    info_module = _load_module("information_restaurant_agent_under_test", "agents/information_agent.py")
    info_agent = info_module.InformationAgent.__new__(info_module.InformationAgent)
    info_agent.maps_api_key = "test-key"
    info_agent.poi_api = MagicMock()
    info_agent.poi_api.get_nearby_places.return_value = {
        "results": [
            {
                "place_id": "restaurant",
                "name": "本帮菜馆",
                "types": ["restaurant"],
                "rating": 4.6,
            },
            {
                "place_id": "hotel",
                "name": "静安酒店",
                "types": ["lodging"],
                "rating": 4.8,
            },
            {
                "place_id": "hotel-restaurant",
                "name": "酒店内餐厅",
                "types": ["restaurant", "lodging"],
                "rating": 4.7,
            },
        ]
    }

    restaurants = info_agent.get_restaurant_candidates(31.2, 121.4)

    assert [restaurant["id"] for restaurant in restaurants] == ["restaurant"]
    assert all(restaurant["kind"] == "restaurant" for restaurant in restaurants)


def test_candidate_reasons_are_personalized_and_evidence_based(monkeypatch):
    _install_information_stubs(monkeypatch)
    info_module = _load_module("information_reason_agent_under_test", "agents/information_agent.py")
    info_agent = info_module.InformationAgent.__new__(info_module.InformationAgent)

    candidates = [
        {
            "id": "museum",
            "kind": "attraction",
            "category": "museum",
            "types": ["museum"],
            "rating": 4.8,
            "price_level": 2,
        },
        {
            "id": "restaurant",
            "kind": "restaurant",
            "types": ["restaurant"],
            "rating": 4.6,
        },
        {
            "id": "hotel",
            "kind": "hotel",
            "types": ["lodging"],
            "rating": 4.7,
            "match_reasons": ["匹配偏好：早餐"],
        },
    ]

    annotated = info_agent.annotate_candidates_with_reasons(
        candidates,
        {
            "hobbies": "museum",
            "budget": "medium",
            "accommodation_preferences": {"amenities": ["早餐"]},
        },
        ranking_source="rules",
    )

    assert "匹配你的兴趣：museum" in annotated[0]["recommendation_reasons"]
    assert "预算匹配：中等" in annotated[0]["recommendation_reasons"]
    assert annotated[1]["recommendation_reasons"] == ["评分 4.6"]
    assert annotated[2]["recommendation_reasons"] == ["匹配偏好：早餐", "评分 4.7"]
    assert [candidate["recommendation_rank"] for candidate in annotated] == [1, 2, 3]
    assert {candidate["ranking_source"] for candidate in annotated} == {"rules"}


def test_attraction_rerank_fallback_reports_rules_source(monkeypatch):
    _install_information_stubs(monkeypatch)
    info_module = _load_module("information_rerank_agent_under_test", "agents/information_agent.py")
    info_agent = info_module.InformationAgent.__new__(info_module.InformationAgent)
    info_agent.llm = MagicMock()
    info_agent.llm.invoke.side_effect = RuntimeError("LLM unavailable")
    info_agent.llm_rerank_cache = {}
    attractions = [{"id": "museum", "name": "博物馆", "rating": 4.8, "category": "museum"}]

    ranked, llm_succeeded = info_agent._rerank_attractions_with_llm(
        attractions, {"hobbies": "museum"}
    )
    annotated = info_agent.annotate_candidates_with_reasons(
        ranked, {"hobbies": "museum"}, ranking_source="llm" if llm_succeeded else "rules"
    )

    assert ranked == attractions
    assert llm_succeeded is False
    assert annotated[0]["ranking_source"] == "rules"


def test_hotel_budget_filter_keeps_unknown_google_price_until_room_quotes_exist(monkeypatch):
    _install_information_stubs(monkeypatch)
    info_module = _load_module("information_hotel_filter_under_test", "agents/information_agent.py")
    info_agent = info_module.InformationAgent.__new__(info_module.InformationAgent)
    hotels = [
        {"id": "unknown", "name": "Google 价格未知酒店", "price_level": None},
        {"id": "low", "name": "经济酒店", "price_level": 1},
        {"id": "matching", "name": "中高档酒店", "price_level": 3},
    ]

    filtered = info_agent._apply_hotel_hard_filters(
        hotels,
        {"price_level": {"min": 2, "max": 3}},
        [],
    )

    assert [hotel["id"] for hotel in filtered] == ["unknown", "matching"]
    info_agent.llm = None
    ranked = info_agent.rank_hotels_with_preferences(
        filtered,
        {"price_level": {"min": 2, "max": 3}},
    )
    assert "匹配住宿预算" not in ranked[0]["match_reasons"]
    assert "匹配住宿预算" in ranked[1]["match_reasons"]


class DummyChatAgent:
    def collect_info(self, user_input, state=None):
        return {
            "stream": iter([AIMessage("ok")]),
            "missing_fields": [],
            "complete": True,
            "state": state or {},
        }


class DummyInformationAgent:
    def city2geocode(self, city):
        return {"lat": 31.23, "lng": 121.47}

    def get_weather(self, *args, **kwargs):
        return {"summary": "晴朗"}

    def get_attractions(self, *args, **kwargs):
        return [{"id": "a1", "name": "外滩", "location": {"lat": 31.24, "lng": 121.49}, "estimated_duration": 2}]

    def get_restaurant_candidates(self, *args, **kwargs):
        return [{"id": "r1", "kind": "restaurant", "name": "本帮菜", "location": {"lat": 31.23, "lng": 121.48}, "estimated_duration": 2}]

    def get_hotel_candidates(self, *args, **kwargs):
        raise RuntimeError("Google lodging unavailable")


class DummyRecommendAgent:
    def generate_map_data(self, attractions):
        return attractions

    def recommend_core_attractions(self, user_prefs, attractions):
        return attractions


class DummyStrategyAgent:
    def plan_remaining_time(self, selected_spots, total_days, all_attractions, user_prefs, weather_summary):
        return {"remaining_hours": 0, "additional_attractions": all_attractions, "daily_plan": {"day1": [spot["name"] for spot in selected_spots]}}

    def get_ai_recommendation(self, *args, **kwargs):
        return iter([AIMessage("ok")])


class DummyRouteAgent:
    def __init__(self):
        self.selected_hotel = None

    def format_daily_plan_to_itinerary(self, daily_plan_name_dict, all_spots_object_map, start_date_str, selected_hotel=None):
        self.selected_hotel = selected_hotel
        return [{"day": 1, "date": start_date_str, "spots": [], "lodging": selected_hotel, "route_origin": selected_hotel}]

    def estimate_budget(self, *args, **kwargs):
        return {"total": 0}


class DummyCommunicationAgent:
    def generate_booking_confirmation(self, *args, **kwargs):
        return "模拟行程已生成"


class DummyBookingAgent:
    def detect_intent(self, _):
        return False


class DummyBookingProvider:
    def search_hotel_rooms(self, criteria):
        return []


def _register_graph_modules(monkeypatch):
    agents_package = types.ModuleType("agents")
    agents_package.__path__ = []
    services_package = types.ModuleType("services")
    services_package.__path__ = []
    monkeypatch.setitem(sys.modules, "agents", agents_package)
    monkeypatch.setitem(sys.modules, "services", services_package)
    monkeypatch.setitem(
        sys.modules,
        "services.date_resolver",
        _load_module("services.date_resolver", "services/date_resolver.py"),
    )
    monkeypatch.setitem(
        sys.modules,
        "services.information_refinement",
        _load_module(
            "services.information_refinement", "services/information_refinement.py"
        ),
    )
    monkeypatch.setitem(
        sys.modules,
        "services.candidate_enrichment",
        _load_module(
            "services.candidate_enrichment", "services/candidate_enrichment.py"
        ),
    )

    for name, class_name, cls in (
        ("agents.chat_agent", "ChatAgent", DummyChatAgent),
        ("agents.information_agent", "InformationAgent", DummyInformationAgent),
        ("agents.recommend_agent", "RecommendAgent", DummyRecommendAgent),
        ("agents.strategy_agent", "StrategyAgent", DummyStrategyAgent),
        ("agents.route_agent", "RouteAgent", DummyRouteAgent),
        ("agents.communication_agent", "CommunicationAgent", DummyCommunicationAgent),
        ("agents.booking_agent", "BookingAgent", DummyBookingAgent),
        ("services.booking_provider", "CtripMockProvider", DummyBookingProvider),
    ):
        module = types.ModuleType(name)
        setattr(module, class_name, cls)
        monkeypatch.setitem(sys.modules, name, module)


@pytest.fixture
def graph(monkeypatch):
    _register_graph_modules(monkeypatch)
    graph_module = _load_module("travel_graph_under_test", "workflows/travel_graph.py")
    return graph_module.TravelGraph()


def test_new_session_tracks_all_grouped_place_selections(graph):
    state = graph.get_session_state("grouped")

    assert state["restaurants"] == []
    assert state["hotels"] == []
    assert state["selected_restaurants"] == []
    assert state["selected_hotel"] is None


def test_new_and_migrated_sessions_have_json_safe_candidate_refinement_state(graph):
    expected_search_state = {
        category: {
            "next_page_token": None,
            "seen_ids": [],
            "exhausted": False,
            "last_query": None,
            "last_error": None,
        }
        for category in ("attractions", "restaurants", "hotels")
    }

    new_state = graph.get_session_state("new-refinement")
    graph.session_states["legacy"] = {"user_info": {"city": "上海"}}
    migrated_state = graph.get_session_state("legacy")

    for state in (new_state, migrated_state):
        assert state["information_refinement"] is None
        assert state["information_message"] is None
        assert state["candidate_delta"] == {}
        assert state["candidate_search_state"] == expected_search_state
        assert state["candidate_price_context"] == {
            "currency": "CNY",
            "stay_dates": None,
            "hotel_quotes_are_mock": True,
        }

    graph.session_states["partial"] = {
        "user_info": {"city": "上海"},
        "candidate_search_state": {
            "restaurants": {"seen_ids": ["persisted-r1"]}
        },
        "candidate_price_context": {"currency": "CNY"},
    }

    partial_state = graph.get_session_state("partial")

    assert partial_state["candidate_search_state"]["restaurants"] == {
        "next_page_token": None,
        "seen_ids": ["persisted-r1"],
        "exhausted": False,
        "last_query": None,
        "last_error": None,
    }
    assert partial_state["candidate_search_state"]["attractions"] == expected_search_state["attractions"]
    assert partial_state["candidate_search_state"]["hotels"] == expected_search_state["hotels"]
    assert partial_state["candidate_price_context"] == {
        "currency": "CNY",
        "stay_dates": None,
        "hotel_quotes_are_mock": True,
    }


def test_migration_normalizes_malformed_candidate_and_date_state(graph):
    graph.session_states["malformed"] = {
        "user_info": {},
        "candidate_delta": {
            "attractions": "not-a-list",
            "restaurants": [{"id": "r2"}],
            "hotels": None,
            "unexpected": [],
        },
        "candidate_search_state": {
            "attractions": {
                "next_page_token": 123,
                "seen_ids": ["a1", "", "a1", 9, True, "a2"],
                "exhausted": "yes",
                "last_query": [],
                "last_error": RuntimeError("secret-state-error"),
            },
            "restaurants": [],
            "unexpected": {"seen_ids": ["x"]},
        },
        "candidate_price_context": {
            "currency": "yuan",
            "stay_dates": {"check_in": 1, "check_out": []},
            "hotel_quotes_are_mock": "yes",
            "unexpected": object(),
        },
        "trip_date_status": {
            "status": "resolved",
            "value": 20260801,
            "source_text": [],
            "error": object(),
        },
    }

    state = graph.get_session_state("malformed")

    assert state["candidate_delta"] == {"restaurants": [{"id": "r2"}]}
    assert set(state["candidate_search_state"]) == {
        "attractions",
        "restaurants",
        "hotels",
    }
    assert state["candidate_search_state"]["attractions"] == {
        "next_page_token": None,
        "seen_ids": ["a1", "a2"],
        "exhausted": False,
        "last_query": None,
        "last_error": None,
    }
    assert state["candidate_search_state"]["restaurants"] == graph._new_candidate_search_state()["restaurants"]
    assert state["candidate_price_context"] == graph._new_candidate_price_context()
    assert state["trip_date_status"] == graph._missing_trip_date_status()


def test_loading_session_state_returns_deeply_isolated_snapshot(graph):
    graph.session_states["session-one"] = deepcopy(graph.state)
    graph.session_states["session-one"]["user_info"] = {
        "city": "上海",
        "nested": {"tags": ["original"]},
    }
    graph.session_states["session-two"] = deepcopy(graph.state)
    graph.session_states["session-two"]["user_info"] = {"city": "东京"}

    loaded = graph.get_session_state("session-one")
    loaded["user_info"]["nested"]["tags"].append("caller-mutation")
    loaded["candidate_search_state"]["restaurants"]["seen_ids"].append("r1")

    reloaded = graph.get_session_state("session-one")
    other = graph.get_session_state("session-two")
    assert reloaded["user_info"]["nested"]["tags"] == ["original"]
    assert reloaded["candidate_search_state"]["restaurants"]["seen_ids"] == []
    assert other["user_info"] == {"city": "东京"}


def test_process_result_and_current_state_are_deeply_isolated_snapshots(graph):
    graph.session_states["snapshot"] = deepcopy(graph.state)
    graph.session_states["snapshot"]["user_info"] = {
        "city": "上海",
        "nested": {"tags": ["original"]},
    }

    result = graph.process_step("complete", session_id="snapshot", user_input="你好")
    current = graph.get_current_state()
    result["state"]["user_info"]["nested"]["tags"].append("result-mutation")
    current["user_info"]["nested"]["tags"].append("current-mutation")

    expected = ["original"]
    assert graph.state["user_info"]["nested"]["tags"] == expected
    assert graph.get_current_state()["user_info"]["nested"]["tags"] == expected
    assert graph.get_session_state("snapshot")["user_info"]["nested"]["tags"] == expected


def test_information_isolates_a_failed_hotel_search(graph):
    graph.state["user_info"] = {"city": "上海", "days": "1", "start_date": "2026-08-01"}

    result = graph._process_information()

    assert result["attractions"]
    assert result["restaurants"]
    assert result["hotels"] == []
    assert result["place_errors"]["hotels"] == "provider_unavailable"
    assert "Google lodging unavailable" not in repr(result)


def test_initial_information_tracks_pages_enrichment_and_price_context(graph):
    graph.state["user_info"] = {
        "city": "上海",
        "days": "2",
        "people": "2",
        "start_date": "2026-08-01",
    }
    pages = {
        "restaurant": {
            "candidates": [
                {
                    "id": "r1",
                    "kind": "restaurant",
                    "name": "本帮菜",
                    "price_level": "2",
                    "rating": {"value": 4.7},
                    "amenities": {"name": "吧台"},
                    "recommendation_reasons": "本地风味",
                },
                {
                    "id": "r1",
                    "kind": "restaurant",
                    "name": "重复的本帮菜",
                    "price_level": 2,
                },
            ],
            "next_page_token": "restaurant-page-2",
        },
        "hotel": {
            "candidates": [
                {
                    "id": "h1",
                    "kind": "hotel",
                    "name": "静安酒店",
                    "price_level": [],
                    "rating": float("inf"),
                    "amenities": "含早餐",
                    "match_reasons": {"reason": "近地铁"},
                }
            ],
            "next_page_token": "hotel-page-2",
        },
    }
    graph.info_agent.get_place_candidate_page = MagicMock(
        side_effect=lambda *args, **kwargs: pages[kwargs["kind"]]
    )
    price_loader = MagicMock(
        return_value={
            "startPrice": {"currencyCode": "CNY", "units": "80"},
            "endPrice": {"currencyCode": "CNY", "units": "160"},
        }
    )
    graph.info_agent.poi_api = types.SimpleNamespace(
        get_place_price_range=price_loader
    )
    graph.booking_provider.search_hotel_rooms = MagicMock(
        return_value=[
            {
                "offer_id": "room-1",
                "room_type": "双床房",
                "nightly_rate": 520,
                "cancellation_policy": "可取消",
            }
        ]
    )

    result = graph._process_information()

    assert [item["id"] for item in result["attractions"]] == ["a1"]
    assert [item["id"] for item in result["restaurants"]] == ["r1"]
    assert result["restaurants"][0]["price_source"] == "google_price_range"
    assert result["restaurants"][0]["price_level"] is None
    assert result["restaurants"][0]["rating"] is None
    assert result["restaurants"][0]["amenities"] == []
    assert result["restaurants"][0]["recommendation_reasons"] == ["本地风味"]
    assert result["hotels"][0]["room_offer_status"] == "available"
    assert result["hotels"][0]["price_level"] is None
    assert result["hotels"][0]["rating"] is None
    assert result["hotels"][0]["amenities"] == ["含早餐"]
    assert result["hotels"][0]["match_reasons"] == []
    assert result["candidate_delta"] == {}
    assert graph.state["candidate_search_state"]["attractions"]["seen_ids"] == ["a1"]
    assert graph.state["candidate_search_state"]["restaurants"] == {
        "next_page_token": "restaurant-page-2",
        "seen_ids": ["r1"],
        "exhausted": False,
        "last_query": None,
        "last_error": None,
    }
    assert graph.state["candidate_search_state"]["hotels"]["next_page_token"] == "hotel-page-2"
    assert graph.state["candidate_search_state"]["hotels"]["seen_ids"] == ["h1"]
    assert graph.state["candidate_price_context"] == {
        "currency": "CNY",
        "stay_dates": {"check_in": "2026-08-01", "check_out": "2026-08-03"},
        "hotel_quotes_are_mock": True,
    }
    assert graph.info_agent.get_place_candidate_page.call_count == 2
    price_loader.assert_called_once_with("r1")


def test_chat_correction_clears_stale_place_selection_before_new_search(graph):
    graph.state.update(
        {
            "user_info": {"city": "上海", "days": "2"},
            "attractions": [{"id": "shanghai-attraction", "name": "外滩"}],
            "restaurants": [{"id": "shanghai-restaurant", "name": "本帮菜"}],
            "hotels": [{"id": "shanghai-hotel", "name": "上海酒店"}],
            "selected_attractions": [{"id": "shanghai-attraction", "name": "外滩"}],
            "selected_restaurants": [{"id": "shanghai-restaurant", "name": "本帮菜"}],
            "selected_hotel": {"id": "shanghai-hotel", "name": "上海酒店"},
            "itinerary": [{"day": 1}],
            "ai_recommendation_generated": True,
        }
    )

    def corrected_info(_, state):
        state["city"] = "东京"
        return {"stream": iter([AIMessage("已修改目的地")]), "missing_fields": ["name"], "complete": False, "state": state}

    graph.chat_agent.collect_info = corrected_info
    result = graph._process_chat(user_input="目的地改为东京")

    assert result["next_step"] == "chat"
    assert graph.state["user_info"]["city"] == "东京"
    assert graph.state["attractions"] == []
    assert graph.state["restaurants"] == []
    assert graph.state["hotels"] == []
    assert graph.state["selected_attractions"] == []
    assert graph.state["selected_restaurants"] == []
    assert graph.state["selected_hotel"] is None
    assert graph.state["itinerary"] == []
    assert graph.state["ai_recommendation_generated"] is False


def test_recommend_stores_all_validated_selection_groups(graph):
    graph.state.update(
        {
            "attractions": [{"id": "a1", "name": "外滩"}],
            "restaurants": [{"id": "r1", "name": "本帮菜"}],
            "hotels": [{"id": "h1", "name": "静安酒店"}],
        }
    )

    graph.info_agent.get_place_candidate_page = MagicMock()
    result = graph._process_recommend(
        selected_attraction_ids=["a1"],
        selected_restaurant_ids=["r1"],
        selected_hotel_id="h1",
        user_input="确认我的地点选择",
    )

    assert result["next_step"] == "strategy"
    assert result["state"]["selected_restaurants"][0]["id"] == "r1"
    assert result["state"]["selected_hotel"]["id"] == "h1"
    graph.info_agent.get_place_candidate_page.assert_not_called()


@pytest.mark.parametrize(
    "selection_kwargs",
    [
        {"selected_attraction_ids": "a1"},
        {"selected_attraction_ids": [{"id": "a1"}]},
        {
            "selected_attraction_ids": ["a1"],
            "selected_restaurant_ids": [[]],
        },
        {"selected_attraction_ids": ["a1"], "selected_hotel_id": 7},
        {"selected_attraction_ids": [True]},
    ],
)
def test_malformed_selection_ids_return_generic_validation_response(
    graph, selection_kwargs
):
    graph.state.update(
        {
            "attractions": [{"id": "a1", "name": "外滩"}],
            "restaurants": [{"id": "r1", "name": "本帮菜"}],
            "hotels": [{"id": "h1", "name": "静安酒店"}],
            "selected_attractions": [],
            "selected_restaurants": [],
            "selected_hotel": None,
        }
    )

    result = graph._process_recommend(**selection_kwargs)

    assert result["next_step"] == "recommend"
    assert result["code"] == "invalid_selection"
    assert result["response"] == "选择数据格式无效，请重新选择。"
    assert "TypeError" not in repr(result)
    assert graph.state["selected_attractions"] == []
    assert graph.state["selected_restaurants"] == []
    assert graph.state["selected_hotel"] is None


def test_natural_confirmation_without_selection_stays_on_recommend(graph):
    graph.state.update(
        {
            "attractions": [{"id": "a1", "name": "外滩"}],
            "restaurants": [{"id": "r1", "name": "本帮菜"}],
            "hotels": [{"id": "h1", "name": "静安酒店"}],
            "selected_attractions": [],
            "selected_restaurants": [],
            "selected_hotel": None,
        }
    )
    graph.strategy_agent.plan_remaining_time = MagicMock()

    result = graph._process_recommend(user_input="确认，开始规划")

    assert result["next_step"] == "recommend"
    assert "选择" in result["information_message"]
    assert graph.state["itinerary"] == []
    graph.strategy_agent.plan_remaining_time.assert_not_called()


def test_more_candidates_intent_takes_priority_over_empty_selection_payload(graph):
    graph.state.update(
        {
            "user_info": {"city": "上海"},
            "attractions": [{"id": "a1", "name": "外滩"}],
        }
    )
    graph.info_agent.get_place_candidate_page = MagicMock()

    result = graph._process_recommend(
        user_input="再推荐一些景点",
        selected_attraction_ids=[],
        selected_restaurant_ids=[],
    )

    assert result["next_step"] == "recommend"
    assert result["response"] == "这次没有找到新的景点，你可以换个筛选条件。"
    graph.info_agent.get_place_candidate_page.assert_called()


def test_unknown_valid_selection_id_returns_stable_unavailable_code(graph):
    graph.state["attractions"] = [{"id": "a1", "name": "外滩"}]

    result = graph._process_recommend(selected_attraction_ids=["missing-a"])

    assert result["next_step"] == "recommend"
    assert result["code"] == "selection_unavailable"
    assert "missing-a" not in repr(result)


def test_more_restaurants_appends_unseen_delta_without_mutating_trip_state(graph):
    attraction = {"id": "a1", "name": "外滩"}
    restaurant = {"id": "r1", "kind": "restaurant", "name": "本帮菜"}
    hotel = {"id": "h1", "kind": "hotel", "name": "静安酒店"}
    user_info = {
        "city": "上海",
        "days": "2",
        "start_date": "2026-08-01",
        "accommodation_preferences": {"amenities": ["早餐"]},
    }
    itinerary = [{"day": 1, "spots": ["外滩"]}]
    graph.state.update(
        {
            "user_info": user_info,
            "attractions": [attraction],
            "restaurants": [restaurant],
            "hotels": [hotel],
            "hotel_candidates": [hotel],
            "selected_attractions": [],
            "selected_restaurants": [],
            "selected_hotel": None,
            "itinerary": itinerary,
        }
    )
    graph.state["candidate_search_state"]["restaurants"] = {
        "next_page_token": "restaurant-page-2",
        "seen_ids": [],
        "exhausted": False,
        "last_query": None,
        "last_error": None,
    }
    graph.info_agent.get_place_candidate_page = MagicMock(
        return_value={
            "candidates": [
                {"id": "r1", "kind": "restaurant", "name": "重复餐厅"},
                {
                    "id": "r2",
                    "kind": "restaurant",
                    "name": "平价面馆",
                    "price_level": 1,
                },
                {"kind": "restaurant", "name": "缺少 ID"},
            ],
            "next_page_token": "restaurant-page-3",
        }
    )
    price_loader = MagicMock(return_value=None)
    graph.info_agent.poi_api = types.SimpleNamespace(
        get_place_price_range=price_loader
    )

    result = graph._process_recommend(
        user_input="再推荐一些便宜的餐厅",
        selected_attraction_ids=["a1"],
        selected_restaurant_ids=["r1"],
        selected_hotel_id="h1",
    )

    assert result["next_step"] == "recommend"
    assert [item["id"] for item in graph.state["restaurants"]] == ["r1", "r2"]
    assert result["candidate_delta"] == {
        "restaurants": [graph.state["restaurants"][1]]
    }
    assert graph.state["restaurants"][1]["price_source"] == "price_level_estimate"
    assert graph.state["attractions"] == [attraction]
    assert graph.state["hotels"] == [hotel]
    assert graph.state["selected_attractions"] == [attraction]
    assert graph.state["selected_restaurants"] == [restaurant]
    assert graph.state["selected_hotel"] == hotel
    assert graph.state["itinerary"] == itinerary
    assert graph.state["user_info"] == user_info
    assert graph.state["candidate_search_state"]["restaurants"] == {
        "next_page_token": "restaurant-page-3",
        "seen_ids": ["r1", "r2"],
        "exhausted": False,
        "last_query": "再推荐一些便宜的餐厅",
        "last_error": None,
    }
    request_kwargs = graph.info_agent.get_place_candidate_page.call_args.kwargs
    assert request_kwargs["page_token"] == "restaurant-page-2"
    assert request_kwargs["keyword"] is None
    assert "max_price_level" not in graph.state["user_info"]
    assert graph.state["user_info"]["accommodation_preferences"] == {
        "amenities": ["早餐"]
    }
    price_loader.assert_called_once_with("r2")
    assert "新增 1 家餐厅" in result["information_message"]


def test_invalid_refinement_selection_does_not_partially_update_other_groups(graph):
    attraction = {"id": "a1", "name": "外滩"}
    graph.state.update(
        {
            "user_info": {"city": "上海"},
            "attractions": [attraction],
            "hotels": [{"id": "h1", "kind": "hotel", "name": "已有酒店"}],
            "selected_attractions": [],
            "selected_hotel": None,
        }
    )

    result = graph._process_recommend(
        user_input="更多酒店",
        selected_attraction_ids=["a1"],
        selected_hotel_id="missing-hotel",
    )

    assert result["code"] == "selection_unavailable"
    assert graph.state["selected_attractions"] == []
    assert graph.state["selected_hotel"] is None


def test_natural_preference_update_clears_derived_state_and_returns_to_chat(graph):
    user_info = {
        "city": "上海",
        "days": "2",
        "start_date": "2026-08-01",
        "budget": "中等",
    }
    graph.state.update(
        {
            "user_info": user_info,
            "attractions": [{"id": "a1"}],
            "restaurants": [{"id": "r1"}],
            "hotels": [{"id": "h1"}],
            "selected_attractions": [{"id": "a1"}],
            "selected_restaurants": [{"id": "r1"}],
            "selected_hotel": {"id": "h1"},
            "itinerary": [{"day": 1}],
            "candidate_delta": {"restaurants": [{"id": "r2"}]},
        }
    )

    result = graph._process_recommend(
        user_input="我想修改偏好",
        selected_restaurant_ids=[],
        selected_hotel_id="",
    )

    assert result["next_step"] == "chat"
    assert graph.state["user_info"] == user_info
    assert graph.state["attractions"] == []
    assert graph.state["restaurants"] == []
    assert graph.state["hotels"] == []
    assert graph.state["selected_attractions"] == []
    assert graph.state["selected_restaurants"] == []
    assert graph.state["selected_hotel"] is None
    assert graph.state["itinerary"] == []
    assert graph.state["candidate_delta"] == {}
    assert graph.state["candidate_search_state"] == graph._new_candidate_search_state()
    assert "需要修改" in result["information_message"]


def test_more_hotels_attach_dated_room_offers_and_refresh_price_context(graph):
    graph.state.update(
        {
            "user_info": {
                "city": "上海",
                "days": "3",
                "people": "2",
                "start_date": "2026-09-10",
            },
            "hotels": [{"id": "h1", "kind": "hotel", "name": "已有酒店"}],
            "hotel_candidates": [
                {"id": "h1", "kind": "hotel", "name": "已有酒店"}
            ],
        }
    )
    graph.state["candidate_search_state"]["hotels"] = {
        "next_page_token": "hotel-page-2",
        "seen_ids": ["h1"],
        "exhausted": False,
        "last_query": None,
        "last_error": None,
    }
    graph.info_agent.get_place_candidate_page = MagicMock(
        return_value={
            "candidates": [{"id": "h2", "kind": "hotel", "name": "新酒店"}],
            "next_page_token": None,
        }
    )
    graph.booking_provider.search_hotel_rooms = MagicMock(
        return_value=[
            {
                "offer_id": "h2-room",
                "room_type": "大床房",
                "nightly_rate": 680,
                "cancellation_policy": "入住前一天可取消",
            }
        ]
    )

    result = graph._process_recommend(user_input="再推荐一些住宿")

    hotel_delta = result["candidate_delta"]["hotels"]
    assert [hotel["id"] for hotel in hotel_delta] == ["h2"]
    assert hotel_delta[0]["room_offer_status"] == "available"
    assert hotel_delta[0]["stay"] == {
        "check_in": "2026-09-10",
        "check_out": "2026-09-13",
    }
    assert graph.state["candidate_price_context"]["stay_dates"] == {
        "check_in": "2026-09-10",
        "check_out": "2026-09-13",
    }
    assert graph.state["hotel_candidates"] == graph.state["hotels"]


def test_duplicate_token_page_uses_one_keyword_fallback_and_stops(graph):
    graph.state.update(
        {
            "user_info": {"city": "上海"},
            "restaurants": [{"id": "r1", "kind": "restaurant", "name": "已有餐厅"}],
        }
    )
    graph.state["candidate_search_state"]["restaurants"] = {
        "next_page_token": "restaurant-page-2",
        "seen_ids": ["r1"],
        "exhausted": False,
        "last_query": None,
        "last_error": None,
    }
    graph.info_agent.get_place_candidate_page = MagicMock(
        side_effect=[
            {
                "candidates": [{"id": "r1", "kind": "restaurant", "name": "重复"}],
                "next_page_token": "restaurant-page-3",
            },
            {
                "candidates": [{"id": "r2", "kind": "restaurant", "name": "本地小馆"}],
                "next_page_token": None,
            },
        ]
    )

    result = graph._process_recommend(user_input="再推荐本地美食餐厅")

    assert [item["id"] for item in result["candidate_delta"]["restaurants"]] == ["r2"]
    assert graph.info_agent.get_place_candidate_page.call_count == 2
    first_call, fallback_call = graph.info_agent.get_place_candidate_page.call_args_list
    assert first_call.kwargs["page_token"] == "restaurant-page-2"
    assert first_call.kwargs["keyword"] is None
    assert fallback_call.kwargs["page_token"] is None
    assert fallback_call.kwargs["keyword"] == "本地美食"
    assert graph.state["candidate_search_state"]["restaurants"]["exhausted"] is True


def test_failed_keyword_fallback_preserves_token_for_future_continuation(graph):
    graph.state.update(
        {
            "user_info": {"city": "上海"},
            "restaurants": [{"id": "r1", "kind": "restaurant", "name": "已有餐厅"}],
        }
    )
    graph.state["candidate_search_state"]["restaurants"] = {
        "next_page_token": "restaurant-page-2",
        "seen_ids": ["r1"],
        "exhausted": False,
        "last_query": None,
        "last_error": None,
    }
    graph.info_agent.get_place_candidate_page = MagicMock(
        side_effect=[
            {
                "candidates": [{"id": "r1", "kind": "restaurant", "name": "重复"}],
                "next_page_token": "restaurant-page-3",
            },
            RuntimeError("keyword-provider-secret"),
            {
                "candidates": [{"id": "r2", "kind": "restaurant", "name": "新餐厅"}],
                "next_page_token": None,
            },
        ]
    )

    first = graph._process_recommend(user_input="再推荐一些餐厅")

    assert first["candidate_delta"] == {}
    assert graph.info_agent.get_place_candidate_page.call_count == 2
    assert graph.state["candidate_search_state"]["restaurants"] == {
        "next_page_token": "restaurant-page-3",
        "seen_ids": ["r1"],
        "exhausted": False,
        "last_query": "再推荐一些餐厅",
        "last_error": "provider_unavailable",
    }
    assert graph.state["place_errors"]["restaurants"] == "provider_unavailable"
    assert "keyword-provider-secret" not in repr(first)

    second = graph._process_recommend(user_input="再推荐一些餐厅")

    assert [item["id"] for item in second["candidate_delta"]["restaurants"]] == ["r2"]
    assert graph.info_agent.get_place_candidate_page.call_count == 3
    continuation_call = graph.info_agent.get_place_candidate_page.call_args_list[2]
    assert continuation_call.kwargs["page_token"] == "restaurant-page-3"


def test_malformed_paged_responses_do_not_bypass_the_two_call_budget(graph):
    graph.state.update(
        {
            "user_info": {"city": "上海"},
            "restaurants": [{"id": "r1", "kind": "restaurant", "name": "已有餐厅"}],
        }
    )
    graph.state["candidate_search_state"]["restaurants"]["next_page_token"] = "page-2"
    graph.state["candidate_search_state"]["restaurants"]["seen_ids"] = ["r1"]
    graph.info_agent.get_place_candidate_page = MagicMock(return_value=None)
    graph.info_agent.get_restaurant_candidates = MagicMock(return_value=[])

    result = graph._process_recommend(user_input="再推荐一些餐厅")

    assert result["candidate_delta"] == {}
    assert graph.info_agent.get_place_candidate_page.call_count == 2
    graph.info_agent.get_restaurant_candidates.assert_not_called()
    assert graph.state["candidate_search_state"]["restaurants"]["last_error"] == "provider_unavailable"


def test_ambiguous_more_request_makes_no_provider_or_route_call_and_resets_delta(graph):
    graph.state.update(
        {
            "attractions": [{"id": "a1", "name": "外滩"}],
            "candidate_delta": {"restaurants": [{"id": "stale"}]},
        }
    )
    graph.info_agent.get_place_candidate_page = MagicMock()
    graph.strategy_agent.plan_remaining_time = MagicMock()

    result = graph._process_recommend(user_input="再推荐一些")

    assert result["next_step"] == "recommend"
    assert result["candidate_delta"] == {}
    assert "景点、餐厅还是住宿" in result["information_message"]
    graph.info_agent.get_place_candidate_page.assert_not_called()
    graph.strategy_agent.plan_remaining_time.assert_not_called()


def test_every_process_request_resets_stale_candidate_delta(graph):
    state = graph.get_session_state("stale-delta")
    state["candidate_delta"] = {"restaurants": [{"id": "stale"}]}

    result = graph.process_step("complete", session_id="stale-delta", user_input="你好")

    assert result["state"]["candidate_delta"] == {}
    assert graph.get_session_state("stale-delta")["candidate_delta"] == {}


def test_candidate_dedupe_is_stable_and_does_not_mutate_inputs(graph):
    existing = [{"id": "a", "name": "A"}]
    incoming = [
        {"id": "a", "name": "duplicate"},
        {"name": "missing id"},
        {"id": "b", "name": "B"},
        {"id": "b", "name": "duplicate B"},
        {"id": "c", "name": "C"},
    ]
    original_existing = [dict(item) for item in existing]
    original_incoming = [dict(item) for item in incoming]

    merged, delta = graph._merge_unseen_candidates(existing, incoming)

    assert [item["id"] for item in merged] == ["a", "b", "c"]
    assert [item["id"] for item in delta] == ["b", "c"]
    assert existing == original_existing
    assert incoming == original_incoming


def test_candidate_dedupe_skips_every_malformed_or_non_string_id(graph):
    existing = [{"id": "a", "name": "A"}]
    incoming = [
        [],
        {},
        {"id": ""},
        {"id": "   "},
        {"id": 7},
        {"id": True},
        {"id": ["b"]},
        {"id": {"value": "b"}},
        {"id": "b", "name": "B"},
    ]
    original = deepcopy(incoming)

    merged, delta = graph._merge_unseen_candidates(
        existing,
        incoming,
        historical_ids=[None, 1, True, "", "a"],
    )

    assert [candidate["id"] for candidate in merged] == ["a", "b"]
    assert [candidate["id"] for candidate in delta] == ["b"]
    assert incoming == original


def test_initial_seen_ids_include_only_unique_nonempty_strings(graph):
    graph._set_initial_candidate_search_state(
        "attractions",
        {
            "candidates": [
                [],
                {"id": 1},
                {"id": True},
                {"id": " "},
                {"id": "a1"},
                {"id": "a1"},
            ],
            "next_page_token": 99,
        },
    )

    assert graph.state["candidate_search_state"]["attractions"] == {
        "next_page_token": None,
        "seen_ids": ["a1"],
        "exhausted": True,
        "last_query": None,
        "last_error": None,
    }


def test_multiple_categories_keep_success_when_another_provider_fails(graph):
    graph.state.update(
        {
            "user_info": {"city": "上海"},
            "attractions": [{"id": "a1", "name": "外滩"}],
            "hotels": [{"id": "h1", "name": "已有酒店"}],
        }
    )
    graph.state["candidate_search_state"]["attractions"]["next_page_token"] = "a-page"
    graph.state["candidate_search_state"]["attractions"]["seen_ids"] = ["a1"]
    graph.state["candidate_search_state"]["hotels"]["next_page_token"] = "h-page"
    graph.state["candidate_search_state"]["hotels"]["seen_ids"] = ["h1"]

    def load_page(*args, **kwargs):
        if kwargs["kind"] == "attraction":
            return {
                "candidates": [
                    [],
                    {"id": 8, "name": "numeric"},
                    {"id": True, "name": "boolean"},
                    {
                        "id": "a2",
                        "kind": "attraction",
                        "name": "博物馆",
                        "recommendation_reasons": ["匹配你的兴趣：博物馆"],
                    }
                ],
                "next_page_token": None,
            }
        raise RuntimeError("secret provider payload")

    graph.info_agent.get_place_candidate_page = MagicMock(side_effect=load_page)

    result = graph._process_recommend(user_input="再推荐景点和住宿")

    assert list(result["candidate_delta"]) == ["attractions"]
    assert result["candidate_delta"]["attractions"][0]["id"] == "a2"
    assert result["candidate_delta"]["attractions"][0]["recommendation_reasons"]
    assert [item["id"] for item in graph.state["hotels"]] == ["h1"]
    assert graph.state["candidate_search_state"]["hotels"]["last_error"] == "provider_unavailable"
    assert graph.info_agent.get_place_candidate_page.call_count == 3
    assert "secret provider payload" not in repr(result)


def test_malformed_candidate_sort_attributes_are_neutralized_per_category(graph):
    graph.state["user_info"] = {"city": "上海"}
    candidates_by_kind = {
        "attraction": [
            {
                "id": "a-bad",
                "name": "属性异常景点",
                "price_level": "2",
                "rating": {"value": 4.8},
                "amenities": {"name": "亲子"},
                "recommendation_reasons": {"reason": "热门"},
            },
            {
                "id": "a-good",
                "name": "有效景点",
                "price_level": 1,
                "rating": 4.8,
                "amenities": ["亲子", 7, "", {"bad": True}],
                "recommendation_reasons": "评分高",
            },
        ],
        "restaurant": [
            {
                "id": "r-bad",
                "name": "属性异常餐厅",
                "price_level": [],
                "rating": float("nan"),
                "amenities": "露台",
                "recommendation_reasons": ["本地风味", {"bad": True}],
            },
            {
                "id": "r-good",
                "name": "有效餐厅",
                "price_level": 0,
                "rating": 4.9,
                "amenities": ["吧台"],
                "recommendation_reasons": ["高分"],
            },
        ],
        "hotel": [
            {
                "id": "h-bad",
                "name": "属性异常酒店",
                "price_level": {"level": 1},
                "rating": [4.8],
                "amenities": [{"name": "含早餐"}],
                "match_reasons": {"reason": "近地铁"},
                "recommendation_reasons": ["位置好", 5],
            },
            {
                "id": "h-good",
                "name": "有效酒店",
                "price_level": 1,
                "rating": 4.7,
                "amenities": "含早餐",
                "match_reasons": "近地铁",
                "recommendation_reasons": "评分高",
            },
        ],
    }

    def load_page(*args, **kwargs):
        return {
            "candidates": deepcopy(candidates_by_kind[kwargs["kind"]]),
            "next_page_token": None,
        }

    graph.info_agent.get_place_candidate_page = MagicMock(side_effect=load_page)
    graph.info_agent.poi_api = types.SimpleNamespace(
        get_place_price_range=MagicMock(return_value=None)
    )

    result = graph._process_recommend(
        user_input="再推荐便宜、4.5分以上、含早餐的景点、餐厅和住宿"
    )

    assert result["next_step"] == "recommend"
    assert list(result["candidate_delta"]) == [
        "attractions",
        "restaurants",
        "hotels",
    ]
    assert graph.state["place_errors"] == {}
    assert [item["id"] for item in result["candidate_delta"]["attractions"]] == [
        "a-good",
        "a-bad",
    ]
    malformed_attraction = next(
        item
        for item in result["candidate_delta"]["attractions"]
        if item["id"] == "a-bad"
    )
    assert malformed_attraction["price_level"] is None
    assert malformed_attraction["rating"] is None
    assert malformed_attraction["amenities"] == []
    assert malformed_attraction["recommendation_reasons"] == []
    valid_attraction = result["candidate_delta"]["attractions"][0]
    assert valid_attraction["amenities"] == ["亲子"]
    assert valid_attraction["recommendation_reasons"] == ["评分高"]

    malformed_restaurant = next(
        item
        for item in result["candidate_delta"]["restaurants"]
        if item["id"] == "r-bad"
    )
    assert malformed_restaurant["price_level"] is None
    assert malformed_restaurant["rating"] is None
    assert malformed_restaurant["amenities"] == ["露台"]
    assert malformed_restaurant["recommendation_reasons"] == ["本地风味"]

    malformed_hotel = next(
        item
        for item in result["candidate_delta"]["hotels"]
        if item["id"] == "h-bad"
    )
    assert malformed_hotel["price_level"] is None
    assert malformed_hotel["rating"] is None
    assert malformed_hotel["amenities"] == []
    assert malformed_hotel["match_reasons"] == []
    assert malformed_hotel["recommendation_reasons"] == ["位置好"]
    valid_hotel = next(
        item
        for item in result["candidate_delta"]["hotels"]
        if item["id"] == "h-good"
    )
    assert valid_hotel["amenities"] == ["含早餐"]
    assert valid_hotel["match_reasons"] == ["近地铁"]
    assert valid_hotel["recommendation_reasons"] == ["评分高"]
    assert "transient_candidate_filters" not in graph.state["user_info"]


def test_post_fetch_category_failure_keeps_other_category_delta(graph):
    graph.state["user_info"] = {"city": "上海"}

    def load_page(*args, **kwargs):
        candidates = {
            "attraction": [{"id": "a2", "name": "新景点"}],
            "restaurant": [{"id": "r2", "name": "新餐厅"}],
        }
        return {
            "candidates": candidates[kwargs["kind"]],
            "next_page_token": f"{kwargs['kind']}-next",
        }

    graph.info_agent.get_place_candidate_page = MagicMock(side_effect=load_page)
    graph._enrich_restaurants = MagicMock(
        side_effect=RuntimeError("POST-FETCH-SECRET")
    )

    result = graph._process_recommend(user_input="再推荐景点和餐厅")

    assert result["next_step"] == "recommend"
    assert list(result["candidate_delta"]) == ["attractions"]
    assert [item["id"] for item in graph.state["attractions"]] == ["a2"]
    assert graph.state["restaurants"] == []
    assert (
        graph.state["candidate_search_state"]["restaurants"]["last_error"]
        == "provider_unavailable"
    )
    assert graph.state["place_errors"]["restaurants"] == "provider_unavailable"
    assert graph.info_agent.get_place_candidate_page.call_count == 2
    assert "POST-FETCH-SECRET" not in repr(result)


def test_route_and_booking_prefer_the_user_selected_hotel(graph):
    hotel = {"id": "h-user", "name": "用户选中酒店", "location": {"lat": 31.2, "lng": 121.4}}
    graph.state.update(
        {
            "user_info": {"days": "1", "start_date": "2026-08-01"},
            "attractions": [{"id": "a1", "name": "外滩", "location": {"lat": 31.24, "lng": 121.49}}],
            "daily_plan": {"day1": ["外滩"]},
            "selected_hotel": hotel,
            "recommended_hotel_id": "h-ranked",
        }
    )

    graph._process_route()

    assert graph.route_agent.selected_hotel == hotel
    assert graph._pick_selected_hotel([], {})["id"] == "h-user"


def test_route_failure_returns_and_logs_only_stable_diagnostics(graph, capsys):
    graph.state.update(
        {
            "user_info": {
                "days": "ROUTE-SECRET",
                "start_date": "2026-08-01",
            },
            "attractions": [{"id": "a1", "name": "外滩"}],
        }
    )

    result = graph._process_route()

    captured = capsys.readouterr()
    assert result["next_step"] == "error"
    assert result["error"] == "internal_error"
    assert "ROUTE-SECRET" not in repr(result)
    assert "ROUTE-SECRET" not in captured.out
    assert "ROUTE-SECRET" not in captured.err


def test_mock_family_trip_keeps_grouped_selection_through_route(graph):
    """Mock a complete grouped-selection flow without calling Maps or an LLM."""
    selected_hotel = {
        "id": "hotel-family",
        "kind": "hotel",
        "name": "静安亲子酒店",
        "address": "上海市静安区",
        "rating": 4.7,
        "price_level": 3,
        "summary": "含早餐，亲子友好，配有健身房",
        "location": {"lat": 31.23, "lng": 121.45},
    }
    graph.state["user_info"] = {
        "city": "上海",
        "days": "2",
        "start_date": "2026-10-01",
        "people": "2",
        "accommodation_preference": "地铁方便、亲子友好、带早餐和健身房",
        "accommodation_preferences": {"amenities": ["早餐", "亲子", "健身房"]},
    }
    graph.info_agent.get_hotel_candidates = MagicMock(
        return_value=[
            {
                "id": "hotel-business",
                "kind": "hotel",
                "name": "外滩商务酒店",
                "rating": 4.9,
                "price_level": 4,
                "location": {"lat": 31.24, "lng": 121.49},
            },
            selected_hotel,
        ]
    )

    information = graph._process_information()
    selection = graph._process_recommend(
        selected_attraction_ids=["a1"],
        selected_restaurant_ids=["r1"],
        selected_hotel_id="hotel-family",
    )
    strategy = graph._process_strategy(user_input="确认地点选择，开始生成行程")
    route = graph._process_route()

    assert information["next_step"] == "recommend"
    assert [hotel["id"] for hotel in information["hotels"]] == ["hotel-business", "hotel-family"]
    assert selection["next_step"] == "strategy"
    assert selection["state"]["selected_restaurants"][0]["id"] == "r1"
    assert strategy["next_step"] == "route"
    assert graph.state["daily_plan"]["day1"] == ["外滩", "本帮菜"]
    assert route["next_step"] == "complete"
    assert graph.route_agent.selected_hotel["id"] == "hotel-family"


def test_google_hotel_candidate_keeps_identity_and_gets_dated_mock_room_offers(graph):
    google_hotel = {
        "id": "google-tokyo-hotel",
        "name": "东京站酒店",
        "address": "东京都千代田区",
        "rating": 4.8,
        "price_level": 4,
        "photos": [{"url": "https://example.test/hotel.jpg"}],
        "location": {"lat": 35.6812, "lng": 139.7671},
        "source": "google_places",
        "recommendation_reasons": ["靠近东京站", "评分 4.8"],
        "match_reasons": ["交通方便"],
    }
    expensive_offer = {
        "offer_id": "offer-suite",
        "room_type": "家庭套房",
        "nightly_rate": 980,
        "breakfast": "含三人早餐",
        "source_provider": "ctrip_mock",
        "check_in": "2026-10-01",
        "check_out": "2026-10-04",
        "rooms": 1,
        "cancellation_policy": "不可取消",
        "metadata": {"notes": ["mock suite"]},
    }
    lowest_offer = {
        "offer_id": "offer-twin",
        "room_type": "高级双床房",
        "nightly_rate": 620,
        "breakfast": "含双早",
        "source_provider": "ctrip_mock",
        "check_in": "2026-10-01",
        "check_out": "2026-10-04",
        "rooms": 1,
        "cancellation_policy": "入住前一天可免费取消",
        "metadata": {"notes": ["mock twin"]},
    }
    graph.state["user_info"] = {
        "city": "东京",
        "start_date": "2026-10-01",
        "days": "3",
        "people": "3",
    }
    graph.info_agent.get_hotel_candidates = MagicMock(return_value=[google_hotel])
    graph.booking_provider.search_hotel_rooms = MagicMock(
        return_value=[expensive_offer, lowest_offer]
    )

    candidates = graph._get_hotel_candidates(35.68, 139.76, {"area": "东京站"})

    candidate = candidates[0]
    for field in (
        "id",
        "name",
        "address",
        "rating",
        "photos",
        "location",
        "source",
        "recommendation_reasons",
        "match_reasons",
    ):
        assert candidate[field] == google_hotel[field]
    assert candidate["stay"] == {
        "check_in": "2026-10-01",
        "check_out": "2026-10-04",
    }
    assert candidate["room_offers"] == [expensive_offer, lowest_offer]
    assert candidate["selected_room_offer"] == lowest_offer
    assert candidate["price_display"] == "房型 ¥620/晚起（模拟报价）"
    assert candidate["price_source"] == "ctrip_mock"
    assert candidate["hotel_quotes_are_mock"] is True
    assert candidate["room_type"] == "高级双床房"
    assert candidate["nightly_rate"] == 620
    assert candidate["cancellation_policy"] == "入住前一天可免费取消"
    graph.booking_provider.search_hotel_rooms.assert_called_once_with(
        {
            "destination": "东京",
            "hotel_id": "google-tokyo-hotel",
            "hotel_name": "东京站酒店",
            "check_in": "2026-10-01",
            "check_out": "2026-10-04",
            "rooms": 1,
            "guests": 3,
        }
    )

    google_hotel["photos"][0]["url"] = "mutated-photo"
    google_hotel["location"]["lat"] = 0
    google_hotel["recommendation_reasons"].append("mutated reason")
    google_hotel["match_reasons"].append("mutated match")
    lowest_offer["nightly_rate"] = 1
    lowest_offer["room_type"] = "mutated room"
    lowest_offer["metadata"]["notes"].append("mutated note")

    assert candidate["photos"] == [{"url": "https://example.test/hotel.jpg"}]
    assert candidate["location"] == {"lat": 35.6812, "lng": 139.7671}
    assert candidate["recommendation_reasons"] == ["靠近东京站", "评分 4.8"]
    assert candidate["match_reasons"] == ["交通方便"]
    assert candidate["selected_room_offer"]["nightly_rate"] == 620
    assert candidate["selected_room_offer"]["room_type"] == "高级双床房"
    assert candidate["selected_room_offer"]["metadata"]["notes"] == ["mock twin"]
    assert candidate["room_offers"][1]["nightly_rate"] == 620
    assert candidate["nightly_rate"] == 620


@pytest.mark.parametrize(
    "start_date,provider_error",
    [
        (None, None),
        ("not-a-date", None),
        ("2026-10-01", RuntimeError("mock room provider unavailable")),
        ("2026-10-01", OSError("mock provider transport unavailable")),
    ],
)
def test_google_hotel_stays_selectable_without_dates_or_room_provider(
    graph, start_date, provider_error
):
    graph.state["user_info"] = {
        "city": "上海",
        "start_date": start_date,
        "days": "2",
        "people": "2",
    }
    graph.info_agent.get_hotel_candidates = MagicMock(
        return_value=[
            {
                "id": "google-hotel",
                "name": "静安酒店",
                "price_level": 4,
                "source": "google_places",
                "nightly_rate": 9999,
                "room_type": "stale room",
                "cancellation_policy": "stale cancellation",
                "selected_room_offer": {"offer_id": "stale-offer"},
                "room_subtotal": 9999,
                "taxes_and_fees": 999,
                "total_price": 10998,
            }
        ]
    )
    graph.booking_provider.search_hotel_rooms = MagicMock()
    if provider_error:
        graph.booking_provider.search_hotel_rooms.side_effect = provider_error

    candidates = graph._get_hotel_candidates(31.23, 121.47, {})

    assert [candidate["id"] for candidate in candidates] == ["google-hotel"]
    assert candidates[0]["room_offers"] == []
    assert candidates[0]["price_display"] == "房价待确认"
    assert candidates[0]["price_source"] == "unavailable"
    assert candidates[0]["hotel_quotes_are_mock"] is False
    assert "nightly_rate" not in candidates[0]
    assert "room_type" not in candidates[0]
    assert "cancellation_policy" not in candidates[0]
    assert "selected_room_offer" not in candidates[0]
    assert "room_subtotal" not in candidates[0]
    assert "taxes_and_fees" not in candidates[0]
    assert "total_price" not in candidates[0]
    if provider_error:
        assert candidates[0]["room_offer_error"] == "provider_unavailable"
        assert str(provider_error) not in repr(candidates[0])
    if start_date == "2026-10-01":
        graph.booking_provider.search_hotel_rooms.assert_called_once()
    else:
        graph.booking_provider.search_hotel_rooms.assert_not_called()


def test_graph_accepts_maximum_hotel_stay_and_guest_limits(graph):
    graph.state["user_info"] = {
        "city": "上海",
        "start_date": "2026-08-01",
        "days": "30",
        "people": "40",
    }
    graph.info_agent.get_hotel_candidates = MagicMock(
        return_value=[{"id": "hotel", "name": "酒店"}]
    )
    graph.booking_provider.search_hotel_rooms = MagicMock(return_value=[])

    candidates = graph._get_hotel_candidates(31.23, 121.47, {})

    assert candidates[0]["stay"] == {
        "check_in": "2026-08-01",
        "check_out": "2026-08-31",
    }
    graph.booking_provider.search_hotel_rooms.assert_called_once_with(
        {
            "destination": "上海",
            "hotel_id": "hotel",
            "hotel_name": "酒店",
            "check_in": "2026-08-01",
            "check_out": "2026-08-31",
            "rooms": 1,
            "guests": 40,
        }
    )


@pytest.mark.parametrize(
    "start_date,days,people",
    [
        ("2026-08-01", "31", "2"),
        ("2026-08-01", "2", "41"),
        ("9999-12-31", "1", "2"),
    ],
)
def test_invalid_or_overflowing_graph_stay_keeps_hotel_unpriced(
    graph, start_date, days, people
):
    graph.state["user_info"] = {
        "city": "上海",
        "start_date": start_date,
        "days": days,
        "people": people,
    }
    graph.info_agent.get_hotel_candidates = MagicMock(
        return_value=[{"id": "hotel", "name": "酒店", "price_level": 4}]
    )
    graph.booking_provider.search_hotel_rooms = MagicMock()

    candidates = graph._get_hotel_candidates(31.23, 121.47, {})

    assert [candidate["id"] for candidate in candidates] == ["hotel"]
    assert candidates[0]["room_offers"] == []
    assert candidates[0]["price_source"] == "unavailable"
    assert "nightly_rate" not in candidates[0]
    graph.booking_provider.search_hotel_rooms.assert_not_called()
