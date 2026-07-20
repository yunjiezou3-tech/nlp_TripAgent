import importlib.util
import sys
import types
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


DATE_RESOLVER_SPEC = importlib.util.spec_from_file_location(
    "services.date_resolver", ROOT / "services/date_resolver.py"
)
DATE_RESOLVER_MODULE = importlib.util.module_from_spec(DATE_RESOLVER_SPEC)
assert DATE_RESOLVER_SPEC.loader is not None
DATE_RESOLVER_SPEC.loader.exec_module(DATE_RESOLVER_MODULE)
DateResolver = DATE_RESOLVER_MODULE.DateResolver


@pytest.mark.parametrize(
    "value",
    [None, "", "   ", "none", "NONE", "not decided", "待定", "未确定"],
)
def test_resolve_marks_missing_values_without_guessing(value):
    result = DateResolver(today=date(2026, 7, 20)).resolve(value)

    assert set(result) == {"status", "value", "source_text", "error"}
    assert result["status"] == "missing"
    assert result["value"] is None
    assert result["error"] is None


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-08-15", "2026-08-15"),
        ("今天", "2026-07-20"),
        ("明天", "2026-07-21"),
        ("后天", "2026-07-22"),
        ("下周一", "2026-07-27"),
        ("下周三", "2026-07-29"),
        ("下周日", "2026-08-02"),
        ("今年国庆", "2026-10-01"),
        ("明年国庆", "2027-10-01"),
    ],
)
def test_resolve_returns_canonical_dates_for_supported_text(value, expected):
    result = DateResolver(today=date(2026, 7, 20)).resolve(value)

    assert result == {
        "status": "resolved",
        "value": expected,
        "source_text": value,
        "error": None,
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [("下周一", "2026-07-27"), ("下周日", "2026-08-02")],
)
def test_resolve_next_week_dates_when_today_is_sunday(value, expected):
    result = DateResolver(today=date(2026, 7, 26)).resolve(value)

    assert result["status"] == "resolved"
    assert result["value"] == expected


@pytest.mark.parametrize("value", ["2026-07-19", "今年国庆"])
def test_resolve_rejects_past_dates(value):
    result = DateResolver(today=date(2026, 10, 2)).resolve(value)

    assert result["status"] == "invalid"
    assert result["value"] is None
    assert result["error"] == "past_date"


@pytest.mark.parametrize("value", ["暑假", "下个月", "2026-02-30", "2026-7-21"])
def test_resolve_rejects_unrecognized_text_instead_of_guessing(value):
    result = DateResolver(today=date(2026, 7, 20)).resolve(value)

    assert result["status"] == "invalid"
    assert result["value"] is None
    assert result["error"] == "unrecognized_date"


class AIMessage:
    def __init__(self, content):
        self.content = content


class DummyAgent:
    def __init__(self, *args, **kwargs):
        pass


class DummyBookingAgent(DummyAgent):
    def detect_intent(self, _):
        return False


class CompleteChatAgent:
    required_fields = [
        "name",
        "city",
        "days",
        "budget",
        "people",
        "kids",
        "health",
        "hobbies",
        "start_date",
        "accommodation_preference",
    ]

    def __init__(self):
        self.calls = []
        self.current_dates = []
        self.composed_states = []
        self.composed_ask_fields = []

    def collect_info(self, user_input, state=None, current_date=None):
        state = state or {}
        self.calls.append(state.copy())
        self.current_dates.append(current_date)
        missing_fields = [field for field in self.required_fields if not state.get(field)]
        message = f"请补充：{','.join(missing_fields)}" if missing_fields else "信息已收集完成"
        return {
            "stream": iter([AIMessage(message)]),
            "missing_fields": missing_fields,
            "complete": not missing_fields,
            "state": state.copy(),
        }

    def _collection_response_stream(
        self,
        state,
        missing_fields,
        question_stream=None,
        ask_fields=None,
        question_overrides=None,
    ):
        self.composed_states.append(state.copy())
        self.composed_ask_fields.append(list(ask_fields or []))
        labels = {
            "name": "称呼",
            "city": "目的地",
            "days": "旅行天数",
            "budget": "预算",
            "people": "出行人数",
            "kids": "是否携带儿童",
            "health": "健康与行动状况",
            "hobbies": "旅行偏好",
            "start_date": "出发日期",
            "accommodation_preference": "住宿偏好",
        }
        lines = ["已收集到的信息"]
        for field in self.required_fields:
            if state.get(field):
                lines.append(f"{labels[field]}：{state[field]}")
        prefix = "\n".join(lines) + "\n\n还需要了解的信息\n"

        def stream():
            yield AIMessage(prefix)
            if ask_fields is not None:
                templates = {
                    "name": "请问怎么称呼您？",
                    "city": "请问您的目的地是哪里？",
                    "start_date": "请问您计划哪天出发？",
                }
                overrides = question_overrides or {}
                questions = [overrides.get(field) or templates[field] for field in ask_fields]
                yield AIMessage("\n".join(questions))
            else:
                yield from question_stream or ()

        return stream()

