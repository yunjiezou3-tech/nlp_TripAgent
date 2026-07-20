from agents.chat_agent import ChatAgent
from agents.information_agent import InformationAgent
from agents.recommend_agent import RecommendAgent
from agents.strategy_agent import StrategyAgent
from agents.route_agent import RouteAgent
from agents.communication_agent import CommunicationAgent
from agents.booking_agent import BookingAgent
from services.booking_provider import CtripMockProvider
from services.candidate_enrichment import PlaceCandidateEnricher
from services.date_resolver import DateResolver
from services.information_refinement import InformationRefinementService
from copy import deepcopy
from datetime import date, datetime, timedelta
from inspect import Parameter, signature
import math
from zoneinfo import ZoneInfo
from langchain_core.messages import AIMessage

# This is a simplified state graph manager since we're not using the actual langgraph library
class TravelGraph:
    def __init__(self):
        self.chat_agent = ChatAgent()
        self.info_agent = InformationAgent() # InfoAgent now handles LLM re-ranking
        self.recommend_agent = RecommendAgent() # Still used for map_data, etc.
        self.strategy_agent = StrategyAgent()
        self.route_agent = RouteAgent()
        self.comm_agent = CommunicationAgent()
        self.booking_agent = BookingAgent()
        self.booking_provider = CtripMockProvider()
        self.information_refinement_service = InformationRefinementService()
        
        self.state = { # Default state for a new session
            "user_info": {},
            "attractions": [], # This will hold LLM-ranked attractions from InfoAgent
            "weather_summary": None, # To store weather summary string
            "selected_attractions": [],
            "restaurants": [],
            "hotels": [],
            "selected_restaurants": [],
            "selected_hotel": None,
            "place_errors": {},
            "additional_attractions": [],
            "should_rent_car": False, # Ensure this defaults to False
            # "rental_post": None, # Intentionally removed from state
            "itinerary": [],
            "budget": {},
            "ai_recommendation_generated": False, # Flag for strategy AI advice
            "hotel_candidates": [],
            "hotel_recommendations": [],
            "recommended_hotel_id": None,
            "booking_mode": None,
            "booking_context": {},
            "booking_drafts": {},
            "active_draft_type": None,
            "traveler_profiles": {},
            "booking_missing_fields": [],
            "booking_candidates": {},
            "information_refinement": None,
            "information_message": None,
            "candidate_delta": {},
            "candidate_search_state": self._new_candidate_search_state(),
            "candidate_price_context": self._new_candidate_price_context(),
            "current_date": self._shanghai_today(),
            "trip_date_status": self._missing_trip_date_status(),
        }
        self.session_states = {} # To store states for different sessions
    
    def get_session_state(self, session_id):
        if session_id not in self.session_states:
            # Create a new state by copying the default state structure
            self.session_states[session_id] = {
                "user_info": {}, "attractions": [], "weather_summary": None,
                "selected_attractions": [], "restaurants": [], "hotels": [],
                "selected_restaurants": [], "selected_hotel": None,
                "place_errors": {}, "additional_attractions": [],
                "should_rent_car": False, # Ensure this defaults to False
                # "rental_post": None, # Intentionally removed from state
                "itinerary": [], "budget": {},
                "ai_recommendation_generated": False,
                "hotel_candidates": [], "hotel_recommendations": [],
                "recommended_hotel_id": None,
                "booking_mode": None, "booking_context": {},
                "booking_drafts": {}, "active_draft_type": None,
                "traveler_profiles": {}, "booking_missing_fields": [],
                "booking_candidates": {},
                "information_refinement": None, "information_message": None,
                "candidate_delta": {},
                "candidate_search_state": self._new_candidate_search_state(),
                "candidate_price_context": self._new_candidate_price_context(),
                "current_date": self._shanghai_today(),
                "trip_date_status": self._missing_trip_date_status(),
            }
        state = self.session_states[session_id]
        state.setdefault("information_refinement", None)
        state.setdefault("information_message", None)
        state.setdefault("candidate_delta", {})
        self._migrate_candidate_state(state)
        self.session_states[session_id].setdefault("current_date", self._shanghai_today())
        self.session_states[session_id]["trip_date_status"] = (
            self._normalize_trip_date_status(
                self.session_states[session_id].get("trip_date_status")
            )
        )
        return deepcopy(self.session_states[session_id])

    @staticmethod
    def _shanghai_today():
        return datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat()

    @staticmethod
    def _missing_trip_date_status():
        return {
            "status": "missing",
            "value": None,
            "source_text": None,
            "error": None,
        }

    @staticmethod
    def _new_candidate_search_state():
        return {
            category: {
                "next_page_token": None,
                "seen_ids": [],
                "exhausted": False,
                "last_query": None,
                "last_error": None,
            }
            for category in ("attractions", "restaurants", "hotels")
        }

    @staticmethod
    def _new_candidate_price_context():
        return {
            "currency": "CNY",
            "stay_dates": None,
            "hotel_quotes_are_mock": True,
        }

    def _migrate_candidate_state(self, state):
        categories = ("attractions", "restaurants", "hotels")
        if not isinstance(state.get("information_refinement"), (dict, type(None))):
            state["information_refinement"] = None
        state["information_message"] = self._optional_string(
            state.get("information_message")
        )
        raw_delta = state.get("candidate_delta")
        if not isinstance(raw_delta, dict):
            raw_delta = {}
        state["candidate_delta"] = {
            category: deepcopy(raw_delta[category])
            for category in categories
            if isinstance(raw_delta.get(category), list)
        }

        raw_search = state.get("candidate_search_state")
        if not isinstance(raw_search, dict):
            raw_search = {}
        normalized_search = {}
        for category in categories:
            raw_category = raw_search.get(category)
            if not isinstance(raw_category, dict):
                raw_category = {}
            token = raw_category.get("next_page_token")
            if not isinstance(token, str) or not token.strip():
                token = None
            else:
                token = token.strip()
            seen_ids = self._unique_string_ids(raw_category.get("seen_ids"))
            exhausted = raw_category.get("exhausted")
            normalized_search[category] = {
                "next_page_token": token,
                "seen_ids": seen_ids,
                "exhausted": exhausted if isinstance(exhausted, bool) else False,
                "last_query": self._optional_string(
                    raw_category.get("last_query")
                ),
                "last_error": self._optional_string(
                    raw_category.get("last_error")
                ),
            }
        state["candidate_search_state"] = normalized_search

        raw_price = state.get("candidate_price_context")
        if not isinstance(raw_price, dict):
            raw_price = {}
        currency = raw_price.get("currency")
        if not (
            isinstance(currency, str)
            and len(currency.strip()) == 3
            and currency.strip().isalpha()
        ):
            currency = "CNY"
        else:
            currency = currency.strip().upper()
        mock_quotes = raw_price.get("hotel_quotes_are_mock")
        state["candidate_price_context"] = {
            "currency": currency,
            "stay_dates": self._normalize_stay_dates(
                raw_price.get("stay_dates")
            ),
            "hotel_quotes_are_mock": (
                mock_quotes if isinstance(mock_quotes, bool) else True
            ),
        }

    @staticmethod
    def _optional_string(value):
        return value if isinstance(value, str) else None

    @staticmethod
    def _unique_string_ids(values):
        if not isinstance(values, list):
            return []
        unique_ids = []
        for value in values:
            if not isinstance(value, str) or not value.strip():
                continue
            candidate_id = value.strip()
            if candidate_id not in unique_ids:
                unique_ids.append(candidate_id)
        return unique_ids

    @staticmethod
    def _normalize_stay_dates(value):
        if not isinstance(value, dict):
            return None
        check_in = value.get("check_in")
        check_out = value.get("check_out")
        try:
            if not isinstance(check_in, str) or not isinstance(check_out, str):
                raise ValueError
            check_in_date = date.fromisoformat(check_in)
            check_out_date = date.fromisoformat(check_out)
            if (
                check_in_date.isoformat() != check_in
                or check_out_date.isoformat() != check_out
                or check_out_date <= check_in_date
            ):
                raise ValueError
        except (TypeError, ValueError):
            return None
        return {"check_in": check_in, "check_out": check_out}

    def _normalize_trip_date_status(self, value):
        if not isinstance(value, dict):
            return self._missing_trip_date_status()
        status = value.get("status")
        resolved_value = value.get("value")
        source_text = self._optional_string(value.get("source_text"))
        error = self._optional_string(value.get("error"))
        if status == "resolved":
            try:
                if not isinstance(resolved_value, str):
                    raise ValueError
                parsed = date.fromisoformat(resolved_value)
                if parsed.isoformat() != resolved_value:
                    raise ValueError
            except (TypeError, ValueError):
                return self._missing_trip_date_status()
            return {
                "status": "resolved",
                "value": resolved_value,
                "source_text": source_text,
                "error": None,
            }
        if status == "invalid" and resolved_value is None:
            return {
                "status": "invalid",
                "value": None,
                "source_text": source_text,
                "error": error,
            }
        if status == "missing" and resolved_value is None:
            return {
                "status": "missing",
                "value": None,
                "source_text": source_text,
                "error": None,
            }
        return self._missing_trip_date_status()

    def _state_snapshot(self):
        return deepcopy(self.state)
    
    def process_step(self, step_name, session_id=None, **kwargs):
        # print(f"[DEBUG] Processing step {step_name} for session_id: {session_id}")
        # print(f"[DEBUG] Initial kwargs: {kwargs}")
        
        if session_id:
            self.state = self.get_session_state(session_id)
            # print(f"[DEBUG] Retrieved session state: {self.state}")
        else:
            session_id = str(id(self)) # Fallback if no session_id, though it should be provided
            self.state = self.get_session_state(session_id)
            print(f"[WARN] No session_id provided, created fallback session: {session_id}")

        self.state["candidate_delta"] = {}
        
        if 'ai_recommendation_generated' in kwargs: # Ensure flag is a boolean
            self.state['ai_recommendation_generated'] = str(kwargs['ai_recommendation_generated']).lower() == 'true'
        
        # print(f"[DEBUG] State before processing {step_name}: {self.state}")
        user_input = kwargs.get("user_input", "")
        if step_name in {"complete", "booking_collect", "booking_draft", "booking_confirm"} and self.booking_agent.detect_intent(user_input):
            step_name = "booking_intent"
        
        result = {}
        if step_name == "chat":
            result = self._process_chat(**kwargs)
        elif step_name == "information":
            result = self._process_information(**kwargs) # This will now call the updated InfoAgent
        elif step_name == "recommend":
            result = self._process_recommend(**kwargs) # This uses the already LLM-ranked list
        elif step_name == "strategy":
            result = self._process_strategy(**kwargs)
        elif step_name == "route":
            result = self._process_route(**kwargs)
        elif step_name == "communication":
            result = self._process_communication(**kwargs)
        elif step_name == "complete":
            result = self._process_complete(**kwargs)
        elif step_name == "booking_intent":
            result = self._process_booking_intent(**kwargs)
        elif step_name == "booking_collect":
            result = self._process_booking_collect(**kwargs)
        elif step_name == "booking_draft":
            result = self._process_booking_draft(**kwargs)
        elif step_name == "booking_confirm":
            result = self._process_booking_confirm(**kwargs)
        else:
            result = {"error": f"Unknown step: {step_name}"}
        
        self.session_states[session_id] = self._state_snapshot()
        result["state"] = self._state_snapshot()
        result["session_id"] = session_id # Ensure session_id is always in the result
        # print(f"[DEBUG] State after processing {step_name}: {self.state}")
        # print(f"[DEBUG] Result for {step_name}: {result}")
        return result
    
    def _process_chat(self, user_input=None, **kwargs):
        if self._can_start_booking(user_input):
            return self._process_booking_intent(user_input=user_input, **kwargs)

        previous_user_info = self.state.get("user_info", {}).copy()
        current_user_info = previous_user_info.copy()
        trip_date_today = self._trip_date_today()
        collect_parameters = signature(self.chat_agent.collect_info).parameters
        supports_current_date = "current_date" in collect_parameters or any(
            parameter.kind == Parameter.VAR_KEYWORD
            for parameter in collect_parameters.values()
        )
        collect_kwargs = (
            {"current_date": trip_date_today.isoformat()}
            if supports_current_date
            else {}
        )
        chat_result = self.chat_agent.collect_info(
            user_input or "", current_user_info, **collect_kwargs
        )
        
        if chat_result.get("state"):
            self.state["user_info"].update(chat_result["state"])
            if self._travel_preferences_changed(previous_user_info, self.state["user_info"]):
                self._clear_derived_plan_state()

        date_result = DateResolver(today=trip_date_today).resolve(
            self.state["user_info"].get("start_date")
        )
        self.state["trip_date_status"] = date_result

        if date_result["status"] == "resolved":
            self.state["user_info"]["start_date"] = date_result["value"]
        else:
            self.state["user_info"].pop("start_date", None)

        missing_fields = list(chat_result.get("missing_fields", []))
        if date_result["status"] != "resolved" and "start_date" not in missing_fields:
            missing_fields.append("start_date")

        response_stream = chat_result.get("stream")
        if date_result["status"] == "invalid":
            response_stream = self._date_follow_up_stream(missing_fields, date_result)

        response_data = {
            "state": self._state_snapshot(),
            "stream": response_stream,
            "missing_fields": missing_fields
        }
        
        if not chat_result.get("complete", False) or date_result["status"] != "resolved":
            response_data["next_step"] = "chat"
            return response_data
            
        # If chat is complete, automatically proceed to information gathering
        # The state (self.state) is already updated, _process_information will use it.
        info_step_result = self._process_information() 
        return info_step_result # This result will contain next_step, stream, data, and state

    def _trip_date_today(self):
        current_date = self.state.get("current_date")
        try:
            if not isinstance(current_date, str):
                raise TypeError
            parsed_date = date.fromisoformat(current_date)
            if parsed_date.isoformat() != current_date:
                raise ValueError
            return parsed_date
        except (TypeError, ValueError):
            current_date = self._shanghai_today()
            self.state["current_date"] = current_date
            return date.fromisoformat(current_date)

    def _date_follow_up_stream(self, missing_fields, date_result):
        if date_result.get("error") == "past_date":
            prompt = "出发日期不能早于今天，请提供今天或之后的明确日期。"
        elif date_result.get("error") == "unrecognized_date":
            prompt = "我无法识别这个出发日期，请提供明确日期，例如 2026-08-15、明天或下周一。"
        else:
            prompt = "请提供明确的出发日期，例如 2026-08-15、明天或下周一。"

        first_other_missing = next(
            (field for field in missing_fields if field != "start_date"),
            None,
        )
        ask_fields = []
        if first_other_missing:
            ask_fields.append(first_other_missing)
        ask_fields.append("start_date")

        return self.chat_agent._collection_response_stream(
            self.state["user_info"],
            missing_fields,
            ask_fields=ask_fields,
            question_overrides={"start_date": prompt},
        )

    @staticmethod
    def _travel_preferences_changed(previous_user_info, current_user_info):
        recommendation_fields = {
            "city", "days", "budget", "people", "kids", "health", "hobbies",
            "start_date", "accommodation_preference", "specificRequirements",
        }
        return any(
            previous_user_info.get(field) != current_user_info.get(field)
            for field in recommendation_fields
        )

    def _clear_derived_plan_state(self):
        """Invalidate locations and plans that were derived from older travel preferences."""
        self.state.update(
            {
                "attractions": [],
                "restaurants": [],
                "hotels": [],
                "hotel_candidates": [],
                "hotel_recommendations": [],
                "recommended_hotel_id": None,
                "selected_attractions": [],
                "selected_restaurants": [],
                "selected_hotel": None,
                "place_errors": {},
                "additional_attractions": [],
                "daily_plan": {},
                "itinerary": [],
                "budget": {},
                "ai_recommendation_generated": False,
                "should_rent_car": False,
                "booking_context": {},
                "booking_drafts": {},
                "booking_candidates": {},
                "booking_missing_fields": [],
                "booking_mode": None,
                "active_draft_type": None,
                "information_refinement": None,
                "information_message": None,
                "candidate_delta": {},
                "candidate_search_state": self._new_candidate_search_state(),
                "candidate_price_context": self._new_candidate_price_context(),
            }
        )
    
    def _process_information(self, **kwargs):
        user_prefs = self.state["user_info"]
        city = user_prefs.get("city")
        self.state["information_refinement"] = None
        self.state["information_message"] = None
        self.state["candidate_delta"] = {}

        if not city:
            def error_gen(): yield AIMessage(content="Please tell me which city you'd like to visit.")
            return {"next_step": "chat", "stream": error_gen(), "missing_fields": ["city"], "state": self._state_snapshot()}

        city_coordinates = self.info_agent.city2geocode(city)
        if not city_coordinates:
            def error_gen(): yield AIMessage(content=f"Sorry, I couldn't find coordinates for {city}.")
            return {"next_step": "chat", "stream": error_gen(), "state": self._state_snapshot()}
        
        # Get weather summary first
        weather_summary_str = None
        user_start_date = user_prefs.get("start_date")
        user_days_str = user_prefs.get("days")

        if user_days_str:
            try:
                num_days = int(user_days_str)
                weather_data_result = self.info_agent.get_weather(
                    city_coordinates["lat"], city_coordinates["lng"],
                    user_start_date, num_days, summary=True
                )
                if weather_data_result and 'summary' in weather_data_result:
                    summary_val = weather_data_result['summary']
                    if hasattr(summary_val, 'content'): # If AIMessage
                        weather_summary_str = summary_val.content
                    elif isinstance(summary_val, str):
                        weather_summary_str = summary_val
                    self.state["weather_summary"] = weather_summary_str
                    print(f"[DEBUG] Weather summary set in state: '{weather_summary_str}'")
                else:
                    print(f"[DEBUG] Weather summary not found or in unexpected format: {weather_data_result}")
            except ValueError:
                print(f"[ERROR] Invalid 'days' for weather: {user_days_str}")
            except Exception as e:
                print(
                    "[ERROR] Exception fetching weather summary: "
                    f"{type(e).__name__}"
                )
        else:
            print("[DEBUG] Weather info not fetched (no days).")
            
        # Get attractions - InfoAgent now handles LLM re-ranking internally
        print(f"[DEBUG] Calling info_agent.get_attractions for '{city}' with user_prefs and weather.")
        attractions_from_info_agent = self.info_agent.get_attractions(
            lat=city_coordinates["lat"],
            lng=city_coordinates["lng"],
            user_prefs=user_prefs, # Pass full user_prefs
            weather_summary=self.state.get("weather_summary"), # Pass fetched weather summary
            number=20, # Desired number of top attractions after LLM ranking
            poi_type="tourist_attraction"
            # sort_by="rating" # Initial sort inside get_attractions before LLM
        )
        
        self.state["attractions"] = attractions_from_info_agent if attractions_from_info_agent else []
        print(f"[DEBUG] attractions state updated with {len(self.state['attractions'])} LLM-ranked items.")
        place_errors = {}
        try:
            restaurant_page = self._get_candidate_page(
                "restaurants",
                city_coordinates["lat"],
                city_coordinates["lng"],
                user_prefs=user_prefs,
            )
            restaurant_candidates, _ = self._merge_unseen_candidates(
                [], restaurant_page["candidates"]
            )
            restaurant_candidates = self._normalize_candidate_batch(
                restaurant_candidates
            )
            restaurant_page = {
                **restaurant_page,
                "candidates": restaurant_candidates,
            }
            self.state["restaurants"] = self._enrich_restaurants(
                restaurant_candidates
            )
        except Exception as error:
            print(
                "[WARN] Failed to load restaurant candidates: "
                f"{type(error).__name__}"
            )
            self.state["restaurants"] = []
            place_errors["restaurants"] = "provider_unavailable"
            restaurant_page = {"candidates": [], "next_page_token": None}

        core_locations = [
            attraction.get("location")
            for attraction in self.state["attractions"]
            if attraction.get("location")
        ]
        try:
            hotel_page = self._get_candidate_page(
                "hotels",
                city_coordinates["lat"],
                city_coordinates["lng"],
                user_prefs=user_prefs,
                core_locations=core_locations,
            )
            hotel_candidates, _ = self._merge_unseen_candidates(
                [], hotel_page["candidates"]
            )
            hotel_candidates = self._normalize_candidate_batch(
                hotel_candidates
            )
            hotel_page = {**hotel_page, "candidates": hotel_candidates}
            self.state["hotels"] = self._attach_hotel_room_offers(
                hotel_candidates,
                city_coordinates["lat"],
                city_coordinates["lng"],
            )
        except Exception as error:
            print(
                "[WARN] Failed to load hotel candidates: "
                f"{type(error).__name__}"
            )
            self.state["hotels"] = []
            place_errors["hotels"] = "provider_unavailable"
            hotel_page = {"candidates": [], "next_page_token": None}

        self.state["hotel_candidates"] = self.state["hotels"]
        self.state["place_errors"] = place_errors
        initial_pages = {
            "attractions": {
                "candidates": self.state["attractions"],
                "next_page_token": None,
            },
            "restaurants": restaurant_page,
            "hotels": hotel_page,
        }
        for category, page in initial_pages.items():
            self._set_initial_candidate_search_state(category, page)
        stay, _, _ = self._hotel_room_search_context()
        self.state["candidate_price_context"] = {
            "currency": "CNY",
            "stay_dates": stay if all(stay.values()) else None,
            "hotel_quotes_are_mock": True,
        }

        def info_gen_message():
            available_groups = [
                name for name, items in (("景点", self.state["attractions"]), ("餐厅", self.state["restaurants"]), ("酒店", self.state["hotels"])) if items
            ]
            if available_groups:
                yield AIMessage(content=f"我已经为你整理了 {city} 的{'、'.join(available_groups)}候选。请至少选择一个景点；餐厅可多选，酒店可选一间。")
            else:
                yield AIMessage(content=f"我暂时没找到可供选择的地点，你可以换个条件或城市试试。")
        
        return {
            "next_step": "recommend",
            "stream": info_gen_message(),
            "attractions": self.state["attractions"], # This list is now LLM-ranked
            "restaurants": self.state["restaurants"],
            "hotels": self.state["hotels"],
            "place_errors": self.state["place_errors"],
            "candidate_delta": self.state["candidate_delta"],
            "information_refinement": self.state["information_refinement"],
            "information_message": self.state["information_message"],
            "candidate_search_state": self.state["candidate_search_state"],
            "candidate_price_context": self.state["candidate_price_context"],
            "map_data": self.recommend_agent.generate_map_data(self.state["attractions"]), # recommend_agent helps with map data
            "state": self._state_snapshot()
        }
    
    def _process_recommend(self, selected_attraction_ids=None, selected_restaurant_ids=None, selected_hotel_id=None, **kwargs):
        """Process recommend agent step"""
        try:
            self.state["candidate_delta"] = {}
            user_prefs = self.state["user_info"]
            attractions = self.state["attractions"]
            restaurants = self.state.get("restaurants", [])
            hotels = self.state.get("hotels", [])

            if "selected_attraction_ids" in kwargs:
                selected_attraction_ids = kwargs["selected_attraction_ids"]
            if "selected_restaurant_ids" in kwargs:
                selected_restaurant_ids = kwargs["selected_restaurant_ids"]
            if "selected_hotel_id" in kwargs:
                selected_hotel_id = kwargs["selected_hotel_id"]

            has_explicit_selection = (
                selected_attraction_ids is not None
                or bool(selected_restaurant_ids)
                or bool(selected_hotel_id)
            )
            refinement = self.information_refinement_service.parse(
                kwargs.get("user_input", "")
            )
            refinement_with_selection = refinement["intent"] in {
                "more_candidates",
                "clarify_category",
                "update_preferences",
            }
            if refinement_with_selection:
                selection_error = self._sync_refinement_selections(
                    selected_attraction_ids,
                    selected_restaurant_ids,
                    selected_hotel_id,
                )
                if selection_error is not None:
                    return selection_error
            if not has_explicit_selection or refinement_with_selection:
                self.state["information_refinement"] = refinement
                self.state["information_message"] = None
                if refinement["intent"] == "more_candidates":
                    return self._process_more_candidates(refinement)
                if refinement["intent"] == "clarify_category":
                    message = refinement.get("clarification_message") or (
                        "请问你想看更多景点、餐厅还是住宿？"
                    )
                    self.state["information_message"] = message
                    return self._recommend_refinement_result(message)
                if refinement["intent"] == "update_preferences":
                    self._clear_derived_plan_state()
                    message = "请告诉我需要修改哪项旅行偏好，我会据此重新整理候选。"
                    self.state["information_refinement"] = refinement
                    self.state["information_message"] = message

                    def correction_stream():
                        yield AIMessage(content=message)

                    return {
                        "next_step": "chat",
                        "stream": correction_stream(),
                        "response": message,
                        "information_refinement": refinement,
                        "information_message": message,
                        "candidate_delta": {},
                        "candidate_search_state": self.state[
                            "candidate_search_state"
                        ],
                        "candidate_price_context": self.state[
                            "candidate_price_context"
                        ],
                        "state": self._state_snapshot(),
                    }
                if refinement["intent"] == "confirm_selection":
                    if not self.state.get("selected_attractions"):
                        message = "请先从当前候选中至少选择一个景点，再确认生成行程。"
                        self.state["information_message"] = message
                        return self._recommend_refinement_result(message)

                    message = "正在根据你选中的景点、餐厅和酒店生成完整旅行方案..."
                    self.state["information_message"] = message

                    def natural_confirmation_stream():
                        yield AIMessage(content=message)

                    return {
                        "next_step": "strategy",
                        "stream": natural_confirmation_stream(),
                        "selected_attractions": self.state[
                            "selected_attractions"
                        ],
                        "selected_restaurants": self.state.get(
                            "selected_restaurants", []
                        ),
                        "selected_hotel": self.state.get("selected_hotel"),
                        "information_refinement": refinement,
                        "information_message": message,
                        "candidate_delta": {},
                        "state": self._state_snapshot(),
                    }

            if has_explicit_selection:
                attractions_valid, selected_attraction_ids = (
                    self._validate_selection_id_list(selected_attraction_ids)
                )
                restaurants_valid, selected_restaurant_ids = (
                    self._validate_selection_id_list(selected_restaurant_ids)
                )
                hotel_valid = selected_hotel_id is None or selected_hotel_id == ""
                if self._valid_candidate_id(selected_hotel_id):
                    hotel_valid = True
                elif selected_hotel_id not in (None, ""):
                    hotel_valid = False
                if not attractions_valid or not restaurants_valid or not hotel_valid:
                    return self._selection_validation_response()
                selected_hotel_id = selected_hotel_id or None

                attraction_ids = self._available_candidate_ids(attractions)
                restaurant_ids = self._available_candidate_ids(restaurants)
                hotel_ids = self._available_candidate_ids(hotels)
                unknown_ids = (
                    (set(selected_attraction_ids) - attraction_ids)
                    | (set(selected_restaurant_ids) - restaurant_ids)
                    | (({selected_hotel_id} if selected_hotel_id else set()) - hotel_ids)
                )
                if unknown_ids:
                    return {
                        "next_step": "recommend",
                        "response": "所选地点已失效，请从当前候选中重新选择。",
                        "code": "selection_unavailable",
                        "state": self._state_snapshot(),
                    }
                if not selected_attraction_ids:
                    return {
                        "next_step": "recommend",
                        "response": "请至少选择一个景点后再生成行程。",
                        "state": self._state_snapshot(),
                    }

                self.state["selected_attractions"] = [
                    attraction
                    for attraction in attractions
                    if isinstance(attraction, dict)
                    and self._valid_candidate_id(attraction.get("id"))
                    in selected_attraction_ids
                ]
                self.state["selected_restaurants"] = [
                    restaurant
                    for restaurant in restaurants
                    if isinstance(restaurant, dict)
                    and self._valid_candidate_id(restaurant.get("id"))
                    in selected_restaurant_ids
                ]
                self.state["selected_hotel"] = next(
                    (
                        hotel
                        for hotel in hotels
                        if isinstance(hotel, dict)
                        and self._valid_candidate_id(hotel.get("id"))
                        == selected_hotel_id
                    ),
                    None,
                )
                
                # Create a generator that yields a transition message
                def transition_generator():
                    yield AIMessage(content="正在根据你选中的景点、餐厅和酒店生成完整旅行方案...")
                
                return {
                    "next_step": "strategy",
                    "stream": transition_generator(),
                    "selected_attractions": self.state["selected_attractions"],
                    "selected_restaurants": self.state["selected_restaurants"],
                    "selected_hotel": self.state["selected_hotel"],
                    "state": self._state_snapshot(),
                }
            else:
                # Recommend attractions to the user
                if not attractions:
                    return {
                        "next_step": "recommend",
                        "stream": None,
                        "response": "No attractions available for recommendation.",
                        "recommended_attractions": [],
                        "map_data": []
                    }
                
                recommended = self.recommend_agent.recommend_core_attractions(user_prefs, attractions,)
                
                # Create a generator that yields the recommendation message
                def recommendation_generator():
                    yield AIMessage(content="这些是我优先推荐给你的景点。")
                
                return {
                    "next_step": "recommend",  # Stay on this step until user selects attractions
                    "stream": recommendation_generator(),
                    "recommended_attractions": recommended,
                    "map_data": self.recommend_agent.generate_map_data(recommended)
                }
        except Exception as error:
            print(f"Error in _process_recommend: {type(error).__name__}")
            return {
                "next_step": "error",
                "stream": None,
                "response": "推荐处理失败，请稍后重试。",
                "code": "recommendation_error",
            }

    @classmethod
    def _validate_selection_id_list(cls, value):
        if value is None:
            return True, []
        if not isinstance(value, list):
            return False, []
        validated = []
        for candidate_id in value:
            if not cls._valid_candidate_id(candidate_id):
                return False, []
            if candidate_id not in validated:
                validated.append(candidate_id)
        return True, validated

    def _sync_refinement_selections(
        self,
        selected_attraction_ids,
        selected_restaurant_ids,
        selected_hotel_id,
    ):
        pending_updates = {}
        selection_groups = (
            (
                "selected_attractions",
                selected_attraction_ids,
                self.state.get("attractions", []),
            ),
            (
                "selected_restaurants",
                selected_restaurant_ids,
                self.state.get("restaurants", []),
            ),
        )
        for state_field, submitted_ids, candidates in selection_groups:
            if submitted_ids is None:
                continue
            valid, normalized_ids = self._validate_selection_id_list(submitted_ids)
            if not valid:
                return self._selection_validation_response()
            available_ids = self._available_candidate_ids(candidates)
            if set(normalized_ids) - available_ids:
                return self._selection_unavailable_response()
            pending_updates[state_field] = [
                candidate
                for candidate in candidates
                if isinstance(candidate, dict)
                and self._valid_candidate_id(candidate.get("id")) in normalized_ids
            ]

        if selected_hotel_id is not None:
            if selected_hotel_id == "":
                pending_updates["selected_hotel"] = None
            elif not self._valid_candidate_id(selected_hotel_id):
                return self._selection_validation_response()
            else:
                selected_hotel = next(
                    (
                        hotel
                        for hotel in self.state.get("hotels", [])
                        if isinstance(hotel, dict)
                        and self._valid_candidate_id(hotel.get("id"))
                        == selected_hotel_id
                    ),
                    None,
                )
                if selected_hotel is None:
                    return self._selection_unavailable_response()
                pending_updates["selected_hotel"] = selected_hotel
        self.state.update(pending_updates)
        return None

    @classmethod
    def _available_candidate_ids(cls, candidates):
        if not isinstance(candidates, list):
            return set()
        return {
            candidate_id
            for candidate in candidates
            if isinstance(candidate, dict)
            for candidate_id in [cls._valid_candidate_id(candidate.get("id"))]
            if candidate_id
        }

    def _selection_validation_response(self):
        return {
            "next_step": "recommend",
            "response": "选择数据格式无效，请重新选择。",
            "code": "invalid_selection",
            "state": self._state_snapshot(),
        }

    def _selection_unavailable_response(self):
        return {
            "next_step": "recommend",
            "response": "所选地点已失效，请从当前候选中重新选择。",
            "code": "selection_unavailable",
            "state": self._state_snapshot(),
        }

    def _process_more_candidates(self, refinement):
        city = self.state.get("user_info", {}).get("city")
        coordinates = self.info_agent.city2geocode(city) if city else None
        if not coordinates:
            self.state["information_message"] = "暂时无法继续加载候选，请稍后再试。"
            return self._recommend_refinement_result(
                self.state["information_message"]
            )

        added_counts = {}
        for category in ("attractions", "restaurants", "hotels"):
            if category not in refinement.get("categories", []):
                continue
            added_counts[category] = self._refine_candidate_category(
                category,
                coordinates["lat"],
                coordinates["lng"],
                refinement,
            )

        labels = {
            "attractions": ("个景点", "景点"),
            "restaurants": ("家餐厅", "餐厅"),
            "hotels": ("家住宿", "住宿"),
        }
        additions = [
            f"新增 {count} {labels[category][0]}"
            for category, count in added_counts.items()
            if count
        ]
        if additions:
            message = "，".join(additions) + "。"
        else:
            requested = "、".join(
                labels[category][1] for category in added_counts
            )
            message = f"这次没有找到新的{requested or '候选'}，你可以换个筛选条件。"
        self.state["information_message"] = message
        return self._recommend_refinement_result(message)

    def _refine_candidate_category(self, category, lat, lng, refinement):
        search_state = self.state["candidate_search_state"].setdefault(
            category, self._new_candidate_search_state()[category]
        )
        search_state["last_query"] = refinement.get("raw_query")
        search_state["last_error"] = None
        transient_filters = refinement.get("transient_filters", {})
        request_preferences = deepcopy(self.state.get("user_info", {}))
        request_preferences["transient_candidate_filters"] = deepcopy(
            transient_filters
        )
        core_locations = [
            attraction.get("location")
            for attraction in self.state.get("attractions", [])
            if isinstance(attraction, dict) and attraction.get("location")
        ]

        token_page = None
        fallback_page = None
        fallback_failed = False
        token = self._valid_page_token(search_state.get("next_page_token"))
        if token:
            try:
                token_page = self._get_candidate_page(
                    category,
                    lat,
                    lng,
                    user_prefs=request_preferences,
                    core_locations=core_locations,
                    page_token=token,
                )
            except Exception:
                token_page = None

        existing = self.state.get(category, [])
        first_candidates = token_page.get("candidates", []) if token_page else []
        merged, delta = self._merge_unseen_candidates(
            existing, first_candidates, search_state.get("seen_ids", [])
        )

        if not delta:
            keyword = self._candidate_fallback_keyword(category, transient_filters)
            try:
                fallback_page = self._get_candidate_page(
                    category,
                    lat,
                    lng,
                    user_prefs=request_preferences,
                    core_locations=core_locations,
                    page_token=None,
                    keyword=keyword,
                )
                merged, delta = self._merge_unseen_candidates(
                    existing,
                    fallback_page["candidates"],
                    search_state.get("seen_ids", []),
                )
            except Exception:
                fallback_failed = True
                merged, delta = self._merge_unseen_candidates(
                    existing, [], search_state.get("seen_ids", [])
                )

        active_page = fallback_page or token_page
        if active_page is None:
            self._update_candidate_search_state(
                search_state,
                existing,
                next_page_token=token,
                error_code="provider_unavailable",
            )
            self.state.setdefault("place_errors", {})[category] = "provider_unavailable"
            return 0

        next_page_token = self._valid_page_token(
            active_page.get("next_page_token")
        )
        if (
            fallback_page is not None
            and not delta
            and next_page_token is None
            and token_page is not None
        ):
            next_page_token = self._valid_page_token(
                token_page.get("next_page_token")
            )

        try:
            delta = self._prepare_candidate_delta(
                category, delta, transient_filters, lat, lng
            )
        except Exception as error:
            print(
                f"[WARN] Failed to prepare {category} candidates: "
                f"{type(error).__name__}"
            )
            self._update_candidate_search_state(
                search_state,
                existing,
                next_page_token=next_page_token,
                error_code="provider_unavailable",
            )
            self.state.setdefault("place_errors", {})[category] = (
                "provider_unavailable"
            )
            return 0

        merged, delta = self._merge_unseen_candidates(
            existing, delta, search_state.get("seen_ids", [])
        )
        self.state[category] = merged
        if category == "hotels":
            self.state["hotel_candidates"] = list(merged)

        seen_ids = list(search_state.get("seen_ids", []))
        for candidate in merged:
            candidate_id = candidate.get("id")
            if candidate_id not in seen_ids:
                seen_ids.append(candidate_id)
        error_code = "provider_unavailable" if fallback_failed else None
        self._update_candidate_search_state(
            search_state,
            merged,
            next_page_token=next_page_token,
            error_code=error_code,
        )
        if error_code:
            self.state.setdefault("place_errors", {})[category] = error_code
        else:
            self.state.setdefault("place_errors", {}).pop(category, None)
        if delta:
            self.state["candidate_delta"][category] = delta
        return len(delta)

    def _update_candidate_search_state(
        self, search_state, candidates, *, next_page_token, error_code
    ):
        seen_ids = self._unique_string_ids(search_state.get("seen_ids"))
        for candidate in candidates if isinstance(candidates, list) else []:
            candidate_id = (
                self._valid_candidate_id(candidate.get("id"))
                if isinstance(candidate, dict)
                else None
            )
            if candidate_id and candidate_id not in seen_ids:
                seen_ids.append(candidate_id)
        next_page_token = self._valid_page_token(next_page_token)
        search_state.update(
            {
                "next_page_token": next_page_token,
                "seen_ids": seen_ids,
                "exhausted": next_page_token is None,
                "last_error": error_code,
            }
        )

    @staticmethod
    def _valid_page_token(value):
        return value.strip() if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _merge_unseen_candidates(existing, incoming, historical_ids=None):
        existing_candidates = existing if isinstance(existing, list) else []
        incoming_candidates = incoming if isinstance(incoming, list) else []
        merged = [
            candidate
            for candidate in existing_candidates
            if isinstance(candidate, dict)
            and TravelGraph._valid_candidate_id(candidate.get("id"))
        ]
        delta = []
        seen_ids = {
            candidate.get("id")
            for candidate in merged
        }
        historical_values = historical_ids if isinstance(historical_ids, list) else []
        seen_ids.update(
            candidate_id
            for candidate_id in historical_values
            if TravelGraph._valid_candidate_id(candidate_id)
        )
        for candidate in incoming_candidates:
            candidate_id = candidate.get("id") if isinstance(candidate, dict) else None
            candidate_id = TravelGraph._valid_candidate_id(candidate_id)
            if not candidate_id or candidate_id in seen_ids:
                continue
            merged.append(candidate)
            delta.append(candidate)
            seen_ids.add(candidate_id)
        return merged, delta

    @staticmethod
    def _valid_candidate_id(value):
        return value if isinstance(value, str) and value.strip() else None

    @staticmethod
    def _candidate_fallback_keyword(category, transient_filters):
        filters = transient_filters if isinstance(transient_filters, dict) else {}
        keyword = filters.get("keyword")
        if isinstance(keyword, str) and keyword.strip():
            return keyword.strip()
        amenities = TravelGraph._normalize_text_values(
            filters.get("amenities", [])
        )
        if amenities:
            return " ".join(amenities)
        return {
            "attractions": "热门景点",
            "restaurants": "当地餐厅",
            "hotels": "住宿",
        }[category]

    @staticmethod
    def _normalize_price_level(value):
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value if 0 <= value <= 4 else None

    @staticmethod
    def _normalize_rating(value):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        return value if math.isfinite(value) else None

    @staticmethod
    def _normalize_text_values(value):
        values = [value] if isinstance(value, str) else value
        if not isinstance(values, (list, tuple)):
            return []
        normalized = []
        for item in values:
            if not isinstance(item, str) or not item.strip():
                continue
            text = item.strip()
            if text not in normalized:
                normalized.append(text)
        return normalized

    @classmethod
    def _normalize_candidate_attributes(cls, candidate):
        if not isinstance(candidate, dict):
            return None
        candidate_id = cls._valid_candidate_id(candidate.get("id"))
        name = candidate.get("name")
        if not candidate_id or not isinstance(name, str) or not name.strip():
            return None

        normalized = dict(candidate)
        normalized["id"] = candidate_id
        normalized["name"] = name.strip()
        if "price_level" in normalized:
            normalized["price_level"] = cls._normalize_price_level(
                normalized.get("price_level")
            )
        if "rating" in normalized:
            normalized["rating"] = cls._normalize_rating(
                normalized.get("rating")
            )
        for field in (
            "amenities",
            "match_reasons",
            "recommendation_reasons",
            "reasons",
        ):
            if field in normalized:
                normalized[field] = cls._normalize_text_values(
                    normalized.get(field)
                )
        return normalized

    @classmethod
    def _normalize_candidate_batch(cls, candidates):
        normalized = []
        for candidate in candidates if isinstance(candidates, list) else []:
            try:
                item = cls._normalize_candidate_attributes(candidate)
            except Exception:
                item = None
            if item is not None:
                normalized.append(item)
        return normalized

    @classmethod
    def _apply_transient_candidate_order(cls, candidates, transient_filters):
        ordered = list(candidates) if isinstance(candidates, list) else []
        filters = transient_filters if isinstance(transient_filters, dict) else {}
        maximum_price = cls._normalize_price_level(
            filters.get("max_price_level")
        )
        minimum_rating = cls._normalize_rating(filters.get("min_rating"))
        if maximum_price is not None:
            def price_sort_key(candidate):
                price_level = cls._normalize_price_level(
                    candidate.get("price_level")
                    if isinstance(candidate, dict)
                    else None
                )
                return (
                    price_level is None or price_level > maximum_price,
                    price_level is None,
                    price_level if price_level is not None else 5,
                )

            ordered.sort(
                key=price_sort_key
            )
        if minimum_rating is not None:
            def rating_sort_key(candidate):
                rating = cls._normalize_rating(
                    candidate.get("rating")
                    if isinstance(candidate, dict)
                    else None
                )
                return rating is None or rating < minimum_rating

            ordered.sort(
                key=rating_sort_key
            )
        return ordered

    def _prepare_candidate_delta(
        self, category, candidates, transient_filters, lat, lng
    ):
        prepared = self._normalize_candidate_batch(candidates)
        prepared = self._apply_transient_candidate_order(
            prepared, transient_filters
        )
        if category == "restaurants":
            prepared = self._enrich_restaurants(prepared)
        elif category == "hotels":
            prepared = self._attach_hotel_room_offers(prepared, lat, lng)
            stay, _, _ = self._hotel_room_search_context()
            self.state["candidate_price_context"] = {
                "currency": "CNY",
                "stay_dates": stay if all(stay.values()) else None,
                "hotel_quotes_are_mock": True,
            }
        return prepared

    def _recommend_refinement_result(self, message):
        def message_stream():
            yield AIMessage(content=message)

        return {
            "next_step": "recommend",
            "stream": message_stream(),
            "response": message,
            "attractions": self.state.get("attractions", []),
            "restaurants": self.state.get("restaurants", []),
            "hotels": self.state.get("hotels", []),
            "selected_attractions": self.state.get("selected_attractions", []),
            "selected_restaurants": self.state.get("selected_restaurants", []),
            "selected_hotel": self.state.get("selected_hotel"),
            "itinerary": self.state.get("itinerary", []),
            "candidate_delta": self.state.get("candidate_delta", {}),
            "information_refinement": self.state.get("information_refinement"),
            "information_message": self.state.get("information_message"),
            "candidate_search_state": self.state.get("candidate_search_state"),
            "candidate_price_context": self.state.get("candidate_price_context"),
            "state": self._state_snapshot(),
        }
    
    def _process_strategy(self, **kwargs):
        """Process strategy agent step"""
        # Check if this is a confirm selection request or a satisfaction confirmation
        user_input_lower = kwargs.get('user_input', '').lower()
        is_confirm_selection = user_input_lower in {
            "here are my selected attractions",
            "确认我的地点选择",
            "确认地点选择，开始生成行程",
        }
        is_satisfaction_confirmation = 'satisfied with your recommendation' in user_input_lower
        
        # Log what type of confirmation message we received
        if is_confirm_selection:
            print("[DEBUG] Received initial confirmation of selections")
        elif is_satisfaction_confirmation:
            print("[DEBUG] Received satisfaction confirmation message")
        else:
            print(f"[DEBUG] Received other input: '{user_input_lower}'")
        
        # Print the current state of should_rent_car for debugging
        if 'should_rent_car' in self.state:
            print(f"[DEBUG] Current should_rent_car value: {self.state['should_rent_car']}")
        else:
            print("[DEBUG] should_rent_car not yet set in state")
            
        # If recommendations haven't been generated yet and this is the initial confirm selection
        if not self.state['ai_recommendation_generated'] and is_confirm_selection:
            # Update state flags BEFORE generating recommendations
            self.state['ai_recommendation_generated'] = True
            self.state['user_input_processed'] = True
            
            selected_attractions = self.state["selected_attractions"]
            selected_restaurants = self.state.get("selected_restaurants", [])
            selected_places = selected_attractions + selected_restaurants
            available_places = self.state["attractions"] + self.state.get("restaurants", [])
            total_days = self.state["user_info"].get("days", 1)

            # Plan remaining time and suggest additional attractions
            strategy_result = self.strategy_agent.plan_remaining_time(
                selected_spots=selected_places,
                total_days=total_days,
                all_attractions=available_places,
                user_prefs=self.state["user_info"],    # Pass user_prefs
                weather_summary=self.state.get("weather_summary") # Pass weather_summary
            )
            
            self.state["attractions"] = strategy_result["additional_attractions"]  ## 现在这里的attractions 是经过筛选的,也是最终的attractions
            self.state["daily_plan"] = strategy_result.get("daily_plan", {}) # Store the daily plan
            self.state["hotel_recommendations"] = self._rank_hotel_recommendations()
            if self.state["hotel_recommendations"]:
                self.state["recommended_hotel_id"] = self.state["hotel_recommendations"][0].get("id")

            # Initialize should_rent_car to False by default
            self.state["should_rent_car"] = False
            print("[DEBUG] Initialized should_rent_car to False")
            
            # Get AI recommendation about the overall plan
            # This will also analyze the recommendation and update should_rent_car in user_prefs
            ai_recommendation = self.strategy_agent.get_ai_recommendation(
                user_prefs=self.state["user_info"],
                selected_spots=selected_places,
                total_days=total_days,
            )
            
            # Get the should_rent_car value from user_prefs after AI recommendation analysis
            # This value is set by extract_rental_recommendation in strategy_agent.py
            ai_should_rent_car = self.state["user_info"].get("should_rent_car", False)
            self.state["should_rent_car"] = ai_should_rent_car
            
            print(f"[CRITICAL] AI rental recommendation set should_rent_car to: {ai_should_rent_car}")
            print(f"[DEBUG] Updated state should_rent_car value: {self.state['should_rent_car']}")
            
            # Create a copy of the state to return
            state_copy = self._state_snapshot()
            
            return {
                "next_step": "route",
                "stream": ai_recommendation,
                "remaining_hours": strategy_result["remaining_hours"],
                "additional_attractions": strategy_result["additional_attractions"],
                "should_rent_car": self.state["should_rent_car"],
                "hotel_recommendations": self.state["hotel_recommendations"],
                "recommended_hotel_id": self.state["recommended_hotel_id"],
                "state": state_copy,
                "ai_recommendation_generated": True,
                "user_input_processed": True
            }
        # Handle both cases: either we have already generated recommendations 
        # or this is a satisfaction confirmation message
        elif self.state['ai_recommendation_generated'] or is_satisfaction_confirmation:
            print("[DEBUG] Recommendations already generated or satisfaction confirmed, moving to next step")
            
            # Check if this is a satisfaction confirmation message and we need to process it specially
            if is_satisfaction_confirmation and not self.state['ai_recommendation_generated']:
                print("[CRITICAL] Handling satisfaction confirmation without prior recommendation generation")
                # This means user sent satisfaction message before going through normal flow
                # We need to ensure should_rent_car is correctly set to false in this case
                self.state["should_rent_car"] = False # Ensure it's false
                print("[DEBUG] Set should_rent_car to False for satisfaction message without prior recommendation")
            
            # ALWAYS GO TO ROUTE STEP, SKIP COMMUNICATION
            next_step = "route"
            print(f"[CRITICAL] Decision point: Forcing next_step to '{next_step}' to skip car rental communication.")
            
            # Create a generator that yields the transition message
            def transition_generator():
                if next_step == "route":
                    yield AIMessage(content="继续为你整理每日路线和预算...")
                else:
                    yield AIMessage(content="继续处理下一步...")
            
            # Create a copy of the state to return
            state_copy = self._state_snapshot()
            
            return {
                "next_step": next_step,
                "stream": transition_generator(),
                "state": state_copy,
                "ai_recommendation_generated": True,
                "user_input_processed": True
            }
        else:
            print("[DEBUG] Not a confirm selection request and recommendations not generated yet")
            # Create a generator that yields a message asking for confirmation
            def confirmation_generator():
                yield AIMessage(content="Please click the 'Confirm Selection' button to proceed with your travel plan.")
            
            # Create a copy of the state to return
            state_copy = self._state_snapshot()
            print(f"[DEBUG] State to be returned: {state_copy}")
            
            return {
                "next_step": "strategy",
                "stream": confirmation_generator(),
                "state": state_copy,
                "ai_recommendation_generated": False,
                "user_input_processed": False
            }
    
    # After strategy step + self.state.get("should_rent_car", False) == True
    def _process_communication(self, response_message=None, **kwargs):
        """Process communication agent step - LOGIC MOSTLY COMMENTED OUT"""
        # First check if car rental is actually recommended (THIS CHECK IS NOW REDUNDANT as we skip this step)
        # if not self.state.get("should_rent_car", False):
        #     # If car rental is NOT recommended, skip to route planning
        #     def skip_rental_generator():
        #         yield AIMessage(content="Moving to the route planning step...")
        #         
        #     return {
        #         "next_step": "route",
        #         "stream": skip_rental_generator(),
        #     }
            
        # if response_message and self.state.get("rental_post"):
        #     # Handle response to rental post
        #     reply = self.comm_agent.handle_rental_response(
        #         self.state["rental_post"],
        #         response_message
        #     )
        #     
        #     # Create a generator that yields the response message
        #     def reply_generator():
        #         yield AIMessage(content="Thank you for handling the car rental.")
        #     
        #     return {
        #         "next_step": "route",  # Move to route planning after rental communication
        #         "stream": reply_generator(),
        #         "reply": reply
        #     }
        # else:
        #     # Generate rental post
        #     location = self.state["user_info"].get("city", "")
        #     duration = self.state["user_info"].get("days", 1)
        #     
        #     rental_post_content = self.comm_agent.post_car_rental_request(
        #         location,
        #         duration,
        #         self.state["user_info"]
        #     )
        #     
        #     self.state["rental_post"] = rental_post_content # Store actual content not the UI representation
        #     
        #     # Create a generator that yields the response message
        #     def response_generator():
        #         yield AIMessage(content="We recommend renting a car for your trip. I've created a car rental request post for you. Feel free to use it.")
        #     
        #     return {
        #         "next_step": "route",  # Continue with route planning while waiting for responses
        #         "stream": response_generator(),
        #         "rental_post": rental_post_content # Return the actual post content
        #     }

        # Fallback / Default behavior if this step is somehow still called:
        print("[WARN] _process_communication was called but should be skipped. Proceeding to route planning.")
        def default_transition_generator():
            yield AIMessage(content="Proceeding to route planning...")
        return {
            "next_step": "route",
            "stream": default_transition_generator(),
            "state": self._state_snapshot()
        }
    
    def _process_route(self, start_date=None, **kwargs):
        """Process route agent step"""
        try:
            # Get start date from user preferences, fallback to provided start_date, then to current date
            start_date = self.state["user_info"].get("start_date") or start_date or datetime.now().strftime("%Y-%m-%d")
            
            
            all_attractions_objects = self.state["attractions"] ## This is the flat list of all planned attraction objects
            daily_plan_name_dict = self.state.get("daily_plan") # This is {"day1": ["NameA"], ...}
            
            #print(f"[DEBUG] All attractions: {all_attractions}")
            
            if not all_attractions_objects:
                return {
                    "next_step": "complete",
                    "response": "No attractions selected for the trip.",
                    "itinerary": [],
                    "budget": {},
                    "optimal_route": []
                }
            
            # Generate itinerary first
            days = int(self.state["user_info"].get("days", 1))  # Ensure days is an integer

            itinerary = []
            if daily_plan_name_dict and isinstance(daily_plan_name_dict, dict) and all_attractions_objects:
                all_spots_map = {spot["name"]: spot for spot in all_attractions_objects if spot and "name" in spot}
                itinerary = self.route_agent.format_daily_plan_to_itinerary(
                    daily_plan_name_dict,
                    all_spots_map,
                    start_date,
                    selected_hotel=self.state.get("selected_hotel"),
                )
            else:
                print("[ERROR] Could not generate itinerary: daily_plan_name_dict or all_attractions_objects missing/invalid.")
                # Fallback: Potentially use the old generate_itinerary if it was kept and makes sense
                # For now, itinerary remains empty, leading to a response with no itinerary.
                # self.state["itinerary"] will be empty, and confirmation will reflect that.

            
            # Fix: convert start_date to datetime if it's a string
            if isinstance(start_date, str):
                start_date_dt = datetime.strptime(start_date, "%Y-%m-%d")
            else:
                start_date_dt = start_date
            end_date = (start_date_dt + timedelta(days=days)).strftime("%Y-%m-%d")
            # Extract the optimal route from the itinerary
            optimal_route = []
            if itinerary:
                for day_plan_item in itinerary: # Iterate through list of day plans
                    day_number = day_plan_item.get("day")
                    for spot in day_plan_item.get("spots", []):
                        spot_with_day = spot.copy() # Avoid modifying original spot in itinerary
                        spot_with_day["day"] = day_number
                        optimal_route.append(spot_with_day)
           
            # Estimate budget

            if self.state["should_rent_car"]:
                car_info = self.info_agent.search_car_rentals(
                    self.state["user_info"].get("city", ""),
                    start_date,
                    end_date,
                    driver_age=self.state["user_info"].get("age", 30)
                )   
                fuel_price = self.info_agent.get_fuel_price(self.state["user_info"].get("city", ""))
                if fuel_price and car_info:
                    print(f"[DEBUG] Successfully got fuel price and car info, fuel_price: {fuel_price}, car_info: {car_info}")
            
            budget = self.route_agent.estimate_budget(
                all_attractions_objects,
                self.state["user_info"],
                self.state["should_rent_car"],
                car_info if self.state["should_rent_car"] else None,
                fuel_price if self.state["should_rent_car"] else None
            )
       
            # Store in state
            self.state["itinerary"] = itinerary
            self.state["budget"] = budget
            
            # Generate confirmation message
            confirmation = self.comm_agent.generate_booking_confirmation(
                itinerary,
                budget,
                self.state["should_rent_car"],
                self.state["user_info"].get("name", "Traveler"),
            )
            
            return {
                "next_step": "complete",
                "response": confirmation,
                "itinerary": itinerary,
                "budget": budget,
                "optimal_route": optimal_route,
                "hotel_recommendations": self.state.get("hotel_recommendations", []),
                "booking_drafts": self.state.get("booking_drafts", {}),
                "state": self._state_snapshot(),
            }
            
        except Exception as error:
            print(f"Error in process route: {type(error).__name__}")
            return {
                "next_step": "error",
                "response": "An error occurred while planning your route. Please try again.",
                "error": "internal_error",
            }
    
    def get_current_state(self):
        """Get the current state of the workflow"""
        return self._state_snapshot()

    def _process_complete(self, user_input=None, **kwargs):
        if self._can_start_booking(user_input):
            return self._process_booking_intent(user_input=user_input, **kwargs)

        def guidance_generator():
            yield AIMessage(content="行程已经生成好了。你可以继续告诉我“帮我订酒店”或“帮我订机票”，我会为你生成待确认订单草稿。")

        return {
            "next_step": "complete",
            "stream": guidance_generator(),
            "state": self._state_snapshot(),
            "hotel_recommendations": self.state.get("hotel_recommendations", []),
            "booking_drafts": self.state.get("booking_drafts", {}),
        }

    def _process_booking_intent(self, user_input=None, **kwargs):
        booking_mode = self.booking_agent.detect_intent(user_input or "") or self.state.get("booking_mode")
        if not booking_mode:
            def no_intent_generator():
                yield AIMessage(content="如果你想继续预订，可以直接说“帮我订酒店”或“帮我订机票”。")

            return {
                "next_step": "complete",
                "stream": no_intent_generator(),
                "state": self._state_snapshot(),
            }

        self.state["booking_mode"] = booking_mode
        booking_context = self.booking_agent.build_booking_context(booking_mode, self.state, user_input or "")
        self.state["booking_context"] = booking_context
        self.state["booking_missing_fields"] = self.booking_agent.collect_missing_fields(booking_mode, booking_context)

        if self.state["booking_missing_fields"]:
            return self._process_booking_collect(user_input=user_input, **kwargs)
        return self._process_booking_draft(user_input=user_input, **kwargs)

    def _process_booking_collect(self, user_input=None, **kwargs):
        booking_mode = self.state.get("booking_mode")
        booking_context = self.state.get("booking_context", {})
        if user_input:
            booking_context.update(self.booking_agent.extract_structured_preferences(user_input))
        self.state["booking_context"] = booking_context
        missing_fields = self.booking_agent.collect_missing_fields(booking_mode, booking_context)
        self.state["booking_missing_fields"] = missing_fields

        if missing_fields:
            prompt = self.booking_agent.build_missing_fields_prompt(booking_mode, missing_fields)

            def collect_generator():
                yield AIMessage(content=prompt)

            return {
                "next_step": "booking_collect",
                "stream": collect_generator(),
                "state": self._state_snapshot(),
                "booking_mode": booking_mode,
                "booking_missing_fields": missing_fields,
            }

        return self._process_booking_draft(user_input=user_input, **kwargs)

    def _process_booking_draft(self, user_input=None, **kwargs):
        booking_mode = self.state.get("booking_mode")
        booking_context = self.state.get("booking_context", {})

        if booking_mode == "hotel":
            hotel_candidates = self.state.get("hotel_recommendations") or self.state.get("hotel_candidates") or self.booking_provider.search_hotels(booking_context)
            self.state["booking_candidates"]["hotels"] = hotel_candidates
            selected_hotel = self._pick_selected_hotel(hotel_candidates, booking_context)
            hotel_draft = self.booking_provider.create_hotel_draft(
                {
                    "hotel": selected_hotel,
                    "criteria": {
                        "city": booking_context.get("destination"),
                        "check_in": booking_context.get("check_in"),
                        "check_out": booking_context.get("check_out"),
                        "rooms": booking_context.get("rooms", 1),
                        "guests": booking_context.get("guests", 1),
                        "special_requests": booking_context.get("special_requests", ""),
                    },
                    "traveler": {
                        "contact_name": booking_context.get("contact_name", ""),
                        "contact_phone": booking_context.get("contact_phone", ""),
                    },
                }
            )
            self.state.setdefault("booking_drafts", {})["hotel_draft"] = hotel_draft
            self.state["active_draft_type"] = "hotel_draft"
            return self._process_booking_confirm(user_input=user_input, **kwargs)

        if booking_mode == "flight":
            flight_candidates = self.booking_provider.search_flights(booking_context)
            self.state["booking_candidates"]["flights"] = flight_candidates
            selected_offer = flight_candidates[0]
            flight_draft = self.booking_provider.create_flight_draft(
                {
                    "offer": selected_offer,
                    "criteria": {
                        "origin": booking_context.get("origin"),
                        "destination": booking_context.get("destination"),
                        "depart_date": booking_context.get("depart_date"),
                        "return_date": booking_context.get("return_date"),
                        "passengers": booking_context.get("passengers"),
                    },
                    "traveler": {
                        "contact_name": booking_context.get("contact_name", ""),
                        "contact_phone": booking_context.get("contact_phone", ""),
                        "passenger_name": booking_context.get("passenger_name", ""),
                        "document_type": booking_context.get("document_type", ""),
                        "document_last4": booking_context.get("document_last4", ""),
                    },
                }
            )
            self.state.setdefault("booking_drafts", {})["flight_draft"] = flight_draft
            self.state["active_draft_type"] = "flight_draft"
            return self._process_booking_confirm(user_input=user_input, **kwargs)

        if booking_mode == "both":
            hotel_candidates = self.state.get("hotel_recommendations") or self.state.get("hotel_candidates") or self.booking_provider.search_hotels(booking_context)
            flight_candidates = self.booking_provider.search_flights(booking_context)
            self.state["booking_candidates"]["hotels"] = hotel_candidates
            self.state["booking_candidates"]["flights"] = flight_candidates

            selected_hotel = self._pick_selected_hotel(hotel_candidates, booking_context)
            selected_offer = flight_candidates[0]

            self.state.setdefault("booking_drafts", {})["hotel_draft"] = self.booking_provider.create_hotel_draft(
                {
                    "hotel": selected_hotel,
                    "criteria": {
                        "city": booking_context.get("destination"),
                        "check_in": booking_context.get("check_in"),
                        "check_out": booking_context.get("check_out"),
                        "rooms": booking_context.get("rooms", 1),
                        "guests": booking_context.get("guests", 1),
                        "special_requests": booking_context.get("special_requests", ""),
                    },
                    "traveler": {
                        "contact_name": booking_context.get("contact_name", ""),
                        "contact_phone": booking_context.get("contact_phone", ""),
                    },
                }
            )
            self.state["booking_drafts"]["flight_draft"] = self.booking_provider.create_flight_draft(
                {
                    "offer": selected_offer,
                    "criteria": {
                        "origin": booking_context.get("origin"),
                        "destination": booking_context.get("destination"),
                        "depart_date": booking_context.get("depart_date"),
                        "return_date": booking_context.get("return_date"),
                        "passengers": booking_context.get("passengers"),
                    },
                    "traveler": {
                        "contact_name": booking_context.get("contact_name", ""),
                        "contact_phone": booking_context.get("contact_phone", ""),
                        "passenger_name": booking_context.get("passenger_name", ""),
                        "document_type": booking_context.get("document_type", ""),
                        "document_last4": booking_context.get("document_last4", ""),
                    },
                }
            )
            self.state["active_draft_type"] = "combo_draft"
            return self._process_booking_confirm(user_input=user_input, **kwargs)

        def unsupported_generator():
            yield AIMessage(content="我已经准备好预订能力了，不过这一轮先分别处理酒店或机票草稿。")

        return {
            "next_step": "booking_collect",
            "stream": unsupported_generator(),
            "state": self._state_snapshot(),
            "booking_mode": booking_mode,
        }

    def _process_booking_confirm(self, user_input=None, **kwargs):
        booking_mode = self.state.get("booking_mode")
        active_draft_type = self.state.get("active_draft_type")
        active_draft = self.state.get("booking_drafts", {}).get(active_draft_type, {})
        candidates = self.state.get("booking_candidates", {})

        if booking_mode == "hotel":
            summary = self.booking_agent.build_booking_candidates_summary("hotel", candidates.get("hotels", []))
            draft_text = (
                f"\n\n已生成酒店待确认草稿：{active_draft.get('selected_offer', {}).get('hotel_name', '')}"
                f"，总价约 ¥{active_draft.get('pricing_summary', {}).get('total_amount', 0)}。"
            )
        elif booking_mode == "flight":
            summary = self.booking_agent.build_booking_candidates_summary("flight", candidates.get("flights", []))
            draft_text = (
                f"\n\n已生成机票待确认草稿：{active_draft.get('selected_offer', {}).get('flight_no', '')}"
                f"，总价约 ¥{active_draft.get('pricing_summary', {}).get('total_amount', 0)}。"
            )
        else:
            hotel_draft = self.state.get("booking_drafts", {}).get("hotel_draft", {})
            flight_draft = self.state.get("booking_drafts", {}).get("flight_draft", {})
            summary = "我已经同时为你准备了酒店和机票候选。"
            draft_text = (
                f"\n\n酒店草稿：{hotel_draft.get('selected_offer', {}).get('hotel_name', '')}"
                f"，总价约 ¥{hotel_draft.get('pricing_summary', {}).get('total_amount', 0)}。"
                f"\n机票草稿：{flight_draft.get('selected_offer', {}).get('flight_no', '')}"
                f"，总价约 ¥{flight_draft.get('pricing_summary', {}).get('total_amount', 0)}。"
            )

        def confirm_generator():
            yield AIMessage(content=summary + draft_text + "\n如果你想调整信息，也可以继续直接用自然语言告诉我。")

        return {
            "next_step": "booking_confirm",
            "stream": confirm_generator(),
            "state": self._state_snapshot(),
            "booking_mode": booking_mode,
            "booking_drafts": self.state.get("booking_drafts", {}),
            "booking_candidates": candidates,
        }

    def _can_start_booking(self, user_input):
        return bool(self.state.get("itinerary")) and self.booking_agent.detect_intent(user_input or "")

    def _get_candidate_page(
        self,
        category,
        lat,
        lng,
        user_prefs=None,
        core_locations=None,
        page_token=None,
        keyword=None,
    ):
        page_loader = getattr(self.info_agent, "get_place_candidate_page", None)
        if callable(page_loader):
            category_config = {
                "attractions": ("tourist_attraction", "attraction"),
                "restaurants": ("restaurant", "restaurant"),
                "hotels": ("lodging", "hotel"),
            }
            place_type, kind = category_config[category]
            loader_kwargs = {
                "place_type": place_type,
                "kind": kind,
                "user_prefs": user_prefs or {},
                "preferences": (user_prefs or {}).get(
                    "accommodation_preferences", {}
                ),
                "core_locations": core_locations or [],
                "page_token": page_token,
                "keyword": keyword,
            }
            parameters = signature(page_loader).parameters
            supports_kwargs = any(
                parameter.kind == Parameter.VAR_KEYWORD
                for parameter in parameters.values()
            )
            if not supports_kwargs:
                loader_kwargs = {
                    key: value
                    for key, value in loader_kwargs.items()
                    if key in parameters
                }
            page = page_loader(lat, lng, **loader_kwargs)
            if not isinstance(page, dict) or not isinstance(
                page.get("candidates"), list
            ):
                raise RuntimeError("Invalid candidate page response")
            candidates = page["candidates"]
            token = page.get("next_page_token")
            return {
                "candidates": candidates,
                "next_page_token": token
                if isinstance(token, str) and token
                else None,
            }

        if category == "restaurants":
            candidates = self._get_restaurant_candidates(lat, lng, user_prefs)
        elif category == "hotels":
            preferences = (user_prefs or {}).get("accommodation_preferences", {})
            if hasattr(self.info_agent, "get_hotel_candidates"):
                candidates = self.info_agent.get_hotel_candidates(
                    lat,
                    lng,
                    preferences=preferences,
                    core_locations=core_locations or [],
                )
            else:
                nearby_data = self.info_agent.search_nearby_places(lat, lng)
                candidates = (nearby_data or {}).get("hotels", [])
        else:
            candidates = self.info_agent.get_attractions(
                lat=lat,
                lng=lng,
                user_prefs=user_prefs or {},
                weather_summary=self.state.get("weather_summary"),
                number=20,
                poi_type="tourist_attraction",
            )
        return {"candidates": candidates or [], "next_page_token": None}

    def _enrich_restaurants(self, restaurants):
        poi_api = getattr(self.info_agent, "poi_api", None)
        price_loader = getattr(poi_api, "get_place_price_range", None)
        if not callable(price_loader):
            price_loader = None
        return PlaceCandidateEnricher(price_loader).enrich_restaurants(
            restaurants or []
        )

    def _set_initial_candidate_search_state(self, category, page):
        candidates = page.get("candidates", []) if isinstance(page, dict) else []
        token = page.get("next_page_token") if isinstance(page, dict) else None
        token = token if isinstance(token, str) and token.strip() else None
        seen_ids = []
        for candidate in candidates:
            candidate_id = candidate.get("id") if isinstance(candidate, dict) else None
            candidate_id = self._valid_candidate_id(candidate_id)
            if candidate_id and candidate_id not in seen_ids:
                seen_ids.append(candidate_id)
        self.state["candidate_search_state"][category] = {
            "next_page_token": token,
            "seen_ids": seen_ids,
            "exhausted": not bool(token),
            "last_query": None,
            "last_error": None,
        }

    def _get_restaurant_candidates(self, lat, lng, user_prefs=None):
        if hasattr(self.info_agent, "get_restaurant_candidates"):
            return self.info_agent.get_restaurant_candidates(lat, lng, user_prefs=user_prefs)
        nearby_data = self.info_agent.search_nearby_places(lat, lng)
        return (nearby_data or {}).get("restaurants", [])

    def _get_hotel_candidates(self, lat, lng, preferences, core_locations=None):
        if hasattr(self.info_agent, "get_hotel_candidates"):
            hotels = self.info_agent.get_hotel_candidates(
                lat, lng, preferences=preferences, core_locations=core_locations or []
            )
        else:
            nearby_data = self.info_agent.search_nearby_places(lat, lng)
            hotels = (nearby_data or {}).get("hotels", [])

        return self._attach_hotel_room_offers(hotels, lat, lng)

    def _attach_hotel_room_offers(self, hotels, lat, lng):

        stay, room_search_context, context_error = self._hotel_room_search_context()
        normalized = []
        for idx, hotel in enumerate(hotels or [], start=1):
            normalized_hotel = {
                "id": hotel.get("id") or hotel.get("place_id") or f"hotel_{idx}",
                "kind": "hotel",
                "name": hotel.get("name"),
                "address": hotel.get("address"),
                "rating": self._normalize_rating(hotel.get("rating")),
                "price_level": self._normalize_price_level(
                    hotel.get("price_level")
                ),
                "location": deepcopy(hotel.get("location"))
                if hotel.get("location")
                else {"lat": lat, "lng": lng},
                "summary": hotel.get("summary") or hotel.get("summary_overview") or "",
                "photos": deepcopy(hotel.get("photos", [])),
                "source": hotel.get("source") or "google_places",
                "amenities": self._normalize_text_values(
                    hotel.get("amenities", [])
                ),
                "match_reasons": self._normalize_text_values(
                    hotel.get("match_reasons", [])
                ),
                "match_score": hotel.get("match_score"),
                "recommendation_reasons": self._normalize_text_values(
                    hotel.get("recommendation_reasons", [])
                ),
                "recommendation_rank": hotel.get("recommendation_rank"),
                "ranking_source": hotel.get("ranking_source"),
                "stay": deepcopy(stay),
                "room_offers": [],
                "price_display": "房价待确认",
                "price_source": "unavailable",
                "hotel_quotes_are_mock": False,
                "room_offer_status": "unavailable",
                "room_offer_error": context_error,
            }

            offers = []
            if room_search_context is not None:
                try:
                    provider_offers = self.booking_provider.search_hotel_rooms(
                        {
                            **room_search_context,
                            "hotel_id": normalized_hotel["id"],
                            "hotel_name": normalized_hotel["name"],
                        }
                    )
                    if isinstance(provider_offers, list):
                        offers = deepcopy(provider_offers)
                        normalized_hotel["room_offer_error"] = (
                            None if offers else "no_offers"
                        )
                    else:
                        normalized_hotel["room_offer_error"] = (
                            "invalid_provider_response"
                        )
                except Exception:
                    offers = []
                    normalized_hotel["room_offer_error"] = "provider_unavailable"

            if offers:
                try:
                    lowest_offer = min(offers, key=lambda offer: offer["nightly_rate"])
                    selected_room_offer = deepcopy(lowest_offer)
                    lowest_rate = selected_room_offer["nightly_rate"]
                    normalized_hotel.update(
                        {
                            "room_offers": deepcopy(offers),
                            "selected_room_offer": selected_room_offer,
                            "price_display": f"房型 ¥{lowest_rate}/晚起（模拟报价）",
                            "price_source": "ctrip_mock",
                            "hotel_quotes_are_mock": True,
                            "room_offer_status": "available",
                            "room_offer_error": None,
                            "room_type": deepcopy(
                                selected_room_offer["room_type"]
                            ),
                            "nightly_rate": lowest_rate,
                            "cancellation_policy": deepcopy(
                                selected_room_offer["cancellation_policy"]
                            ),
                        }
                    )
                except (KeyError, TypeError, ValueError):
                    normalized_hotel["room_offer_error"] = (
                        "invalid_provider_response"
                    )
            normalized.append(normalized_hotel)
        return normalized

    def _hotel_room_search_context(self):
        user_info = self.state.get("user_info", {})
        check_in_text = user_info.get("start_date")
        unavailable_stay = {"check_in": None, "check_out": None}
        try:
            if not isinstance(check_in_text, str):
                raise ValueError
            check_in = date.fromisoformat(check_in_text)
            if check_in.isoformat() != check_in_text:
                raise ValueError

            days = self._graph_bounded_integer(
                user_info.get("days"),
                1,
                getattr(self.booking_provider, "MAX_NIGHTS", 30),
            )
            guests = self._graph_bounded_integer(
                user_info.get("people", 1),
                1,
                getattr(self.booking_provider, "MAX_GUESTS", 40),
            )
            check_out_text = (check_in + timedelta(days=days)).isoformat()
        except (TypeError, ValueError, OverflowError):
            return unavailable_stay, None, "invalid_stay_criteria"

        stay = {"check_in": check_in_text, "check_out": check_out_text}
        return stay, {
            "destination": user_info.get("city"),
            "check_in": check_in_text,
            "check_out": check_out_text,
            "rooms": 1,
            "guests": guests,
        }, None

    @staticmethod
    def _graph_bounded_integer(value, minimum, maximum):
        if isinstance(value, bool):
            raise ValueError
        parsed = int(value)
        if str(parsed) != str(value).strip() or not minimum <= parsed <= maximum:
            raise ValueError
        return parsed

    def _rank_hotel_recommendations(self):
        hotel_candidates = self.state.get("hotel_candidates", [])
        selected_attractions = self.state.get("selected_attractions", [])
        preference_text = (self.state.get("user_info", {}).get("accommodation_preference", "") or "").lower()

        def score(candidate):
            value = float(candidate.get("rating") or 0) * 10
            summary = f"{candidate.get('summary', '')} {' '.join(candidate.get('match_reasons', []))}".lower()
            if any(keyword in preference_text for keyword in ["地铁", "交通"]) and any(keyword in summary for keyword in ["地铁", "交通", "便利"]):
                value += 8
            if any(keyword in preference_text for keyword in ["亲子", "家庭"]) and any(keyword in summary for keyword in ["亲子", "家庭"]):
                value += 8
            if "早餐" in preference_text and "早餐" in summary:
                value += 5
            if selected_attractions:
                value += 2
            return value

        ranked = sorted(hotel_candidates, key=score, reverse=True)
        for item in ranked:
            item["score"] = score(item)
        return ranked[:3]

    def _pick_selected_hotel(self, hotel_candidates, booking_context):
        selected_hotel = self.state.get("selected_hotel")
        if selected_hotel:
            return selected_hotel
        recommended_id = self.state.get("recommended_hotel_id")
        if recommended_id:
            for hotel in hotel_candidates:
                if hotel.get("id") == recommended_id:
                    return hotel
        return hotel_candidates[0] if hotel_candidates else {
            "id": "fallback_hotel",
            "name": f"{booking_context.get('destination', '目的地')}优选酒店",
            "address": booking_context.get("destination", ""),
            "source": "ctrip_mock",
            "nightly_rate": 688,
        }
