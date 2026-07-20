import copy
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MODULE_SPEC = importlib.util.spec_from_file_location(
    "services.information_refinement", ROOT / "services/information_refinement.py"
)
MODULE = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC.loader is not None
MODULE_SPEC.loader.exec_module(MODULE)
InformationRefinementService = MODULE.InformationRefinementService


def expected_result(
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


@pytest.mark.parametrize("phrase", ["确认", "就选这些", "生成行程", "开始规划"])
def test_parse_recognizes_confirmation_phrases(phrase):
    result = InformationRefinementService().parse(f"好的，{phrase}")

    assert result == expected_result("confirm_selection", f"好的，{phrase}")


@pytest.mark.parametrize(
    "query",
    [
        "我想修改偏好",
        "重新填写偏好",
        "目的地改成杭州",
        "预算改为经济型",
        "住宿偏好改成含早餐",
    ],
)
def test_parse_recognizes_long_term_preference_corrections(query):
    result = InformationRefinementService().parse(query)

    assert result == expected_result("update_preferences", query)


@pytest.mark.parametrize(
    "query",
    [
        "更多景点",
        "再推荐景点",
        "再来一些景点",
        "换一批景点",
        "对这些景点不满意",
        "景点还有吗",
    ],
)
def test_parse_recognizes_each_more_request_phrase(query):
    result = InformationRefinementService().parse(query)

    assert result["intent"] == "more_candidates"
    assert result["categories"] == ["attractions"]


@pytest.mark.parametrize(
    ("alias", "category"),
    [
        ("景点", "attractions"),
        ("景区", "attractions"),
        ("博物馆", "attractions"),
        ("玩的地方", "attractions"),
        ("去处", "attractions"),
        ("餐厅", "restaurants"),
        ("饭店", "restaurants"),
        ("餐馆", "restaurants"),
        ("美食", "restaurants"),
        ("吃饭", "restaurants"),
        ("酒店", "hotels"),
        ("住宿", "hotels"),
        ("民宿", "hotels"),
        ("住的地方", "hotels"),
    ],
)
def test_parse_maps_category_aliases_to_canonical_values(alias, category):
    result = InformationRefinementService().parse(f"再推荐一些{alias}")

    assert result["intent"] == "more_candidates"
    assert result["categories"] == [category]


def test_parse_returns_multiple_categories_in_stable_canonical_order():
    result = InformationRefinementService().parse("再推荐酒店、餐厅和景点")

    assert result["intent"] == "more_candidates"
    assert result["categories"] == ["attractions", "restaurants", "hotels"]


@pytest.mark.parametrize("query", ["更多", "再来点别的", "还有吗"])
def test_parse_requests_category_clarification_without_filters(query):
    result = InformationRefinementService().parse(query)

    assert result == expected_result(
        "clarify_category",
        query,
        clarification_message="请问你想看更多景点、餐厅还是住宿？",
    )


@pytest.mark.parametrize("price_phrase", ["便宜一点", "经济型"])
def test_parse_extracts_economic_price_filter(price_phrase):
    result = InformationRefinementService().parse(f"再推荐{price_phrase}的酒店")

    assert result["transient_filters"] == {"max_price_level": 1}


@pytest.mark.parametrize("price_phrase", ["中等价位", "中档"])
def test_parse_extracts_medium_price_filter(price_phrase):
    result = InformationRefinementService().parse(f"再推荐{price_phrase}的餐厅")

    assert result["transient_filters"] == {"price_level": 2}


@pytest.mark.parametrize(
    ("rating_phrase", "expected_rating"),
    [
        ("高评分", 4.5),
        ("评分0以上", 0.0),
        ("评分4.5以上", 4.5),
        ("4.7分以上", 4.7),
        ("评分5以上", 5.0),
    ],
)
def test_parse_extracts_rating_filter(rating_phrase, expected_rating):
    result = InformationRefinementService().parse(f"再推荐{rating_phrase}的景点")

    assert result["transient_filters"] == {"min_rating": expected_rating}


@pytest.mark.parametrize(
    "invalid_rating",
    [
        "-1以上",
        "5.1以上",
        "6.5以上",
        "14.5以上",
        "4.5.0以上",
        "..4.5以上",
        "++4.5以上",
        "5e0以上",
    ],
)
def test_parse_rejects_invalid_complete_rating_tokens_without_losing_other_filters(
    invalid_rating,
):
    result = InformationRefinementService().parse(
        f"再推荐评分{invalid_rating}、含早餐的酒店"
    )

    assert result["transient_filters"] == {"amenities": ["含早餐"]}


@pytest.mark.parametrize("family_phrase", ["亲子", "带孩子"])
def test_parse_extracts_family_friendly_filter(family_phrase):
    result = InformationRefinementService().parse(f"再推荐适合{family_phrase}的景点")

    assert result["transient_filters"] == {"family_friendly": True}


@pytest.mark.parametrize("transit_phrase", ["近地铁", "交通方便"])
def test_parse_extracts_near_transit_filter(transit_phrase):
    result = InformationRefinementService().parse(f"再推荐{transit_phrase}的酒店")

    assert result["transient_filters"] == {"near_transit": True}


def test_parse_preserves_amenities_in_mention_order():
    result = InformationRefinementService().parse(
        "再推荐有健身房、含早餐、吧台和洗衣机的酒店"
    )

    assert result["transient_filters"] == {
        "amenities": ["健身房", "含早餐", "吧台", "洗衣机"]
    }


def test_parse_deduplicates_repeated_amenities_without_changing_order():
    result = InformationRefinementService().parse(
        "再推荐含早餐、健身房、含早餐、洗衣房和健身房的酒店"
    )

    assert result["transient_filters"] == {
        "amenities": ["含早餐", "健身房", "洗衣房"]
    }


def test_parse_preserves_amenity_order_across_multiple_positive_request_clauses():
    result = InformationRefinementService().parse(
        "换一批含早餐的酒店，再推荐有健身房和吧台的酒店"
    )

    assert result["transient_filters"] == {
        "amenities": ["含早餐", "健身房", "吧台"]
    }


@pytest.mark.parametrize("keyword", ["博物馆", "公园", "夜景", "本地美食"])
def test_parse_extracts_meaningful_request_keyword(keyword):
    category = "餐厅" if keyword == "本地美食" else "景点"
    result = InformationRefinementService().parse(f"再推荐一些适合{keyword}的{category}")

    assert result["transient_filters"]["keyword"] == keyword


@pytest.mark.parametrize(
    ("query", "category", "keyword"),
    [
        ("再推荐博物馆", "attractions", "博物馆"),
        ("再推荐本地美食", "restaurants", "本地美食"),
    ],
)
def test_category_alias_and_keyword_overlap_keeps_both_meanings(
    query, category, keyword
):
    result = InformationRefinementService().parse(query)

    assert result["categories"] == [category]
    assert result["transient_filters"] == {"keyword": keyword}


def test_parse_combines_independent_transient_filters():
    result = InformationRefinementService().parse(
        "再推荐近地铁、适合亲子、高评分、经济型、含早餐和健身房、能看夜景的酒店"
    )

    assert result == expected_result(
        "more_candidates",
        "再推荐近地铁、适合亲子、高评分、经济型、含早餐和健身房、能看夜景的酒店",
        categories=["hotels"],
        transient_filters={
            "max_price_level": 1,
            "min_rating": 4.5,
            "family_friendly": True,
            "near_transit": True,
            "amenities": ["含早餐", "健身房"],
            "keyword": "夜景",
        },
    )


@pytest.mark.parametrize(
    ("query", "categories", "transient_filters"),
    [
        (
            "再推荐一些酒店，最好含早餐",
            ["hotels"],
            {"amenities": ["含早餐"]},
        ),
        ("再推荐一些，酒店就行", ["hotels"], {}),
        (
            "再推荐餐厅，便宜一点，适合带孩子",
            ["restaurants"],
            {"max_price_level": 1, "family_friendly": True},
        ),
        (
            "最好近地铁，再推荐一些酒店",
            ["hotels"],
            {"near_transit": True},
        ),
    ],
)
def test_parse_attaches_recognized_details_from_neighboring_clauses(
    query, categories, transient_filters
):
    result = InformationRefinementService().parse(query)

    assert result == expected_result(
        "more_candidates",
        query,
        categories=categories,
        transient_filters=transient_filters,
    )


@pytest.mark.parametrize(
    "query",
    [
        "再推荐一些酒店，今天天气不错，最好含早餐",
        "最好近地铁，今天天气不错，再推荐一些酒店",
    ],
)
def test_unrelated_adjacent_chatter_blocks_detail_attachment(query):
    result = InformationRefinementService().parse(query)

    assert result == expected_result(
        "more_candidates", query, categories=["hotels"]
    )


@pytest.mark.parametrize(
    "query",
    [
        "不要再推荐含早餐的酒店，再推荐景点",
        "再推荐景点，不要再推荐含早餐的酒店",
    ],
)
def test_negated_more_clause_is_never_attached_as_request_detail(query):
    result = InformationRefinementService().parse(query)

    assert result == expected_result(
        "more_candidates", query, categories=["attractions"]
    )


def test_confirmation_takes_precedence_over_more_request_and_filters():
    query = "不用更多了，就选这些含早餐的酒店，生成行程"

    result = InformationRefinementService().parse(query)

    assert result == expected_result("confirm_selection", query)


def test_explicit_preference_update_takes_precedence_over_incidental_confirmation():
    query = "确认目的地改成杭州"

    result = InformationRefinementService().parse(query)

    assert result == expected_result("update_preferences", query)


@pytest.mark.parametrize("query", ["不确认", "先不确认", "不要确认"])
def test_negated_confirmation_does_not_confirm_selection(query):
    result = InformationRefinementService().parse(query)

    assert result == expected_result("unknown", query)


@pytest.mark.parametrize(
    ("query", "category"),
    [
        ("先不确认，再推荐一些酒店", "hotels"),
        ("不要确认，换一批景点", "attractions"),
    ],
)
def test_negated_confirmation_allows_a_later_positive_more_request(query, category):
    result = InformationRefinementService().parse(query)

    assert result["intent"] == "more_candidates"
    assert result["categories"] == [category]


@pytest.mark.parametrize(
    "query", ["不要再推荐住宿了", "别换一批", "不需要更多"]
)
def test_negated_more_action_does_not_request_candidates(query):
    result = InformationRefinementService().parse(query)

    assert result == expected_result("unknown", query)


def test_separate_positive_more_action_ignores_negated_action_category():
    query = "不要再推荐住宿了，换一批景点"

    result = InformationRefinementService().parse(query)

    assert result == expected_result(
        "more_candidates", query, categories=["attractions"]
    )


def test_preference_update_takes_precedence_over_more_request_and_filters():
    query = "这些酒店不满意，住宿偏好改成含早餐"

    result = InformationRefinementService().parse(query)

    assert result == expected_result("update_preferences", query)


def test_category_words_without_more_request_are_not_treated_as_search_intent():
    query = "景点和餐厅哪个更适合雨天？"

    result = InformationRefinementService().parse(query)

    assert result == expected_result("unknown", query)


@pytest.mark.parametrize(
    "query", ["更多去处", "推荐几个去处", "推荐几个好去处", "好去处还有吗"]
)
def test_clear_user_facing_destination_alias_contexts_remain_supported(query):
    result = InformationRefinementService().parse(query)

    assert result["intent"] == "more_candidates"
    assert result["categories"] == ["attractions"]


def test_destination_alias_does_not_match_the_unrelated_word_quchuli():
    query = "再推荐我去处理的酒店"

    result = InformationRefinementService().parse(query)

    assert result["categories"] == ["hotels"]


def test_destination_alias_does_not_supply_category_from_quchuli():
    query = "还有吗？我稍后去处理"

    result = InformationRefinementService().parse(query)

    assert result == expected_result(
        "clarify_category",
        query,
        clarification_message="请问你想看更多景点、餐厅还是住宿？",
    )


@pytest.mark.parametrize(
    "query", ["更多去处理一下", "推荐几个去处理方案", "更多去处罚款方案"]
)
def test_destination_alias_never_matches_prefixes_of_unrelated_words(query):
    result = InformationRefinementService().parse(query)

    assert result == expected_result(
        "clarify_category",
        query,
        clarification_message="请问你想看更多景点、餐厅还是住宿？",
    )


@pytest.mark.parametrize("query", [None, "", "   ", "你好", "今天天气怎么样"])
def test_parse_returns_unknown_for_empty_or_unrelated_chat(query):
    result = InformationRefinementService().parse(query)

    assert result == expected_result("unknown", "" if query is None else query.strip())


@pytest.mark.parametrize(
    "query", [["再推荐酒店"], {"query": "再推荐酒店"}, 123, 4.5, True, False]
)
def test_parse_rejects_non_string_inputs_without_stringifying_them(query):
    result = InformationRefinementService().parse(query)

    assert result == expected_result("unknown", "")


def test_parse_trims_raw_query_without_other_normalization():
    result = InformationRefinementService().parse("  再推荐景点  ")

    assert result["raw_query"] == "再推荐景点"


def test_repeated_calls_do_not_retain_categories_or_filters():
    service = InformationRefinementService()

    first = service.parse("再推荐高评分、含早餐的酒店")
    second = service.parse("再推荐景点")

    assert first["categories"] == ["hotels"]
    assert first["transient_filters"] == {
        "min_rating": 4.5,
        "amenities": ["含早餐"],
    }
    assert second == expected_result(
        "more_candidates",
        "再推荐景点",
        categories=["attractions"],
    )


def test_parse_is_deterministic_for_repeated_identical_queries():
    service = InformationRefinementService()
    query = "再推荐交通方便、4.5以上的酒店"

    assert service.parse(query) == service.parse(query)


def test_parse_does_not_mutate_rejected_mutable_input():
    service = InformationRefinementService()
    query = ["再推荐酒店", {"filters": ["含早餐"]}]
    original = copy.deepcopy(query)

    service.parse(query)

    assert query == original


def test_mutating_a_result_does_not_affect_later_calls():
    service = InformationRefinementService()
    query = "再推荐含早餐的酒店"
    first = service.parse(query)

    first["categories"].append("attractions")
    first["transient_filters"]["amenities"].append("健身房")

    assert service.parse(query) == expected_result(
        "more_candidates",
        query,
        categories=["hotels"],
        transient_filters={"amenities": ["含早餐"]},
    )
