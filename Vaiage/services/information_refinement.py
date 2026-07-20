import re


class InformationRefinementService:
    CLARIFICATION_MESSAGE = "请问你想看更多景点、餐厅还是住宿？"

    CONFIRMATION_PHRASES = ("确认", "就选这些", "生成行程", "开始规划")
    UPDATE_PREFERENCE_PHRASES = (
        "修改偏好",
        "重新填写偏好",
        "目的地改成",
        "目的地改为",
        "预算改成",
        "预算改为",
        "住宿偏好改成",
        "住宿偏好改为",
    )
    MORE_PHRASES = (
        "更多",
        "再推荐",
        "推荐几个",
        "再来",
        "换一批",
        "不满意",
        "还有吗",
    )

    CATEGORY_ALIASES = (
        ("attractions", ("景点", "景区", "博物馆", "玩的地方")),
        ("restaurants", ("餐厅", "饭店", "餐馆", "美食", "吃饭")),
        ("hotels", ("酒店", "住宿", "民宿", "住的地方")),
    )

    ECONOMIC_PHRASES = ("便宜", "经济", "实惠", "低价", "cheap", "economic")
    MEDIUM_PRICE_PHRASES = ("中等", "中档", "适中", "medium")
    FAMILY_PHRASES = ("亲子", "带孩子")
    TRANSIT_PHRASES = ("近地铁", "交通方便")
    AMENITY_PHRASES = ("含早餐", "洗衣房", "洗衣机", "健身房", "吧台")
    KEYWORD_PHRASES = (
        "博物馆",
        "公园",
        "夜景",
        "本地美食",
        "历史文化",
        "自然风光",
        "当地特色",
        "夜市",
        "海鲜",
        "购物",
        "徒步",
    )
    CLEAR_DESTINATION_PATTERN = re.compile(
        r"去处(?=$|还有吗|[，,。；;！？!?？、呢吧啊和或])"
    )
    RATING_CANDIDATE_PATTERN = re.compile(
        r"(?<![A-Za-z0-9_+\-.])([+-]?[\d.]+)(?![A-Za-z0-9_+\-.])"
        r"\s*分?\s*(?:以上|及以上)"
    )
    COMPLETE_NUMBER_PATTERN = re.compile(r"[+-]?\d+(?:\.\d+)?")
    NEGATION_PREFIX_PATTERN = re.compile(
        r"(?:先不|不要|别|不需要|不用|无需|不想要?|暂不|暂时不|还不|不)(?:再)?\s*$"
    )
    CLAUSE_SEPARATOR_PATTERN = re.compile(r"[，,。；;！？!?？\n]")

    def parse(self, query):
        if not isinstance(query, str):
            return self._result("unknown", "")

        raw_query = query.strip()
        if not raw_query:
            return self._result("unknown", raw_query)

        if self._has_positive_phrase(raw_query, self.UPDATE_PREFERENCE_PHRASES):
            return self._result("update_preferences", raw_query)

        if self._has_positive_phrase(raw_query, self.CONFIRMATION_PHRASES):
            return self._result("confirm_selection", raw_query)

        active_more_query = self._active_more_query(raw_query)
        if not active_more_query:
            return self._result("unknown", raw_query)

        categories = self._extract_categories(active_more_query)
        if not categories:
            return self._result(
                "clarify_category",
                raw_query,
                clarification_message=self.CLARIFICATION_MESSAGE,
            )

        return self._result(
            "more_candidates",
            raw_query,
            categories=categories,
            transient_filters=self._extract_transient_filters(active_more_query),
        )

    def _extract_categories(self, query):
        categories = []
        for category, aliases in self.CATEGORY_ALIASES:
            matched = self._contains_any(query, aliases)
            if category == "attractions":
                matched = matched or bool(self.CLEAR_DESTINATION_PATTERN.search(query))
            if matched:
                categories.append(category)
        return categories

    def _extract_transient_filters(self, query):
        filters = {}
        normalized_query = query.casefold()

        if self._contains_any(normalized_query, self.ECONOMIC_PHRASES):
            filters["max_price_level"] = 1
        elif self._contains_any(normalized_query, self.MEDIUM_PRICE_PHRASES):
            filters["price_level"] = 2

        rating_candidates = self.RATING_CANDIDATE_PATTERN.findall(query)
        valid_ratings = []
        invalid_rating = False
        for candidate in rating_candidates:
            if not self.COMPLETE_NUMBER_PATTERN.fullmatch(candidate):
                invalid_rating = True
                continue
            rating = float(candidate)
            if 0 <= rating <= 5:
                valid_ratings.append(rating)
            else:
                invalid_rating = True

        if valid_ratings and not invalid_rating:
            filters["min_rating"] = valid_ratings[0]
        elif not rating_candidates and "高评分" in query:
            filters["min_rating"] = 4.5

        if self._contains_any(query, self.FAMILY_PHRASES):
            filters["family_friendly"] = True
        if self._contains_any(query, self.TRANSIT_PHRASES):
            filters["near_transit"] = True

        amenities = self._extract_in_mention_order(query, self.AMENITY_PHRASES)
        if amenities:
            filters["amenities"] = amenities

        keywords = self._extract_in_mention_order(query, self.KEYWORD_PHRASES)
        if keywords:
            filters["keyword"] = keywords[0]

        return filters

    @staticmethod
    def _contains_any(query, phrases):
        return any(phrase in query for phrase in phrases)

    @classmethod
    def _has_positive_phrase(cls, query, phrases):
        return any(
            not cls._is_negated(query, match.start())
            for phrase in phrases
            for match in re.finditer(re.escape(phrase), query)
        )

    def _active_more_query(self, query):
        clauses = [
            clause.strip()
            for clause in self.CLAUSE_SEPARATOR_PATTERN.split(query)
            if clause.strip()
        ]
        action_indices = {
            index
            for index, clause in enumerate(clauses)
            if self._has_positive_phrase(clause, self.MORE_PHRASES)
        }
        if not action_indices:
            return ""

        selected_indices = set(action_indices)
        for action_index in action_indices:
            for direction in (-1, 1):
                neighbor_index = action_index + direction
                while 0 <= neighbor_index < len(clauses):
                    if neighbor_index in action_indices:
                        break
                    if not self._is_attached_detail_clause(clauses[neighbor_index]):
                        break
                    selected_indices.add(neighbor_index)
                    neighbor_index += direction

        return "，".join(clauses[index] for index in sorted(selected_indices))

    def _is_attached_detail_clause(self, clause):
        if self._contains_any(
            clause, self.CONFIRMATION_PHRASES + self.UPDATE_PREFERENCE_PHRASES
        ):
            return False
        if self._has_negated_phrase(clause, self.MORE_PHRASES):
            return False
        return bool(
            self._extract_categories(clause)
            or self._extract_transient_filters(clause)
        )

    @classmethod
    def _is_negated(cls, query, phrase_start):
        return bool(cls.NEGATION_PREFIX_PATTERN.search(query[:phrase_start]))

    @classmethod
    def _has_negated_phrase(cls, query, phrases):
        return any(
            cls._is_negated(query, match.start())
            for phrase in phrases
            for match in re.finditer(re.escape(phrase), query)
        )

    @staticmethod
    def _extract_in_mention_order(query, phrases):
        mentions = []
        for phrase_order, phrase in enumerate(phrases):
            mentions.extend(
                (match.start(), phrase_order, phrase)
                for match in re.finditer(re.escape(phrase), query)
            )

        ordered_unique = []
        for _, _, phrase in sorted(mentions):
            if phrase not in ordered_unique:
                ordered_unique.append(phrase)
        return ordered_unique

    @staticmethod
    def _result(
        intent,
        raw_query,
        categories=None,
        transient_filters=None,
        clarification_message=None,
    ):
        return {
            "intent": intent,
            "categories": categories or [],
            "transient_filters": transient_filters or {},
            "raw_query": raw_query,
            "clarification_message": clarification_message,
        }
