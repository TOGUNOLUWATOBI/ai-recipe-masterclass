"""Tests for grocery_discounts.py's pure logic and client wiring, using mocked HTTP
responses -- no real Kassalapp API key needed."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from rag.grocery_discounts import (
    GROCERY_STORE_GROUPS,
    KassalappClient,
    _extract_reference_price,
    _filter_usable_candidates,
    _is_baby_food,
    _is_non_food,
    _maybe_wait_for_rate_limit,
    _percent_below,
    _top_level_category,
    find_discounted_products,
)


@pytest.fixture(autouse=True)
def no_real_sleep():
    with patch("rag.grocery_discounts.time.sleep"):
        yield


def test_grocery_store_groups_has_no_duplicates():
    assert len(GROCERY_STORE_GROUPS) == len(set(GROCERY_STORE_GROUPS))


def test_percent_below_computes_discount_correctly():
    assert _percent_below(current=80, reference=100) == 20.0


def test_percent_below_returns_zero_for_price_increase():
    assert _percent_below(current=120, reference=100) == 0.0


def test_percent_below_handles_zero_reference_without_dividing_by_zero():
    assert _percent_below(current=50, reference=0) == 0.0


def test_extract_reference_price_averages_price_history():
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
    assert _extract_reference_price({"totally": "different shape"}, "123") is None
    assert _extract_reference_price({"data": "not a list"}, "123") is None


def test_is_baby_food_detects_tagged_category():
    product = {"name": "Anything", "category": [{"name": "Barnemat"}]}
    assert _is_baby_food(product) is True


def test_is_baby_food_detects_untagged_age_naming_convention():
    product = {"name": "Kyllinggryte Økologisk 6mnd 190g Hipp", "category": []}
    assert _is_baby_food(product) is True


def test_is_baby_food_false_for_ordinary_product():
    product = {"name": "Kyllingfilet 500g", "category": [{"name": "Kjøtt"}]}
    assert _is_baby_food(product) is False


def test_is_baby_food_detects_brand_field_mention():
    product = {"name": "Kylling&Eple Måltid Økologisk 180g Alex&Phil", "category": [], "brand": "Alex&phil barnemat"}
    assert _is_baby_food(product) is True


def test_top_level_category_extracts_depth_minus_2():
    product = {"category": [
        {"id": 1, "depth": -2, "name": "Frukt & grønt"},
        {"id": 2, "depth": -1, "name": "Frukt"},
        {"id": 3, "depth": 0, "name": "Sitrusfrukt"},
    ]}
    assert _top_level_category(product) == "Frukt & grønt"


def test_top_level_category_falls_back_to_shallowest_available_depth():
    """Regression test for a real finding: category hierarchy depth isn't consistent
    across product types -- most have 3 levels (-2/-1/0), but e.g. Coca-Cola's real
    category array is only [{"depth": -1, "name": "Drikke"}, {"depth": 0, "name":
    "Brus"}], no -2 entry at all. A hardcoded depth=-2 check would silently miss this
    and dump an otherwise well-categorized product into the "Annet" fallback -- must
    use whichever entry has the minimum depth instead."""
    assert _top_level_category({"category": [{"depth": -1, "name": "Drikke"}, {"depth": 0, "name": "Brus"}]}) == "Drikke"


def test_top_level_category_returns_none_when_category_list_is_empty():
    assert _top_level_category({"category": []}) is None
    assert _top_level_category({}) is None


def test_is_non_food_excludes_personal_care():
    product = {"category": [{"depth": -2, "name": "Personlige artikler"}]}
    assert _is_non_food(product) is True


def test_is_non_food_excludes_household_goods():
    product = {"category": [{"depth": -2, "name": "Hus & hjem"}]}
    assert _is_non_food(product) is True


def test_is_non_food_excludes_baby_products_category():
    product = {"category": [{"depth": -2, "name": "Barneprodukter"}]}
    assert _is_non_food(product) is True


def test_is_non_food_false_for_real_food_category():
    product = {"category": [{"depth": -2, "name": "Kjøtt"}]}
    assert _is_non_food(product) is False


def test_filter_usable_candidates_excludes_baby_food():
    products = [
        {"name": "Kyllinggryte Økologisk 6mnd 190g Hipp", "category": [], "ean": "1", "current_price": 30.0},
        {"name": "Kyllingfilet 500g", "category": [{"depth": -2, "name": "Kjøtt"}], "ean": "2", "current_price": 80.0},
    ]
    result = _filter_usable_candidates(products)
    assert [p["ean"] for p in result] == ["2"]


def test_filter_usable_candidates_excludes_non_food_categories():
    products = [
        {"name": "Shampoo", "category": [{"depth": -2, "name": "Personlige artikler"}], "ean": "1", "current_price": 30.0},
        {"name": "Kyllingfilet 500g", "category": [{"depth": -2, "name": "Kjøtt"}], "ean": "2", "current_price": 80.0},
    ]
    result = _filter_usable_candidates(products)
    assert [p["ean"] for p in result] == ["2"]


def test_filter_usable_candidates_excludes_products_missing_ean_or_price():
    products = [
        {"name": "No EAN", "current_price": 10.0},
        {"name": "No price", "ean": "1"},
        {"name": "Usable", "ean": "2", "current_price": 20.0},
    ]
    result = _filter_usable_candidates(products)
    assert [p["ean"] for p in result] == ["2"]


def test_filter_usable_candidates_returns_every_usable_product_not_just_one():
    products = [
        {"name": "Kyllingfilet 500g", "ean": "1", "current_price": 80.0},
        {"name": "Kyllinglår 1kg", "ean": "2", "current_price": 60.0},
        {"name": "Kyllingvinger 400g", "ean": "3", "current_price": 40.0},
    ]
    result = _filter_usable_candidates(products)
    assert len(result) == 3


def test_filter_usable_candidates_handles_empty_list():
    assert _filter_usable_candidates([]) == []


class _FakeResponse:
    def __init__(self, json_data, status=200, headers=None):
        self._json = json_data
        self.status_code = status
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._json


def test_kassalapp_client_search_products_by_store():
    client = KassalappClient(api_key="test-key", base_url="https://kassal.app/api/v1")

    with patch("rag.grocery_discounts.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse({"data": [{"name": "Kyllingfilet", "ean": "1"}]})
        result = client.search_products(store="KIWI", size=100, unique=1)

    assert result == [{"name": "Kyllingfilet", "ean": "1"}]
    call_kwargs = mock_get.call_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert call_kwargs["params"] == {"size": 100, "store": "KIWI", "unique": 1}


def test_kassalapp_client_search_products_by_category():
    client = KassalappClient(api_key="test-key", base_url="https://kassal.app/api/v1")

    with patch("rag.grocery_discounts.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse({"data": [{"name": "Kyllingfilet", "ean": "1"}]})
        result = client.search_products(category="Kylling", size=20)

    assert result == [{"name": "Kyllingfilet", "ean": "1"}]
    call_kwargs = mock_get.call_args.kwargs
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


def test_kassalapp_client_starts_with_unknown_rate_limit():
    client = KassalappClient(api_key="test-key", base_url="https://kassal.app/api/v1")
    assert client.rate_limit_remaining is None


def test_kassalapp_client_search_products_tracks_rate_limit_from_headers():
    client = KassalappClient(api_key="test-key", base_url="https://kassal.app/api/v1")

    with patch("rag.grocery_discounts.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse({"data": []}, headers={"X-RateLimit-Remaining": "42"})
        client.search_products(store="KIWI")

    assert client.rate_limit_remaining == 42


def test_kassalapp_client_get_price_history_bulk_tracks_rate_limit_from_headers():
    client = KassalappClient(api_key="test-key", base_url="https://kassal.app/api/v1")

    with patch("rag.grocery_discounts.requests.post") as mock_post:
        mock_post.return_value = _FakeResponse({"data": []}, headers={"X-RateLimit-Remaining": "17"})
        client.get_price_history_bulk(["111"])

    assert client.rate_limit_remaining == 17


def test_kassalapp_client_tracks_rate_limit_even_on_error_response():
    client = KassalappClient(api_key="test-key", base_url="https://kassal.app/api/v1")

    with patch("rag.grocery_discounts.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse({}, status=429, headers={"X-RateLimit-Remaining": "0"})
        with pytest.raises(requests.HTTPError):
            client.search_products(store="KIWI")

    assert client.rate_limit_remaining == 0


def test_kassalapp_client_ignores_missing_rate_limit_header():
    client = KassalappClient(api_key="test-key", base_url="https://kassal.app/api/v1")

    with patch("rag.grocery_discounts.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse({"data": []})
        client.search_products(store="KIWI")

    assert client.rate_limit_remaining is None


def test_maybe_wait_for_rate_limit_pauses_when_budget_is_low():
    client = MagicMock()
    client.rate_limit_remaining = 2

    with patch("rag.grocery_discounts.time.sleep") as mock_sleep:
        _maybe_wait_for_rate_limit(client, threshold=3, cooldown=61.0)

    mock_sleep.assert_called_once_with(61.0)
    assert client.rate_limit_remaining is None


def test_maybe_wait_for_rate_limit_does_nothing_when_budget_is_healthy():
    client = MagicMock()
    client.rate_limit_remaining = 50

    with patch("rag.grocery_discounts.time.sleep") as mock_sleep:
        _maybe_wait_for_rate_limit(client, threshold=3, cooldown=61.0)

    mock_sleep.assert_not_called()
    assert client.rate_limit_remaining == 50


def test_maybe_wait_for_rate_limit_does_nothing_when_remaining_is_unknown():
    client = MagicMock()

    with patch("rag.grocery_discounts.time.sleep") as mock_sleep:
        _maybe_wait_for_rate_limit(client, threshold=3, cooldown=61.0)

    mock_sleep.assert_not_called()


def _history_response(*ean_price_pairs):
    return {"data": [{"ean": ean, "price_history": [{"price": price}]} for ean, price in ean_price_pairs]}


def _product(ean, name, price, top_level_category="Kjøtt", store_name="Kiwi", store_logo="k.svg"):
    return {
        "name": name,
        "ean": ean,
        "current_price": price,
        "category": [{"depth": -2, "name": top_level_category}],
        "store": {"name": store_name, "logo": store_logo},
    }


def test_find_discounted_products_evaluates_every_candidate_in_a_store_not_just_one():
    client = MagicMock()
    client.search_products.return_value = [
        _product("1", "Kyllingfilet 500g", 80.0),
        _product("2", "Kyllinglår 1kg", 60.0),
        _product("3", "Kyllingvinger 400g", 40.0),
    ]
    client.get_price_history_bulk.return_value = _history_response(("1", 100.0), ("2", 100.0), ("3", 100.0))

    result = find_discounted_products(client, store_groups=["KIWI"], threshold_pct=15.0)

    assert {r["product_name"] for r in result} == {"Kyllingfilet 500g", "Kyllinglår 1kg", "Kyllingvinger 400g"}
    assert all(r["store_name"] == "Kiwi" for r in result)


def test_find_discounted_products_labels_results_with_the_products_own_top_level_category():
    client = MagicMock()
    client.search_products.return_value = [
        _product("1", "Kyllingfilet", 80.0, top_level_category="Kjøtt"),
        _product("2", "Agurk", 10.0, top_level_category="Frukt & grønt"),
    ]
    client.get_price_history_bulk.return_value = _history_response(("1", 100.0), ("2", 100.0))

    result = find_discounted_products(client, store_groups=["KIWI"], threshold_pct=15.0)

    labels = {r["product_name"]: r["category"] for r in result}
    assert labels == {"Kyllingfilet": "Kjøtt", "Agurk": "Frukt & grønt"}


def test_find_discounted_products_excludes_non_food_and_baby_food_candidates():
    """Non-food/baby-food exclusion still applies unconditionally -- these must never
    appear at all, discount or not, unlike an ordinary product with no computable
    discount (which is still shown, just without a badge)."""
    client = MagicMock()
    client.search_products.return_value = [
        _product("1", "Kyllingfilet", 80.0, top_level_category="Kjøtt"),
        _product("2", "Shampoo", 30.0, top_level_category="Personlige artikler"),
        {"name": "Babymat 6mnd", "ean": "3", "current_price": 20.0, "category": [{"depth": -2, "name": "Kjøtt"}], "store": {}},
    ]
    client.get_price_history_bulk.return_value = _history_response(("1", 100.0))

    result = find_discounted_products(client, store_groups=["KIWI"], threshold_pct=15.0)

    assert [r["product_name"] for r in result] == ["Kyllingfilet"]
    client.get_price_history_bulk.assert_called_once()
    assert set(client.get_price_history_bulk.call_args.args[0]) == {"1"}


def test_find_discounted_products_includes_items_below_threshold_without_a_discount_badge():
    """Core behavior change: an item whose price history exists but doesn't clear the
    threshold is still returned (unlike the old design, which dropped it entirely) --
    just with discount_pct/reference_price left None so the UI doesn't show a
    misleading badge for a trivial or nonexistent discount."""
    client = MagicMock()
    client.search_products.return_value = [
        _product("1", "Discounted Item", 80.0),
        _product("2", "Not Discounted Item", 98.0),
    ]
    client.get_price_history_bulk.return_value = _history_response(("1", 100.0), ("2", 100.0))

    result = find_discounted_products(client, store_groups=["KIWI"], threshold_pct=15.0)

    by_name = {r["product_name"]: r for r in result}
    assert set(by_name) == {"Discounted Item", "Not Discounted Item"}
    assert by_name["Discounted Item"]["discount_pct"] == 20.0
    assert by_name["Discounted Item"]["reference_price"] == 100.0
    assert by_name["Not Discounted Item"]["discount_pct"] is None
    assert by_name["Not Discounted Item"]["reference_price"] is None


def test_find_discounted_products_batches_price_history_into_one_call_per_store():
    client = MagicMock()
    client.search_products.return_value = [_product("1", "A", 10.0), _product("2", "B", 10.0)]
    client.get_price_history_bulk.return_value = _history_response(("1", 100.0), ("2", 100.0))

    find_discounted_products(client, store_groups=["KIWI"], threshold_pct=15.0)

    client.get_price_history_bulk.assert_called_once()
    assert set(client.get_price_history_bulk.call_args.args[0]) == {"1", "2"}


def test_find_discounted_products_includes_products_with_no_price_history_at_all():
    """Regression test for a real finding: roughly half of real sausage products
    checked live had NO price history recorded by Kassalapp at all -- these must still
    be shown (a real, currently-on-sale product could be among them; we simply can't
    tell), not silently dropped just because we can't evaluate them."""
    client = MagicMock()
    client.search_products.return_value = [_product("1", "Untracked Product", 50.0)]
    client.get_price_history_bulk.return_value = {"data": [{"ean": "1", "price_history": []}]}

    result = find_discounted_products(client, store_groups=["KIWI"], threshold_pct=15.0)

    assert len(result) == 1
    assert result[0]["product_name"] == "Untracked Product"
    assert result[0]["discount_pct"] is None
    assert result[0]["reference_price"] is None


