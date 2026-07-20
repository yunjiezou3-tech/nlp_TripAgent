# Chat Information Refinement And Pricing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让偏好收集结果可读且可纠正，在 Information 阶段支持按景点、餐厅、住宿分别追加个性化候选，并为餐厅、住宿补齐图片和可解释价格信息。

**Architecture:** 保留现有 `TravelGraph` 编排职责，新增 `DateResolver`、`InformationRefinementService`、`PlaceCandidateEnricher` 三个轻量服务。Google Places 继续负责地点、图片与可用价格区间；酒店具体日期的房型报价由 `CtripMockProvider` 提供，前端仅消费统一候选结构和增量 `candidate_delta`。

**Tech Stack:** Python 3、Flask、LangGraph/LangChain、Google Maps Places API、pytest、Vue 3、Pinia、TypeScript、Vite。

---

## Implementation Constraints

- 当前工作区包含既有未提交改动，执行时不得回退或覆盖这些改动；提交前只暂存本任务确认过的文件/补丁。
- 日期计算必须注入 `current_date`，测试固定为 `2026-07-20`，不得依赖测试运行当天。
- Google Places 的 `priceRange` 仅作为地点参考价格，不宣称为指定日期实时房价。
- 酒店具体房型和价格必须带 `source_provider: "ctrip_mock"` 与“模拟报价”标识。
- “更多推荐”只追加去重后的新候选，已有候选和已选 ID 均保持不变。
- 临时条件只作用于本次增量检索，不回写长期 `user_info`。
- 每个任务先写失败测试，再写最小实现；完成后运行该任务定向测试。

## Task 1: Add Deterministic Trip-Date Resolution

**Files:**

- Create: `Vaiage/services/date_resolver.py`
- Create: `Vaiage/tests/test_date_resolver.py`
- Modify: `Vaiage/workflows/travel_graph.py`

- [ ] **Step 1: Write failing date resolver tests**

```python
from datetime import date

from services.date_resolver import DateResolver


def test_resolves_relative_chinese_date_from_injected_today():
    resolver = DateResolver(today=date(2026, 7, 20))

    result = resolver.resolve("下周五")

    assert result == {
        "status": "resolved",
        "value": "2026-07-31",
        "source_text": "下周五",
        "error": None,
    }


def test_rejects_past_date():
    resolver = DateResolver(today=date(2026, 7, 20))

    result = resolver.resolve("2026-07-01")

    assert result["status"] == "invalid"
    assert result["error"] == "past_date"


def test_marks_unspecified_date_as_missing():
    resolver = DateResolver(today=date(2026, 7, 20))

    assert resolver.resolve("not decided")["status"] == "missing"
```

- [ ] **Step 2: Run the tests and confirm the expected failure**

Run from `Vaiage/`:

```bash
pytest -q tests/test_date_resolver.py
```

Expected: collection fails because `services.date_resolver` does not exist.

- [ ] **Step 3: Implement `DateResolver` with explicit and common relative dates**

```python
class DateResolver:
    def __init__(self, today: date | None = None):
        self.today = today or datetime.now(ZoneInfo("Asia/Shanghai")).date()

    def resolve(self, value: str | None) -> dict[str, str | None]:
        source_text = str(value or "").strip()
        if source_text.lower() in {"", "none", "not decided", "待定", "未确定"}:
            return self._result("missing", None, source_text or None, None)
        target = self._parse_explicit(source_text) or self._parse_relative(source_text)
        if target is None:
            return self._result("invalid", None, source_text, "unrecognized_date")
        if target < self.today:
            return self._result("invalid", None, source_text, "past_date")
        return self._result("resolved", target.isoformat(), source_text, None)
```

`resolve()` must always return `status/value/source_text/error`. Resolve explicit dates, reject past dates, and leave unrecognized text as `invalid` so Chat can ask a focused date question.

- [ ] **Step 4: Add a graph-level date gate before Information**

In `TravelGraph._process_chat`, resolve `user_info.start_date` after extraction. Only transition to Information when the date status is `resolved`; otherwise keep `step="chat"` and include a date-specific missing question.

Add state fields:

```python
"current_date": "2026-07-20",
"trip_date_status": {
    "status": "missing",
    "value": None,
    "source_text": None,
    "error": None,
},
```

Remove the current `_process_information` fallback that silently sets the trip to seven days from now.

