import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


class Message:
    def __init__(self, content):
        self.content = content


def load_chat_module(monkeypatch, chat_openai_class=None):
    class DefaultChatOpenAI:
        pass

    chat_openai_class = chat_openai_class or DefaultChatOpenAI

    langchain_openai = types.ModuleType("langchain_openai")
    langchain_openai.ChatOpenAI = chat_openai_class
    messages = types.ModuleType("langchain_core.messages")
    messages.SystemMessage = Message
    messages.HumanMessage = Message
    messages.AIMessage = Message
    monkeypatch.setitem(sys.modules, "langchain_openai", langchain_openai)
    monkeypatch.setitem(sys.modules, "langchain_core.messages", messages)

    spec = importlib.util.spec_from_file_location("chat_agent_collection_under_test", ROOT / "agents/chat_agent.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeModel:
    def __init__(self, extracted=None, stream_chunks=None):
        self.extracted = extracted or {}
        self.stream_chunks = stream_chunks or ['{"ask_fields":["name"]}']
        self.invoke_messages = []
        self.stream_messages = []
        self.stream_calls = 0

    def invoke(self, messages):
        self.invoke_messages.append(messages)
        return Message(json.dumps(self.extracted, ensure_ascii=False))

    def stream(self, messages):
        self.stream_calls += 1
        self.stream_messages = messages
        return iter([Message(content) for content in self.stream_chunks])


def make_agent(chat_module, model):
    agent = chat_module.ChatAgent.__new__(chat_module.ChatAgent)
    agent.model = model
    agent.required_fields = [
        "name", "city", "days", "budget", "people", "kids", "health", "hobbies", "start_date", "accommodation_preference"
    ]
    agent.all_fields = agent.required_fields + [
        "origin",
        "specificRequirements",
        "dietary_needs",
        "travel_pace",
        "transport_preference",
    ]
    agent.conversation_history = []
    return agent


def stream_text(result):
    return "".join(message.content for message in result["stream"])


def test_constructor_makes_question_model_fail_fast_and_extractor_deterministic(monkeypatch):
    constructor_calls = []

    class RecordingChatOpenAI:
        def __init__(self, **kwargs):
            constructor_calls.append(kwargs)

    chat_module = load_chat_module(monkeypatch, RecordingChatOpenAI)

    chat_module.ChatAgent(model_name="test-model")

    assert len(constructor_calls) == 2
    extractor_options, question_options = constructor_calls
    assert extractor_options["temperature"] == 0
    assert "max_retries" not in extractor_options
    assert question_options["temperature"] == 0.2
    assert question_options["streaming"] is True
    assert question_options["max_retries"] == 0


def test_non_complete_reply_has_exact_headers_and_stable_populated_field_order(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    agent = make_agent(chat_module, FakeModel(stream_chunks=['{"ask_fields":["name"]}']))
    state = {
        "transport_preference": "铁路",
        "dietary_needs": ["素食", "无花生"],
        "specificRequirements": {"无障碍": "需要", "安静": True},
        "accommodation_preference": "交通便利",
        "hobbies": ["博物馆", "咖啡"],
        "health": "good",
        "budget": "8000",
        "kids": "no",
        "people": 2,
        "days": 4,
        "start_date": "2026-08-01",
        "city": "东京",
        "origin": "上海",
        "travel_pace": "舒缓",
    }

    result = agent.collect_info("", state)

    assert stream_text(result) == (
        "已收集到的信息\n"
        "出发地：上海\n"
        "目的地：东京\n"
        "出发日期：2026-08-01\n"
        "旅行天数：4\n"
        "出行人数：2\n"
        "是否携带儿童：否\n"
        "预算：8000\n"
        "健康与行动状况：良好\n"
        "旅行偏好：博物馆、咖啡\n"
        "住宿偏好：交通便利\n"
        "具体要求：安静：是；无障碍：需要\n"
        "饮食需求：素食、无花生\n"
        "旅行节奏：舒缓\n"
        "交通偏好：铁路\n\n"
        "还需要了解的信息\n"
        "请问怎么称呼您？"
    )
    assert result["missing_fields"] == ["name"]
    assert result["complete"] is False


def test_deterministic_prefix_is_streamed_before_question_model_chunks(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    model = FakeModel(stream_chunks=['{"ask_fields":', '["name"]}'])
    agent = make_agent(chat_module, model)

    chunks = list(agent.collect_info("", {"city": "杭州"})["stream"])

    assert chunks[0].content == "已收集到的信息\n目的地：杭州\n\n还需要了解的信息\n"
    assert [chunk.content for chunk in chunks[1:]] == ["请问怎么称呼您？"]


def test_missing_value_recognizes_empty_and_undecided_start_dates(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    agent = make_agent(chat_module, FakeModel())

    for value in (None, "", "   ", "not decided", "NOT DECIDED", "待定", "未确定"):
        assert agent._is_missing_value("start_date", value) is True

    assert agent._is_missing_value("start_date", "2026-08-01") is False
    assert agent._is_missing_value("hobbies", "待定") is False


def test_collect_info_uses_separate_models_once_and_passes_current_date_to_both(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    extractor = FakeModel({"city": "东京"})
    question = FakeModel(stream_chunks=['{"ask_fields":["name"]}'])
    agent = make_agent(chat_module, question)
    agent.extractor_model = extractor
    agent.question_model = question

    result = agent.collect_info("目的地是东京", {}, current_date="2026-07-20")
    list(result["stream"])

    assert len(extractor.invoke_messages) == 1
    assert question.stream_calls == 1
    assert question.invoke_messages == []
    assert "2026-07-20" in extractor.invoke_messages[0][0].content
    follow_up_prompt = question.stream_messages[-1].content
    assert "2026-07-20" in follow_up_prompt
    assert "已收集到的信息\n目的地：东京" in follow_up_prompt
    allowed_fields = follow_up_prompt.split("允许选择的缺失字段 ID：", 1)[1].split("。", 1)[0]
    assert '"name"' in allowed_fields
    assert '"city"' not in allowed_fields


def test_question_prompt_forbids_collection_stage_planning_and_recommendations(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    model = FakeModel()
    agent = make_agent(chat_module, model)

    agent.collect_info("", {"city": "东京"}, current_date="2026-07-20")

    follow_up_prompt = model.stream_messages[-1].content
    for forbidden_topic in ("景点", "餐厅", "酒店", "路线", "行程规划", "推荐"):
        assert forbidden_topic in follow_up_prompt
    assert "只输出严格 JSON" in follow_up_prompt
    assert '{"ask_fields"' in follow_up_prompt
    assert "最多选择 1-2 个字段 ID" in follow_up_prompt


def test_structured_question_selection_renders_only_validated_budget_template(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    model = FakeModel(stream_chunks=['{"ask_fields":["budget"]}'])
    agent = make_agent(chat_module, model)
    agent.required_fields = ["budget", "start_date"]

    text = stream_text(agent.collect_info("", {}))

    assert text == (
        "已收集到的信息\n\n"
        "还需要了解的信息\n"
        "请问您的旅行预算是多少？"
    )
    assert "出发" not in text
    assert model.stream_calls == 1


def test_single_json_fence_is_accepted(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    model = FakeModel(
        stream_chunks=['```json\n{"ask_fields":["budget"]}\n```']
    )
    agent = make_agent(chat_module, model)
    agent.required_fields = ["budget", "start_date"]

    text = stream_text(agent.collect_info("", {}))

    assert text.endswith("请问您的旅行预算是多少？")
    assert "出发" not in text


@pytest.mark.parametrize(
    "model_output",
    [
        '{"ask_fields":["budget","budget"]}',
        '{"ask_fields":"budget"}',
        '{"ask_fields":[1]}',
    ],
)
def test_malformed_ask_fields_values_use_deterministic_fallback(
    monkeypatch, model_output
):
    chat_module = load_chat_module(monkeypatch)
    model = FakeModel(stream_chunks=[model_output])
    agent = make_agent(chat_module, model)
    agent.required_fields = ["name", "budget", "start_date"]

    text = stream_text(agent.collect_info("", {}))

    assert text.endswith("请问怎么称呼您？\n请问您的旅行预算是多少？")
    assert model_output not in text


def test_duplicate_json_object_keys_use_deterministic_fallback(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    model = FakeModel(
        stream_chunks=[
            '{"ask_fields":["budget"],"ask_fields":["start_date"]}'
        ]
    )
    agent = make_agent(chat_module, model)
    agent.required_fields = ["name", "budget", "start_date"]

    text = stream_text(agent.collect_info("", {}))

    assert text.endswith("请问怎么称呼您？\n请问您的旅行预算是多少？")
    assert "哪天出发" not in text


def test_extra_text_around_json_is_rejected_without_leaking(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    model_output = '请选择：{"ask_fields":["start_date"]}'
    model = FakeModel(stream_chunks=[model_output])
    agent = make_agent(chat_module, model)
    agent.required_fields = ["name", "budget", "start_date"]

    text = stream_text(agent.collect_info("", {}))

    assert "请选择" not in text
    assert "ask_fields" not in text
    assert text.endswith("请问怎么称呼您？\n请问您的旅行预算是多少？")


def test_iteration_time_question_stream_failure_uses_fallback_without_retry(monkeypatch):
    chat_module = load_chat_module(monkeypatch)

    class IterationFailingModel(FakeModel):
        def stream(self, messages):
            self.stream_calls += 1

            def chunks():
                yield Message('{"ask_fields":')
                raise RuntimeError("stream interrupted")

            return chunks()

    model = IterationFailingModel()
    agent = make_agent(chat_module, model)
    agent.required_fields = ["name", "budget"]

    text = stream_text(agent.collect_info("", {}))

    assert text.endswith("请问怎么称呼您？\n请问您的旅行预算是多少？")
    assert "ask_fields" not in text
    assert model.stream_calls == 1


def test_collection_guard_replaces_model_trip_planning_with_missing_field_question(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    model = FakeModel(stream_chunks=["推荐你游览外滩，并安排一家餐厅。"])
    agent = make_agent(chat_module, model)
    agent.required_fields = ["name"]

    text = stream_text(agent.collect_info("", {}))

    assert "推荐" not in text
    assert "外滩" not in text
    assert "餐厅" not in text
    assert text == "已收集到的信息\n\n还需要了解的信息\n请问怎么称呼您？"


def test_collection_guard_replaces_question_about_a_populated_field(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    model = FakeModel(stream_chunks=['{"ask_fields":["city"]}'])
    agent = make_agent(chat_module, model)
    agent.required_fields = ["name", "city"]

    text = stream_text(agent.collect_info("", {"city": "杭州"}))

    assert text == (
        "已收集到的信息\n"
        "目的地：杭州\n\n"
        "还需要了解的信息\n"
        "请问怎么称呼您？"
    )
    assert model.stream_calls == 1


def test_raw_question_prose_is_rejected_without_leaking_gui_xing(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    model = FakeModel(stream_chunks=["请问您贵姓？"])
    agent = make_agent(chat_module, model)
    agent.required_fields = ["name", "budget"]

    text = stream_text(agent.collect_info("", {}))

    assert "贵姓" not in text
    assert text.endswith("请问怎么称呼您？\n请问您的旅行预算是多少？")


def test_duplicate_heading_from_model_is_rejected_and_never_leaks(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    model = FakeModel(
        stream_chunks=['还需要了解的信息\n{"ask_fields":["start_date"]}']
    )
    agent = make_agent(chat_module, model)
    agent.required_fields = ["name", "budget", "start_date"]

    text = stream_text(agent.collect_info("", {}))

    assert text.count("还需要了解的信息") == 1
    assert text.endswith("请问怎么称呼您？\n请问您的旅行预算是多少？")


@pytest.mark.parametrize(
    "model_output",
    [
        '{"ask_fields":["unknown_field"]}',
        '{"ask_fields":["name","budget","start_date"]}',
    ],
)
def test_unknown_or_too_many_structured_fields_use_deterministic_fallback(
    monkeypatch, model_output
):
    chat_module = load_chat_module(monkeypatch)
    model = FakeModel(stream_chunks=[model_output])
    agent = make_agent(chat_module, model)
    agent.required_fields = ["name", "budget", "start_date"]

    text = stream_text(agent.collect_info("", {}))

    assert text.endswith("请问怎么称呼您？\n请问您的旅行预算是多少？")
    assert "ask_fields" not in text


def test_summary_omits_nested_values_that_are_entirely_missing(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    agent = make_agent(chat_module, FakeModel())

    summary = agent._format_collected_summary(
        {
            "specificRequirements": {"安静": None},
            "dietary_needs": [None, ""],
        }
    )

    assert summary == "已收集到的信息"
    assert "None" not in summary


def test_summary_recursively_keeps_only_useful_nested_values(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    agent = make_agent(chat_module, FakeModel())

    summary = agent._format_collected_summary(
        {
            "hobbies": [None, "博物馆", "", "咖啡"],
            "specificRequirements": {
                "安静": None,
                "备注": "",
                "无障碍": "需要",
            },
        }
    )

    assert summary == (
        "已收集到的信息\n"
        "旅行偏好：博物馆、咖啡\n"
        "具体要求：无障碍：需要"
    )
    assert "None" not in summary


def test_collection_keeps_exact_structure_when_question_model_fails(monkeypatch):
    chat_module = load_chat_module(monkeypatch)

    class FailingQuestionModel(FakeModel):
        def stream(self, messages):
            self.stream_calls += 1
            raise RuntimeError("question model unavailable")

    model = FailingQuestionModel()
    agent = make_agent(chat_module, model)
    agent.required_fields = ["name"]

    result = agent.collect_info("", {})

    assert stream_text(result) == "已收集到的信息\n\n还需要了解的信息\n请问怎么称呼您？"
    assert result["error"] == "question model unavailable"
    assert model.stream_calls == 1


def test_collect_info_recognizes_health_good_without_llm_support(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    agent = make_agent(chat_module, FakeModel())

    result = agent.collect_info("我身体健康状况良好", {})

    assert result["state"]["health"] == "good"


def test_collect_info_keeps_departure_and_destination_in_their_own_fields(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    # Simulate a model that makes the reported city-role mistake.
    agent = make_agent(chat_module, FakeModel({"city": "上海"}))

    result = agent.collect_info("我从上海出发去东京", {})

    assert result["state"]["origin"] == "上海"
    assert result["state"]["city"] == "东京"


def test_collect_info_handles_a_pause_between_departure_and_destination(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    agent = make_agent(chat_module, FakeModel())

    result = agent.collect_info("我从上海出发，想去东京旅行", {})

    assert result["state"]["origin"] == "上海"
    assert result["state"]["city"] == "东京"


def test_collect_info_allows_an_explicit_destination_correction(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    agent = make_agent(chat_module, FakeModel())

    result = agent.collect_info("目的地改为东京", {"origin": "上海", "city": "上海"})

    assert result["state"]["origin"] == "上海"
    assert result["state"]["city"] == "东京"


def test_explicit_trip_days_override_a_model_confused_by_the_calendar_day(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    agent = make_agent(chat_module, FakeModel({"days": 10}))

    result = agent.collect_info("计划2026年8月10日去上海旅行4天", {})

    assert result["state"]["start_date"] == "2026-08-10"
    assert result["state"]["days"] == "4"


def test_family_friendly_hotel_preference_can_imply_children_are_traveling(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    agent = make_agent(chat_module, FakeModel({"kids": "yes"}))

    result = agent.collect_info(
        "2位成人出行，住宿希望亲子友好并且带早餐",
        {"kids": "no"},
    )

    assert result["state"]["kids"] == "yes"


def test_llm_extracted_children_status_is_kept_when_rule_parser_is_silent(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    agent = make_agent(chat_module, FakeModel({"kids": "no"}))

    result = agent.collect_info("这趟两个大人出行", {})

    assert result["state"]["kids"] == "no"


def test_explicit_no_children_in_full_trip_query_fills_kids_even_if_llm_misses_it(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    agent = make_agent(
        chat_module,
        FakeModel(
            {
                "name": "邹邹",
                "origin": "广州",
                "city": "东京",
                "start_date": "2026-10-03",
                "days": "5",
                "people": "2",
                "budget": "30000",
                "hobbies": "美术馆、街区漫步、日料",
                "accommodation_preference": "新宿或涩谷地铁站附近的中高档酒店，要早餐和健身房",
                "travel_pace": "不要太赶",
            }
        ),
    )

    result = agent.collect_info(
        "我叫邹邹，今年10月3日从广州去东京5天，两位成人，不携带儿童，预算3万元，"
        "喜欢美术馆、街区漫步和日料。希望住新宿或涩谷地铁站附近的中高档酒店，"
        "要早餐和健身房，行程节奏不要太赶。",
        {},
        current_date="2026-07-20",
    )

    assert result["state"]["city"] == "东京"
    assert result["state"]["budget"] == "30000"
    assert result["state"]["kids"] == "no"
    assert "kids" not in result["missing_fields"]
    assert result["missing_fields"] == ["health"]


def test_llm_extracted_children_and_health_values_are_normalized(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    agent = make_agent(
        chat_module,
        FakeModel({"kids": "2个大人1个小孩", "health": "不适合太累"}),
    )

    result = agent.collect_info("我们是2个大人1个小孩，身体还可以但不适合太累", {})

    assert result["state"]["kids"] == "yes"
    assert result["state"]["health"] == "limited"


def test_llm_extracted_no_children_phrase_is_normalized(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    agent = make_agent(chat_module, FakeModel({"kids": "不携带儿童"}))

    result = agent.collect_info("不携带儿童", {})

    assert result["state"]["kids"] == "no"


def test_extraction_prompt_teaches_llm_children_and_health_examples(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    model = FakeModel({"city": "东京"})
    agent = make_agent(chat_module, model)

    agent.collect_info("目的地东京", {}, current_date="2026-07-20")

    extraction_prompt = model.invoke_messages[0][0].content
    assert "不携带儿童" in extraction_prompt
    assert "两个大人" in extraction_prompt
    assert "2大一小" in extraction_prompt
    assert "两个大人和一个上小学的孩子" in extraction_prompt
    assert "亲子友好酒店" in extraction_prompt
    assert "不适合太累" in extraction_prompt


def test_explicit_family_trip_still_sets_children_yes(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    agent = make_agent(chat_module, FakeModel({"kids": "no"}))

    result = agent.collect_info("这次是带孩子的亲子游", {})

    assert result["state"]["kids"] == "yes"


def test_follow_up_prompt_only_collects_missing_fields(monkeypatch):
    chat_module = load_chat_module(monkeypatch)
    model = FakeModel()
    agent = make_agent(chat_module, model)

    agent.collect_info("预算五千，身体健康良好", {})

    follow_up_prompt = model.stream_messages[-1].content
    assert "Do not recommend attractions, restaurants, hotels, routes, or an itinerary" in follow_up_prompt
    assert "Ask only for the missing fields" in follow_up_prompt


def test_candidate_page_has_a_preference_correction_path():
    source = (ROOT.parent / "nlp_tripagent_frontend/src/views/MapView.vue").read_text()

    assert "修改旅行偏好" in source
    assert "function returnToChatForEdits" in source
    assert "sessionStore.setStep('chat')" in source


def test_booking_confirmation_uses_langchain_invoke(monkeypatch):
    class ChatOpenAI:
        pass

    langchain_openai = types.ModuleType("langchain_openai")
    langchain_openai.ChatOpenAI = ChatOpenAI
    messages = types.ModuleType("langchain_core.messages")
    messages.SystemMessage = Message
    messages.HumanMessage = Message
    monkeypatch.setitem(sys.modules, "langchain_openai", langchain_openai)
    monkeypatch.setitem(sys.modules, "langchain_core.messages", messages)

    spec = importlib.util.spec_from_file_location("communication_agent_under_test", ROOT / "agents/communication_agent.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    class InvokeOnlyModel:
        def invoke(self, message_list):
            assert len(message_list) == 2
            return Message("行程已生成")

    agent = module.CommunicationAgent.__new__(module.CommunicationAgent)
    agent.model = InvokeOnlyModel()

    result = agent.generate_booking_confirmation(
        [{"date": "2026-08-01", "spots": [{"name": "外滩"}]}],
        {"total": 1200},
    )

    assert result == "行程已生成"


def test_booking_confirmation_prompt_requires_chinese_structured_trip_plan(monkeypatch):
    class ChatOpenAI:
        pass

    langchain_openai = types.ModuleType("langchain_openai")
    langchain_openai.ChatOpenAI = ChatOpenAI
    messages = types.ModuleType("langchain_core.messages")
    messages.SystemMessage = Message
    messages.HumanMessage = Message
    monkeypatch.setitem(sys.modules, "langchain_openai", langchain_openai)
    monkeypatch.setitem(sys.modules, "langchain_core.messages", messages)

    spec = importlib.util.spec_from_file_location("communication_agent_prompt_under_test", ROOT / "agents/communication_agent.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    class RecordingModel:
        def __init__(self):
            self.messages = None

        def invoke(self, message_list):
            self.messages = message_list
            return Message("行程概览\n温馨提示\n每日具体行程")

    agent = module.CommunicationAgent.__new__(module.CommunicationAgent)
    agent.model = RecordingModel()

    agent.generate_booking_confirmation(
        [{"date": "2026-08-01", "spots": [{"name": "外滩", "start_time": "09:00", "end_time": "11:00"}]}],
        {"total": 1200},
        user_name="小王",
    )

    system_prompt = agent.model.messages[0].content
    human_prompt = agent.model.messages[1].content
    assert "中文" in system_prompt
    assert "行程概览" in system_prompt
    assert "温馨提示" in system_prompt
    assert "每日具体行程" in system_prompt
    assert "Subject:" not in human_prompt
    assert "email" not in human_prompt.lower()
    assert "attached" not in human_prompt.lower()
    assert "时间、地点、午饭、晚饭" in human_prompt


def test_strategy_recommendation_uses_langchain_invoke(monkeypatch):
    class ChatOpenAI:
        pass

    langchain_openai = types.ModuleType("langchain_openai")
    langchain_openai.ChatOpenAI = ChatOpenAI
    messages = types.ModuleType("langchain_core.messages")
    messages.SystemMessage = Message
    messages.HumanMessage = Message
    messages.AIMessage = Message
    utils = types.ModuleType("utils")
    utils.ask_openai = lambda _: {"answer": "{}"}
    monkeypatch.setitem(sys.modules, "langchain_openai", langchain_openai)
    monkeypatch.setitem(sys.modules, "langchain_core.messages", messages)
    monkeypatch.setitem(sys.modules, "utils", utils)

    spec = importlib.util.spec_from_file_location("strategy_agent_under_test", ROOT / "agents/strategy_agent.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    class InvokeOnlyModel:
        def invoke(self, message_list):
            assert len(message_list) == 2
            return Message("[car_rental:NO] 无需租车。")

    agent = module.StrategyAgent.__new__(module.StrategyAgent)
    agent.model = InvokeOnlyModel()
    user_prefs = {"name": "小王", "kids": "no"}

    result = list(agent.get_ai_recommendation(user_prefs, [], 1))

    assert result[0].content.strip() == "无需租车。"
    assert user_prefs["should_rent_car"] is False


def test_strategy_prompt_defines_required_travel_plan_sections():
    source = (ROOT / "agents/strategy_agent.py").read_text()

    assert "行程概览" in source
    assert "温馨提示" in source
    assert "每日具体行程" in source
    assert "时间" in source
    assert "地点" in source
    assert "午饭" in source
    assert "晚饭" in source


def test_results_page_continue_chat_spans_full_content_width():
    source = (ROOT.parent / "nlp_tripagent_frontend/src/views/ResultsPage.vue").read_text()

    assert 'class="continue-chat-card"' in source
    assert ".continue-chat-card" in source
    assert "grid-column: 1 / -1" in source
