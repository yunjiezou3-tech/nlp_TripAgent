import os
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage
import json
import re
from typing import Generator


ACCOMMODATION_AMENITIES = {
    "早餐": ("早餐", "早饭", "含早", "含早餐"),
    "亲子": ("亲子", "儿童", "家庭友好", "适合带娃"),
    "洗衣机": ("洗衣机", "洗衣房", "自助洗衣", "洗衣服务"),
    "健身房": ("健身房", "健身中心", "健身设施"),
    "吧台": ("吧台", "酒吧", "bar"),
    "无障碍": ("无障碍", "轮椅", "电梯"),
}

FIELD_ORDER = (
    "name",
    "origin",
    "city",
    "start_date",
    "days",
    "people",
    "kids",
    "budget",
    "health",
    "hobbies",
    "accommodation_preference",
    "specificRequirements",
    "dietary_needs",
    "travel_pace",
    "transport_preference",
)

FIELD_LABELS = {
    "name": "称呼",
    "origin": "出发地",
    "city": "目的地",
    "start_date": "出发日期",
    "days": "旅行天数",
    "people": "出行人数",
    "kids": "是否携带儿童",
    "budget": "预算",
    "health": "健康与行动状况",
    "hobbies": "旅行偏好",
    "accommodation_preference": "住宿偏好",
    "specificRequirements": "具体要求",
    "dietary_needs": "饮食需求",
    "travel_pace": "旅行节奏",
    "transport_preference": "交通偏好",
}

FIELD_QUESTION_TEMPLATES = {
    "name": "请问怎么称呼您？",
    "origin": "请问您从哪里出发？",
    "city": "请问您的目的地是哪里？",
    "start_date": "请问您计划哪天出发？",
    "days": "请问您计划旅行几天？",
    "people": "请问一共有多少人出行？",
    "kids": "请问是否携带儿童？",
    "budget": "请问您的旅行预算是多少？",
    "health": "请问您的健康与行动状况如何？",
    "hobbies": "请问您有哪些旅行偏好？",
    "accommodation_preference": "请问您有什么住宿偏好？",
    "specificRequirements": "请问您还有哪些具体要求？",
    "dietary_needs": "请问您有哪些饮食需求？",
    "travel_pace": "请问您偏好怎样的旅行节奏？",
    "transport_preference": "请问您偏好哪种交通方式？",
}


def parse_accommodation_preferences(text: str) -> dict:
    """Normalize hotel preferences that can be applied before Places ranking."""
    raw_text = text or ""
    normalized = raw_text.lower()
    result = {
        "area": "",
        "price_level": {"min": None, "max": None},
        "min_rating": None,
        "max_distance_to_core_km": None,
        "amenities": [],
    }

    area_match = re.search(
        r"(?:住在?|入住|住宿(?:在|选)?|酒店(?:在|选)?)([^，。；,;]{2,30}?(?:附近|周边|一带|区域))",
        raw_text,
    )
    if area_match:
        result["area"] = area_match.group(1).strip()

    rating_match = re.search(r"(?:评分|rating)\s*(\d(?:\.\d+)?)\s*(?:以上|及以上|起|\+)", normalized)
    if rating_match:
        result["min_rating"] = float(rating_match.group(1))

    distance_match = re.search(r"(?:距离?|离|距)\s*(?:核心景点|景点|市中心)?\s*(\d+(?:\.\d+)?)\s*(?:公里|千米|km)", normalized)
    if distance_match:
        result["max_distance_to_core_km"] = float(distance_match.group(1))

    if any(keyword in normalized for keyword in ("经济", "低预算", "便宜", "实惠")):
        result["price_level"] = {"min": 0, "max": 1}
    elif any(keyword in normalized for keyword in ("中高", "中上")):
        result["price_level"] = {"min": 2, "max": 3}
    elif any(keyword in normalized for keyword in ("中等", "中档", "预算中")):
        result["price_level"] = {"min": 2, "max": 2}
    elif any(keyword in normalized for keyword in ("高档", "高端", "豪华", "奢华")):
        result["price_level"] = {"min": 3, "max": 4}

    matched_amenities = []
    for amenity, keywords in ACCOMMODATION_AMENITIES.items():
        positions = [normalized.find(keyword) for keyword in keywords if normalized.find(keyword) >= 0]
        if positions:
            matched_amenities.append((min(positions), amenity))
    result["amenities"] = [amenity for _, amenity in sorted(matched_amenities)]
    return result