- [ ] **Step 5: Run focused tests**

```bash
pytest -q tests/test_date_resolver.py tests/test_chat_collection.py
```

Expected: all date tests pass; existing chat collection tests remain green.

- [ ] **Step 6: Create a checkpoint commit when the touched files contain no unrelated hunks**

```bash
git add Vaiage/services/date_resolver.py Vaiage/tests/test_date_resolver.py Vaiage/workflows/travel_graph.py
git commit -m "feat: require resolvable trip dates"
```

If `travel_graph.py` contains inseparable pre-existing user changes, do not commit it; record the verification result and continue without altering those changes.

## Task 2: Format Collected Preferences And Restrict Follow-Up Questions

**Files:**

- Modify: `Vaiage/agents/chat_agent.py`
- Modify: `Vaiage/tests/test_chat_collection.py`
- Modify: `Vaiage/workflows/travel_graph.py`

- [ ] **Step 1: Add failing formatter and missing-value tests**

```python
def test_collection_response_lists_required_and_optional_preferences():
    agent = build_agent_with_fake_models(question_chunks=["还需要了解您的预算。"])
    state = {
        "name": "小林",
        "origin": "上海",
        "city": "东京",
        "health_condition": "良好",
        "accommodation_preference": "亲子、含早餐、有洗衣房",
        "budget": None,
    }

    result = agent.collect_info("健康状况良好", state, current_date="2026-07-20")
    text = "".join(result["response"])

    assert text.startswith("已收集到的信息\n")
    assert "出发地：上海" in text
    assert "目的地：东京" in text
    assert "健康状况：良好" in text
    assert "住宿偏好：亲子、含早餐、有洗衣房" in text
    assert "还需要了解的信息\n" in text


def test_not_decided_start_date_is_still_missing():
    assert ChatAgent._is_missing_value("start_date", "not decided") is True
```

- [ ] **Step 2: Confirm the tests fail for the current free-form response**

```bash
pytest -q tests/test_chat_collection.py
```

Expected: new assertions fail because the response currently contains only model-generated prose.

- [ ] **Step 3: Add deterministic `CollectedInfoFormatter` behavior**

Implement a formatter in `chat_agent.py` that outputs one populated field per line in stable order. Include optional fields such as origin, hobbies, health, children, accommodation preference, dietary needs, pace, and transport preference when present.

```python
def format_collected_info(self, state: dict) -> str:
    lines = ["已收集到的信息"]
    for field in self.DISPLAY_FIELD_ORDER:
        value = state.get(field)
        if not self._is_missing_value(field, value):
            lines.append(f"{self.FIELD_LABELS[field]}：{self._display_value(value)}")
    return "\n".join(lines)
```

Wrap the question-model stream so its complete response is always:

```text
已收集到的信息
姓名：小林
出发地：上海
目的地：东京
健康状况：良好
住宿偏好：亲子、含早餐、有洗衣房

还需要了解的信息
请问您的预算范围是多少？
```

The question model receives only the missing-field list and is instructed to ask concise collection questions. It must not recommend attractions, restaurants, hotels, routes, or itineraries.

- [ ] **Step 4: Pass `current_date` through the graph call**

Update `TravelGraph._process_chat` to call:

```python
chat_result = self.chat_agent.collect_info(
    user_input,
    user_info,
    current_date=state["current_date"],
)
```

Keep the existing extractor/question model separation intact.

- [ ] **Step 5: Run chat regressions**

```bash
pytest -q tests/test_chat_collection.py
```

Expected: collected information is deterministic, missing questions remain scoped, and origin/destination correction still works.

- [ ] **Step 6: Create a checkpoint commit if safe**

```bash
git add Vaiage/agents/chat_agent.py Vaiage/tests/test_chat_collection.py Vaiage/workflows/travel_graph.py
git commit -m "feat: structure preference collection replies"
```

## Task 3: Detect Information Refinement Intent Without Mutating Preferences

**Files:**

- Create: `Vaiage/services/information_refinement.py`
- Create: `Vaiage/tests/test_information_refinement.py`

- [ ] **Step 1: Write failing intent parsing tests**

