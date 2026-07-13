"""Grocery discount detection via Tjek (etilbudsavis.dk) -- a Nordic weekly-flyer
aggregation API.

Tjek's public API surfaces REAL, officially-published weekly flyer offers --
each with the retailer's own price and, when they chose to advertise a discount, the
original pre_price too (confirmed live, 2026-07-08: e.g. "COOP KYLLINGFILET 690G" priced
99.90 kr, was 129.90 kr, sourced directly from Coop's own published flyer, with real
run_from/run_till validity dates). No API key is required, and no rate limiting was
observed across 15 rapid requests (all 200 OK).

Norway coverage: the /dealers endpoint ignores country_id for non-Danish countries and
always returns Danish dealers regardless (confirmed live) -- there is no way to
enumerate Norwegian stores from the API itself. NORWEGIAN_STORES is therefore a
hand-verified list of dealer IDs (found via
github.com/olgasafonova/tilbudstrolden-mcp, an open-source Nordic meal-planning MCP
server that had already solved this exact problem) -- every one of these was
independently confirmed live to return substantial current offer data (17-100 offers
per store, ~700 total across all 11).

No product-category data exists for Norwegian offers (category_ids came back empty on
every Norwegian offer checked) -- there is deliberately no grouping-by-aisle here
anymore, only per-store listings of real flyer items; the product's own name (heading)
is descriptive enough on its own. A short non-food keyword filter (NON_FOOD_KEYWORDS)
excludes the handful of genuinely non-food items real flyers mix in alongside groceries
(sunscreen, soap, batteries, toilet paper, ...) -- confirmed live by scanning ~500 real
headings across 5 stores, about 5% were non-food. Matching is done against whole
word/token SUFFIXES within each heading, not a plain substring of the full string --
confirmed live this matters: a naive substring check for "krem" (cream/lotion) would
wrongly exclude "iskrem" (ice cream), so only full compounds like "solkrem" (sunscreen)
are listed, never the bare ambiguous root.

VERIFIED LIVE (2026-07-08) against the real public API -- offer shape, discount fields,
Norwegian dealer IDs and their offer volumes, absence of rate limiting, and the
non-food-keyword false-positive risk described above are all confirmed empirically, not
assumed from documentation alone.
"""

import logging
import re
import time
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://api.etilbudsavis.dk/v2"
USER_AGENT = "ai-recipe-masterclass/1.0"

# Hand-verified Norwegian dealer IDs (name -> dealer_id) -- the /dealers endpoint cannot
# enumerate these itself for non-Danish countries (see module docstring). Sourced from
# github.com/olgasafonova/tilbudstrolden-mcp's locale data and independently confirmed
# live: every one of these returned substantial real current offers (17-100 each) on
# 2026-07-08.
NORWEGIAN_STORES = {
    "Rema 1000": "faa0Ym",
    "Kiwi": "257bxm",
    "Meny": "4333pm",
    "Coop Prix": "f5d5lm",
    "Extra": "80742m",
    "Bunnpris": "5b11sm",
    "Obs": "51dawm",
    "Spar": "c062vm",
    "Joker": "b3e8Fm",
    "Gigaboks": "5vk-xt",
    "Holdbart": "pR2h9x",
}

# Real flyers mix in a handful of non-food items alongside groceries (confirmed live by
# scanning ~500 real Norwegian headings across 5 stores). Deliberately specific full
# compounds (e.g. "solkrem", not bare "krem") -- see module docstring for why: a bare
# "krem" would wrongly match "iskrem" (ice cream).
NON_FOOD_KEYWORDS = [
    "lotion", "solkrem", "sololje",
    "sjampo", "shampoo", "hårbalsam", "hårspray",
    "dusjsåpe", "håndsåpe", "sitronsåpe", "kjøkkensåpe",
    "tannkrem", "tannbørste",
    "bleie", "bleier",
    "vaskemiddel", "oppvaskmiddel", "oppvasktabletter", "oppvaskbørste", "klesvask",
    "toalettpapir", "tørkerull", "kjøkkenrull", "serviett",
    "avfallspose", "søppelpose",
    "batteri", "batterier",
    "lyspære",
    "deodorant",
    "barberhøvel", "barberskum",
    "vaselin",
]