class ChatAgent:
    def __init__(self, model_name="deepseek-chat"):
        """Initialize the ChatAgent with specified model."""
        model_options = {
            "model_name": model_name,
            "openai_api_key": os.getenv("DEEPSEEK_API_KEY"),
            "openai_api_base": "https://api.deepseek.com/v1",
        }
        # Keep extraction deterministic and keep follow-up generation narrowly scoped.
        self.extractor_model = ChatOpenAI(temperature=0, **model_options)
        self.question_model = ChatOpenAI(
            temperature=0.2,
            streaming=True,
            max_retries=0,
            **model_options,
        )
        self.model = self.question_model  # Backward compatibility for existing integrations.
        # Define required fields (these must be filled)
        self.required_fields = ["name", "city", "days", "budget", "people", "kids", "health", "hobbies", "start_date", "accommodation_preference"]
        # Define all fields, including optional ones
        self.all_fields = list(FIELD_ORDER)
        self.conversation_history = []

    def _get_extractor_model(self):
        return getattr(self, "extractor_model", self.model)

    def _get_question_model(self):
        return getattr(self, "question_model", self.model)
        
    def _init_system_message(self):
        """Initialize system message for the conversation."""
        return SystemMessage(content="""
        You are a helpful travel assistant. Your job is to collect information about the user's travel plans.
        Be friendly, conversational, and help the user plan their trip. Collect all necessary information.
        Also pay attention to any specific requirements the traveler mentions, such as accessibility needs,
        food restrictions, special interests, or any constraints that might affect their trip.
        Prefer replying in Chinese unless the user explicitly asks for another language.
        """)
        
    def collect_info(self, user_input: str, state: dict = None, current_date: str = None) -> dict:
        """Check for missing information and ask user questions to complete the required information."""
        if state is None:
            state = {}
        
        # Initialize conversation if it's empty
        if not self.conversation_history:
            self.conversation_history.append(self._init_system_message())
        
        # Merge new inputs into state
        if user_input and user_input.strip():
            new_info = self.extract_info_from_message(user_input, state, current_date=current_date)
            for field, value in new_info.items():
                if not self._is_missing_value(field, value):
                    state[field] = value
            if state.get("accommodation_preference"):
                state["accommodation_preferences"] = parse_accommodation_preferences(
                    state["accommodation_preference"]
                )
        
        # Add user input to conversation if not empty
        if user_input and user_input.strip():
            self.conversation_history.append(HumanMessage(content=user_input))
        
        # Get AI response based on current state and conversation history
        messages = self.conversation_history.copy()
        
        missing_fields = [
            field
            for field in self.required_fields
            if self._is_missing_value(field, state.get(field))
        ]
        
        # Only prompt for missing information if there are actually missing fields
        if missing_fields:
            messages.append(
                SystemMessage(
                    content=self._build_collection_prompt(
                        state,
                        missing_fields,
                        current_date=current_date,
                    )
                )
            )
        else:
            return {
                "stream": self._collection_response_stream(state, [], None),
                "missing_fields": [],
                "complete": True,
                "state": state.copy(),
            }
        
        try:
            question_stream = self._get_question_model().stream(messages)
            response = self._collection_response_stream(state, missing_fields, question_stream)
            return {
                "stream": response,
                "missing_fields": missing_fields,
                "complete": False,
                "state": state.copy()
            }
        except Exception as e:
            print(f"Error getting AI response: {e}")
            return {
                "stream": self._collection_response_stream(state, missing_fields, None),
                "missing_fields": missing_fields,
                "complete": False,
                "state": state.copy(),
                "error": str(e)
            }
    
    def interact_with_user(self, message: str, state: dict = None) -> Generator:
        """Process user message and generate a streaming response."""
        if state is None:
            state = {}
            
        # Add user message to conversation
        self.conversation_history.append(HumanMessage(content=message))
        
        # Generate streaming response based on the conversation history
        try:
            return self._get_question_model().stream(self.conversation_history)
        except Exception as e:
            print(f"Error in interact_with_user: {e}")
            return None
    
    def _build_collection_prompt(
        self,
        state: dict,
        missing_fields: list[str],
        current_date: str = None,
    ) -> str:
        missing_labels = [FIELD_LABELS.get(field, field) for field in missing_fields]
        collected_summary = self._format_collected_summary(state)
        date_context = current_date or "未提供"
        return f"""
        这是信息收集回合，不是旅行规划回合。
        当前日期锚点（YYYY-MM-DD）：{date_context}。
        当前已收集摘要：
        {collected_summary}
        精确缺失字段标签：{json.dumps(missing_labels, ensure_ascii=False)}。
        允许选择的缺失字段 ID：{json.dumps(missing_fields, ensure_ascii=False)}。

        只输出严格 JSON，唯一允许的结构是：{{"ask_fields":["field_id"]}}。
        ask_fields 最多选择 1-2 个字段 ID，且只能来自允许选择的缺失字段 ID 列表。
        不要输出自然语言问题、摘要、标题、确认语、Markdown 或任何额外键及额外文本。
        严禁景点、餐厅、酒店、路线、行程规划或任何推荐内容，也不要比较目的地。
        Return only strict JSON. Select at most 1-2 IDs exclusively from the allowed missing field IDs.
        Do not recommend attractions, restaurants, hotels, routes, or an itinerary.
        Ask only for the missing fields.
        Do not return natural-language prose or recommend attractions, restaurants, hotels, routes, or an itinerary.
        """

    @staticmethod
    def _is_missing_value(field: str, value) -> bool:
        if value is None:
            return True
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return True
            if field == "start_date" and normalized.lower() in {
                "none",
                "not decided",
                "待定",
                "未确定",
            }:
                return True
        if isinstance(value, (list, tuple, set, dict)) and not value:
            return True
        return False

    def _format_collected_summary(self, state: dict) -> str:
        lines = ["已收集到的信息"]
        for field in FIELD_ORDER:
            value = state.get(field)
            if self._is_missing_value(field, value):
                continue
            formatted_value = self._format_collection_value(field, value)
            if formatted_value:
                lines.append(f"{FIELD_LABELS[field]}：{formatted_value}")
        return "\n".join(lines)

    def _format_collection_value(self, field: str, value) -> str:
        if self._is_missing_value(field, value):
            return ""
        if isinstance(value, bool):
            return "是" if value else "否"
        if isinstance(value, dict):
            parts = []
            for key in sorted(value, key=str):
                item = value[key]
                formatted_item = self._format_collection_value(str(key), item)
                if not formatted_item:
                    continue
                label = FIELD_LABELS.get(str(key), str(key))
                if label:
                    parts.append(f"{label}：{formatted_item}")
            return "；".join(parts)
        if isinstance(value, (list, tuple, set)):
            items = value if not isinstance(value, set) else sorted(value, key=str)
            formatted_items = [
                self._format_collection_value(field, item)
                for item in items
            ]
            return "、".join(item for item in formatted_items if item)

        text = str(value).strip()
        if field == "kids":
            return {"yes": "是", "no": "否", "true": "是", "false": "否"}.get(
                text.lower(), text
            )
        if field == "health":
            return {
                "good": "良好",
                "excellent": "极佳",
                "limited": "行动不便",
            }.get(text.lower(), text)
        return text

    @staticmethod
    def _strip_json_fence(content: str) -> str:
        stripped = content.strip()
        fenced = re.fullmatch(r"```json\s*(.*?)\s*```", stripped, flags=re.DOTALL)
        return fenced.group(1).strip() if fenced else stripped

    def _parse_ask_fields(self, content: str, missing_fields: list[str]):
        def reject_duplicate_keys(pairs):
            payload = {}
            for key, value in pairs:
                if key in payload:
                    raise ValueError(f"duplicate JSON key: {key}")
                payload[key] = value
            return payload

        try:
            payload = json.loads(
                self._strip_json_fence(content),
                object_pairs_hook=reject_duplicate_keys,
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

        if not isinstance(payload, dict) or set(payload) != {"ask_fields"}:
            return None
        return self._normalize_ask_fields(payload["ask_fields"], missing_fields)

    @staticmethod
    def _normalize_ask_fields(ask_fields, missing_fields):
        if not isinstance(ask_fields, list) or not 1 <= len(ask_fields) <= 2:
            return None
        if any(not isinstance(field, str) for field in ask_fields):
            return None
        if len(set(ask_fields)) != len(ask_fields):
            return None
        if any(field not in missing_fields for field in ask_fields):
            return None
        return ask_fields

    @staticmethod
    def _render_field_questions(ask_fields, question_overrides=None) -> str:
        overrides = question_overrides or {}
        questions = []
        for field in ask_fields:
            question = overrides.get(field) or FIELD_QUESTION_TEMPLATES.get(field)
            if question:
                questions.append(question)
        return "\n".join(questions)

    def _collection_response_stream(
        self,
        state,
        missing_fields,
        question_stream=None,
        ask_fields=None,
        question_overrides=None,
    ):
        def response_stream():
            if not missing_fields:
                yield AIMessage(content="信息已收集完成，正在检索候选地点。")
                return

            prefix = f"{self._format_collected_summary(state)}\n\n还需要了解的信息\n"
            yield AIMessage(content=prefix)

            selected_fields = ask_fields
            if selected_fields is None:
                try:
                    chunks = list(question_stream or ())
                except Exception:
                    chunks = []
                model_content = "".join(
                    getattr(chunk, "content", str(chunk)) for chunk in chunks
                )
                selected_fields = self._parse_ask_fields(model_content, missing_fields)
            else:
                selected_fields = self._normalize_ask_fields(
                    selected_fields, missing_fields
                )
            if selected_fields is None:
                selected_fields = missing_fields[:2]

            rendered_questions = self._render_field_questions(
                selected_fields, question_overrides=question_overrides
            )
            if rendered_questions:
                yield AIMessage(content=rendered_questions)

        return response_stream()

    @staticmethod
    def _clean_location(value: str) -> str:
        value = (value or "").strip(" ，。；,;：:")
        value = re.sub(r"(?:旅游|旅行|游玩|玩|待)?\s*\d{1,2}\s*天$", "", value).strip()
        value = re.sub(r"(?:旅游|旅行|游玩|玩|待)$", "", value).strip()
        return value

    def _extract_rule_based_info(self, message: str) -> dict:
        """Extract high-confidence Chinese travel facts without depending on model interpretation."""
        text = message.strip()
        result = {}

        trip_match = re.search(
            r"(?:从|由)\s*(?P<origin>[^，。；,;、\s]{2,30}?)\s*(?:出发|启程)?\s*(?:，|,)?\s*(?:想)?\s*(?:去|到|前往|飞往)\s*(?P<city>[^，。；,;、\s]{2,30})",
            text,
        )
        if trip_match:
            result["origin"] = self._clean_location(trip_match.group("origin"))
            result["city"] = self._clean_location(trip_match.group("city"))

        origin_match = re.search(
            r"(?:出发地|始发地)\s*(?:不是\s*[^，。；,;、]+[，,;、]?\s*)?(?:改为|改成|是|为|[:：])\s*(?P<origin>[^，。；,;、\s]{2,30})",
            text,
        )
        if origin_match:
            result["origin"] = self._clean_location(origin_match.group("origin"))

        destination_match = re.search(
            r"(?:目的地|目的城市)\s*(?:不是\s*[^，。；,;、]+[，,;、]?\s*)?(?:改为|改成|是|为|[:：])\s*(?P<city>[^，。；,;、\s]{2,30})",
            text,
        )
        if destination_match:
            result["city"] = self._clean_location(destination_match.group("city"))

        if "health" not in result:
            if any(term in text for term in ("行动不便", "身体不便", "腿脚不便", "轮椅", "无障碍", "健康欠佳")):
                result["health"] = "limited"
            elif any(term in text for term in ("健康状况极佳", "身体非常好", "身体很棒")):
                result["health"] = "excellent"
            elif any(term in text for term in ("健康状况良好", "身体健康", "身体状况良好", "健康良好", "身体很好")):
                result["health"] = "good"

        days_match = re.search(
            r"(?:旅行|游玩|停留|行程|玩|待|住)\D{0,4}(\d{1,2})\s*天",
            text,
        )
        if not days_match:
            days_match = re.search(r"(?<![\d年月日/.-])(\d{1,2})\s*天", text)
        if not days_match:
            days_match = re.search(r"(?<![\d年月/.-])(\d{1,2})\s*日(?:游|行程)", text)
        if days_match:
            result["days"] = days_match.group(1)

        people_match = re.search(r"(?:共|一共|我们|同行)?\s*(\d{1,2})\s*(?:人|位)", text)
        if people_match:
            result["people"] = people_match.group(1)

        lower_text = text.lower()
        if any(term in text for term in ("不携带儿童", "不携带孩子", "不携带小孩", "不带孩子", "不带小孩", "没有孩子", "全是成年人", "无儿童")) or any(
            term in lower_text for term in ("without kids", "no children", "all adults")
        ):
            result["kids"] = "no"
        elif (
            any(term in text for term in ("带孩子", "带小孩", "儿童同行", "宝宝同行", "亲子游", "亲子旅行", "亲子出行"))
            or re.search(r"\d{1,2}\s*(?:个|名|位)?\s*(?:儿童|孩子|小孩|宝宝)", text)
            or any(term in lower_text for term in ("with kids", "with children", "family with children"))
        ):
            result["kids"] = "yes"
        elif re.search(r"\d{1,2}\s*(?:名|位|个)?\s*成人", text):
            result["kids"] = "no"

        date_match = re.search(r"(20\d{2})[年/-](\d{1,2})[月/-](\d{1,2})(?:日)?", text)
        if date_match:
            result["start_date"] = "{}-{:02d}-{:02d}".format(
                date_match.group(1), int(date_match.group(2)), int(date_match.group(3))
            )

        budget_match = re.search(r"(?:预算|花费|费用)\D{0,6}(\d+(?:\.\d+)?)\s*(万|万元|千|元|块|人民币)?", text)
        if budget_match:
            amount = float(budget_match.group(1))
            if budget_match.group(2) in {"万", "万元"}:
                amount *= 10000
            elif budget_match.group(2) == "千":
                amount *= 1000
            result["budget"] = str(int(amount)) if amount.is_integer() else str(amount)

        return {field: value for field, value in result.items() if value}

    @staticmethod
    def _has_explicit_kids_signal(message: str) -> bool:
        text = message.strip()
        lower_text = text.lower()
        explicit_chinese_terms = (
            "不带孩子",
            "不带小孩",
            "不带娃",
            "不携带儿童",
            "不携带孩子",
            "不携带小孩",
            "没有孩子",
            "没有儿童同行",
            "无儿童",
            "带孩子",
            "带小孩",
            "带娃",
            "儿童同行",
            "宝宝同行",
            "亲子游",
            "亲子旅行",
            "亲子出行",
        )
        explicit_english_terms = (
            "without kids",
            "no children",
            "with kids",
            "with children",
            "family with children",
        )
        return any(term in text for term in explicit_chinese_terms) or any(
            term in lower_text for term in explicit_english_terms
        )

    @staticmethod
    def _normalize_extracted_info(extracted_info: dict) -> dict:
        normalized = dict(extracted_info or {})
        kids_value = str(normalized.get("kids", "")).lower().strip()
        if kids_value in {
            "yes",
            "true",
            "是",
            "有",
            "带",
            "带孩子",
            "带小孩",
            "带娃",
            "有儿童",
            "儿童同行",
            "亲子",
            "亲子游",
            "亲子旅行",
            "亲子友好",
            "亲子友好酒店",
        } or re.search(r"(?:\d|一|二|两|三|四|五|六|七|八|九|十)\s*(?:个|名|位)?\s*(?:小孩|孩子|儿童|娃|宝宝)", kids_value):
            normalized["kids"] = "yes"
        elif kids_value in {
            "no",
            "false",
            "否",
            "没有",
            "不带",
            "不带孩子",
            "不带小孩",
            "不带娃",
            "不携带儿童",
            "不携带孩子",
            "不携带小孩",
            "无儿童",
            "没有儿童同行",
            "没有孩子同行",
            "两个大人",
            "2个大人",
            "2位成人",
            "两位成人",
            "全成人",
            "都是成年人",
        }:
            normalized["kids"] = "no"

        health_value = str(normalized.get("health", "")).lower()
        if health_value in {"健康", "良好", "健康良好", "身体健康", "身体还可以", "行动方便", "good"}:
            normalized["health"] = "good"
        elif health_value in {
            "行动不便",
            "身体不便",
            "腿脚不便",
            "腿脚一般",
            "走不太动",
            "不适合太累",
            "不要太累",
            "limited",
        }:
            normalized["health"] = "limited"
        elif health_value in {"极佳", "健康状况极佳", "身体非常好", "身体很棒", "excellent"}:
            normalized["health"] = "excellent"
        return normalized

    def extract_info_from_message(
        self,
        message: str,
        state: dict = None,
        current_date: str = None,
    ) -> dict:
        """Use LLM to extract structured travel information from user message."""
        system_prompt = f"""Extract the following travel information from the user's message and return JSON.
        Carefully analyze the message to understand both explicit and implicit information. This is an UPDATE PATCH:
        only populate fields that the user states or explicitly corrects in this message.

        `city` is always the destination city to visit. `origin` is the departure city.
        For “从上海出发去东京”, return {{"origin": "上海", "city": "东京"}}.
        Never put a departure city in `city`. If the user says “目的地改为东京”, overwrite only `city` with “东京”.
        Current state is reference only: {json.dumps(state or {}, ensure_ascii=False)}
        Current date anchor (YYYY-MM-DD): {current_date or "not provided"}
        
        For the `kids` field, judge whether children are actually part of the travelers.
        Use "yes" or "no" only:
        - 明确说明“不携带儿童”“没有儿童同行”“两个大人”“两位成人”“不带娃”“全是成年人” => "kids": "no".
        - “2大一小”“2个大人1个小孩”“两个大人和一个上小学的孩子”“带孩子”“带娃”“亲子游” => "kids": "yes".
        - “想要亲子友好酒店/儿童友好酒店/适合带娃的住宿” usually implies children are traveling. Set "kids": "yes" and also keep this phrase in accommodation_preference when it is a hotel preference.
        For the `health` field, infer the traveler's mobility and fatigue tolerance:
        - “身体很好/健康状况极佳/体力很好” => "excellent".
        - “身体健康/健康状况良好/行动方便/身体还可以” => "good".
        - “行动不便/腿脚不便/腿脚一般/走不太动/不适合太累/不要太累” => "limited".
        If the user mentions hotel preference, like "budget hostel", "with swimming pool", "亲子友好酒店", or "带早餐", enter them into the “accommodation preference” field.
        The people field should be an integer.
        Specifically, if the user gives a start date, resolve relative wording against the current date anchor and set
        "start_date" in YYYY-MM-DD format. Otherwise, leave "start_date" as an empty string.
        Pay attention to negations and context. Don't just look for keywords, understand the meaning.
        
        IMPORTANT: Also extract any specific requirements, constraints, or special requests the user mentions. 
        This includes but is not limited to:
        - Accessibility needs (e.g., wheelchair access, limited mobility)
        - Food restrictions or dietary preferences (put these in dietary_needs)
        - Special interests or experiences they want to have
        - Particular constraints (e.g., fear of heights, need quiet accommodations)
        - Any important preferences not covered by other fields
        
        Return the following JSON structure:
        {{
        {', '.join([f'"{field}": ""' for field in self.all_fields])}
        }}
        
        For required fields, if any information is missing or unclear, leave it as an empty string.
        For specificRequirements, capture important preferences or constraints not covered by another field.
        
        IMPORTANT: Return ONLY the JSON object, without any code block markers like ```json or ```.
        """
        
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=message)
        ]

        try:
            llm_response = self._get_extractor_model().invoke(messages)
            
            # 添加JSON解析的容错处理
            content = llm_response.content.strip()
            
            # 清理代码块标记
            if content.startswith('```json'):
                content = content[7:]  # 移除 ```json
            if content.startswith('```'):
                content = content[3:]  # 移除 ```
            if content.endswith('```'):
                content = content[:-3]  # 移除结尾的 ```
            content = content.strip()
            
            # 尝试解析JSON，如果失败则返回空结果
            try:
                extracted_info = json.loads(content)
            except json.JSONDecodeError as e:
                print(f"JSON解析错误: {e}")
                print(f"LLM返回内容: {content}")
                return self._extract_rule_based_info(message)

            # Only update fields that have non-empty values
            filtered_info = {}
            extracted_info = self._normalize_extracted_info(extracted_info)
            for field in set(self.all_fields) | {"origin"}:
                value = extracted_info.get(field, "")
                if value:  # Only include non-empty values
                    filtered_info[field] = value

            rule_based_info = self._extract_rule_based_info(message)
            if "kids" in filtered_info:
                if not self._has_explicit_kids_signal(message):
                    rule_based_info.pop("kids", None)
            if "health" in filtered_info:
                rule_based_info.pop("health", None)
            filtered_info.update(rule_based_info)
            return filtered_info
        except Exception as e:
            print("Error in extract_info_from_message:", e)
            return self._extract_rule_based_info(message)
