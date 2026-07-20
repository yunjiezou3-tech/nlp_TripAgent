from __future__ import annotations

import re
from datetime import datetime, timedelta


class BookingAgent:
    def detect_intent(self, user_input: str) -> str | None:
        text = (user_input or "").lower()
        if any(keyword in text for keyword in ["机票", "航班", "flight", "air ticket"]):
            if any(keyword in text for keyword in ["酒店", "hotel", "住宿"]):
                return "both"
            return "flight"
        if any(keyword in text for keyword in ["酒店", "hotel", "住宿", "订房"]):
            return "hotel"
        return None

    def build_booking_context(self, booking_mode: str, state: dict, user_input: str = "") -> dict:
        user_info = state.get("user_info", {})
        itinerary = state.get("itinerary") or []
        first_day = itinerary[0] if itinerary else {}
        last_day = itinerary[-1] if itinerary else {}

        context = {
            "booking_mode": booking_mode,
            "destination": user_info.get("city") or user_info.get("destination"),
            "origin": user_info.get("origin"),
            "check_in": user_info.get("start_date") or first_day.get("date"),
            "check_out": self._derive_checkout_date(
                user_info.get("start_date") or first_day.get("date"),
                user_info.get("days", 1),
                last_day.get("date"),
            ),
            "depart_date": user_info.get("start_date") or first_day.get("date"),
            "return_date": self._derive_checkout_date(
                user_info.get("start_date") or first_day.get("date"),
                user_info.get("days", 1),
                last_day.get("date"),
            ),
            "rooms": 1,
            "guests": self._safe_int(user_info.get("people"), 1),
            "passengers": self._safe_int(user_info.get("people"), 1),
            "contact_name": user_info.get("name", ""),
            "contact_phone": user_info.get("contact_phone", ""),
            "passenger_name": user_info.get("passenger_name", user_info.get("name", "")),
            "document_type": user_info.get("document_type", ""),
            "document_last4": user_info.get("document_last4", ""),
            "special_requests": user_info.get("specificRequirements", ""),
            "accommodation_preference": user_info.get("accommodation_preference", ""),
        }

        extracted = self.extract_structured_preferences(user_input)
        context.update({key: value for key, value in extracted.items() if value not in ("", None)})
        return context

    def collect_missing_fields(self, booking_mode: str, context: dict) -> list[str]:
        if booking_mode == "hotel":
            required = ["destination", "check_in", "check_out", "guests", "contact_name", "contact_phone"]
        elif booking_mode == "flight":
            required = [
                "origin",
                "destination",
                "depart_date",
                "passengers",
                "contact_name",
                "contact_phone",
                "passenger_name",
                "document_type",
                "document_last4",
            ]
        else:
            hotel_missing = self.collect_missing_fields("hotel", context)
            flight_missing = self.collect_missing_fields("flight", context)
            return sorted(set(hotel_missing + flight_missing))

        return [field for field in required if not context.get(field)]

    def build_missing_fields_prompt(self, booking_mode: str, missing_fields: list[str]) -> str:
        field_labels = {
            "destination": "目的地/入住城市",
            "check_in": "入住日期",
            "check_out": "离店日期",
            "guests": "入住人数",
            "rooms": "房间数",
            "contact_name": "联系人姓名",
            "contact_phone": "联系人手机号",
            "origin": "出发地",
            "depart_date": "出发日期",
            "return_date": "返程日期",
            "passengers": "乘机人数",
            "passenger_name": "乘机人姓名",
            "document_type": "证件类型",
            "document_last4": "证件尾号",
        }
        mode_label = {"hotel": "酒店", "flight": "机票", "both": "机票和酒店"}.get(booking_mode, "预订")
        readable = "、".join(field_labels.get(field, field) for field in missing_fields)
        return f"可以继续为你生成{mode_label}待确认订单草稿。还差这些信息：{readable}。"

    def build_booking_candidates_summary(self, booking_mode: str, candidates: list[dict]) -> str:
        if booking_mode == "hotel":
            lines = ["我先为你筛了 3 家更匹配住宿偏好的酒店："]
            for idx, hotel in enumerate(candidates[:3], start=1):
                lines.append(
                    f"{idx}. {hotel.get('name')}，评分 {hotel.get('rating', 'N/A')}，"
                    f"约 ¥{hotel.get('nightly_rate', 0)}/晚，亮点：{'、'.join(hotel.get('match_reasons', []))}"
                )
            lines.append("如果你认可其中一家，我会继续生成待确认订单草稿。")
            return "\n".join(lines)

        lines = ["我先为你筛了 2 个机票候选："]
        for idx, offer in enumerate(candidates[:2], start=1):
            lines.append(
                f"{idx}. {offer.get('flight_no')} {offer.get('airline')}，"
                f"{offer.get('depart_time')} 出发，合计 ¥{offer.get('total_amount', 0)}"
            )
        lines.append("如果你认可其中一个航班，我会继续生成待确认机票草稿。")
        return "\n".join(lines)

    def extract_structured_preferences(self, user_input: str) -> dict:
        text = user_input or ""
        result = {}

        date_matches = re.findall(r"(\d{4}-\d{2}-\d{2})", text)
        if date_matches:
            result["check_in"] = date_matches[0]
            result["depart_date"] = date_matches[0]
        if len(date_matches) > 1:
            result["check_out"] = date_matches[1]
            result["return_date"] = date_matches[1]

        guest_match = re.search(r"(\d+)\s*(位|人)", text)
        if guest_match:
            count = int(guest_match.group(1))
            result["guests"] = count
            result["passengers"] = count

        room_match = re.search(r"(\d+)\s*(间|个房间)", text)
        if room_match:
            result["rooms"] = int(room_match.group(1))

        phone_match = re.search(
            r"(?:联系人手机号|联系电话|手机号|手机|电话)\s*[:：]?\s*([+\d][\d\s-]{4,20}\d)",
            text,
        )
        if not phone_match:
            phone_match = re.search(r"(1\d{10})", text)
        if phone_match:
            result["contact_phone"] = re.sub(r"[\s-]", "", phone_match.group(1))

        if "护照" in text:
            result["document_type"] = "护照"
        elif "身份证" in text:
            result["document_type"] = "身份证"

        document_last4_match = re.search(r"(?:尾号|后四位)\s*[:：]?\s*([A-Za-z0-9]{4,})", text)
        if not document_last4_match:
            document_last4_match = re.search(
                r"(?:护照|身份证|证件)\s*(?:号|号码)?\s*[:：]?\s*([A-Za-z0-9]{4,})",
                text,
            )
        if document_last4_match:
            result["document_last4"] = document_last4_match.group(1)[-4:]

        return result

    def _derive_checkout_date(self, start_date: str | None, days: int | str | None, fallback: str | None) -> str | None:
        if fallback:
            try:
                fallback_dt = datetime.strptime(fallback, "%Y-%m-%d") + timedelta(days=1)
                return fallback_dt.strftime("%Y-%m-%d")
            except ValueError:
                pass
        if not start_date:
            return None
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            day_count = max(self._safe_int(days, 1), 1)
            return (start_dt + timedelta(days=day_count)).strftime("%Y-%m-%d")
        except ValueError:
            return None

    def _safe_int(self, value, default: int) -> int:
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