```python
from services.information_refinement import InformationRefinementService


def test_parses_single_category_with_temporary_filter():
    service = InformationRefinementService()

    intent = service.parse("再推荐一些便宜点、适合带孩子的餐厅")

    assert intent == {
        "action": "more_candidates",
        "category": "restaurants",
        "temporary_filters": ["便宜", "亲子"],
        "raw_query": "再推荐一些便宜点、适合带孩子的餐厅",
    }


def test_does_not_treat_confirmation_as_more_request():
    service = InformationRefinementService()

    assert service.parse("就选这些，生成行程")["action"] == "confirm_selection"


def test_asks_for_category_when_more_request_is_ambiguous():
    service = InformationRefinementService()

    result = service.parse("这些都不太喜欢，再来一些")

    assert result["action"] == "clarify_category"
    assert result["category"] is None
```

- [ ] **Step 2: Confirm the module is missing**

```bash
pytest -q tests/test_information_refinement.py
```

Expected: import failure.

- [ ] **Step 3: Implement deterministic classification first**

Use explicit category aliases and action phrases before any optional LLM fallback:

```python
CATEGORY_ALIASES = {
    "attractions": ("景点", "景区", "博物馆", "玩的地方"),
    "restaurants": ("餐厅", "饭店", "吃饭", "美食"),
    "hotels": ("酒店", "住宿", "民宿", "住的地方"),
}
MORE_PHRASES = ("更多", "再推荐", "再来", "换一批", "不满意")
CONFIRM_PHRASES = ("确认", "就选这些", "生成行程", "开始规划")
```

Extract only request-scoped filters such as “便宜”“高评分”“亲子”“博物馆”“近地铁”“含早餐”. Do not update `user_info`; return them in `temporary_filters` only.

- [ ] **Step 4: Run parser tests**

```bash
pytest -q tests/test_information_refinement.py
```

Expected: all tests pass without network or model access.

- [ ] **Step 5: Create a checkpoint commit**

```bash
git add Vaiage/services/information_refinement.py Vaiage/tests/test_information_refinement.py
git commit -m "feat: parse information refinement requests"
```

## Task 4: Add Paginated Place Fetching And Candidate Price Enrichment

**Files:**

- Modify: `Vaiage/services/maps_api.py`
- Modify: `Vaiage/agents/information_agent.py`
- Create: `Vaiage/services/candidate_enrichment.py`
- Create: `Vaiage/tests/test_candidate_enrichment.py`
- Modify: `Vaiage/tests/test_grouped_place_selection.py`

- [ ] **Step 1: Write failing candidate enrichment tests**

```python
from services.candidate_enrichment import PlaceCandidateEnricher


def test_restaurant_prefers_google_price_range():
    enricher = PlaceCandidateEnricher(
        price_range_loader=lambda place_id: {
            "startPrice": {"units": "80", "currencyCode": "CNY"},
            "endPrice": {"units": "160", "currencyCode": "CNY"},
        }
    )

    result = enricher.enrich_restaurant({"id": "r1", "price_level": 2})

    assert result["price_display"] == "Google 价格区间 ¥80-160"
    assert result["price_source"] == "google_price_range"
    assert result["price_tier"] == "中等"


def test_restaurant_falls_back_to_estimated_price_level_range():
    enricher = PlaceCandidateEnricher(price_range_loader=lambda _: None)

    result = enricher.enrich_restaurant({"id": "r2", "price_level": 1})

    assert result["price_display"] == "参考人均 ¥40-80（估算）"
    assert result["price_source"] == "price_level_estimate"
    assert result["price_tier"] == "经济"
```

Add a normalization assertion that restaurant and hotel candidates retain up to three photo objects with `url`, dimensions, and attribution metadata when available.

- [ ] **Step 2: Run tests and observe missing enrichment behavior**

```bash
pytest -q tests/test_candidate_enrichment.py tests/test_grouped_place_selection.py
```

Expected: enrichment import fails or price assertions fail.

- [ ] **Step 3: Extend the Maps API wrapper without breaking current callers**

Add optional pagination and keyword parameters:

```python
def get_nearby_places(
    self,
    location,
    type,
    radius=5000,
    language="zh-CN",
    page_token=None,
    keyword=None,
):
    params = {
        "location": location,
        "radius": radius,
        "type": type,
        "language": language,
    }
    if page_token:
        params = {"page_token": page_token, "language": language}
    elif keyword:
        params["keyword"] = keyword
    return self.gmaps.places_nearby(**params)
```

