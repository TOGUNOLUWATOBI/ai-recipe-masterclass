"""Tests for grocery_discounts.py's pure logic and client wiring, using mocked HTTP
responses — no real Kassalapp API key needed. The response shapes and category names
mocked here match what a live call actually returned (verified 2026-07-06), not just
Kassalapp's documentation — see the module docstring for what was only caught this way:
nested price_history instead of a flat price field, free-text search being unreliable
for this domain (baby food/deli noise), and the category taxonomy that fixes it for
most tracked ingredients."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from rag.grocery_discounts import (
    KassalappClient,
    _extract_reference_price,
    _is_baby_food,
    _name_matches_term,
    _percent_below,
    _select_representative_product,
    find_discounted_ingredients,
    get_norwegian_term,
)


@pytest.fixture(autouse=True)
def no_real_sleep():
    """find_discounted_ingredients() paces real Kassalapp calls with time.sleep(0.3) to
    avoid rate limiting — harmless in production, but would needlessly slow down every
    test in this file (mocked calls don't need pacing) without this patched out."""
    with patch("rag.grocery_discounts.time.sleep"):
        yield


_STUB_TRANSLATIONS = {"chicken": "kylling", "salmon": "laks", "garlic": "hvitløk"}


@pytest.fixture(autouse=True)
def stub_translation():
    """find_discounted_ingredients() now calls get_norwegian_term() for every
    ingredient (even category-based ones, to disambiguate within the category — see the
    module docstring), so it must not hit the real translation API from these tests.
    Doesn't affect the two tests that exercise get_norwegian_term() directly — they
    import the real function by name, unaffected by patching the module's attribute."""
    with patch("rag.grocery_discounts.get_norwegian_term", side_effect=lambda en: _STUB_TRANSLATIONS[en]):
        yield


def test_percent_below_computes_discount_correctly():
    assert _percent_below(current=80, reference=100) == 20.0


def test_percent_below_returns_zero_for_price_increase():
    assert _percent_below(current=120, reference=100) == 0.0


def test_percent_below_handles_zero_reference_without_dividing_by_zero():
    assert _percent_below(current=50, reference=0) == 0.0


def test_extract_reference_price_averages_price_history():
    """Real shape confirmed via a live call: data[].price_history[] is a full list of
    daily {price, date, store} entries, not a single pre-aggregated value."""
    response = {
        "data": [
            {"ean": "123", "price_history": [{"price": 40.0}, {"price": 50.0}]},
            {"ean": "456", "price_history": [{"price": 10.0}]},
        ]
    }
    assert _extract_reference_price(response, "123") == 45.0


def test_extract_reference_price_returns_none_when_ean_not_found():
    response = {"data": [{"ean": "999", "price_history": [{"price": 45.5}]}]}
    assert _extract_reference_price(response, "123") is None


def test_extract_reference_price_returns_none_for_empty_history():
    response = {"data": [{"ean": "123", "price_history": []}]}
    assert _extract_reference_price(response, "123") is None


def test_extract_reference_price_degrades_gracefully_on_unexpected_shape():
    """Regression guard: an unexpected response shape (e.g. Kassalapp changing their
    API) should degrade to "no data" rather than crash the whole discount scan."""
    assert _extract_reference_price({"totally": "different shape"}, "123") is None
    assert _extract_reference_price({"data": "not a list"}, "123") is None


def test_is_baby_food_detects_tagged_category():
    product = {"name": "Anything", "category": [{"name": "Barnemat"}]}
    assert _is_baby_food(product) is True


def test_is_baby_food_detects_untagged_age_naming_convention():
    """Regression test for a real finding: one live baby-food result had an EMPTY
    category list despite obviously being baby food by its "6mnd" (6 months) naming —
    category alone would have missed it."""
    product = {"name": "Kyllinggryte Økologisk 6mnd 190g Hipp", "category": []}
    assert _is_baby_food(product) is True


def test_is_baby_food_false_for_ordinary_product():
    product = {"name": "Kyllingfilet 500g", "category": [{"name": "Kjøtt"}]}
    assert _is_baby_food(product) is False


def test_is_baby_food_detects_brand_field_mention():
    """Regression test for a real finding: one live baby-food product (brand
    "Alex&Phil") had neither a matching category nor the "Nmnd" naming pattern, but the
    brand field itself said "Alex&phil barnemat" — checking category and name alone
    would have missed this one too."""
    product = {"name": "Kylling&Eple Måltid Økologisk 180g Alex&Phil", "category": [], "brand": "Alex&phil barnemat"}
    assert _is_baby_food(product) is True


def test_name_matches_term_matches_compound_word_prefix():
    """"kyllingfilet" is one word (no space) that starts with "kylling" — must still
    match, this is the common case for raw-meat product naming."""
    assert _name_matches_term("Kyllingfilet 500g", "kylling") is True


def test_name_matches_term_matches_brand_first_naming():
    """Regression test for a real finding: "eggs" translates correctly to "egg", but
    the actual product is named "Prior Egg 12stk" (brand first) — a plain
    whole-string .startswith() check would miss this since the string starts with the
    brand, not the ingredient. Checking each word's prefix instead of the whole
    string's catches it via the second word."""
    assert _name_matches_term("Prior Egg 12stk", "egg") is True


def test_name_matches_term_rejects_cross_word_substring_match():
    """Regression guard for the original bug this whole heuristic exists to prevent:
    "løk" (onion) must not match "Hvitløk" (garlic, a different vegetable) just
    because "løk" is a substring of it — "hvitløk" doesn't START with "løk", so no
    word matches."""
    assert _name_matches_term("Hvitløkspate 180g Finsbråten", "løk") is False


def test_select_representative_product_prefers_name_starting_with_search_term():
    """Regression test for a real finding: Kassalapp's top search hit for "kylling"
    (chicken) was baby food containing chicken as one ingredient among several, not
    chicken itself. A product whose name actually starts with the search term is a much
    better proxy for "this is the ingredient," not just "mentions it.\""""
    products = [
        {"name": "Couscous Kylling 8mnd 190g Nestle", "ean": "1", "current_price": 20.0},
        {"name": "Kyllingfilet 500g", "ean": "2", "current_price": 80.0},
    ]
    assert _select_representative_product(products, "kylling")["name"] == "Kyllingfilet 500g"


def test_select_representative_product_matches_brand_first_naming():
    """Regression test for the real "eggs" finding: within the "Egg" category, the
    representative product was named "Prior Egg 12stk" — brand first — and the old
    whole-string-prefix heuristic fell through to an unrelated first result instead."""
    products = [
        {"name": "Skinke Kokt 150g Folkets", "ean": "1", "current_price": 40.0},
        {"name": "Prior Egg 12stk", "ean": "2", "current_price": 45.0},
    ]
    assert _select_representative_product(products, "egg")["name"] == "Prior Egg 12stk"


def test_select_representative_product_excludes_baby_food_even_if_name_matches():
    """Regression test for a real finding: "Kyllinggryte...6mnd...Hipp" (a baby food
    chicken stew) also starts with "kylling" and would have wrongly passed the plain
    startswith heuristic — baby-food exclusion must run first."""
    products = [
        {"name": "Kyllinggryte Økologisk 6mnd 190g Hipp", "category": [], "ean": "1", "current_price": 30.0},
        {"name": "Kyllingfilet 500g", "category": [{"name": "Kjøtt"}], "ean": "2", "current_price": 80.0},
    ]
    assert _select_representative_product(products, "kylling")["name"] == "Kyllingfilet 500g"


def test_select_representative_product_falls_back_to_baby_food_if_nothing_else_matches():
    """If literally every result is baby food (confirmed live: all 10 results for
    "kylling" on one free-text search were), still return something rather than
    nothing — a slightly-off signal beats no signal at all for a discount scan."""
    products = [{"name": "Couscous Kylling 8mnd 190g Nestle", "category": [], "ean": "1", "current_price": 20.0}]
    assert _select_representative_product(products, "kylling") == products[0]


def test_select_representative_product_falls_back_to_first_result():
    products = [{"name": "Couscous Kylling 8mnd 190g Nestle", "ean": "1", "current_price": 20.0}]
    assert _select_representative_product(products, "kylling") == products[0]


def test_select_representative_product_handles_empty_list():
    assert _select_representative_product([], "kylling") is None


def test_select_representative_product_returns_none_when_nothing_has_a_usable_price():
    products = [{"name": "Kyllingfilet 500g"}]  # no ean, no current_price
    assert _select_representative_product(products, "kylling") is None


class _FakeResponse:
    def __init__(self, json_data, status=200):
        self._json = json_data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._json


def test_kassalapp_client_search_products_by_category():
    client = KassalappClient(api_key="test-key", base_url="https://kassal.app/api/v1")

    with patch("rag.grocery_discounts.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse({"data": [{"name": "Kyllingfilet", "ean": "1"}]})
        result = client.search_products(category="Kylling", size=20)

    assert result == [{"name": "Kyllingfilet", "ean": "1"}]
    call_kwargs = mock_get.call_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert call_kwargs["params"] == {"size": 20, "category": "Kylling"}


def test_kassalapp_client_search_products_by_free_text():
    client = KassalappClient(api_key="test-key", base_url="https://kassal.app/api/v1")

    with patch("rag.grocery_discounts.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse({"data": [{"name": "Tine Melk", "ean": "1"}]})
        result = client.search_products(search="melk", size=3)

    assert result == [{"name": "Tine Melk", "ean": "1"}]
    call_kwargs = mock_get.call_args.kwargs
    assert call_kwargs["params"] == {"size": 3, "search": "melk"}


def test_kassalapp_client_get_price_history_bulk_posts_expected_payload():
    client = KassalappClient(api_key="test-key", base_url="https://kassal.app/api/v1")

    with patch("rag.grocery_discounts.requests.post") as mock_post:
        mock_post.return_value = _FakeResponse({"data": []})
        client.get_price_history_bulk(["111", "222"], days=14, aggregation="min")

    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["json"] == {"eans": ["111", "222"], "days": 14, "aggregation": "min"}


def _price_history_response(ean, price):
    history = [{"price": price}] if price is not None else []
    return {"data": [{"ean": ean, "price_history": history}]}


def test_find_discounted_ingredients_uses_category_lookup_when_available():
    tracked = [{"en": "chicken", "category": "Kylling"}]
    client = MagicMock()
    client.search_products.return_value = [{"ean": "1", "current_price": 80.0, "name": "Kyllingfilet"}]
    client.get_price_history_bulk.return_value = _price_history_response("1", 100.0)

    result = find_discounted_ingredients(client, tracked=tracked, threshold_pct=15.0)

    assert len(result) == 1
    assert result[0]["ingredient_en"] == "chicken"
    assert result[0]["discount_pct"] == 20.0
    call_kwargs = client.search_products.call_args.kwargs
    assert call_kwargs == {"category": "Kylling", "size": 20}


def test_find_discounted_ingredients_falls_back_to_search_when_no_category():
    """Regression test: ingredients with no clean Kassalapp category (garlic, carrots,
    spinach in the real tracked list) must still go through translated free-text
    search, not silently get skipped."""
    tracked = [{"en": "garlic", "category": None}]
    client = MagicMock()
    client.search_products.return_value = [{"ean": "1", "current_price": 80.0, "name": "Hvitløk"}]
    client.get_price_history_bulk.return_value = _price_history_response("1", 100.0)

    result = find_discounted_ingredients(client, tracked=tracked, threshold_pct=15.0)

    assert len(result) == 1
    assert result[0]["ingredient_en"] == "garlic"
    call_kwargs = client.search_products.call_args.kwargs
    assert call_kwargs == {"search": "hvitløk", "size": 20}


def test_find_discounted_ingredients_excludes_items_below_threshold():
    tracked = [{"en": "chicken", "category": "Kylling"}]
    client = MagicMock()
    client.search_products.return_value = [{"ean": "1", "current_price": 95.0, "name": "Kyllingfilet"}]
    client.get_price_history_bulk.return_value = _price_history_response("1", 100.0)  # only 5% below

    result = find_discounted_ingredients(client, tracked=tracked, threshold_pct=15.0)

    assert result == []


def test_find_discounted_ingredients_skips_ingredients_with_no_search_results():
    tracked = [{"en": "chicken", "category": "Kylling"}, {"en": "salmon", "category": "Laks"}]
    client = MagicMock()

    def by_category(category=None, search=None, size=20):
        if category == "Laks":
            return [{"ean": "2", "current_price": 50.0, "name": "Laksefilet"}]
        return []

    client.search_products.side_effect = by_category
    client.get_price_history_bulk.return_value = _price_history_response("2", 100.0)

    result = find_discounted_ingredients(client, tracked=tracked, threshold_pct=15.0)

    assert len(result) == 1
    assert result[0]["ingredient_en"] == "salmon"


def test_find_discounted_ingredients_skips_products_missing_ean_or_price():
    tracked = [{"en": "chicken", "category": "Kylling"}]
    client = MagicMock()
    client.search_products.return_value = [{"name": "Kyllingfilet"}]  # no ean, no current_price

    result = find_discounted_ingredients(client, tracked=tracked, threshold_pct=15.0)

    assert result == []


def test_find_discounted_ingredients_continues_after_a_search_failure():
    """One ingredient's API call failing (network error, rate limit) shouldn't abort
    the whole scan — the rest of the tracked list should still get checked."""
    tracked = [{"en": "chicken", "category": "Kylling"}, {"en": "salmon", "category": "Laks"}]
    client = MagicMock()

    def flaky_search(category=None, search=None, size=20):
        if category == "Kylling":
            raise requests.RequestException("simulated network failure")
        return [{"ean": "2", "current_price": 50.0, "name": "Laksefilet"}]

    client.search_products.side_effect = flaky_search
    client.get_price_history_bulk.return_value = _price_history_response("2", 100.0)

    result = find_discounted_ingredients(client, tracked=tracked, threshold_pct=15.0)

    assert len(result) == 1
    assert result[0]["ingredient_en"] == "salmon"


def test_get_norwegian_term_caches_and_falls_back_to_english_on_failure():
    import rag.grocery_discounts as gd
    gd._translation_cache.clear()

    with patch("rag.grocery_discounts.requests.get") as mock_get:
        mock_get.side_effect = requests.RequestException("simulated network failure")
        result = get_norwegian_term("xyzzy-unlikely-term")

    assert result == "xyzzy-unlikely-term"  # graceful fallback, not a raised exception
    assert gd._translation_cache["xyzzy-unlikely-term"] == "xyzzy-unlikely-term"


def test_get_norwegian_term_uses_override_before_calling_api():
    import rag.grocery_discounts as gd
    gd._translation_cache.clear()

    with patch("rag.grocery_discounts.requests.get") as mock_get:
        result = get_norwegian_term("salmon")

    assert result == "laks"
    mock_get.assert_not_called()


def test_get_norwegian_term_butter_override():
    """Regression test for a real finding: MyMemory translated "butter" to
    "påleggssalat og smørepålegg" (a nonsense multi-word phrase), matching zero
    Kassalapp products."""
    import rag.grocery_discounts as gd
    gd._translation_cache.clear()

    with patch("rag.grocery_discounts.requests.get") as mock_get:
        result = get_norwegian_term("butter")

    assert result == "smør"
    mock_get.assert_not_called()
