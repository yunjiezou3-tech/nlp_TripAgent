import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


class AIMessage:
    def __init__(self, content):
        self.content = content


class OfflineWorkflow:
    instances = []

    def __init__(self):
        self.calls = []
        self.__class__.instances.append(self)
        self.state = {
            "attractions": [{"id": "a1", "name": "外滩"}],
            "restaurants": [{"id": "r1", "name": "本帮菜"}],
            "hotels": [{"id": "h1", "name": "静安酒店"}],
            "selected_attractions": [{"id": "a1", "name": "外滩"}],
            "selected_restaurants": [{"id": "r1", "name": "本帮菜"}],
            "selected_hotel": {"id": "h1", "name": "静安酒店"},
            "hotel_recommendations": [{"id": "h1", "name": "静安酒店"}],
            "recommended_hotel_id": "h1",
            "booking_drafts": {"hotel": {"draft_id": "draft-1"}},
            "booking_missing_fields": [],
            "booking_mode": "hotel",
            "booking_candidates": {"hotels": [{"id": "h1"}]},
            "itinerary": [{"day": 1, "spots": ["外滩"]}],
            "candidate_delta": {"hotels": [{"id": "state-delta"}]},
            "information_refinement": {
                "intent": "more_candidates",
                "categories": ["restaurants"],
                "transient_filters": {},
                "raw_query": "更多餐厅",
                "clarification_message": None,
            },
            "information_message": "state message",
            "candidate_search_state": {
                category: {
                    "next_page_token": None,
                    "seen_ids": [],
                    "exhausted": True,
                    "last_query": "更多餐厅" if category == "restaurants" else None,
                    "last_error": None,
                }
                for category in ("attractions", "restaurants", "hotels")
            },
            "candidate_price_context": {
                "currency": "CNY",
                "stay_dates": {
                    "check_in": "2026-08-01",
                    "check_out": "2026-08-03",
                },
                "hotel_quotes_are_mock": True,
            },
            "current_date": "2026-07-20",
            "trip_date_status": {
                "status": "resolved",
                "value": "2026-08-01",
                "source_text": "2026-08-01",
                "error": None,
            },
        }

    def process_step(self, step_name, **kwargs):
        assert step_name == "recommend"
        self.calls.append({"step_name": step_name, **kwargs})
        return {
            "next_step": "recommend",
            "stream": iter([AIMessage("已补充候选")]),
            "candidate_delta": {"restaurants": [{"id": "result-delta"}]},
            "information_message": "result message",
            "state": self.state,
        }

    def get_current_state(self):
        return self.state