Add a Places API (New) detail helper that requests only `priceRange` and returns `None` on disabled API, unsupported place, timeout, or malformed response. It must not log API keys or full photo URLs.

```python
def get_place_price_range(self, place_id: str, language="zh-CN") -> dict | None:
    headers = {
        "X-Goog-Api-Key": self.api_key,
        "X-Goog-FieldMask": "priceRange",
    }
    response = requests.get(
        f"https://places.googleapis.com/v1/places/{quote(place_id, safe='')}",
        headers=headers,
        params={"languageCode": language},
        timeout=5,
    )
    if response.status_code != 200:
        return None
    return response.json().get("priceRange")
```

- [ ] **Step 4: Preserve pagination metadata in `InformationAgent`**

Add a new non-breaking page method:

```python
def get_place_candidate_page(
    self,
    kind: str,
    location: dict,
    page_token: str | None = None,
    keyword: str | None = None,
) -> dict:
    return {
        "candidates": normalized_candidates,
        "next_page_token": response.get("next_page_token"),
    }
```

Existing `get_restaurant_candidates()` and `get_hotel_candidates()` continue to return lists by reading `page["candidates"]`.

- [ ] **Step 5: Implement `PlaceCandidateEnricher`**

Use a stable fallback table and explicit labels:

```python
RESTAURANT_PRICE_ESTIMATES = {
    0: (20, 40, "经济"),
    1: (40, 80, "经济"),
    2: (80, 160, "中等"),
    3: (160, 300, "较高"),
    4: (300, 600, "较高"),
}
```

Normalize price and photo fields without replacing recommendation reasons or IDs. If Google supplies a non-CNY range, retain its currency symbol/code instead of converting silently.

- [ ] **Step 6: Run focused tests**

```bash
pytest -q tests/test_candidate_enrichment.py tests/test_grouped_place_selection.py
```

Expected: price fallback, Google preference, photo normalization, and existing category separation all pass.

- [ ] **Step 7: Create a checkpoint commit if safe**

```bash
git add Vaiage/services/maps_api.py Vaiage/agents/information_agent.py Vaiage/services/candidate_enrichment.py Vaiage/tests/test_candidate_enrichment.py Vaiage/tests/test_grouped_place_selection.py
git commit -m "feat: enrich place candidates with prices and photos"
```

## Task 5: Add Dated Mock Hotel Room Offers

**Files:**

- Modify: `Vaiage/services/booking_provider.py`
- Modify: `Vaiage/workflows/travel_graph.py`
- Modify: `Vaiage/tests/test_booking_flow.py`
- Modify: `Vaiage/tests/test_candidate_enrichment.py`

- [ ] **Step 1: Write failing provider contract tests**

```python
def test_ctrip_mock_room_offers_use_requested_stay_dates():
    provider = CtripMockProvider()

    offers = provider.search_hotel_rooms({
        "hotel_id": "google-hotel-1",
        "hotel_name": "东京湾亲子酒店",
        "destination": "东京",
        "check_in": "2026-08-01",
        "check_out": "2026-08-04",
        "guests": 2,
        "rooms": 1,
    })

    assert len(offers) >= 2
    assert offers[0]["check_in"] == "2026-08-01"
    assert offers[0]["check_out"] == "2026-08-04"
    assert offers[0]["source_provider"] == "ctrip_mock"
    assert offers[0]["is_mock"] is True
    assert offers[0]["nightly_rate"] > 0
```

- [ ] **Step 2: Confirm current provider lacks the room-search method**

```bash
pytest -q tests/test_booking_flow.py tests/test_candidate_enrichment.py
```

Expected: `search_hotel_rooms` is missing.

- [ ] **Step 3: Extend the provider abstraction and mock implementation**

Add to `BookingProvider`:

```python
@abstractmethod
def search_hotel_rooms(self, criteria: dict) -> list[dict]:
    raise NotImplementedError
```

Return two or three offers per Google hotel with a provider-neutral shape:

```python
{
    "offer_id": "ctrip-mock-room-google-hotel-1-deluxe-twin",
    "room_type": "豪华双床房",
    "bed_type": "2张单人床",
    "breakfast": "含双早",
    "nightly_rate": 980,
    "currency": "CNY",
    "total_price": 2940,
    "taxes_and_fees": 180,
    "cancellation_policy": "入住前1天可免费取消",
    "check_in": "2026-08-01",
    "check_out": "2026-08-04",
    "source_provider": "ctrip_mock",
    "is_mock": True,
    "provider_trace_id": "ctrip-mock-20260801-google-hotel-1",
}
```

