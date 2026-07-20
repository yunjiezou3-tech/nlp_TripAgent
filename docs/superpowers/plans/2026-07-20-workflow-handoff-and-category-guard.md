# Workflow Handoff and Category Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep restaurant and hotel candidates strictly separated, then automatically generate and display the itinerary after grouped-place confirmation.

**Architecture:** The information agent will validate Google Places `types` before normalizing each result, and the map view will retain a lightweight defensive group filter. The confirmation flow will advance from strategy to route to complete without user messages; it will show stage-specific progress, lock chat input during generation, and route to results only after the itinerary exists.

**Tech Stack:** Python, Google Places legacy nearby search, Flask streaming API, Vue 3, TypeScript, Pinia, pytest, vue-tsc.

---

### Task 1: Enforce place-category boundaries

**Files:**
- Modify: `Vaiage/agents/information_agent.py`
- Modify: `Vaiage/tests/test_grouped_place_selection.py`

- [ ] **Step 1: Write a failing mixed-type Places test**

```python
def test_restaurant_candidates_exclude_lodging_results(monkeypatch):
    agent = build_information_agent(monkeypatch)
    agent.poi_api.get_nearby_places.return_value = {
        "results": [
            {"place_id": "restaurant", "name": "本帮菜", "types": ["restaurant"]},
            {"place_id": "hotel", "name": "静安酒店", "types": ["lodging"]},
            {"place_id": "hotel-restaurant", "name": "酒店餐厅", "types": ["restaurant", "lodging"]},
        ]
    }

    restaurants = agent.get_restaurant_candidates(31.2, 121.4)

    assert [item["id"] for item in restaurants] == ["restaurant"]
```

- [ ] **Step 2: Run the focused test**

Run: `cd Vaiage && pytest -q tests/test_grouped_place_selection.py::test_restaurant_candidates_exclude_lodging_results`

Expected: FAIL because `_get_place_candidates` normalizes every API result as the requested group.

- [ ] **Step 3: Filter raw Places results before normalization**

```python
def _matches_requested_kind(place, kind):
    types = set(place.get("types", []))
    if kind == "restaurant":
        return "restaurant" in types and "lodging" not in types
    if kind == "hotel":
        return "lodging" in types
    return True
```

Filter `response["results"]` with this helper before `_normalize_place_candidate`.

- [ ] **Step 4: Run backend category tests**

Run: `cd Vaiage && pytest -q tests/test_grouped_place_selection.py`

Expected: PASS.

### Task 2: Make strategy advance directly to routing

**Files:**
- Modify: `Vaiage/workflows/travel_graph.py`
- Modify: `Vaiage/tests/test_grouped_place_selection.py`
- Modify: `Vaiage/tests/test_booking_flow.py`

- [ ] **Step 1: Change strategy expectations to require a route handoff**

```python
strategy = graph._process_strategy(user_input="确认地点选择，开始生成行程")

assert strategy["next_step"] == "route"
assert strategy["state"]["daily_plan"]
```

- [ ] **Step 2: Run focused workflow tests**

Run: `cd Vaiage && pytest -q tests/test_grouped_place_selection.py::test_mock_family_trip_keeps_grouped_selection_through_route tests/test_booking_flow.py::test_strategy_generates_structured_hotel_recommendations`

Expected: FAIL because the initial strategy response currently remains on `strategy`.

- [ ] **Step 3: Return `next_step="route"` after planning strategy**

Keep the AI strategy text stream, but return the already-populated `daily_plan` with `next_step="route"`. Do not require a second chat message to progress.

- [ ] **Step 4: Run the focused workflow tests**

Run: `cd Vaiage && pytest -q tests/test_grouped_place_selection.py::test_mock_family_trip_keeps_grouped_selection_through_route tests/test_booking_flow.py::test_strategy_generates_structured_hotel_recommendations`

Expected: PASS.

### Task 3: Add an automatic, visible frontend generation pipeline

**Files:**
- Modify: `nlp_tripagent_frontend/src/views/MapView.vue`
- Modify: `nlp_tripagent_frontend/src/components/ChatAssistant.vue`

- [ ] **Step 1: Keep the user on the map page during `strategy` and `route`**

Remove the automatic route to `/` for `strategy` from both response handlers. Retain the `/results` route for `complete` only.

- [ ] **Step 2: Chain strategy and route calls after confirmation**

```ts
await triggerStrategyStep()
await triggerRouteStep()
```

Set a local planning stage before each request. `triggerRouteStep` sends `step: 'route'`; its completion response contains the itinerary and triggers `/results`.

- [ ] **Step 3: Render progress and lock interactive controls**

```vue
<section v-if="planningStage" class="planning-progress" aria-live="polite">
  <strong>{{ planningLabel }}</strong>
  <span>生成完成后将自动进入行程结果页。</span>
</section>
```

Disable map selection controls while `confirming` is true. In `ChatAssistant`, derive `isPlanning` from `sessionStore.step` being `strategy` or `route`; disable the input and display a planning placeholder while true.

- [ ] **Step 4: Type-check and build the frontend**

Run: `cd nlp_tripagent_frontend && npx vue-tsc --noEmit && npx vite build`

Expected: both commands exit `0`.

### Task 4: Full regression verification

**Files:**
- Modify: `Vaiage/tests/test_grouped_place_selection.py`
- Modify: `Vaiage/tests/test_booking_flow.py`

- [ ] **Step 1: Run all backend tests**

Run: `cd Vaiage && pytest -q tests`

Expected: PASS.

- [ ] **Step 2: Verify local service availability after backend restart**

Run: `curl -sS -o /dev/null -w '%{http_code}' http://127.0.0.1:8002/`

Expected: `200`.
