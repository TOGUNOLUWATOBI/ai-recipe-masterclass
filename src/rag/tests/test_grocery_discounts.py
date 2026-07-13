"""Tests for grocery_discounts.py's Tjek client and pure logic, using mocked HTTP
responses -- no network access needed. Response shapes mocked here match what a live
call to api.etilbudsavis.dk actually returned (verified 2026-07-08), not just assumed
from documentation."""

from unittest.mock import MagicMock, patch

import pytest
import requests

from rag.grocery_discounts import (
    NON_FOOD_KEYWORDS,
    NORWEGIAN_STORES,
    TjekClient,
    _compute_unit_price,
    _is_non_food,
    find_discounted_products,
)


@pytest.fixture(autouse=True)
def no_real_sleep():
    with patch("rag.grocery_discounts.time.sleep"):
        yield


def test_norwegian_stores_has_no_duplicate_dealer_ids():
    assert len(NORWEGIAN_STORES) == len(set(NORWEGIAN_STORES.values()))


class _FakeResponse:
    def __init__(self, json_data, status=200):
        self._json = json_data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"status {self.status_code}")

    def json(self):
        return self._json


def test_tjek_client_get_store_offers_calls_expected_url_and_params():
    client = TjekClient()

    with patch("rag.grocery_discounts.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse([{"heading": "TEST"}])
        result = client.get_store_offers("257bxm", limit=50)

    assert result == [{"heading": "TEST"}]
    call_args = mock_get.call_args
    assert call_args.args[0] == "https://api.etilbudsavis.dk/v2/offers"
    assert call_args.kwargs["params"] == {"dealer_id": "257bxm", "limit": 50}
    assert "User-Agent" in call_args.kwargs["headers"]


def test_tjek_client_raises_on_http_error():
    client = TjekClient()

    with patch("rag.grocery_discounts.requests.get") as mock_get:
        mock_get.return_value = _FakeResponse({}, status=500)
        with pytest.raises(requests.HTTPError):
            client.get_store_offers("257bxm")


def test_compute_unit_price_converts_grams_to_kg():
    quantity = {"unit": {"symbol": "g"}, "size": {"from": 500}}
    assert _compute_unit_price(50.0, quantity) == (100.0, "kg")


def test_compute_unit_price_converts_ml_to_liter():
    quantity = {"unit": {"symbol": "ml"}, "size": {"from": 250}}
    assert _compute_unit_price(25.0, quantity) == (100.0, "L")


def test_compute_unit_price_handles_kg_directly():
    quantity = {"unit": {"symbol": "kg"}, "size": {"from": 2}}
    assert _compute_unit_price(100.0, quantity) == (50.0, "kg")


def test_compute_unit_price_handles_liter_directly_lowercase_and_uppercase():
    lowercase = {"unit": {"symbol": "l"}, "size": {"from": 2}}
    uppercase = {"unit": {"symbol": "L"}, "size": {"from": 2}}
    assert _compute_unit_price(100.0, lowercase) == (50.0, "L")
    assert _compute_unit_price(100.0, uppercase) == (50.0, "L")


def test_compute_unit_price_falls_back_to_pieces():
    quantity = {"unit": None, "size": None, "pieces": {"from": 12}}
    assert _compute_unit_price(36.0, quantity) == (3.0, "pc")


def test_compute_unit_price_converts_dl_to_liter():
    quantity = {"unit": {"symbol": "dl"}, "size": {"from": 5}}
    assert _compute_unit_price(20.0, quantity) == (40.0, "L")


def test_compute_unit_price_handles_pcs_symbol_directly():
    # Real Tjek data shape (e.g. "KRONE-IS HEIA NORGE"): unit.symbol="pcs" with a
    # size.from present (the piece count) -- confirmed live this previously fell
    # through to a bare `return None` before even checking the separate `pieces`
    # field, silently dropping a computable unit price for every "pcs"-labeled item.
    quantity = {"unit": {"symbol": "pcs"}, "size": {"from": 10}}
    assert _compute_unit_price(79.9, quantity) == (7.99, "pc")


def test_compute_unit_price_handles_stk_symbol_directly():
    quantity = {"unit": {"symbol": "stk"}, "size": {"from": 4}}
    assert _compute_unit_price(20.0, quantity) == (5.0, "pc")


def test_compute_unit_price_falls_back_to_pieces_when_symbol_unrecognized():
    # An unhandled symbol (with a size present) should still try the separate
    # "pieces" count before giving up -- it must not short-circuit to None the
    # way it used to for every not-explicitly-handled symbol.
    quantity = {"unit": {"symbol": "boks"}, "size": {"from": 1}, "pieces": {"from": 6}}
    assert _compute_unit_price(30.0, quantity) == (5.0, "pc")


def test_compute_unit_price_returns_none_when_no_quantity_info():
    assert _compute_unit_price(50.0, None) is None
    assert _compute_unit_price(50.0, {}) is None


def test_compute_unit_price_returns_none_for_zero_size():
    quantity = {"unit": {"symbol": "g"}, "size": {"from": 0}}
    assert _compute_unit_price(50.0, quantity) is None


def test_is_non_food_detects_real_observed_non_food_headings():
    """Regression test using real headings observed live on 2026-07-08."""
    assert _is_non_food("NIVEA SUN -SOLKREM") is True
    assert _is_non_food("LAMBI TOALETTPAPIR") is True
    assert _is_non_food("BATTERIER ENERGIZER") is True
    assert _is_non_food("XTRA LED LYSPÆRE") is True
    assert _is_non_food("ZALO OPPVASKBØRSTE") is True
    assert _is_non_food("SITRONSÅPE") is True


def test_is_non_food_does_not_false_positive_on_ice_cream():
    """Regression test for a real finding: a naive substring check for "krem" would
    wrongly exclude "iskrem" (ice cream) since it contains "krem" -- confirming the
    suffix-per-token approach with only full compounds listed avoids this."""
    assert _is_non_food("Mochi iskrem 180 g") is False
    assert "krem" not in NON_FOOD_KEYWORDS


def test_is_non_food_does_not_false_positive_on_food_bags():
    """Regression test: "avfallspose" (trash bag) is excluded, but "saftposer" (juice
    pouches) and "salatposer" (salad bags) -- real food items containing "pose" -- must
    not be caught by an overly broad "pose" keyword."""
    assert _is_non_food("Mr. Freeze saftposer 20 x 45 ml") is False
    assert _is_non_food("SALATPOSER") is False
    assert _is_non_food("COOP AVFALLSPOSE") is True


def test_is_non_food_false_for_ordinary_food():
    assert _is_non_food("KYLLINGFILET 690 G") is False


def _offer(heading, price, pre_price=None, store_name="Kiwi", store_logo="k.svg", quantity=None):
    return {
        "heading": heading,
        "pricing": {"price": price, "pre_price": pre_price, "currency": "NOK"},
        "quantity": quantity,
        "dealer": {"name": store_name, "logo": store_logo},
    }


def test_find_discounted_products_includes_every_offer_not_just_discounted_ones():
    client = MagicMock()
    client.get_store_offers.return_value = [
        _offer("KYLLINGFILET", 80.0, pre_price=100.0),
        _offer("LAKSEFILET", 90.0),  # no pre_price -- still included
    ]

    result = find_discounted_products(client, stores={"Kiwi": "257bxm"})

    assert {r["product_name"] for r in result} == {"KYLLINGFILET", "LAKSEFILET"}
    by_name = {r["product_name"]: r for r in result}
    assert by_name["KYLLINGFILET"]["discount_pct"] == 20.0
    assert by_name["KYLLINGFILET"]["reference_price"] == 100.0
    assert by_name["LAKSEFILET"]["discount_pct"] is None
    assert by_name["LAKSEFILET"]["reference_price"] is None


def test_find_discounted_products_ignores_a_pre_price_that_is_not_actually_higher():
    """Defensive guard: a pre_price that's equal to or lower than the current price
    isn't a real discount (data glitch or promotional pricing quirk) -- must not compute
    a discount_pct in that case."""
    client = MagicMock()
    client.get_store_offers.return_value = [_offer("ITEM", 100.0, pre_price=90.0)]

    result = find_discounted_products(client, stores={"Kiwi": "257bxm"})

    assert result[0]["discount_pct"] is None
    assert result[0]["reference_price"] is None


def test_find_discounted_products_excludes_non_food_items():
    client = MagicMock()
    client.get_store_offers.return_value = [
        _offer("KYLLINGFILET", 80.0),
        _offer("NIVEA SUN -SOLKREM", 49.0),
    ]

    result = find_discounted_products(client, stores={"Kiwi": "257bxm"})

    assert [r["product_name"] for r in result] == ["KYLLINGFILET"]


def test_find_discounted_products_excludes_offers_missing_a_price():
    client = MagicMock()
    client.get_store_offers.return_value = [
        {"heading": "NO PRICE ITEM", "pricing": {"price": None, "pre_price": None, "currency": "NOK"}, "dealer": {}},
    ]

    result = find_discounted_products(client, stores={"Kiwi": "257bxm"})

    assert result == []


def test_find_discounted_products_computes_unit_price():
    client = MagicMock()
    client.get_store_offers.return_value = [
        _offer("KYLLINGFILET 500G", 50.0, quantity={"unit": {"symbol": "g"}, "size": {"from": 500}})
    ]

    result = find_discounted_products(client, stores={"Kiwi": "257bxm"})

    assert result[0]["unit_price"] == 100.0
    assert result[0]["unit_price_unit"] == "kg"


def test_find_discounted_products_labels_with_the_stores_own_dealer_name():
    client = MagicMock()
    client.get_store_offers.return_value = [_offer("ITEM", 50.0, store_name="KIWI", store_logo="logo.svg")]

    result = find_discounted_products(client, stores={"Kiwi": "257bxm"})

    assert result[0]["store_name"] == "KIWI"
    assert result[0]["store_logo_url"] == "logo.svg"


def test_find_discounted_products_continues_after_a_request_failure():
    client = MagicMock()

    def by_store(dealer_id, limit=100):
        if dealer_id == "bad-id":
            raise requests.RequestException("simulated network failure")
        return [_offer("LAKSEFILET", 50.0)]

    client.get_store_offers.side_effect = by_store

    result = find_discounted_products(client, stores={"Broken": "bad-id", "Kiwi": "257bxm"})

    assert len(result) == 1
    assert result[0]["product_name"] == "LAKSEFILET"


def test_find_discounted_products_sorts_confirmed_discounts_first_by_descending_pct():
    client = MagicMock()
    client.get_store_offers.return_value = [
        _offer("SMALL DISCOUNT", 90.0, pre_price=100.0),
        _offer("NO DISCOUNT", 50.0),
        _offer("BIG DISCOUNT", 50.0, pre_price=100.0),
    ]

    result = find_discounted_products(client, stores={"Kiwi": "257bxm"})

    assert [r["product_name"] for r in result] == ["BIG DISCOUNT", "SMALL DISCOUNT", "NO DISCOUNT"]


def test_find_discounted_products_uses_default_norwegian_stores_when_not_specified():
    client = MagicMock()
    client.get_store_offers.return_value = []

    find_discounted_products(client)

    assert client.get_store_offers.call_count == len(NORWEGIAN_STORES)