def test_find_discounted_products_includes_products_even_when_price_history_call_fails():
    """A failed price-history-bulk call is no longer a reason to hide that store's
    products entirely -- they're still returned, just without discount info, matching
    how a missing/empty history is handled."""
    client = MagicMock()
    client.search_products.side_effect = [
        [_product("1", "Kyllingfilet", 80.0)],
        [_product("2", "Laksefilet", 50.0)],
    ]
    client.get_price_history_bulk.side_effect = [
        requests.RequestException("simulated failure"),
        _history_response(("2", 60.0)),
    ]

    result = find_discounted_products(client, store_groups=["KIWI", "COOP_NO"], threshold_pct=15.0)

    by_name = {r["product_name"]: r for r in result}
    assert set(by_name) == {"Kyllingfilet", "Laksefilet"}
    assert by_name["Kyllingfilet"]["discount_pct"] is None


def test_find_discounted_products_skips_stores_with_no_search_results():
    client = MagicMock()

    def by_store(store=None, search=None, category=None, unique=None, size=100):
        if store == "COOP_NO":
            return [_product("2", "Laksefilet", 50.0)]
        return []

    client.search_products.side_effect = by_store
    client.get_price_history_bulk.return_value = _history_response(("2", 100.0))

    result = find_discounted_products(client, store_groups=["KIWI", "COOP_NO"], threshold_pct=15.0)

    assert len(result) == 1
    assert result[0]["product_name"] == "Laksefilet"
    assert client.get_price_history_bulk.call_count == 1


