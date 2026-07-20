from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
from datetime import datetime, timedelta
import hashlib
import json


MIN_NIGHTS = 1
MAX_NIGHTS = 30
MIN_ROOMS = 1
MAX_ROOMS = 10
MIN_GUESTS = 1
MAX_GUESTS = 40


class BookingProvider(ABC):
    @abstractmethod
    def search_hotels(self, criteria: dict) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def search_hotel_rooms(self, criteria: dict) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def search_flights(self, criteria: dict) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def create_hotel_draft(self, payload: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def create_flight_draft(self, payload: dict) -> dict:
        raise NotImplementedError


class CtripMockProvider(BookingProvider):
    provider_name = "ctrip_mock"
    MIN_NIGHTS = MIN_NIGHTS
    MAX_NIGHTS = MAX_NIGHTS
    MIN_ROOMS = MIN_ROOMS
    MAX_ROOMS = MAX_ROOMS
    MIN_GUESTS = MIN_GUESTS
    MAX_GUESTS = MAX_GUESTS

    def search_hotels(self, criteria: dict) -> list[dict]:
        city = criteria.get("city") or criteria.get("destination") or "目的地"
        preference_text = criteria.get("accommodation_preference", "")
        check_in = criteria.get("check_in") or criteria.get("start_date") or datetime.now().strftime("%Y-%m-%d")
        check_out = criteria.get("check_out") or self._default_checkout(check_in, criteria.get("days", 1))

        base_hotels = [
            {
                "id": self._stable_id(city, "metro"),
                "name": f"{city}静安景观酒店",
                "address": f"{city}核心商圈地铁口步行 5 分钟",
                "rating": 4.7,
                "price_level": 3,
                "summary": "交通便利，适合亲子和城市漫游。",
                "photos": [],
                "source": self.provider_name,
                "location": {"lat": 31.2304, "lng": 121.4737},
                "room_type": "高级双床房",
                "nightly_rate": 688,
                "cancellation_policy": "入住前一天 18:00 前可免费取消",
                "match_reasons": ["靠近地铁", "适合家庭", "含早餐"],
                "check_in": check_in,
                "check_out": check_out,
            },
            {
                "id": self._stable_id(city, "sight"),
                "name": f"{city}外滩轻居酒店",
                "address": f"{city}热门景点 15 分钟车程",
                "rating": 4.5,
                "price_level": 2,
                "summary": "性价比高，适合短住和景点打卡。",
                "photos": [],
                "source": self.provider_name,
                "location": {"lat": 31.2400, "lng": 121.4900},
                "room_type": "精选大床房",
                "nightly_rate": 488,
                "cancellation_policy": "入住前两天 12:00 前可免费取消",
                "match_reasons": ["靠近景点", "预算友好"],
                "check_in": check_in,
                "check_out": check_out,
            },
            {
                "id": self._stable_id(city, "family"),
                "name": f"{city}亲子行政酒店",
                "address": f"{city}亲子乐园和商场周边",
                "rating": 4.8,
                "price_level": 4,
                "summary": "更大的房型和家庭设施，适合多人入住。",
                "photos": [],
                "source": self.provider_name,
                "location": {"lat": 31.2200, "lng": 121.4600},
                "room_type": "家庭套房",
                "nightly_rate": 888,
                "cancellation_policy": "入住前一天 12:00 前可免费取消",
                "match_reasons": ["家庭友好", "房间更大", "早餐丰富"],
                "check_in": check_in,
                "check_out": check_out,
            },
        ]

        if "预算" in preference_text and ("低" in preference_text or "经济" in preference_text):
            base_hotels.sort(key=lambda item: item["nightly_rate"])
        elif "亲子" in preference_text or "家庭" in preference_text:
            base_hotels.sort(key=lambda item: ("家庭友好" not in "".join(item["match_reasons"]), item["nightly_rate"]))

        return base_hotels

    def search_hotel_rooms(self, criteria: dict) -> list[dict]:
        if not isinstance(criteria, dict):
            raise ValueError("room search criteria must be a dictionary")

        hotel_id = self._required_text(criteria, "hotel_id")
        hotel_name = self._required_text(criteria, "hotel_name")
        check_in = self._parse_explicit_date(criteria.get("check_in"), "check_in")
        check_out = self._parse_explicit_date(criteria.get("check_out"), "check_out")
        if check_out <= check_in:
            raise ValueError("check_out must be after check_in")

        nights = (check_out - check_in).days
        self._validate_bounded_integer(
            nights, "nights", self.MIN_NIGHTS, self.MAX_NIGHTS
        )
        rooms = self._bounded_integer(
            criteria, "rooms", self.MIN_ROOMS, self.MAX_ROOMS
        )
        guests = self._bounded_integer(
            criteria, "guests", self.MIN_GUESTS, self.MAX_GUESTS
        )
        destination = str(criteria.get("destination") or criteria.get("city") or "")
        check_in_text = check_in.strftime("%Y-%m-%d")
        check_out_text = check_out.strftime("%Y-%m-%d")

        rate_seed = int(
            self._stable_id(destination, hotel_id, hotel_name)[:4], 16
        )
        base_rate = 420 + (rate_seed % 12) * 10
        room_templates = (
            {
                "code": "standard-queen",
                "room_type": "精选大床房",
                "bed_type": "1 张 1.8 米大床",
                "breakfast": "不含早餐",
                "rate_increment": 0,
                "tax_rate": 8,
                "cancellation_policy": "入住前 2 天 18:00 前可免费取消",
            },
            {
                "code": "superior-twin",
                "room_type": "高级双床房",
                "bed_type": "2 张 1.2 米单人床",
                "breakfast": "含双人早餐",
                "rate_increment": 120,
                "tax_rate": 10,
                "cancellation_policy": "入住前 1 天 18:00 前可免费取消",
            },
            {
                "code": "family-suite",
                "room_type": "家庭套房",
                "bed_type": "1 张大床及 1 张单人床",
                "breakfast": "含三人早餐",
                "rate_increment": 280,
                "tax_rate": 12,
                "cancellation_policy": "模拟特价房，不可取消",
            },
        )

        offers = []
        for room in room_templates:
            nightly_rate = base_rate + room["rate_increment"]
            room_subtotal = nightly_rate * nights * rooms
            taxes_and_fees = (room_subtotal * room["tax_rate"] + 99) // 100
            offer_key = self._stable_id(
                destination,
                hotel_id,
                hotel_name,
                check_in_text,
                check_out_text,
                rooms,
                guests,
                room["code"],
            )
            offers.append(
                {
                    "offer_id": f"mock_room_{offer_key}",
                    "hotel_id": hotel_id,
                    "hotel_name": hotel_name,
                    "room_type": room["room_type"],
                    "bed_type": room["bed_type"],
                    "breakfast": room["breakfast"],
                    "nightly_rate": nightly_rate,
                    "currency": "CNY",
                    "room_subtotal": room_subtotal,
                    "total_price": room_subtotal + taxes_and_fees,
                    "taxes_and_fees": taxes_and_fees,
                    "cancellation_policy": room["cancellation_policy"],
                    "check_in": check_in_text,
                    "check_out": check_out_text,
                    "rooms": rooms,
                    "guests": guests,
                    "inventory_status": "available",
                    "source_provider": self.provider_name,
                    "is_mock": True,
                    "provider_trace_id": f"mock_trace_{offer_key}",
                    "raw_payload_ref": f"mock_payload_{offer_key}",
                }
            )
        return offers

    def search_flights(self, criteria: dict) -> list[dict]:
        origin = criteria.get("origin") or criteria.get("departure_city") or "出发地"
        destination = criteria.get("destination") or criteria.get("city") or "目的地"
        depart_date = criteria.get("depart_date") or criteria.get("start_date") or datetime.now().strftime("%Y-%m-%d")
        passengers = int(criteria.get("passengers") or criteria.get("people") or 1)

        return [
            {
                "id": self._stable_id(origin, destination, "morning"),
                "source": self.provider_name,
                "airline": "携程联运模拟航班",
                "flight_no": "MU5123",
                "cabin": "经济舱",
                "depart_airport": f"{origin}国际机场",
                "arrive_airport": f"{destination}国际机场",
                "depart_time": f"{depart_date} 09:20",
                "arrive_time": f"{depart_date} 12:05",
                "taxes": 180 * passengers,
                "ticket_price": 980 * passengers,
                "total_amount": 1160 * passengers,
                "baggage": "20kg 托运行李",
            },
            {
                "id": self._stable_id(origin, destination, "evening"),
                "source": self.provider_name,
                "airline": "携程联运模拟航班",
                "flight_no": "CA1728",
                "cabin": "高端经济舱",
                "depart_airport": f"{origin}国际机场",
                "arrive_airport": f"{destination}国际机场",
                "depart_time": f"{depart_date} 18:10",
                "arrive_time": f"{depart_date} 21:15",
                "taxes": 220 * passengers,
                "ticket_price": 1360 * passengers,
                "total_amount": 1580 * passengers,
                "baggage": "23kg 托运行李",
            },
        ]

    def create_hotel_draft(self, payload: dict) -> dict:
        hotel = payload.get("hotel", {})
        criteria = payload.get("criteria", {})
        traveler = payload.get("traveler", {})
        check_in = criteria.get("check_in") or datetime.now().strftime("%Y-%m-%d")
        check_out = criteria.get("check_out") or self._default_checkout(check_in, 1)
        parsed_check_in = self._parse_explicit_date(check_in, "check_in")
        parsed_check_out = self._parse_explicit_date(check_out, "check_out")
        if parsed_check_out <= parsed_check_in:
            raise ValueError("check_out must be after check_in")

        nights = (parsed_check_out - parsed_check_in).days
        self._validate_bounded_integer(
            nights, "nights", self.MIN_NIGHTS, self.MAX_NIGHTS
        )
        rooms = self._bounded_integer(
            criteria, "rooms", self.MIN_ROOMS, self.MAX_ROOMS
        )
        guests = self._bounded_integer(
            criteria, "guests", self.MIN_GUESTS, self.MAX_GUESTS
        )
        room_offer = self._matching_room_offer(
            payload,
            hotel,
            hotel.get("id"),
            check_in,
            check_out,
            rooms,
            guests,
        )

        if room_offer is not None:
            nightly_rate = int(room_offer["nightly_rate"])
            room_subtotal = int(room_offer["room_subtotal"])
            taxes_and_fees = int(room_offer["taxes_and_fees"])
            total_price = int(room_offer["total_price"])
            currency = room_offer.get("currency") or "CNY"
        else:
            nightly_rate = int(hotel.get("nightly_rate") or 688)
            room_subtotal = nightly_rate * nights * rooms
            taxes_and_fees = 0
            total_price = room_subtotal
            currency = "CNY"

        selected_offer = {
            "hotel_id": hotel.get("id"),
            "hotel_name": hotel.get("name", "待确认酒店"),
            "address": hotel.get("address", ""),
            "offer_id": room_offer.get("offer_id") if room_offer else None,
            "room_type": (
                room_offer.get("room_type")
                if room_offer
                else hotel.get("room_type", "高级大床房")
            ),
            "bed_type": (
                deepcopy(room_offer.get("bed_type"))
                if room_offer
                else deepcopy(hotel.get("bed_type"))
            ),
            "breakfast": (
                deepcopy(room_offer.get("breakfast"))
                if room_offer
                else deepcopy(hotel.get("breakfast"))
            ),
            "nightly_rate": nightly_rate,
            "source_provider": (
                room_offer.get("source_provider")
                if room_offer
                else hotel.get("price_source")
            ),
            "cancellation_policy": (
                deepcopy(room_offer.get("cancellation_policy"))
                if room_offer
                else hotel.get(
                    "cancellation_policy",
                    "入住前一天 18:00 前可免费取消",
                )
            ),
        }

        return {
            "status": "draft",
            "source_provider": self.provider_name,
            "provider_trace_id": self._stable_id(hotel.get("id", "hotel"), traveler.get("contact_phone", "trace")),
            "raw_payload_ref": self._stable_id("hotel-raw", hotel.get("id", "hotel")),
            "search_criteria": {
                "city": criteria.get("city"),
                "check_in": check_in,
                "check_out": check_out,
                "rooms": rooms,
                "guests": guests,
                "special_requests": criteria.get("special_requests", ""),
            },
            "selected_offer": selected_offer,
            "pricing_summary": {
                "currency": currency,
                "room_subtotal": room_subtotal,
                "taxes_and_fees": taxes_and_fees,
                "total_price": total_price,
                "room_rate_total": room_subtotal,
                "service_fee": 0,
                "taxes": taxes_and_fees,
                "total_amount": total_price,
            },
            "traveler_snapshot": {
                "contact_name": traveler.get("contact_name", ""),
                "contact_phone": traveler.get("contact_phone", ""),
                "guest_count": guests,
            },
            "confirmation_message": f"已为你生成 {hotel.get('name', '该酒店')} 的待确认订单草稿，确认后可继续支付。",
            "expires_at": (datetime.now() + timedelta(hours=2)).isoformat(timespec="minutes"),
        }

    def create_flight_draft(self, payload: dict) -> dict:
        offer = payload.get("offer", {})
        criteria = payload.get("criteria", {})
        traveler = payload.get("traveler", {})
        passengers = int(criteria.get("passengers") or 1)
        total_amount = int(offer.get("total_amount") or (offer.get("ticket_price", 980) + offer.get("taxes", 180)))

        return {
            "status": "draft",
            "source_provider": self.provider_name,
            "provider_trace_id": self._stable_id(offer.get("id", "flight"), traveler.get("contact_phone", "trace")),
            "raw_payload_ref": self._stable_id("flight-raw", offer.get("id", "flight")),
            "search_criteria": {
                "origin": criteria.get("origin"),
                "destination": criteria.get("destination"),
                "depart_date": criteria.get("depart_date"),
                "return_date": criteria.get("return_date"),
                "passengers": passengers,
            },
            "selected_offer": {
                "offer_id": offer.get("id"),
                "airline": offer.get("airline", "携程联运模拟航班"),
                "flight_no": offer.get("flight_no", "MU5123"),
                "cabin": offer.get("cabin", "经济舱"),
                "depart_time": offer.get("depart_time"),
                "arrive_time": offer.get("arrive_time"),
            },
            "pricing_summary": {
                "currency": "CNY",
                "ticket_amount": int(offer.get("ticket_price", 980 * passengers)),
                "taxes": int(offer.get("taxes", 180 * passengers)),
                "total_amount": total_amount,
            },
            "traveler_snapshot": {
                "contact_name": traveler.get("contact_name", ""),
                "contact_phone": traveler.get("contact_phone", ""),
                "passenger_name": traveler.get("passenger_name", ""),
                "document_type": traveler.get("document_type", ""),
                "document_last4": traveler.get("document_last4", ""),
            },
            "confirmation_message": f"已为你生成 {offer.get('flight_no', '航班')} 的待确认机票草稿，确认后可继续支付。",
            "expires_at": (datetime.now() + timedelta(hours=1)).isoformat(timespec="minutes"),
        }

    def _default_checkout(self, check_in: str, days: int) -> str:
        return (self._parse_date(check_in) + timedelta(days=max(int(days or 1), 1))).strftime("%Y-%m-%d")

    def _parse_date(self, date_str: str) -> datetime:
        return datetime.strptime(date_str, "%Y-%m-%d")

    def _required_text(self, criteria: dict, field: str) -> str:
        value = criteria.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field} is required for room search")
        return value.strip()

    def _parse_explicit_date(self, value, field: str) -> datetime:
        if not isinstance(value, str):
            raise ValueError(f"{field} is required in YYYY-MM-DD format")
        try:
            parsed = datetime.strptime(value, "%Y-%m-%d")
        except ValueError as error:
            raise ValueError(f"{field} must use valid YYYY-MM-DD format") from error
        if parsed.strftime("%Y-%m-%d") != value:
            raise ValueError(f"{field} must use valid YYYY-MM-DD format")
        return parsed

    def _bounded_integer(
        self, criteria: dict, field: str, minimum: int, maximum: int
    ) -> int:
        if field not in criteria:
            return 1
        return self._validate_bounded_integer(
            criteria[field], field, minimum, maximum
        )

    def _validate_bounded_integer(
        self, value, field: str, minimum: int, maximum: int
    ) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(
                f"{field} must be an integer between {minimum} and {maximum}"
            )
        if not minimum <= value <= maximum:
            raise ValueError(f"{field} must be between {minimum} and {maximum}")
        return value

    def _matching_room_offer(
        self,
        payload: dict,
        hotel: dict,
        hotel_id,
        check_in: str,
        check_out: str,
        rooms: int,
        guests: int,
    ) -> dict | None:
        if "room_offer" in payload:
            explicit_offer = payload["room_offer"]
            if not self._room_offer_matches(
                explicit_offer,
                hotel_id,
                check_in,
                check_out,
                rooms,
                guests,
            ):
                raise self._requote_required_error()
            return deepcopy(explicit_offer)

        has_attached_offer_fields = any(
            field in hotel for field in ("selected_room_offer", "room_offers")
        )
        if not has_attached_offer_fields:
            return None

        candidates = []
        if hotel.get("selected_room_offer") is not None:
            candidates.append(hotel["selected_room_offer"])

        room_offers = hotel.get("room_offers") or []
        if isinstance(room_offers, list):
            try:
                candidates.extend(
                    sorted(room_offers, key=lambda offer: offer["nightly_rate"])
                )
            except (KeyError, TypeError, ValueError):
                candidates.extend(room_offers)

        for offer in candidates:
            if self._room_offer_matches(
                offer,
                hotel_id,
                check_in,
                check_out,
                rooms,
                guests,
            ):
                return deepcopy(offer)
        raise self._requote_required_error()

    def _room_offer_matches(
        self,
        offer,
        hotel_id,
        check_in: str,
        check_out: str,
        rooms: int,
        guests: int,
    ) -> bool:
        required_fields = {
            "hotel_id",
            "check_in",
            "check_out",
            "rooms",
            "guests",
            "nightly_rate",
            "room_subtotal",
            "taxes_and_fees",
            "total_price",
        }
        if not isinstance(offer, dict) or not required_fields <= offer.keys():
            return False

        try:
            offer_rooms = self._validate_bounded_integer(
                offer["rooms"], "rooms", self.MIN_ROOMS, self.MAX_ROOMS
            )
            offer_guests = self._validate_bounded_integer(
                offer["guests"], "guests", self.MIN_GUESTS, self.MAX_GUESTS
            )
        except ValueError:
            return False

        return (
            self._same_typed_value(offer["hotel_id"], hotel_id)
            and self._same_typed_value(offer["check_in"], check_in)
            and self._same_typed_value(offer["check_out"], check_out)
            and self._same_typed_value(offer_rooms, rooms)
            and self._same_typed_value(offer_guests, guests)
        )

    @staticmethod
    def _same_typed_value(left, right) -> bool:
        return type(left) is type(right) and left == right

    @staticmethod
    def _requote_required_error() -> ValueError:
        return ValueError(
            "room_offer_requote_required: no room offer matches hotel_id, "
            "check_in, check_out, rooms, and guests; request a new quote"
        )

    def _stable_id(self, *parts: str) -> str:
        canonical_parts = [
            {
                "type": f"{type(part).__module__}.{type(part).__qualname__}",
                "value": str(part),
            }
            for part in parts
        ]
        raw = json.dumps(
            canonical_parts,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
