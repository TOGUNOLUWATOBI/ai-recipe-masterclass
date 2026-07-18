"""Tests for classification_report.py -- Epic J2's classification-quality visibility."""

from rag.classification_report import build_classification_quality_report


def _row(product_name, store_name="Kiwi", recipe_eligible=True, recipe_exclusion_reason=None):
    return {
        "product_name": product_name,
        "store_name": store_name,
        "recipe_eligible": recipe_eligible,
        "recipe_exclusion_reason": recipe_exclusion_reason,
    }


def test_empty_snapshot_reports_zero_everything():
    report = build_classification_quality_report([], {})

    assert report["total_unique_products"] == 0
    assert report["classified_by_heuristic_pct"] == 0.0
    assert report["classified_by_llm_pct"] == 0.0
    assert report["classified_by_manual_override_pct"] == 0.0
    assert report["left_unknown_pct"] == 0.0
    assert report["most_frequently_excluded_products"] == []
    assert report["most_frequently_corrected_products"] == []


def test_a_product_with_no_cached_classification_source_counts_as_heuristic():
    discounts = [_row("POTETER")]

    report = build_classification_quality_report(discounts, classification_sources={})

    assert report["total_unique_products"] == 1
    assert report["classified_by_heuristic_pct"] == 100.0
    assert report["classified_by_llm_pct"] == 0.0


def test_percentages_split_across_all_three_sources():
    discounts = [_row("POTETER"), _row("KYLLINGFILET"), _row("COCA-COLA ZERO", recipe_eligible=False)]
    sources = {"KYLLINGFILET": "llm", "COCA-COLA ZERO": "manual_override"}

    report = build_classification_quality_report(discounts, sources)

    assert report["total_unique_products"] == 3
    assert report["classified_by_heuristic_pct"] == round(100 / 3, 1)
    assert report["classified_by_llm_pct"] == round(100 / 3, 1)
    assert report["classified_by_manual_override_pct"] == round(100 / 3, 1)


def test_left_unknown_pct_counts_the_insufficient_confidence_exclusion_reason():
    discounts = [
        _row("MYSTERY ITEM", recipe_eligible=False, recipe_exclusion_reason="insufficient_confidence"),
        _row("POTETER"),
    ]

    report = build_classification_quality_report(discounts, classification_sources={})

    assert report["left_unknown_pct"] == 50.0


def test_duplicate_product_name_across_stores_counts_once_toward_total_but_not_the_frequency_lists():
    """The percentage denominator is unique products (a product on offer at three
    stores shouldn't inflate "what fraction of the catalogue is LLM-classified"), but
    the two most-frequent lists deliberately count every row -- see the module
    docstring."""
    discounts = [
        _row("COCA-COLA ZERO", store_name="Kiwi", recipe_eligible=False, recipe_exclusion_reason="beverage"),
        _row("COCA-COLA ZERO", store_name="Meny", recipe_eligible=False, recipe_exclusion_reason="beverage"),
        _row("POTETER", store_name="Kiwi"),
    ]

    report = build_classification_quality_report(discounts, classification_sources={})

    assert report["total_unique_products"] == 2
    assert report["most_frequently_excluded_products"][0] == {
        "product_name": "COCA-COLA ZERO", "count": 2, "recipe_exclusion_reason": "beverage",
    }


def test_most_frequently_excluded_products_ranks_by_count_descending():
    discounts = [
        _row("A", store_name="Kiwi", recipe_eligible=False, recipe_exclusion_reason="beverage"),
        _row("B", store_name="Kiwi", recipe_eligible=False, recipe_exclusion_reason="snack_or_treat"),
        _row("B", store_name="Meny", recipe_eligible=False, recipe_exclusion_reason="snack_or_treat"),
        _row("B", store_name="Rema", recipe_eligible=False, recipe_exclusion_reason="snack_or_treat"),
    ]

    report = build_classification_quality_report(discounts, classification_sources={})

    names_in_order = [entry["product_name"] for entry in report["most_frequently_excluded_products"]]
    assert names_in_order == ["B", "A"]


def test_most_frequently_excluded_products_never_includes_an_eligible_product():
    discounts = [_row("POTETER")]

    report = build_classification_quality_report(discounts, classification_sources={})

    assert report["most_frequently_excluded_products"] == []


def test_most_frequently_corrected_products_only_includes_manual_overrides():
    discounts = [
        _row("COCA-COLA ZERO", store_name="Kiwi", recipe_eligible=False, recipe_exclusion_reason="beverage"),
        _row("COCA-COLA ZERO", store_name="Meny", recipe_eligible=False, recipe_exclusion_reason="beverage"),
        _row("MYSTERY ITEM", recipe_eligible=False, recipe_exclusion_reason="insufficient_confidence"),
    ]
    sources = {"COCA-COLA ZERO": "manual_override", "MYSTERY ITEM": "llm"}

    report = build_classification_quality_report(discounts, sources)

    assert report["most_frequently_corrected_products"] == [{"product_name": "COCA-COLA ZERO", "count": 2}]


def test_most_frequent_lists_are_capped_at_ten():
    discounts = [_row(f"ITEM {i}", recipe_eligible=False, recipe_exclusion_reason="other") for i in range(15)]

    report = build_classification_quality_report(discounts, classification_sources={})

    assert len(report["most_frequently_excluded_products"]) == 10