@pytest.fixture
def api_module(monkeypatch):
    OfflineWorkflow.instances.clear()
    workflows_package = types.ModuleType("workflows")
    workflows_package.__path__ = []
    travel_graph_module = types.ModuleType("workflows.travel_graph")
    travel_graph_module.TravelGraph = OfflineWorkflow
    monkeypatch.setitem(sys.modules, "workflows", workflows_package)
    monkeypatch.setitem(sys.modules, "workflows.travel_graph", travel_graph_module)

    spec = importlib.util.spec_from_file_location("main_contract_under_test", ROOT / "main.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.app.config.update(TESTING=True)
    module.time.sleep = lambda _: None
    module.workflows.clear()
    return module


def test_generated_session_id_is_reused_and_passed_to_every_process_call(api_module):
    client = api_module.app.test_client()

    first = client.post("/api/process", json={"step": "recommend"})
    second = client.post("/api/process", json={"step": "recommend"})

    assert first.status_code == second.status_code == 200
    with client.session_transaction() as flask_session:
        resolved_id = flask_session["session_id"]
    assert isinstance(resolved_id, str) and resolved_id
    assert list(api_module.workflows) == [resolved_id]
    assert len(OfflineWorkflow.instances) == 1
    assert [call["session_id"] for call in OfflineWorkflow.instances[0].calls] == [
        resolved_id,
        resolved_id,
    ]


def test_explicit_stream_session_is_reused_by_process(api_module):
    client = api_module.app.test_client()

    stream_response = client.get(
        "/api/stream?session_id=explicit-shared&step=recommend"
    )
    process_response = client.post("/api/process", json={"step": "recommend"})

    assert stream_response.status_code == process_response.status_code == 200
    with client.session_transaction() as flask_session:
        assert flask_session["session_id"] == "explicit-shared"
    assert list(api_module.workflows) == ["explicit-shared"]
    assert len(OfflineWorkflow.instances) == 1
    assert [call["session_id"] for call in OfflineWorkflow.instances[0].calls] == [
        "explicit-shared",
        "explicit-shared",
    ]


def test_reset_explicit_other_workflow_preserves_active_cookie_and_workflow(api_module):
    client = api_module.app.test_client()
    client.post(
        "/api/process",
        json={"session_id": "flask-active", "step": "recommend"},
    )
    api_module.workflows["reset-target"] = OfflineWorkflow()

    response = client.get("/api/reset?session_id=reset-target")

    assert response.status_code == 200
    assert "reset-target" not in api_module.workflows
    assert "flask-active" in api_module.workflows
    with client.session_transaction() as flask_session:
        assert flask_session["session_id"] == "flask-active"


def test_reset_without_explicit_target_removes_active_workflow_and_cookie(api_module):
    client = api_module.app.test_client()
    client.post(
        "/api/process",
        json={"session_id": "flask-active", "step": "recommend"},
    )

    response = client.get("/api/reset")

    assert response.status_code == 200
    assert "flask-active" not in api_module.workflows
    with client.session_transaction() as flask_session:
        assert "session_id" not in flask_session


def test_reset_explicit_active_workflow_removes_workflow_and_cookie(api_module):
    client = api_module.app.test_client()
    client.post(
        "/api/process",
        json={"session_id": "flask-active", "step": "recommend"},
    )

    response = client.get("/api/reset?session_id=flask-active")

    assert response.status_code == 200
    assert "flask-active" not in api_module.workflows
    with client.session_transaction() as flask_session:
        assert "session_id" not in flask_session


def test_process_sanitizes_workflow_exception_response_and_logs(api_module, capsys):
    class FailingWorkflow:
        def process_step(self, *args, **kwargs):
            raise RuntimeError("provider-secret-token")

        def get_current_state(self):
            return {}

    api_module.TravelGraph = FailingWorkflow

    response = api_module.app.test_client().post(
        "/api/process", json={"step": "recommend"}
    )

    assert response.status_code == 500
    assert response.get_json() == {
        "code": "internal_error",
        "error": "处理请求失败，请稍后重试。",
    }
    assert "provider-secret-token" not in response.get_data(as_text=True)
    assert "provider-secret-token" not in capsys.readouterr().out


def test_process_and_stream_sanitize_returned_diagnostics_without_changing_user_text(
    api_module, capsys
):
    class SecretStateValue:
        def __str__(self):
            return "STATE-LOG-SECRET"

    class ReturnedDiagnosticWorkflow:
        def __init__(self):
            self.state = {
                "place_errors": {
                    "restaurants": "STATE-PLACE-SECRET",
                    "hotels": "provider_unavailable",
                },
                "candidate_search_state": {
                    "restaurants": {"last_error": "STATE-LAST-SECRET"},
                },
                "information_message": "这里是安全的用户提示",
                "should_rent_car": SecretStateValue(),
            }

        def process_step(self, *args, **kwargs):
            return {
                "next_step": "recommend",
                "error": "RETURNED-ERROR-SECRET",
                "errors": {"restaurants": "RETURNED-NESTED-SECRET"},
                "response": "这里是安全的用户回复",
                "information_message": "这里是安全的用户提示",
                "stream": iter([]),
                "state": self.state,
            }

        def get_current_state(self):
            return self.state

    api_module.TravelGraph = ReturnedDiagnosticWorkflow
    client = api_module.app.test_client()

    process_response = client.post(
        "/api/process",
        json={"session_id": "returned-process", "step": "recommend"},
    )
    stream_response = client.get(
        "/api/stream?session_id=returned-stream&step=recommend"
    )
    process_payload = process_response.get_json()
    stream_events = [
        json.loads(block.removeprefix("data: "))
        for block in stream_response.get_data(as_text=True).strip().split("\n\n")
    ]
    completion = next(event for event in stream_events if event["type"] == "complete")

    assert process_response.status_code == stream_response.status_code == 200
    combined = json.dumps([process_payload, completion], ensure_ascii=False)
    captured = capsys.readouterr()
    assert "SECRET" not in combined
    assert "STATE-LOG-SECRET" not in captured.out
    assert "STATE-LOG-SECRET" not in captured.err
    assert process_payload["error"] == "处理请求失败，请稍后重试。"
    assert process_payload["errors"] == {"restaurants": "internal_error"}
    for payload in (process_payload, completion):
        assert payload["place_errors"] == {
            "restaurants": "provider_unavailable",
            "hotels": "provider_unavailable",
        }
        assert (
            payload["state"]["candidate_search_state"]["restaurants"][
                "last_error"
            ]
            == "provider_unavailable"
        )
        assert payload["information_message"] == "这里是安全的用户提示"
    assert process_payload["response"] == "这里是安全的用户回复"


def test_nearby_uses_generic_error_contract_without_logging_secret(api_module, capsys):
    class FailingNearbyAgent:
        def search_nearby_places(self, *args, **kwargs):
            raise RuntimeError("NEARBY-PROVIDER-SECRET")

    workflow = types.SimpleNamespace(info_agent=FailingNearbyAgent())
    api_module.workflows["nearby-session"] = workflow

    response = api_module.app.test_client().get(
        "/api/nearby/31.2,121.4?session_id=nearby-session"
    )

    captured = capsys.readouterr()
    assert response.status_code == 500
    assert response.get_json() == {
        "code": "internal_error",
        "error": "处理请求失败，请稍后重试。",
    }
    assert "NEARBY-PROVIDER-SECRET" not in response.get_data(as_text=True)
    assert "NEARBY-PROVIDER-SECRET" not in captured.out
    assert "NEARBY-PROVIDER-SECRET" not in captured.err


@pytest.mark.parametrize(
    "body,content_type",
    [("{not-json", "application/json"), ("[]", "application/json")],
)
def test_process_rejects_malformed_or_non_object_json(api_module, body, content_type):
    response = api_module.app.test_client().post(
        "/api/process", data=body, content_type=content_type
    )

    assert response.status_code == 400
    assert response.get_json() == {
        "code": "invalid_request",
        "error": "请求格式无效。",
    }
    assert OfflineWorkflow.instances == []


def test_stream_accepts_plain_strings_and_sanitizes_generator_failure(
    api_module, capsys
):
    class FailingStreamWorkflow:
        def process_step(self, *args, **kwargs):
            def chunks():
                yield "第一段"
                raise RuntimeError("stream-provider-secret")

            return {"next_step": "recommend", "stream": chunks(), "state": {}}

        def get_current_state(self):
            return {}

    api_module.TravelGraph = FailingStreamWorkflow

    response = api_module.app.test_client().get("/api/stream?step=recommend")
    body = response.get_data(as_text=True)
    events = [
        json.loads(block.removeprefix("data: "))
        for block in body.strip().split("\n\n")
    ]

    assert response.status_code == 200
    assert events == [
        {"type": "chunk", "content": "第一段"},
        {
            "type": "error",
            "code": "stream_error",
            "error": "流式响应失败，请稍后重试。",
        },
    ]
    assert "stream-provider-secret" not in body
    assert "stream-provider-secret" not in capsys.readouterr().out


def test_process_and_stream_project_unsafe_state_values_without_leaking(api_module):
    class CustomValue:
        pass

    class UnsafeStateWorkflow:
        def __init__(self):
            unsafe_cycle = {}
            unsafe_cycle["self"] = unsafe_cycle
            self.state = {
                "attractions": [],
                "restaurants": [],
                "hotels": [],
                "candidate_delta": {},
                "booking_context": {
                    "safe": "kept",
                    "custom": CustomValue(),
                    "exception": RuntimeError("unsafe-state-secret"),
                },
                "unsafe_set": {"secret-member"},
                "unsafe_generator": (value for value in ["secret-generator"]),
                "unsafe_cycle": unsafe_cycle,
            }

        def process_step(self, *args, **kwargs):
            return {
                "next_step": "recommend",
                "stream": iter([]),
                "state": self.state,
            }

        def get_current_state(self):
            return self.state

    api_module.TravelGraph = UnsafeStateWorkflow
    client = api_module.app.test_client()

    process_response = client.post(
        "/api/process",
        json={"session_id": "unsafe-process", "step": "recommend"},
    )
    stream_response = client.get(
        "/api/stream?session_id=unsafe-stream&step=recommend"
    )
    stream_events = [
        json.loads(block.removeprefix("data: "))
        for block in stream_response.get_data(as_text=True).strip().split("\n\n")
    ]
    completion = next(event for event in stream_events if event["type"] == "complete")

    assert process_response.status_code == stream_response.status_code == 200
    for payload in (process_response.get_json(), completion):
        assert payload["state"]["booking_context"] == {
            "safe": "kept",
            "custom": None,
            "exception": None,
        }
        assert payload["state"]["unsafe_set"] is None
        assert payload["state"]["unsafe_generator"] is None
        assert payload["state"]["unsafe_cycle"] == {"self": None}
        assert payload["booking_context"]["safe"] == "kept"
        assert "unsafe-state-secret" not in json.dumps(payload, ensure_ascii=False)


CONTRACT_KEYS = {
    "attractions",
    "restaurants",
    "hotels",
    "selected_attractions",
    "selected_restaurants",
    "selected_hotel",
    "hotel_recommendations",
    "recommended_hotel_id",
    "booking_drafts",
    "booking_missing_fields",
    "booking_mode",
    "booking_candidates",
    "itinerary",
    "candidate_delta",
    "information_refinement",
    "information_message",
    "candidate_search_state",
    "candidate_price_context",
    "current_date",
    "trip_date_status",
    "next_step",
}


def _assert_completion_contract(payload):
    assert CONTRACT_KEYS <= payload.keys()
    assert payload["candidate_delta"] == {
        "restaurants": [{"id": "result-delta"}]
    }
    assert payload["information_message"] == "result message"
    assert payload["information_refinement"]["intent"] == "more_candidates"
    assert payload["selected_hotel"]["id"] == "h1"
    assert payload["current_date"] == "2026-07-20"
    assert payload["trip_date_status"]["error"] is None
    json.dumps({key: payload[key] for key in CONTRACT_KEYS}, ensure_ascii=False)


def test_process_exposes_json_safe_completion_contract_with_state_fallback(api_module):
    response = api_module.app.test_client().post(
        "/api/process",
        json={"session_id": "process-contract", "step": "recommend"},
    )

    assert response.status_code == 200
    _assert_completion_contract(response.get_json())


def test_stream_exposes_same_json_safe_completion_contract(api_module):
    response = api_module.app.test_client().get(
        "/api/stream?session_id=stream-contract&step=recommend"
    )

    assert response.status_code == 200
    events = [
        json.loads(block.removeprefix("data: "))
        for block in response.get_data(as_text=True).strip().split("\n\n")
    ]
    assert events[0] == {"type": "chunk", "content": "已补充候选"}
    completion = next(event for event in events if event["type"] == "complete")
    _assert_completion_contract(completion)
