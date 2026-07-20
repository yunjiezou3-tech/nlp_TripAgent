import copy
import re
from decimal import Decimal


class PlaceCandidateEnricher:
    INT64_MIN = -(2**63)
    INT64_MAX = 2**63 - 1
    PRICE_LEVEL_ESTIMATES = {
        0: ("参考人均 ¥20-40（估算）", "经济"),
        1: ("参考人均 ¥40-80（估算）", "经济"),
        2: ("参考人均 ¥80-160（估算）", "中等"),
        3: ("参考人均 ¥160-300（估算）", "较高"),
        4: ("参考人均 ¥300-600（估算）", "较高"),
    }

    def __init__(self, price_range_loader=None):
        self.price_range_loader = price_range_loader

    @staticmethod
    def _parse_integer(
        value, default=None, minimum=None, maximum=None, allow_string=True
    ):
        if value is None:
            return default
        if isinstance(value, bool):
            return None
        if isinstance(value, int):
            parsed = value
        elif allow_string and isinstance(value, str) and re.fullmatch(r"[+-]?\d+", value.strip()):
            try:
                parsed = int(value)
            except ValueError:
                return None
        else:
            return None
        if minimum is not None and parsed < minimum:
            return None
        if maximum is not None and parsed > maximum:
            return None
        return parsed

    @classmethod
    def _parse_money(cls, money):
        if not isinstance(money, dict):
            return None
        currency = money.get("currencyCode")
        if not isinstance(currency, str) or not re.fullmatch(r"[A-Za-z]{3}", currency.strip()):
            return None

        units = cls._parse_integer(
            money.get("units"),
            default=0,
            minimum=cls.INT64_MIN,
            maximum=cls.INT64_MAX,
        )
        nanos = cls._parse_integer(
            money.get("nanos"),
            default=0,
            minimum=-999_999_999,
            maximum=999_999_999,
            allow_string=False,
        )
        if units is None or nanos is None:
            return None
        if (units > 0 and nanos < 0) or (units < 0 and nanos > 0):
            return None

        amount = Decimal(units) + Decimal(nanos) / Decimal(1_000_000_000)
        return currency.strip().upper(), amount

    @classmethod
    def _parse_price_range(cls, price_range):
        if not isinstance(price_range, dict):
            return None
        start = cls._parse_money(price_range.get("startPrice"))
        end = cls._parse_money(price_range.get("endPrice"))
        if not start or not end:
            return None
        start_currency, start_amount = start
        end_currency, end_amount = end
        if (
            start_currency != end_currency
            or start_amount < 0
            or end_amount < 0
            or start_amount > end_amount
        ):
            return None
        return start_currency, start_amount, end_amount

    @staticmethod
    def _format_amount(amount):
        return format(amount.normalize(), "f")

    def enrich_restaurant(self, candidate):
        enriched = copy.deepcopy(candidate)
        price_range = None
        place_id = candidate.get("id")
        if callable(self.price_range_loader) and place_id:
            try:
                price_range = self.price_range_loader(place_id)
            except Exception:
                price_range = None

        parsed_range = self._parse_price_range(price_range)
        if parsed_range:
            currency, start, end = parsed_range
            currency_display = "¥" if currency == "CNY" else f"{currency} "
            enriched["price_display"] = (
                f"Google 价格区间 {currency_display}{self._format_amount(start)}-"
                f"{self._format_amount(end)}"
            )
            enriched["price_source"] = "google_price_range"
            price_level = candidate.get("price_level")
            estimate = None
            if isinstance(price_level, int) and not isinstance(price_level, bool):
                estimate = self.PRICE_LEVEL_ESTIMATES.get(price_level)
            enriched["price_tier"] = estimate[1] if estimate else None
            return enriched

        price_level = candidate.get("price_level")
        if isinstance(price_level, int) and not isinstance(price_level, bool):
            estimate = self.PRICE_LEVEL_ESTIMATES.get(price_level)
            if estimate:
                enriched["price_display"], enriched["price_tier"] = estimate
                enriched["price_source"] = "price_level_estimate"
                return enriched

        enriched["price_display"] = "价格待确认"
        enriched["price_source"] = "unavailable"
        enriched["price_tier"] = None
        return enriched

    def enrich_restaurants(self, candidates):
        return [self.enrich_restaurant(candidate) for candidate in candidates]