def _load_graph_module(monkeypatch):
    agents_package = types.ModuleType("agents")
    agents_package.__path__ = []
    services_package = types.ModuleType("services")
    services_package.__path__ = []
    monkeypatch.setitem(sys.modules, "agents", agents_package)
    monkeypatch.setitem(sys.modules, "services", services_package)
    monkeypatch.setitem(sys.modules, "services.date_resolver", DATE_RESOLVER_MODULE)

    for name, class_name, cls in (
        ("agents.chat_agent", "ChatAgent", DummyAgent),
        ("agents.information_agent", "InformationAgent", DummyAgent),
        ("agents.recommend_agent", "RecommendAgent", DummyAgent),
        ("agents.strategy_agent", "StrategyAgent", DummyAgent),
        ("agents.route_agent", "RouteAgent", DummyAgent),
        ("agents.communication_agent", "CommunicationAgent", DummyAgent),
        ("agents.booking_agent", "BookingAgent", DummyBookingAgent),
        ("services.booking_provider", "CtripMockProvider", DummyAgent),
        ("services.candidate_enrichment", "PlaceCandidateEnricher", DummyAgent),
        (
            "services.information_refinement",
            "InformationRefinementService",
            DummyAgent,
        ),
    ):
        module = types.ModuleType(name)
        setattr(module, class_name, cls)
        monkeypatch.setitem(sys.modules, name, module)

    messages = types.ModuleType("langchain_core.messages")
    messages.AIMessage = AIMessage
    monkeypatch.setitem(sys.modules, "langchain_core.messages", messages)

    spec = importlib.util.spec_from_file_location(
        "travel_graph_date_gate_under_test", ROOT / "workflows/travel_graph.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _complete_user_info(start_date):
    return {
        "name": "测试用户",
        "city": "上海",
        "days": "2",
        "budget": "3000",
        "people": "2",
        "kids": "no",
        "health": "good",
        "hobbies": "博物馆",
        "start_date": start_date,
        "accommodation_preference": "经济型",
    }


def test_graph_defaults_trip_date_status_to_full_missing_result(monkeypatch):
    graph = _load_graph_module(monkeypatch).TravelGraph()
    expected = {
        "status": "missing",
        "value": None,
        "source_text": None,
        "error": None,
    }

    assert graph.state["trip_date_status"] == expected
    assert graph.get_session_state("new-session")["trip_date_status"] == expected


def test_chat_resolves_date_against_preserved_current_date_before_information(monkeypatch):
    graph = _load_graph_module(monkeypatch).TravelGraph()
    graph.chat_agent = CompleteChatAgent()
    graph.session_states["fixed-date"] = {
        **graph.state,
        "current_date": "2026-07-20",
        "user_info": _complete_user_info("明天"),
    }
    information_calls = []

    def process_information():
        information_calls.append(True)
        return {"next_step": "recommend", "state": graph.state.copy()}

    graph._process_information = process_information

    result = graph.process_step("chat", session_id="fixed-date", user_input="")

    assert information_calls == [True]
    assert result["next_step"] == "recommend"
    assert graph.state["current_date"] == "2026-07-20"
    assert graph.state["trip_date_status"] == {
        "status": "resolved",
        "value": "2026-07-21",
        "source_text": "明天",
        "error": None,
    }
    assert graph.state["user_info"]["start_date"] == "2026-07-21"
    assert graph.chat_agent.current_dates == ["2026-07-20"]


@pytest.mark.parametrize("persisted_current_date", [None, 123, "not-a-date"])
def test_chat_normalizes_invalid_persisted_current_date(monkeypatch, persisted_current_date):
    graph = _load_graph_module(monkeypatch).TravelGraph()
    graph.chat_agent = CompleteChatAgent()
    graph._shanghai_today = lambda: "2026-07-20"
    graph.state["current_date"] = persisted_current_date
    graph.state["user_info"] = _complete_user_info("明天")
    graph._process_information = lambda: {"next_step": "recommend", "state": graph.state.copy()}

    result = graph._process_chat(user_input="")

    assert result["next_step"] == "recommend"
    assert graph.state["current_date"] == "2026-07-20"
    assert graph.state["user_info"]["start_date"] == "2026-07-21"


def test_chat_keeps_invalid_date_missing_and_generates_date_follow_up(monkeypatch):
    graph = _load_graph_module(monkeypatch).TravelGraph()
    graph.chat_agent = CompleteChatAgent()
    graph.state["current_date"] = "2026-07-20"
    graph.state["user_info"] = _complete_user_info("暑假")

    def fail_if_information_runs():
        raise AssertionError("information step must not run for an invalid date")

    graph._process_information = fail_if_information_runs

    result = graph._process_chat(user_input="")

    assert result["next_step"] == "chat"
    assert result["missing_fields"] == ["start_date"]
    response_text = "".join(message.content for message in result["stream"])
    assert response_text.startswith("已收集到的信息\n")
    assert response_text.count("已收集到的信息") == 1
    assert response_text.count("还需要了解的信息") == 1
    assert "暑假" not in response_text
    assert response_text.endswith(
        "我无法识别这个出发日期，请提供明确日期，例如 2026-08-15、明天或下周一。"
    )
    assert len(graph.chat_agent.calls) == 1
    assert len(graph.chat_agent.composed_states) == 1
    assert "start_date" not in graph.chat_agent.composed_states[0]
    assert not graph.state["user_info"].get("start_date")
    assert graph.state["trip_date_status"] == {
        "status": "invalid",
        "value": None,
        "source_text": "暑假",
        "error": "unrecognized_date",
    }


def test_chat_preserves_other_missing_field_prompt_when_date_is_invalid(monkeypatch):
    graph = _load_graph_module(monkeypatch).TravelGraph()
    graph.chat_agent = CompleteChatAgent()
    graph.state["current_date"] = "2026-07-20"
    graph.state["user_info"] = _complete_user_info("暑假")
    graph.state["user_info"].pop("city")

    result = graph._process_chat(user_input="")

    assert result["next_step"] == "chat"
    assert result["missing_fields"] == ["city", "start_date"]
    response_text = "".join(message.content for message in result["stream"])
    assert response_text.startswith("已收集到的信息\n")
    assert response_text.count("已收集到的信息") == 1
    assert response_text.count("还需要了解的信息") == 1
    assert "暑假" not in response_text
    assert "请问您的目的地是哪里？" in response_text
    assert response_text.endswith(
        "我无法识别这个出发日期，请提供明确日期，例如 2026-08-15、明天或下周一。"
    )
    assert len(graph.chat_agent.calls) == 1
    assert len(graph.chat_agent.composed_states) == 1


def test_invalid_date_with_all_other_fields_missing_asks_at_most_two_including_date(monkeypatch):
    graph = _load_graph_module(monkeypatch).TravelGraph()
    graph.chat_agent = CompleteChatAgent()
    graph.state["current_date"] = "2026-07-20"
    graph.state["user_info"] = {"start_date": "暑假"}

    result = graph._process_chat(user_input="")
    response_text = "".join(message.content for message in result["stream"])
    question_lines = response_text.split("还需要了解的信息\n", 1)[1].splitlines()

    assert result["next_step"] == "chat"
    assert len(question_lines) == 2
    assert "请问怎么称呼您？" in question_lines
    assert any("无法识别这个出发日期" in line for line in question_lines)
    assert graph.chat_agent.composed_ask_fields == [["name", "start_date"]]


def test_chat_does_not_duplicate_a_genuinely_missing_date_prompt(monkeypatch):
    graph = _load_graph_module(monkeypatch).TravelGraph()
    graph.chat_agent = CompleteChatAgent()
    graph.state["current_date"] = "2026-07-20"
    graph.state["user_info"] = _complete_user_info(None)

    result = graph._process_chat(user_input="")

    assert result["next_step"] == "chat"
    assert result["missing_fields"] == ["start_date"]
    assert [message.content for message in result["stream"]] == ["请补充：start_date"]
    assert len(graph.chat_agent.calls) == 1
    assert graph.chat_agent.current_dates == ["2026-07-20"]