The method must reject missing/invalid stay dates instead of inventing dates.

- [ ] **Step 4: Attach room offers to Google hotel candidates**

In the hotel candidate path, keep Google’s place ID, name, rating, address, photos, and recommendation reasons, then append:

```python
hotel["room_offers"] = provider.search_hotel_rooms(criteria)
hotel["stay"] = {"check_in": check_in, "check_out": check_out}
hotel["price_display"] = "房型 ¥980/晚起（模拟报价）"
hotel["price_source"] = "ctrip_mock"
```

For booking backward compatibility, mirror the first offer’s `room_type`, `nightly_rate`, and `cancellation_policy` onto the candidate top level until the booking draft flow is migrated to explicit offer selection.

- [ ] **Step 5: Run provider and booking regressions**

```bash
pytest -q tests/test_booking_flow.py tests/test_candidate_enrichment.py
```

Expected: dated offers pass and existing hotel draft creation remains green.

- [ ] **Step 6: Create a checkpoint commit if safe**

```bash
git add Vaiage/services/booking_provider.py Vaiage/workflows/travel_graph.py Vaiage/tests/test_booking_flow.py Vaiage/tests/test_candidate_enrichment.py
git commit -m "feat: add dated mock hotel room offers"
```

## Task 6: Integrate Incremental Recommendations Into The Workflow And API

**Files:**

- Modify: `Vaiage/workflows/travel_graph.py`
- Modify: `Vaiage/main.py`
- Modify: `Vaiage/tests/test_grouped_place_selection.py`
- Create: `Vaiage/tests/test_stream_contract.py`

- [ ] **Step 1: Add failing workflow tests for append-only behavior**

```python
def test_more_restaurants_appends_only_new_restaurants_and_preserves_selection(graph):
    state = seeded_information_state(
        restaurants=[{"id": "r1", "name": "旧餐厅"}],
        hotels=[{"id": "h1", "name": "旧酒店"}],
        selected_restaurant_ids=["r1"],
    )

    result = graph.process_step({
        **state,
        "step": "recommend",
        "user_input": "再推荐几家便宜的餐厅",
    })

    assert result["step"] == "recommend"
    assert result["selected_restaurant_ids"] == ["r1"]
    assert result["hotels"] == state["hotels"]
    assert result["restaurants"][0]["id"] == "r1"
    assert all(item["id"] != "r1" for item in result["candidate_delta"]["restaurants"])


def test_ambiguous_more_request_does_not_generate_route(graph):
    result = graph.process_step({
        **seeded_information_state(),
        "step": "recommend",
        "user_input": "再来一些",
    })

    assert result["step"] == "recommend"
    assert result["candidate_delta"] == {}
    assert "景点、餐厅还是住宿" in result["information_message"]
```

Add a test proving temporary filters are recorded under `information_refinement` but are not merged into `user_info`.

- [ ] **Step 2: Add failing stream contract tests**

```python
def test_stream_complete_includes_candidate_delta_and_date_context(client):
    payload = read_last_stream_event(client, request_payload)

    assert "candidate_delta" in payload
    assert "information_refinement" in payload
    assert "candidate_search_state" in payload
    assert "current_date" in payload
    assert "trip_date_status" in payload
```

- [ ] **Step 3: Run tests and confirm current workflow routes incorrectly or lacks fields**

```bash
pytest -q tests/test_grouped_place_selection.py tests/test_stream_contract.py
```

Expected: new assertions fail.

- [ ] **Step 4: Add search state and append-only helpers to `TravelGraph`**

Initialize/reset:

```python
"information_refinement": None,
"candidate_search_state": {
    "attractions": {"next_page_token": None, "seen_ids": []},
    "restaurants": {"next_page_token": None, "seen_ids": []},
    "hotels": {"next_page_token": None, "seen_ids": []},
},
"candidate_delta": {},
"candidate_price_context": {
    "currency": "CNY",
    "stay_dates": None,
    "hotel_quotes_are_mock": True,
},
```

Implement a category-keyed merge helper:

```python
def _append_unique_candidates(self, current: list[dict], incoming: list[dict]):
    seen = {item.get("id") for item in current}
    delta = [item for item in incoming if item.get("id") not in seen]
    return current + delta, delta
```

