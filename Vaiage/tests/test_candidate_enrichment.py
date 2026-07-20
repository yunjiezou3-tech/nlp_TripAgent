import copy
import importlib.util
import sys
import types
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
import requests


ROOT = Path(__file__).resolve().parents[1]


class Message:
    def __init__(self, content):
        self.content = content


def _load_module(module_name, relative_path):
    spec = importlib.util.spec_from_file_location(module_name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _install_information_stubs(monkeypatch):
    langchain_openai = types.ModuleType("langchain_openai")
    langchain_openai.ChatOpenAI = object
    messages = types.ModuleType("langchain_core.messages")
    messages.SystemMessage = Message
    messages.HumanMessage = Message
    monkeypatch.setitem(sys.modules, "langchain_openai", langchain_openai)
    monkeypatch.setitem(sys.modules, "langchain_core.messages", messages)

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


def _information_agent(monkeypatch, module_name="candidate_information_agent"):
    _install_information_stubs(monkeypatch)
    module = _load_module(module_name, "agents/information_agent.py")
    agent = module.InformationAgent.__new__(module.InformationAgent)
    agent.maps_api_key = "maps-test-key"
    agent.llm = None
    agent.poi_api = MagicMock()
    return agent


def _enricher(loader=None, module_name="candidate_enrichment_under_test"):
    module = _load_module(module_name, "services/candidate_enrichment.py")
    return module.PlaceCandidateEnricher(price_range_loader=loader)


def _money(currency, units, nanos=0):
    return {"currencyCode": currency, "units": units, "nanos": nanos}


def test_nearby_places_keeps_legacy_positional_arguments_and_supports_keyword():
    module = _load_module("maps_api_legacy_under_test", "services/maps_api.py")
    gmaps = MagicMock()
    api = module.POIApi(api_key="secret", gmaps_client=gmaps, http_get=MagicMock())

    api.get_nearby_places((31.2, 121.4), "restaurant", 2500, "zh-CN", keyword="本帮菜")

    gmaps.places_nearby.assert_called_once_with(
        location=(31.2, 121.4),
        radius=2500,
        type="restaurant",
        language="zh-CN",
        keyword="本帮菜",
    )


def test_nearby_places_token_call_uses_only_google_page_token_contract():
    module = _load_module("maps_api_token_under_test", "services/maps_api.py")
    gmaps = MagicMock()
    api = module.POIApi(api_key="secret", gmaps_client=gmaps, http_get=MagicMock())

    api.get_nearby_places(None, None, page_token="next-page")

    gmaps.places_nearby.assert_called_once_with(page_token="next-page")


def test_get_place_price_range_uses_places_new_with_encoded_id_and_injected_http():
    module = _load_module("maps_api_price_under_test", "services/maps_api.py")
    expected = {
        "startPrice": _money("CNY", "80"),
        "endPrice": _money("CNY", "160"),
    }
    response = SimpleNamespace(status_code=200, json=lambda: {"priceRange": expected})
    http_get = MagicMock(return_value=response)
    api = module.POIApi(api_key="secret", gmaps_client=MagicMock(), http_get=http_get)

    assert api.get_place_price_range("places/上海 1", language="zh-CN") == expected
    http_get.assert_called_once_with(
        "https://places.googleapis.com/v1/places/places%2F%E4%B8%8A%E6%B5%B7%201",
        headers={"X-Goog-Api-Key": "secret", "X-Goog-FieldMask": "priceRange"},
        params={"languageCode": "zh-CN"},
        timeout=5,
    )


def test_get_place_price_range_without_key_never_requires_google_client(monkeypatch):
    monkeypatch.delenv("MAPS_API_KEY", raising=False)
    module = _load_module("maps_api_no_key_under_test", "services/maps_api.py")
    http_get = MagicMock()

    api = module.POIApi(http_get=http_get)

    assert api.get_place_price_range("place-id") is None
    assert api.gmaps is None
    http_get.assert_not_called()


@pytest.mark.parametrize(
    "api_key,response",
    [
        (None, None),
        ("secret", SimpleNamespace(status_code=503, json=MagicMock())),
        ("secret", SimpleNamespace(status_code=200, json=lambda: [])),
        ("secret", SimpleNamespace(status_code=200, json=lambda: {})),
        ("secret", SimpleNamespace(status_code=200, json=lambda: {"priceRange": []})),
        ("secret", SimpleNamespace(status_code=200, json=MagicMock(side_effect=ValueError("bad json")))),
    ],
)
def test_get_place_price_range_returns_none_for_missing_key_or_bad_response(
    monkeypatch, api_key, response
):
    monkeypatch.delenv("MAPS_API_KEY", raising=False)
    module = _load_module(f"maps_api_bad_response_{id(response)}", "services/maps_api.py")
    http_get = MagicMock(return_value=response)
    api = module.POIApi(api_key=api_key, gmaps_client=MagicMock(), http_get=http_get)

    assert api.get_place_price_range("place-id") is None
    if api_key is None:
        http_get.assert_not_called()


@pytest.mark.parametrize("error", [requests.Timeout("slow"), requests.RequestException("offline")])
def test_get_place_price_range_returns_none_for_request_errors_without_leaking_secrets(
    error, capsys
):
    module = _load_module(f"maps_api_request_error_{type(error).__name__}", "services/maps_api.py")
    http_get = MagicMock(side_effect=error)
    api = module.POIApi(api_key="do-not-log-key", gmaps_client=MagicMock(), http_get=http_get)

    assert api.get_place_price_range("private-photo-url-fragment") is None
    output = capsys.readouterr()
    combined = output.out + output.err
    assert "do-not-log-key" not in combined
    assert "private-photo-url-fragment" not in combined


@pytest.mark.parametrize("failure_point", ["http_get", "response_json"])
def test_get_place_price_range_fails_closed_for_any_injected_http_exception(
    failure_point, capsys
):
    module = _load_module(
        f"maps_api_runtime_error_{failure_point}", "services/maps_api.py"
    )
    secret_error = RuntimeError("raw-provider-payload secret-auth-header")
    if failure_point == "http_get":
        http_get = MagicMock(side_effect=secret_error)
    else:
        response = SimpleNamespace(
            status_code=200,
            json=MagicMock(side_effect=secret_error),
        )
        http_get = MagicMock(return_value=response)
    api = module.POIApi(
        api_key="runtime-secret-key",
        gmaps_client=MagicMock(),
        http_get=http_get,
    )

    assert api.get_place_price_range("private-place-id") is None
    output = capsys.readouterr()
    combined = output.out + output.err
    assert "runtime-secret-key" not in combined
    assert "private-place-id" not in combined
    assert "raw-provider-payload" not in combined
    assert "secret-auth-header" not in combined


def test_candidate_page_returns_token_passes_keyword_and_keeps_three_photo_attributions(monkeypatch):
    agent = _information_agent(monkeypatch, "candidate_page_information_agent")
    agent.poi_api.get_nearby_places.return_value = {
        "results": [
            {
                "place_id": "r1",
                "name": "海景餐厅",
                "types": ["restaurant"],
                "rating": 4.7,
                "photos": [
                    {
                        "photo_reference": f"photo-{index}",
                        "width": 1000 + index,
                        "height": 700 + index,
                        "html_attributions": [f"<a>摄影师 {index}</a>"],
                    }
                    for index in range(4)
                ],
            }
        ],
        "next_page_token": "token-2",
    }

    page = agent.get_place_candidate_page(
        31.2,
        121.4,
        "restaurant",
        "restaurant",
        radius=3000,
        keyword="江景",
        user_prefs={"budget": "high"},
    )

    agent.poi_api.get_nearby_places.assert_called_once_with(
        location=(31.2, 121.4),
        type="restaurant",
        radius=3000,
        language="zh-CN",
        keyword="江景",
    )
    assert page["next_page_token"] == "token-2"
    assert [photo["attributions"] for photo in page["candidates"][0]["photos"]] == [
        ["<a>摄影师 0</a>"],
        ["<a>摄影师 1</a>"],
        ["<a>摄影师 2</a>"],
    ]
    assert len(page["candidates"][0]["photos"]) == 3


def test_photo_normalization_skips_malformed_entries_until_three_valid_photos(monkeypatch):
    agent = _information_agent(monkeypatch, "candidate_valid_photos_information_agent")
    source_photos = [
        {},
        None,
        {"photo_reference": None},
        {"photo_reference": ""},
        {"photo_reference": "   "},
        {"photo_reference": 123},
        {
            "photo_reference": "valid-1",
            "width": 901,
            "height": 601,
            "html_attributions": ["credit-1"],
        },
        {
            "photo_reference": "valid-2",
            "width": 902,
            "height": 602,
            "html_attributions": ["credit-2"],
        },
        {
            "photo_reference": "valid-3",
            "width": 903,
            "height": 603,
            "html_attributions": ["credit-3"],
        },
        {
            "photo_reference": "valid-4",
            "width": 904,
            "height": 604,
            "html_attributions": ["credit-4"],
        },
    ]

    candidate = agent._normalize_place_candidate(
        {"place_id": "r1", "name": "餐厅", "photos": source_photos},
        "restaurant",
    )

    assert candidate["photos"] == [
        {
            "url": "https://maps.googleapis.com/maps/api/place/photo?maxwidth=800&photoreference=valid-1&key=maps-test-key",
            "width": 901,
            "height": 601,
            "attributions": ["credit-1"],
        },
        {
            "url": "https://maps.googleapis.com/maps/api/place/photo?maxwidth=800&photoreference=valid-2&key=maps-test-key",
            "width": 902,
            "height": 602,
            "attributions": ["credit-2"],
        },
        {
            "url": "https://maps.googleapis.com/maps/api/place/photo?maxwidth=800&photoreference=valid-3&key=maps-test-key",
            "width": 903,
            "height": 603,
            "attributions": ["credit-3"],
        },
    ]


def test_photo_attributions_are_deeply_isolated_from_source_mutation(monkeypatch):
    agent = _information_agent(monkeypatch, "candidate_photo_copy_information_agent")
    source_attributions = [["credit-1"], ["credit-2"]]
    place = {
        "place_id": "r1",
        "name": "餐厅",
        "photos": [
            {
                "photo_reference": "valid-1",
                "width": 901,
                "height": 601,
                "html_attributions": source_attributions,
            }
        ],
    }

    candidate = agent._normalize_place_candidate(place, "restaurant")
    source_attributions[0].append("mutated")
    source_attributions.append(["late-credit"])
    place["photos"][0]["width"] = 1

    assert candidate["photos"][0] == {
        "url": "https://maps.googleapis.com/maps/api/place/photo?maxwidth=800&photoreference=valid-1&key=maps-test-key",
        "width": 901,
        "height": 601,
        "attributions": [["credit-1"], ["credit-2"]],
    }


def test_candidate_page_passes_page_token_and_preserves_restaurant_lodging_separation(monkeypatch):
    agent = _information_agent(monkeypatch, "candidate_token_information_agent")
    agent.poi_api.get_nearby_places.return_value = {
        "results": [
            {"place_id": "r1", "name": "餐厅", "types": ["restaurant"], "rating": 4.5},
            {"place_id": "h1", "name": "酒店", "types": ["lodging"], "rating": 4.9},
            {
                "place_id": "mixed",
                "name": "酒店餐厅",
                "types": ["restaurant", "lodging"],
                "rating": 4.8,
            },
        ]
    }

    page = agent.get_place_candidate_page(
        31.2, 121.4, "restaurant", "restaurant", page_token="token-2"
    )

    agent.poi_api.get_nearby_places.assert_called_once_with(
        location=(31.2, 121.4),
        type="restaurant",
        radius=10000,
        language="zh-CN",
        page_token="token-2",
    )
    assert [candidate["id"] for candidate in page["candidates"]] == ["r1"]
    assert page["next_page_token"] is None


def test_existing_list_candidate_method_delegates_to_page_method(monkeypatch):
    agent = _information_agent(monkeypatch, "candidate_list_information_agent")
    candidates = [{"id": "r1", "name": "餐厅"}]
    agent.get_place_candidate_page = MagicMock(
        return_value={"candidates": candidates, "next_page_token": "ignored-by-list-method"}
    )

    result = agent._get_place_candidates(
        31.2,
        121.4,
        "restaurant",
        "restaurant",
        radius=5000,
        user_prefs={"budget": "medium"},
        keyword="面馆",
    )

    assert result == candidates
    agent.get_place_candidate_page.assert_called_once_with(
        31.2,
        121.4,
        "restaurant",
        "restaurant",
        radius=5000,
        preferences=None,
        core_locations=None,
        user_prefs={"budget": "medium"},
        page_token=None,
        keyword="面馆",
    )


def test_google_cny_price_range_is_preferred_without_mutating_candidate():
    calls = []
    price_range = {
        "startPrice": _money("CNY", "80"),
        "endPrice": _money("CNY", 160),
    }
    candidate = {
        "id": "r1",
        "name": "本帮菜",
        "price_level": 1,
        "photos": [{"url": "photo"}],
        "recommendation_reasons": ["评分 4.8"],
    }
    original = copy.deepcopy(candidate)
    enricher = _enricher(lambda place_id: calls.append(place_id) or price_range)

    enriched = enricher.enrich_restaurant(candidate)

    assert enriched is not candidate
    assert candidate == original
    assert calls == ["r1"]
    assert enriched["price_display"] == "Google 价格区间 ¥80-160"
    assert "人均" not in enriched["price_display"]
    assert enriched["price_source"] == "google_price_range"
    assert enriched["id"] == "r1"
    assert enriched["photos"] == candidate["photos"]
    assert enriched["recommendation_reasons"] == candidate["recommendation_reasons"]


@pytest.mark.parametrize(
    "currency,start,end,expected",
    [
        ("USD", _money("USD", "10", 500_000_000), _money("USD", 20, 250_000_000), "Google 价格区间 USD 10.5-20.25"),
        ("JPY", _money("JPY", "1200"), _money("JPY", 2400), "Google 价格区间 JPY 1200-2400"),
    ],
)
def test_google_range_preserves_non_cny_currency_and_nanos(currency, start, end, expected):
    enricher = _enricher(
        lambda _: {"startPrice": start, "endPrice": end},
        module_name=f"candidate_enrichment_currency_{currency}",
    )

    enriched = enricher.enrich_restaurant({"id": "r1", "price_level": 0})

    assert enriched["price_display"] == expected
    assert enriched["price_source"] == "google_price_range"


@pytest.mark.parametrize(
    "candidate,expected_tier",
    [
        ({"price_level": 0}, "经济"),
        ({"price_level": 1}, "经济"),
        ({"price_level": 2}, "中等"),
        ({"price_level": 3}, "较高"),
        ({"price_level": 4}, "较高"),
        ({}, None),
        ({"price_level": -1}, None),
        ({"price_level": 5}, None),
        ({"price_level": "2"}, None),
        ({"price_level": 2.0}, None),
        ({"price_level": True}, None),
    ],
)
def test_google_range_derives_tier_only_from_valid_integer_price_level(
    candidate, expected_tier
):
    price_range = {
        "startPrice": _money("CNY", 80),
        "endPrice": _money("CNY", 160),
    }
    candidate = {"id": "r1", **candidate}
    enricher = _enricher(lambda _: price_range)

    enriched = enricher.enrich_restaurant(candidate)

    assert enriched["price_display"] == "Google 价格区间 ¥80-160"
    assert "人均" not in enriched["price_display"]
    assert enriched["price_source"] == "google_price_range"
    assert enriched["price_tier"] == expected_tier


@pytest.mark.parametrize(
    "units",
    [
        -(2**63),
        str(-(2**63)),
        2**63 - 1,
        str(2**63 - 1),
    ],
)
def test_google_money_units_accept_signed_int64_boundaries(units):
    enricher = _enricher(module_name=f"candidate_enrichment_int64_boundary_{repr(units)}")

    parsed = enricher._parse_money(_money("CNY", units))

    assert parsed is not None
    assert parsed[0] == "CNY"
    assert parsed[1] == int(units)


@pytest.mark.parametrize(
    "units",
    [
        True,
        False,
        -(2**63) - 1,
        str(-(2**63) - 1),
        2**63,
        str(2**63),
        "NaN",
        "nan",
        "Infinity",
        "+Infinity",
        "-Infinity",
        "inf",
        "-inf",
        "1.5",
        float("nan"),
        float("inf"),
    ],
)
def test_google_money_rejects_invalid_or_out_of_int64_units(units):
    enricher = _enricher(module_name=f"candidate_enrichment_bad_units_{repr(units)}")

    assert enricher._parse_money(_money("CNY", units)) is None


@pytest.mark.parametrize(
    "units",
    [True, 2**63, str(2**63), "NaN", "Infinity"],
)
def test_invalid_google_money_units_fall_back_instead_of_using_google_label(units):
    price_range = {
        "startPrice": _money("CNY", units),
        "endPrice": _money("CNY", 160),
    }
    enricher = _enricher(lambda _: price_range)

    enriched = enricher.enrich_restaurant({"id": "r1", "price_level": 2})

    assert enriched["price_display"] == "参考人均 ¥80-160（估算）"
    assert enriched["price_source"] == "price_level_estimate"
    assert enriched["price_tier"] == "中等"


@pytest.mark.parametrize(
    "nanos",
    [
        True,
        False,
        "0",
        "500000000",
        1.0,
        float("nan"),
        float("inf"),
        "NaN",
        "Infinity",
        -1_000_000_000,
        1_000_000_000,
    ],
)
def test_invalid_google_money_nanos_fall_back_instead_of_using_google_label(nanos):
    price_range = {
        "startPrice": _money("CNY", 80, nanos),
        "endPrice": _money("CNY", 160),
    }
    enricher = _enricher(lambda _: price_range)

    enriched = enricher.enrich_restaurant({"id": "r1", "price_level": 2})

    assert enriched["price_display"] == "参考人均 ¥80-160（估算）"
    assert enriched["price_source"] == "price_level_estimate"
    assert enriched["price_tier"] == "中等"


@pytest.mark.parametrize(
    "nanos,expected_amount",
    [
        (-999_999_999, "-0.999999999"),
        (999_999_999, "0.999999999"),
    ],
)
def test_google_money_accepts_and_formats_valid_nanos_endpoints(
    nanos, expected_amount
):
    enricher = _enricher(module_name=f"candidate_enrichment_nanos_endpoint_{nanos}")

    parsed = enricher._parse_money(_money("CNY", 0, nanos))

    assert parsed is not None
    assert parsed[0] == "CNY"
    assert enricher._format_amount(parsed[1]) == expected_amount


@pytest.mark.parametrize(
    "price_level,expected_display,expected_tier",
    [
        (0, "参考人均 ¥20-40（估算）", "经济"),
        (1, "参考人均 ¥40-80（估算）", "经济"),
        (2, "参考人均 ¥80-160（估算）", "中等"),
        (3, "参考人均 ¥160-300（估算）", "较高"),
        (4, "参考人均 ¥300-600（估算）", "较高"),
    ],
)
def test_price_level_fallback_mapping(price_level, expected_display, expected_tier):
    enricher = _enricher(module_name=f"candidate_enrichment_level_{price_level}")

    enriched = enricher.enrich_restaurant({"id": "r1", "price_level": price_level})

    assert enriched["price_display"] == expected_display
    assert enriched["price_source"] == "price_level_estimate"
    assert enriched["price_tier"] == expected_tier


@pytest.mark.parametrize(
    "price_range",
    [
        {},
        {"startPrice": _money("CNY", 80)},
        {"startPrice": _money("CNY", 80), "endPrice": _money("USD", 160)},
        {"startPrice": _money("CNY", 180), "endPrice": _money("CNY", 160)},
        {"startPrice": _money("CNY", -1), "endPrice": _money("CNY", 160)},
        {"startPrice": _money("CNY", "bad"), "endPrice": _money("CNY", 160)},
        {"startPrice": _money("CNY", 80, 1_000_000_000), "endPrice": _money("CNY", 160)},
    ],
)
def test_invalid_google_range_falls_back_to_price_level(price_range):
    enricher = _enricher(
        lambda _: price_range,
        module_name=f"candidate_enrichment_invalid_{id(price_range)}",
    )

    enriched = enricher.enrich_restaurant({"id": "r1", "price_level": 2})

    assert enriched["price_display"] == "参考人均 ¥80-160（估算）"
    assert enriched["price_source"] == "price_level_estimate"
    assert enriched["price_tier"] == "中等"


def test_loader_exception_falls_back_and_is_called_once():
    calls = []

    def unavailable(place_id):
        calls.append(place_id)
        raise requests.Timeout("slow")

    enricher = _enricher(unavailable, "candidate_enrichment_loader_error")

    enriched = enricher.enrich_restaurant({"id": "r1", "price_level": 3})

    assert calls == ["r1"]
    assert enriched["price_source"] == "price_level_estimate"
    assert enriched["price_tier"] == "较高"


@pytest.mark.parametrize("price_level", [None, -1, 5, "2", 2.0, True])
def test_missing_or_non_integer_price_level_is_unavailable(price_level):
    enricher = _enricher(module_name=f"candidate_enrichment_unavailable_{repr(price_level)}")

    enriched = enricher.enrich_restaurant({"id": "r1", "price_level": price_level})

    assert enriched["price_display"] == "价格待确认"
    assert enriched["price_source"] == "unavailable"
    assert enriched["price_tier"] is None


def test_enrich_restaurants_calls_loader_at_most_once_per_supplied_candidate():
    calls = []
    enricher = _enricher(lambda place_id: calls.append(place_id), "candidate_enrichment_many")
    restaurants = [{"id": "r1", "price_level": 1}, {"id": "r2", "price_level": 2}]

    enriched = enricher.enrich_restaurants(restaurants)

    assert calls == ["r1", "r2"]
    assert [candidate["price_source"] for candidate in enriched] == [
        "price_level_estimate",
        "price_level_estimate",
    ]
