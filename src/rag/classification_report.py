"""Epic J2: visibility into classification quality -- how much of the current catalogue
was classified by the cheap keyword heuristic vs. the LLM tier vs. a manual override vs.
left as a genuinely uncertain "unknown", plus which specific products are excluded most
often and which were corrected by a manual override -- so the team maintaining the
classifier knows exactly where it needs tuning instead of guessing.

Deliberately reads the *current* discounts snapshot rather than the permanent
product_classifications cache alone: that cache only ever stores an "llm" or
"manual_override" row (see refresh_discounts.py -- the keyword heuristic is cheap
enough to recompute inline and is never itself cached), so a product_name with no
cache row was necessarily classified by the heuristic. "Frequency" for the two
most-frequent lists below means how often that product currently shows up across all
stores' offers, not how many times it's ever been reclassified -- there's no
reclassification history kept, only the current winning classification (see Epic A4).
"""

from collections import Counter
from typing import Any, Dict, List

# Epic A3/product_classification.py: the LLM path collapses genuine uncertainty to
# food_usage_class="unknown" (recipe_exclusion_reason="insufficient_confidence");
# the heuristic and manual overrides never produce this outcome, so it's always
# attributable to the LLM tier specifically.
_UNKNOWN_EXCLUSION_REASON = "insufficient_confidence"

_TOP_N = 10


def build_classification_quality_report(
    discounts: List[Dict[str, Any]], classification_sources: Dict[str, str],
) -> Dict[str, Any]:
    """`discounts` is the current cached snapshot (get_latest_snapshot()'s first
    return value); `classification_sources` is product_name -> "llm"/"manual_override"
    for whichever of those names have a product_classifications row (see
    discounts_store.get_classification_sources()) -- a name absent from it was
    classified by the heuristic.

    Percentages are computed over unique product names in the current snapshot, not
    over every row -- the same product discounted at three stores should count once,
    not three times, when asking "what fraction of the catalogue was LLM-classified."
    The two "most frequent" lists below are the opposite: they deliberately count every
    row, since a product currently on offer at more stores is more visible/impactful to
    get wrong.
    """
    unique_products: Dict[str, Dict[str, Any]] = {}
    for row in discounts:
        name = row.get("product_name")
        if name and name not in unique_products:
            unique_products[name] = row

    total = len(unique_products)
    source_counts = Counter(
        classification_sources.get(name, "heuristic") for name in unique_products
    )
    unknown_count = sum(
        1 for row in unique_products.values() if row.get("recipe_exclusion_reason") == _UNKNOWN_EXCLUSION_REASON
    )

    def pct(count: int) -> float:
        return round(100 * count / total, 1) if total else 0.0

    excluded_counts = Counter(
        row["product_name"] for row in discounts
        if row.get("product_name") and not row.get("recipe_eligible")
    )
    reason_by_name = {
        name: row.get("recipe_exclusion_reason")
        for name, row in unique_products.items()
    }
    most_frequently_excluded = [
        {"product_name": name, "count": count, "recipe_exclusion_reason": reason_by_name.get(name)}
        for name, count in excluded_counts.most_common(_TOP_N)
    ]

    corrected_names = {
        name for name, source in classification_sources.items()
        if source == "manual_override" and name in unique_products
    }
    corrected_counts = Counter(
        row["product_name"] for row in discounts if row.get("product_name") in corrected_names
    )
    most_frequently_corrected = [
        {"product_name": name, "count": count}
        for name, count in corrected_counts.most_common(_TOP_N)
    ]

    return {
        "total_unique_products": total,
        "classified_by_heuristic_pct": pct(source_counts.get("heuristic", 0)),
        "classified_by_llm_pct": pct(source_counts.get("llm", 0)),
        "classified_by_manual_override_pct": pct(source_counts.get("manual_override", 0)),
        "left_unknown_pct": pct(unknown_count),
        "most_frequently_excluded_products": most_frequently_excluded,
        "most_frequently_corrected_products": most_frequently_corrected,
    }
