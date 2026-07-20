# Grouped Place Selection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collect structured accommodation preferences, fetch Google lodging candidates, and let users select attractions, restaurants, and one hotel before itinerary generation.

**Architecture:** Keep the existing Places API Legacy `googlemaps` client and introduce a shared place-candidate schema. The workflow will collect all three candidate groups in `information`, validate all three user selections in `recommend`, and pass the chosen restaurant and hotel locations into strategy and route planning.

**Tech Stack:** Python, Flask, Google Maps Places API Legacy via `googlemaps`, LangChain/DeepSeek, Vue 3, Pinia, TypeScript, pytest.

---

### Task 1: Place and accommodation preference contracts

**Files:**
- Modify: `Vaiage/agents/chat_agent.py`
- Modify: `Vaiage/workflows/travel_graph.py`
- Create: `Vaiage/tests/test_grouped_place_selection.py`

- [ ] **Step 1: Write failing tests for structured accommodation preference extraction and workflow defaults**

```python
def test_chat_preferences_include_structured_accommodation_fields():
    extracted = parse_accommodation_preferences(
        "住新宿站附近，预算中等，评分 4.2 以上，要早餐和健身房"
    )
    assert extracted["area"] == "新宿站附近"
    assert extracted["min_rating"] == 4.2
    assert extracted["amenities"] == ["早餐", "健身房"]


def test_new_session_has_grouped_place_state(graph):
    state = graph.get_session_state("session")
    assert state["restaurants"] == []
    assert state["hotels"] == []
    assert state["selected_restaurants"] == []
    assert state["selected_hotel"] is None
```

- [ ] **Step 2: Run the focused tests and verify they fail because the new contract is absent**

Run: `pytest tests/test_grouped_place_selection.py -k "accommodation or grouped_place_state" -v`

Expected: FAIL because `parse_accommodation_preferences` and the new state keys are missing.

- [ ] **Step 3: Add the normalized preference parser and state fields**

```python
def parse_accommodation_preferences(text: str) -> dict:
    return {
        "area": "",
        "price_level": {"min": None, "max": None},
        "min_rating": None,
        "max_distance_to_core_km": None,
        "amenities": [],
    }
```

Use the existing LLM extraction response to populate `accommodation_preference`, then normalize its text into `accommodation_preferences`. Add `restaurants`, `hotels`, `selected_restaurants`, `selected_hotel`, and `place_errors` to both default session state constructors.

- [ ] **Step 4: Run the focused tests and verify they pass**

Run: `pytest tests/test_grouped_place_selection.py -k "accommodation or grouped_place_state" -v`

Expected: PASS.

### Task 2: Google lodging and restaurant candidate retrieval

**Files:**
- Modify: `Vaiage/services/maps_api.py`
- Modify: `Vaiage/agents/information_agent.py`
- Modify: `Vaiage/workflows/travel_graph.py`
- Modify: `Vaiage/tests/test_grouped_place_selection.py`

- [ ] **Step 1: Write failing tests for `lodging` lookup, hard filters, and per-category failure isolation**

```python
def test_lodging_search_uses_lodging_type_and_normalizes_result(info_agent, poi_api):
    poi_api.get_nearby_places.return_value = {"results": [LODGING_RESULT]}
    hotels = info_agent.get_hotel_candidates(31.2, 121.4, {"min_rating": 4.2})
    poi_api.get_nearby_places.assert_called_once_with(
        location=(31.2, 121.4), type="lodging", radius=10000, language="zh-CN"
    )
    assert hotels[0]["kind"] == "hotel"


def test_failed_hotel_lookup_does_not_remove_attractions_or_restaurants(graph):
    result = graph._process_information()
    assert result["attractions"]
    assert result["restaurants"]
    assert result["hotels"] == []
    assert result["place_errors"]["hotels"]
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `pytest tests/test_grouped_place_selection.py -k "lodging or failed_hotel" -v`

Expected: FAIL because hotel lookup still uses `hotel`, no normalized candidate API exists, and category errors are not returned.

- [ ] **Step 3: Implement grouped Google candidate retrieval**

Add `InformationAgent.get_restaurant_candidates()` and `InformationAgent.get_hotel_candidates()` that use `POIApi.get_nearby_places()` with `restaurant` and `lodging` respectively. Normalize results to:

```python
{
    "id": place_id,
    "kind": "hotel",
    "name": name,
    "address": address,
    "location": {"lat": lat, "lng": lng},
    "rating": rating,
    "price_level": price_level,
    "photos": photos,
    "summary": summary,
    "types": types,
    "source": "google_places",
}
```

Apply price-level, minimum-rating, and distance filters before returning candidates. Capture category-specific exceptions in `place_errors`; return empty lists instead of Sample Hotel or Sample Restaurant data.

- [ ] **Step 4: Add LLM hotel re-ranking with amenity weights**

```python
def rank_hotels_with_preferences(hotels, preferences, core_locations):
    """Return hotel candidates with `match_score` and `match_reasons`."""