The recommendation step must branch in this order:

1. Parse natural-language refinement intent.
2. If `more_candidates`, fetch only that category and remain in `recommend`.
3. If `clarify_category`, emit a scoped question and remain in `recommend`.
4. If explicit confirmation/selected IDs, continue the existing strategy/route chain.
5. Otherwise preserve existing recommendation interaction behavior.

For pagination, use the stored token when present. If Google returns no token or a token yields no unseen items, perform one keyword-adjusted fallback using the temporary filters; never loop indefinitely.

- [ ] **Step 5: Expose all new fields from `/api/process` and `/api/stream`**

Add these completion keys in `main.py`:

```python
"candidate_delta",
"information_refinement",
"information_message",
"candidate_search_state",
"candidate_price_context",
"current_date",
"trip_date_status",
```

Keep existing `attractions/restaurants/hotels`, recommendation reasons, selection IDs, itinerary, and booking fields unchanged.

- [ ] **Step 6: Run integration tests**

```bash
pytest -q tests/test_grouped_place_selection.py tests/test_stream_contract.py tests/test_booking_flow.py
```

Expected: append-only category refinement, confirmation routing, stream shape, and booking regressions all pass.

- [ ] **Step 7: Create a checkpoint commit if safe**

```bash
git add Vaiage/workflows/travel_graph.py Vaiage/main.py Vaiage/tests/test_grouped_place_selection.py Vaiage/tests/test_stream_contract.py
git commit -m "feat: support incremental place recommendations"
```

## Task 7: Render Photos, Prices, And Natural-Language Refinement In Vue

**Files:**

- Modify: `nlp_tripagent_frontend/src/types/session.ts`
- Modify: `nlp_tripagent_frontend/src/services/vaiageApi.ts`
- Modify: `nlp_tripagent_frontend/src/stores/session.ts`
- Modify: `nlp_tripagent_frontend/src/views/MapView.vue`
- Create: `nlp_tripagent_frontend/src/components/CandidatePrice.vue`

- [ ] **Step 1: Extend shared TypeScript contracts first**

```typescript
export interface PlacePhoto {
  url: string
  width?: number
  height?: number
  attributions?: string[]
}

export interface HotelRoomOffer {
  offer_id: string
  room_type: string
  breakfast: string
  nightly_rate: number
  total_price: number
  currency: string
  cancellation_policy: string
  source_provider: string
  is_mock: boolean
}

export interface PlaceCandidate {
  id: string
  kind: 'attraction' | 'restaurant' | 'hotel'
  name: string
  photos?: PlacePhoto[]
  price_display?: string
  price_source?: string
  price_tier?: '经济' | '中等' | '较高'
  stay?: { check_in: string; check_out: string }
  room_offers?: HotelRoomOffer[]
  recommendation_reason?: string
}

export interface CandidateDelta {
  attractions?: PlaceCandidate[]
  restaurants?: PlaceCandidate[]
  hotels?: PlaceCandidate[]
}
```

Add the matching optional fields to `TravelResponse` and `SessionState`.

- [ ] **Step 2: Add a deduplicating Pinia merge action**

```typescript
function appendUnique(
  current: PlaceCandidate[],
  incoming: PlaceCandidate[] = [],
): PlaceCandidate[] {
  const ids = new Set(current.map(item => item.id))
  return [...current, ...incoming.filter(item => !ids.has(item.id))]
}

function mergeCandidateDelta(delta: CandidateDelta) {
  attractions.value = appendUnique(attractions.value, delta.attractions)
  restaurants.value = appendUnique(restaurants.value, delta.restaurants)
  hotels.value = appendUnique(hotels.value, delta.hotels)
  // Do not touch selected ID arrays.
}
```

- [ ] **Step 3: Map stream fields into the store**

Update `vaiageApi.ts` stream completion parsing and the Map view response handler to store date context, information feedback, and `candidate_delta`. Ensure full-list payloads still work for the initial Information response.

- [ ] **Step 4: Create a compact candidate price component**

`CandidatePrice.vue` must distinguish source semantics:

```vue
<template>
  <div v-if="priceDisplay" class="candidate-price">
    <strong>{{ priceDisplay }}</strong>
    <span v-if="priceTier" class="price-tier">{{ priceTier }}</span>
    <small v-if="isMock">携程 Mock，非实时价格</small>
  </div>
</template>
```