def test_find_discounted_products_continues_after_a_search_failure():
    client = MagicMock()

    def flaky_search(store=None, search=None, category=None, unique=None, size=100):
        if store == "KIWI":
            raise requests.RequestException("simulated network failure")
        return [_product("2", "Laksefilet", 50.0)]

    client.search_products.side_effect = flaky_search
    client.get_price_history_bulk.return_value = _history_response(("2", 100.0))

    result = find_discounted_products(client, store_groups=["KIWI", "COOP_NO"], threshold_pct=15.0)

    assert len(result) == 1
    assert result[0]["product_name"] == "Laksefilet"


def test_find_discounted_products_skips_products_missing_ean_or_price():
    client = MagicMock()
    client.search_products.return_value = [{"name": "Kyllingfilet"}]

    result = find_discounted_products(client, store_groups=["KIWI"], threshold_pct=15.0)

    assert result == []
    client.get_price_history_bulk.assert_not_called()


def test_find_discounted_products_does_not_dedupe_across_stores():
    """Deliberate design change: the same EAN appearing at two different stores must be
    priced and shown independently for each -- this is a per-store browse now, not a
    single merged "is this on sale anywhere" list, so one store's listing is never
    hidden just because the same product was already seen at another store."""
    client = MagicMock()
    client.search_products.return_value = [_product("1", "Shared Product", 50.0)]
    client.get_price_history_bulk.return_value = _history_response(("1", 100.0))

    result = find_discounted_products(client, store_groups=["KIWI", "COOP_NO"], threshold_pct=15.0)

    assert len(result) == 2
    assert client.get_price_history_bulk.call_count == 2


def test_find_discounted_products_sorts_confirmed_discounts_first_by_descending_pct():
    client = MagicMock()
    client.search_products.return_value = [
        _product("1", "Small Discount", 90.0),
        _product("2", "No Discount", 99.0),
        _product("3", "Big Discount", 50.0),
    ]
    client.get_price_history_bulk.return_value = _history_response(("1", 100.0), ("2", 100.0), ("3", 100.0))

    result = find_discounted_products(client, store_groups=["KIWI"], threshold_pct=5.0)

    assert [r["product_name"] for r in result] == ["Big Discount", "Small Discount", "No Discount"]


def test_find_discounted_products_pauses_proactively_when_budget_is_low():
    client = MagicMock()
    client.rate_limit_remaining = 2
    client.search_products.return_value = [_product("1", "Kyllingfilet", 80.0)]
    client.get_price_history_bulk.return_value = _history_response(("1", 100.0))

    with patch("rag.grocery_discounts.time.sleep") as mock_sleep:
        find_discounted_products(client, store_groups=["KIWI"], threshold_pct=15.0)

    assert any(call.args == (61.0,) for call in mock_sleep.call_args_list)