```

Prompt with the structured amenities list as weighted preferences, never claim an amenity is confirmed unless present in Google-provided content, and return fallback score ordering when the LLM response is invalid.

- [ ] **Step 5: Return all candidate groups from `information`**

Set `state["restaurants"]`, `state["hotels"]`, and `state["place_errors"]`; return `attractions`, `restaurants`, `hotels`, `place_errors`, and `map_data` in the stream completion payload. Allow transition to `recommend` whenever at least one group has candidates.

- [ ] **Step 6: Run the focused tests and verify they pass**

Run: `pytest tests/test_grouped_place_selection.py -k "lodging or failed_hotel" -v`

Expected: PASS.

### Task 3: Validate grouped selections and pass them to planning

**Files:**
- Modify: `Vaiage/workflows/travel_graph.py`
- Modify: `Vaiage/agents/strategy_agent.py`
- Modify: `Vaiage/agents/route_agent.py`
- Modify: `Vaiage/tests/test_grouped_place_selection.py`

- [ ] **Step 1: Write failing tests for selection validation and hotel route anchoring**

```python
def test_recommend_stores_all_three_validated_selection_groups(graph):
    result = graph._process_recommend(
        selected_attraction_ids=["a1"],
        selected_restaurant_ids=["r1"],
        selected_hotel_id="h1",
    )
    assert result["state"]["selected_restaurants"][0]["id"] == "r1"
    assert result["state"]["selected_hotel"]["id"] == "h1"


def test_route_uses_selected_hotel_as_day_origin_and_destination(route_agent):
    itinerary = route_agent.format_daily_plan_to_itinerary(
        {"day1": ["景点 A", "饭店 B"]}, place_map, "2026-08-01", selected_hotel=HOTEL
    )
    assert itinerary[0]["lodging"]["id"] == "h1"
    assert itinerary[0]["route_origin"]["id"] == "h1"
```

- [ ] **Step 2: Run the focused tests and verify they fail**

Run: `pytest tests/test_grouped_place_selection.py -k "selection_groups or hotel_as_day" -v`

Expected: FAIL because the workflow only accepts attraction IDs and route formatting has no hotel argument.

- [ ] **Step 3: Extend request parsing and selection validation**

Accept `selected_restaurant_ids` and `selected_hotel_id` in Flask query parsing, `VaiageApiService`, and `TravelGraph.process_step()`. In `_process_recommend()`, reject unknown IDs, require at least one selected attraction, allow zero restaurants, and allow zero or one hotel.

- [ ] **Step 4: Make selected restaurants and hotel planning constraints**

Pass selected attractions plus restaurants to `StrategyAgent.plan_remaining_time()`. Require all selected names in the generated daily plan. Extend `RouteAgent.format_daily_plan_to_itinerary(..., selected_hotel=None)` so each day records `lodging`, starts and ends route optimization at the selected hotel, and does not render the hotel as an activity.

- [ ] **Step 5: Use the selected hotel for booking drafts**

Update `TravelGraph._pick_selected_hotel()` to prefer `state["selected_hotel"]`, then the existing recommended hotel, and finally the first provider candidate.

- [ ] **Step 6: Run the focused tests and verify they pass**

Run: `pytest tests/test_grouped_place_selection.py -k "selection_groups or hotel_as_day" -v`

Expected: PASS.

### Task 4: Build the grouped selection experience

**Files:**
- Modify: `nlp_tripagent_frontend/src/types/session.ts`
- Modify: `nlp_tripagent_frontend/src/stores/session.ts`
- Modify: `nlp_tripagent_frontend/src/services/apiClient.ts`
- Modify: `nlp_tripagent_frontend/src/services/vaiageApi.ts`
- Modify: `nlp_tripagent_frontend/src/views/MapView.vue`

- [ ] **Step 1: Add frontend types and request payload fields**

```ts
interface PlaceCandidate {
  id: string
  kind: 'attraction' | 'restaurant' | 'hotel'
  name: string
  address?: string
  rating?: number
  price_level?: number
  location?: { lat: number; lng: number }
  match_reasons?: string[]
}
```

Add `restaurants`, `hotels`, `selectedRestaurants`, `selectedHotel`, and `placeErrors` to the session store. Extend streaming options and completion response types with grouped candidates and selected IDs.

- [ ] **Step 2: Render and select all groups on the map page**

Render three distinct sections: multi-select attractions, multi-select restaurants, and single-select hotels. Display hotel `match_reasons`, disable confirmation until at least one attraction is selected, and show a group-specific unavailable message from `placeErrors`.

- [ ] **Step 3: Submit grouped selection once**

```ts
await vaiageApiService.streamChatMessage('确认我的地点选择', onChunk, {
  step: 'recommend',
  selectedAttractionIds,
  selectedRestaurantIds,
  selectedHotelId,
})
```

Keep existing attraction map markers; selecting a restaurant or hotel updates only its own group state and does not clear attraction selections.

- [ ] **Step 4: Run frontend verification**

Run: `npm run build`

Expected: `vue-tsc -b && vite build` exits with code 0. If `npm` is unavailable in the execution environment, record that limitation and run the available TypeScript or static validation command instead.

### Task 5: Regression verification

**Files:**
- Modify: `Vaiage/tests/test_booking_flow.py`
- Modify: `Vaiage/tests/test_grouped_place_selection.py`

- [ ] **Step 1: Add regression coverage for hotel booking precedence**

```python
def test_booking_prefers_user_selected_hotel_over_ranked_recommendation(graph):
    graph.state["selected_hotel"] = {"id": "h-user", "name": "用户选中酒店"}
    graph.state["recommended_hotel_id"] = "h-ranked"
    assert graph._pick_selected_hotel([], {})["id"] == "h-user"
```

- [ ] **Step 2: Run the full backend test suite**

Run: `pytest tests -v`

Expected: all booking-flow and grouped-place-selection tests pass.

- [ ] **Step 3: Compile Python production modules**

Run: `python -m compileall agents services workflows main.py`

Expected: exit code 0 with no syntax errors.

- [ ] **Step 4: Review the final diff**

Run: `git diff --check && git diff --stat`

Expected: no whitespace errors; only intended backend, frontend, test, and plan files changed.
