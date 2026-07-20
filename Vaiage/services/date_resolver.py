import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo


class DateResolver:
    MISSING_VALUES = {"", "none", "not decided", "待定", "未确定"}
    WEEKDAYS = {
        "一": 0,
        "二": 1,
        "三": 2,
        "四": 3,
        "五": 4,
        "六": 5,
        "日": 6,
    }

    def __init__(self, today=None):
        if today is None:
            today = datetime.now(ZoneInfo("Asia/Shanghai")).date()
        elif isinstance(today, datetime):
            today = today.date()
        if not isinstance(today, date):
            raise TypeError("today must be a date object")
        self.today = today

    def resolve(self, value):
        source_text = None if value is None else str(value).strip()
        if source_text is None or source_text.casefold() in self.MISSING_VALUES:
            return self._result("missing", source_text=source_text)

        resolved_date = self._parse(source_text)
        if resolved_date is None:
            return self._result("invalid", source_text=source_text, error="unrecognized_date")
        if resolved_date < self.today:
            return self._result("invalid", source_text=source_text, error="past_date")
        return self._result("resolved", value=resolved_date.isoformat(), source_text=source_text)

    def _parse(self, source_text):
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", source_text):
            try:
                return date.fromisoformat(source_text)
            except ValueError:
                return None

        relative_days = {"今天": 0, "明天": 1, "后天": 2}
        if source_text in relative_days:
            return self.today + timedelta(days=relative_days[source_text])

        next_week_match = re.fullmatch(r"下周([一二三四五六日])", source_text)
        if next_week_match:
            next_monday = self.today + timedelta(days=7 - self.today.weekday())
            return next_monday + timedelta(days=self.WEEKDAYS[next_week_match.group(1)])

        if source_text == "今年国庆":
            return date(self.today.year, 10, 1)
        if source_text == "明年国庆":
            return date(self.today.year + 1, 10, 1)
        return None

    @staticmethod
    def _result(status, value=None, source_text=None, error=None):
        return {
            "status": status,
            "value": value,
            "source_text": source_text,
            "error": error,
        }