Do not display Google `priceRange` as a dated hotel quote.

- [ ] **Step 5: Enhance all three grouped candidate cards**

In `MapView.vue`:

- Show the first candidate photo for attractions, restaurants, and hotels.
- Use a CSS-rendered placeholder if no photo is available or image loading fails; do not introduce a remote placeholder dependency.
- Keep recommendation reason visible beneath the summary.
- Show a Google place price range when present; only the `price_level` fallback is labeled as estimated per-capita price.
- Show hotel stay dates, starting room rate, mock label, breakfast, and cancellation policy from the first room offer.
- Preserve category headings, selection checkboxes, and current visual language.

- [ ] **Step 6: Add a refinement composer below the grouped lists**

Add a text input with examples such as “再推荐几个博物馆”“换几家便宜的餐厅”“再找几家近地铁、含早餐的酒店”. Submit with `step: "recommend"` and the current session state.

While loading:

- Disable only the refinement composer and final confirmation button.
- Keep current candidates and selections visible.
- Display “正在补充餐厅候选…” based on the parsed/requested category.

After completion:

- Merge `candidate_delta` rather than replacing lists.
- Show `information_message` inline.
- Scroll the affected group to the first newly appended card.
- If category is ambiguous, show the backend clarification without navigating away.

- [ ] **Step 7: Run frontend type and production builds**

Run from `nlp_tripagent_frontend/`:

```bash
npx vue-tsc --noEmit
npx vite build
```

Expected: both commands exit 0, with no missing contract fields or Vue template errors.

- [ ] **Step 8: Create a checkpoint commit if safe**

```bash
git add nlp_tripagent_frontend/src/types/session.ts nlp_tripagent_frontend/src/services/vaiageApi.ts nlp_tripagent_frontend/src/stores/session.ts nlp_tripagent_frontend/src/views/MapView.vue nlp_tripagent_frontend/src/components/CandidatePrice.vue
git commit -m "feat: refine and enrich grouped place choices"
```

## Task 8: Full Regression And Acceptance Verification

**Files:**

- Modify only if a regression is found in files already listed above.

- [ ] **Step 1: Run the complete backend test suite**

Run from `Vaiage/`:

```bash
pytest -q
```

Expected: all tests pass; no test performs a live Google or LLM call.

- [ ] **Step 2: Re-run frontend verification**

Run from `nlp_tripagent_frontend/`:

```bash
npx vue-tsc --noEmit
npx vite build
```

Expected: both commands exit 0.

- [ ] **Step 3: Start the existing backend and frontend services**

Use the project’s current start commands and verify:

- Backend health/process endpoint is reachable on `http://127.0.0.1:8002`.
- Vue frontend is reachable on `http://127.0.0.1:3000`.
- Do not print request logs containing Maps photo URLs or API keys.

- [ ] **Step 4: Execute the acceptance conversation**

Use this fixed scenario:

```text
我叫小林，从上海出发，想在2026年8月1日去东京玩4天，2个大人带1个6岁孩子，身体状况良好。预算2万元，喜欢动漫、博物馆和本地美食。住宿希望近地铁、亲子友好、含早餐，最好有洗衣房和健身房。
```

Verify:

- Chat shows one collected field per line and asks only for truly missing data.
- Information displays separated attraction, restaurant, and hotel groups.
- Restaurant/hotel cards show photos and recommendation reasons.
- Restaurants show Google price range when available, otherwise labeled estimates.
- Hotels show `2026-08-01` stay context and explicitly labeled Ctrip Mock room offers.
- “再推荐几家便宜的餐厅” appends only new restaurants and preserves selections.
- “再找几家近地铁、含早餐的酒店” appends only new hotels.
- “再来一些” asks which category instead of generating a route.
- Confirming selected places still enters strategy/route generation and eventually shows the itinerary.

- [ ] **Step 5: Inspect the final diff for accidental changes and secrets**

```bash
git status --short
git diff --check
git diff -- Vaiage nlp_tripagent_frontend
```

Confirm no `.env` file, API key, generated build output, or unrelated user file is staged.

- [ ] **Step 6: Record final verification evidence**

Report exact backend test count, frontend command results, manual acceptance outcome, and any Google API fallback observed. Do not claim live room inventory because the room offers are mocked.
