# Candidate Recommendation Reasons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show evidence-based, personalized recommendation reasons on attraction, restaurant, and hotel candidate cards.

**Architecture:** `InformationAgent` attaches one shared `recommendation_reasons` list plus rank metadata to every returned candidate. Deterministic matching produces safe evidence-based reasons, and the existing attraction/hotel LLM ordering remains optional; no prompt may claim attributes missing from Google Places data. `MapView` renders the returned reasons without independently inferring preferences.

**Tech Stack:** Python, Google Places normalized candidates, LangChain/OpenAI-compatible LLM, Flask streaming API, Vue 3, TypeScript, Pinia, pytest, vue-tsc.

---

### Task 1: Define and test evidence-based candidate annotations

**Files:**
- Modify: `Vaiage/agents/information_agent.py`
- Modify: `Vaiage/tests/test_grouped_place_selection.py`

- [ ] **Step 1: Write failing tests for attraction, restaurant, and hotel reasons**

```python
def test_candidate_reasons_use_user_preferences_without_inventing_attributes(monkeypatch):
    agent = build_information_agent(monkeypatch)
    candidates = [
        {"id": "museum", "kind": "attraction", "rating": 4.8, "category": "museum", "types": ["museum"]},
        {"id": "restaurant", "kind": "restaurant", "rating": 4.6, "types": ["restaurant"]},
    ]

    annotated = agent.annotate_candidates_with_reasons(
        candidates,
        {"hobbies": "museum", "kids": "yes", "budget": "medium"},
    )

    assert "匹配你的兴趣：museum" in annotated[0]["recommendation_reasons"]
    assert "评分 4.8" in annotated[0]["recommendation_reasons"]
    assert annotated[1]["recommendation_reasons"] == ["评分 4.6"]
```

- [ ] **Step 2: Run the new test to verify it fails**

Run: `cd Vaiage && pytest -q tests/test_grouped_place_selection.py::test_candidate_reasons_use_user_preferences_without_inventing_attributes`

Expected: FAIL because `InformationAgent` has no shared annotation method.

- [ ] **Step 3: Add a shared candidate annotation helper**

```python
def annotate_candidates_with_reasons(self, candidates, user_prefs, ranking_source):
    for index, candidate in enumerate(candidates, start=1):
        reasons = self._build_candidate_reasons(candidate, user_prefs)
        candidate["recommendation_reasons"] = reasons[:2]
        candidate["recommendation_rank"] = index
        candidate["ranking_source"] = ranking_source
    return candidates
```

Implement `_build_candidate_reasons` using only `category`, `types`, `rating`, `price_level`, `summary`, existing hotel `match_reasons`, and extracted user preferences. Add generic rating only when no direct preference match is evidenced.

- [ ] **Step 4: Run the focused tests**

Run: `cd Vaiage && pytest -q tests/test_grouped_place_selection.py`

Expected: PASS.

### Task 2: Attach annotations to all information-stage candidate groups

**Files:**
- Modify: `Vaiage/agents/information_agent.py`
- Modify: `Vaiage/workflows/travel_graph.py`
- Modify: `Vaiage/tests/test_grouped_place_selection.py`

- [ ] **Step 1: Write failing workflow tests for all three returned groups**

```python
def test_information_returns_reasoned_candidate_groups(graph):
    graph.state["user_info"] = {"city": "上海", "days": "2", "hobbies": "museum"}

    result = graph._process_information()

    assert result["attractions"][0]["recommendation_reasons"]
    assert result["restaurants"][0]["recommendation_reasons"]
    assert result["hotels"][0]["recommendation_reasons"]
```

- [ ] **Step 2: Run the new test to verify it fails**

Run: `cd Vaiage && pytest -q tests/test_grouped_place_selection.py::test_information_returns_reasoned_candidate_groups`

Expected: FAIL because the information response does not annotate every group.

- [ ] **Step 3: Annotate each group after retrieval and ranking**

```python
attractions = self.info_agent.annotate_candidates_with_reasons(
    attractions, user_prefs, ranking_source="llm" if self.info_agent.llm else "rules"
)
restaurants = self.info_agent.annotate_candidates_with_reasons(restaurants, user_prefs, ranking_source="rules")
hotels = self.info_agent.annotate_candidates_with_reasons(hotels, user_prefs, ranking_source="llm" if self.info_agent.llm else "rules")
```

Keep category failures isolated: an empty or failed group remains empty and has an error entry, rather than fabricated reasons or fallback candidates.

- [ ] **Step 4: Run backend regression tests**

Run: `cd Vaiage && pytest -q tests`

Expected: PASS.

### Task 3: Render backend reasons consistently in candidate cards

**Files:**
- Modify: `nlp_tripagent_frontend/src/types/session.ts`
- Modify: `nlp_tripagent_frontend/src/views/MapView.vue`

- [ ] **Step 1: Extend candidate typings**

```ts
export interface PlaceCandidate {
  // Existing fields...
  recommendation_reasons?: string[]
  recommendation_rank?: number
  ranking_source?: 'llm' | 'rules'
}
```

- [ ] **Step 2: Render one shared recommendation-reason block for every card type**

```vue
<p v-if="candidate.recommendation_reasons?.length" class="recommendation-reasons">
  <span class="reason-label">推荐理由</span>
  <span>{{ candidate.recommendation_reasons.join(' · ') }}</span>
</p>
```

Use the same visual hierarchy under the attraction, restaurant, and hotel metadata. Preserve hotel `match_reasons` only as a compatibility fallback until all active backend responses send `recommendation_reasons`.

- [ ] **Step 3: Type-check and build the frontend**

Run: `cd nlp_tripagent_frontend && npx vue-tsc --noEmit && npx vite build`

Expected: both commands exit `0`.

### Task 4: Verify streamed data and regression behavior

**Files:**
- Modify: `Vaiage/tests/test_grouped_place_selection.py`

- [ ] **Step 1: Add a no-fabrication regression assertion**

```python
assert all("早餐" not in reason for reason in restaurant["recommendation_reasons"])
```

Use a restaurant mock without breakfast evidence while the user requests breakfast, proving that facilities are not inferred across categories.

- [ ] **Step 2: Run all checks**

Run: `cd Vaiage && pytest -q tests && cd ../nlp_tripagent_frontend && npx vue-tsc --noEmit && npx vite build`

Expected: backend tests and frontend type-check/build pass.