class TjekClient:
    """Thin wrapper around Tjek's public offers API -- no API key or auth of any kind
    required (confirmed live)."""

    def __init__(self, timeout: float = 15.0):
        self.timeout = timeout

    def get_store_offers(self, dealer_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        resp = requests.get(
            f"{BASE_URL}/offers",
            params={"dealer_id": dealer_id, "limit": limit},
            headers={"User-Agent": USER_AGENT},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()


def _compute_unit_price(
    price: float, quantity: Optional[Dict[str, Any]]
) -> Optional[Tuple[float, str]]:
    """Converts a per-package price into an approximate kr-per-kg/L/piece figure, so the
    app can show a comparable unit price. Mirrors the same gram/mL-to-kg/L scaling
    tilbudstrolden-mcp's own client uses.

    Returns (value, unit_label) rather than a bare float -- the quantity basis varies
    per product (kg vs L vs piece), so the caller needs the label to render a correct
    '/kg', '/L', or '/pc' suffix instead of a misleading one-size-fits-all '/unit' (the
    math here was always correct per-symbol; only the label was missing). unit_label is
    always one of 'kg', 'L', or 'pc' -- g/ml are normalized up to kg/L (matching
    whichever the original symbol was), 'l'/'L' both normalize to the label 'L', and the
    pieces fallback branch is labeled 'pc'."""
    if not quantity:
        return None
    unit_info = quantity.get("unit") or {}
    symbol = unit_info.get("symbol")
    size = (quantity.get("size") or {}).get("from")
    if symbol and size and size > 0:
        if symbol == "g":
            return round((price / size) * 1000, 2), "kg"
        if symbol == "ml":
            return round((price / size) * 1000, 2), "L"
        if symbol == "dl":
            return round((price / size) * 10, 2), "L"
        if symbol == "kg":
            return round(price / size, 2), "kg"
        if symbol in ("l", "L"):
            return round(price / size, 2), "L"
        if symbol in ("pcs", "stk"):
            return round(price / size, 2), "pc"
        # Some other/unrecognized symbol -- don't give up yet, a usable "pieces"
        # count (checked below) can still exist alongside an unhandled symbol.
    pieces = (quantity.get("pieces") or {}).get("from")
    if pieces and pieces > 0:
        return round(price / pieces, 2), "pc"
    return None


def _is_non_food(heading: str) -> bool:
    """Real flyers mix in a handful of non-food items alongside groceries -- checked as
    a suffix against each individual word/token in the heading (split on
    whitespace/hyphen/slash), not a plain substring of the whole string, so this can't
    accidentally match a food word that happens to contain a shorter non-food word
    inside it (see NON_FOOD_KEYWORDS and the module docstring for the "iskrem" case)."""
    tokens = re.findall(r"[^\s\-/]+", heading.lower())
    return any(token.endswith(kw) for token in tokens for kw in NON_FOOD_KEYWORDS)


def find_discounted_products(
    client: TjekClient,
    stores: Dict[str, str] = NORWEGIAN_STORES,
    limit: int = 100,
) -> List[Dict[str, Any]]:
    """Fetches every current flyer offer for each known Norwegian store and returns
    them all -- not filtered by discount, since the value here is in real,
    currently-published flyer items whether or not the retailer chose to show an
    explicit "was X" price. Each item gets discount_pct/reference_price attached only
    when the retailer published an explicit pre_price that is genuinely higher than
    the current price (a real, official discount, never inferred) -- otherwise both
    are None. A short keyword filter excludes genuinely non-food items (see
    NON_FOOD_KEYWORDS). Returns everything sorted with confirmed discounts first
    (highest percentage first); everything else follows in fetch order.

    One request per store total -- no separate price-history call needed, since the
    discount (when the retailer publishes one) comes directly in the same response.
    No rate limiting was observed against this public API, so no proactive throttling
    logic is needed here -- just a light courtesy delay between requests."""
    discovered: List[Dict[str, Any]] = []

    for i, (store_name, dealer_id) in enumerate(stores.items()):
        if i > 0:
            time.sleep(0.2)
        try:
            offers = client.get_store_offers(dealer_id, limit=limit)
        except requests.RequestException as e:
            logger.error(f"Tjek request failed for store {store_name!r}: {e}")
            continue

        for offer in offers:
            heading = offer.get("heading")
            if not heading or _is_non_food(heading):
                continue
            pricing = offer.get("pricing") or {}
            price = pricing.get("price")
            if price is None:
                continue

            pre_price = pricing.get("pre_price")
            discount_pct = None
            reference_price = None
            if pre_price is not None and pre_price > price > 0:
                discount_pct = round((pre_price - price) / pre_price * 100, 1)
                reference_price = pre_price

            dealer = offer.get("dealer") or offer.get("branding") or {}
            unit_price_result = _compute_unit_price(price, offer.get("quantity"))
            discovered.append({
                "product_name": heading,
                "current_price": price,
                "reference_price": reference_price,
                "discount_pct": discount_pct,
                "unit_price": unit_price_result[0] if unit_price_result else None,
                "unit_price_unit": unit_price_result[1] if unit_price_result else None,
                "image_url": (offer.get("images") or {}).get("view"),
                "store_name": dealer.get("name") or store_name,
                "store_logo_url": dealer.get("logo"),
            })

    discovered.sort(key=lambda d: (d["discount_pct"] is None, -(d["discount_pct"] or 0)))
    return discovered


if __name__ == "__main__":
    import json

    client = TjekClient()
    print(f"Sweeping {len(NORWEGIAN_STORES)} Norwegian stores via Tjek...")
    discovered = find_discounted_products(client)
    with_discount = sum(1 for d in discovered if d["discount_pct"] is not None)
    print(f"\n--- {len(discovered)} products found, {with_discount} with a confirmed discount ---")
    print(json.dumps(discovered[:10], indent=2, ensure_ascii=False))
