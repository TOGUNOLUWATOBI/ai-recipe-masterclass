"""Grocery discount detection via Kassalapp (kassal.app) -- a Norwegian grocery
price-comparison API. Powers the discount-driven recipe flow: browse real grocery
products store by store, then feed them into
RecipeRAGPipeline.find_recipes_or_generate() as the ingredient list.

No dedicated "on sale" endpoint or discount flag exists anywhere in Kassalapp's API
(confirmed against the docs at kassal.app/api/docs, the full ProductResource schema, and
all ~49 real product labels -- none are sale-related, all are certifications like
organic/halal/vegan or packaging-material tags). find_discounted_products() therefore
returns EVERY usable food product per swept store, not just ones it can confirm are
discounted -- our own current-price-vs-history comparison is informative when available,
but is not reliable enough to use as an inclusion filter: confirmed live that a real,
significant fraction of products (roughly half, in one live sample of "pølser"/sausage
products across several stores) have NO price history at all, so a real, currently
advertised discount can be silently invisible to this method purely because Kassalapp
hasn't recorded enough history for that specific product yet. Filtering strictly by a
computed discount_pct would (and did) hide a large share of genuinely on-sale food next
to items we simply can't evaluate -- there's no way to tell those two cases apart from
the API alone, so both must be shown, with a discount badge attached only when the
comparison is actually possible and meaningful. Results are sorted with the highest
confirmed discounts first; everything else (including items with no computable discount
at all) follows.

Sweeps by STORE (GROCERY_STORE_GROUPS), not by a curated ingredient/category roster --
confirmed live that Kassalapp's /products endpoint accepts a store filter (e.g.
store=KIWI) with no location required, returning that chain's catalog nationally. A
single store query (size=100, unique=1) already surfaces excellent category diversity
(96 distinct leaf categories observed in one 100-product sample) at a fraction of the
API cost of sweeping category-by-category: 14 grocery store groups need only ~28
Kassalapp calls total (one search + one batched price-history call per store),
comfortably under the account-wide 60-request rate limit -- unlike the category-sweep
approach this replaces, a full run typically completes without needing the rate-limit
cooldown pause at all.

Categorization for display grouping happens client-side, using each product's own
top-level (depth=-2) category from its embedded category array -- confirmed live this
gives a clean, small set of aisle-like buckets (Kjøtt, Frukt & grønt, Meieri & egg, Ost,
Bakeri, ...) across real multi-store samples, unlike the much more granular depth=0 leaf
category (96 distinct leaf names in the same 100-product sample -- too fragmented to
group by). A handful of top-level buckets aren't food at all (Personlige artikler,
Hus & hjem, Barneprodukter) and are filtered out.

Store groups are Kassalapp's real, documented enum (confirmed against their OpenAPI spec
at kassal.app/docs/api.json) -- GROCERY_STORE_GROUPS is deliberately the conservative
subset: clearly non-grocery chains (ARK/NORLI/ADLIBRIS are bookstores;
COOP_BYGGMIX/COOP_OBS_BYGG/COOP_ELEKTRO are hardware/electronics) and several
grocery-adjacent-but-uncertain chains (Havaristen, Holdbart, Matkroken, Naerbutikken,
Fudi, Engrossnett) are excluded rather than guessed at.

IMPORTANT (confirmed live, 2026-07-08): the price_history array embedded directly in
/products search results is NOT a reliable "recent" window -- three sample products
showed embedded histories spanning 2022-11 to 2023-01, 2024-12 to 2025-04, and 2026-06 to
2026-07 respectively, wildly inconsistent and often stale by years. Do NOT use the
embedded price_history to compute a discount -- always use the dedicated
/products/prices-bulk?days=N endpoint (via get_price_history_bulk), which reliably
returns a real recent window (confirmed against several products).

Kassalapp enforces an account-wide rate limit of 60 requests per rolling window, shared
across all endpoints (confirmed live via X-RateLimit-Remaining, present on every
response) with no Retry-After or X-RateLimit-Reset header ever provided -- see
_maybe_wait_for_rate_limit for how a full sweep proactively avoids exhausting it.

VERIFIED LIVE (2026-07-06, 2026-07-08) against a real API key -- response shapes, store
group enum, category taxonomy/hierarchy, price_history reliability, rate limits, and
per-store category diversity are all confirmed empirically, not assumed from
documentation alone.
"""

import logging
import re
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# Kassalapp's real store-group enum (confirmed against their OpenAPI spec), filtered to
# grocery/food chains -- excludes clearly non-grocery groups (ARK/NORLI/ADLIBRIS are
# bookstores; COOP_BYGGMIX/COOP_OBS_BYGG/COOP_ELEKTRO are hardware/electronics) and
# several grocery-adjacent-but-unconfirmed chains (Havaristen, Holdbart, Matkroken,
# Naerbutikken, Fudi, Engrossnett) -- deliberately excluded rather than guessed at.
#
# Also excludes Coop's specific store-format codes (COOP_MARKED, COOP_MEGA, COOP_PRIX,
# COOP_OBS) -- confirmed live these return ZERO products even at size=100, and
# COOP_EXTRA returns exactly one (non-food). Coop's real catalog data in Kassalapp lives
# under the generic COOP_NO code instead, not per physical-format banner -- these four
# would be pure wasted API calls (2 each) for no data, and COOP_EXTRA one call for a
# single irrelevant result.
GROCERY_STORE_GROUPS = [
    "MENY_NO", "SPAR_NO", "JOKER_NO", "ODA_NO", "BUNNPRIS", "KIWI", "REMA_1000",
    "EUROPRIS_NO", "COOP_NO",
]

# Top-level (depth=-2) categories that aren't food -- confirmed live these appear
# alongside real groceries in a per-store product listing (Kassalapp isn't a
# grocery-only catalog).
NON_FOOD_TOP_LEVEL_CATEGORIES = {"Personlige artikler", "Hus & hjem", "Barneprodukter"}


class KassalappClient:
    def __init__(self, api_key: str, base_url: str, timeout: float = 15.0):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.rate_limit_remaining: Optional[int] = None

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}

    def _update_rate_limit(self, response: requests.Response) -> None:
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            try:
                self.rate_limit_remaining = int(remaining)
            except ValueError:
                pass

    def search_products(
        self,
        search: Optional[str] = None,
        category: Optional[str] = None,
        store: Optional[str] = None,
        unique: Optional[int] = None,
        size: int = 5,
    ) -> List[Dict[str, Any]]:
        """search, category, and store are independent filters. store (e.g. "KIWI",
        "COOP_NO") scopes to one chain's catalog nationally -- no location required
        (confirmed live). unique=1 collapses duplicate EAN results server-side."""
        params: Dict[str, Any] = {"size": size}
        if search:
            params["search"] = search
        if category:
            params["category"] = category
        if store:
            params["store"] = store
        if unique is not None:
            params["unique"] = unique
        resp = requests.get(
            f"{self.base_url}/products",
            headers=self._headers(),
            params=params,
            timeout=self.timeout,
        )
        self._update_rate_limit(resp)
        resp.raise_for_status()
        return resp.json().get("data", [])

    def get_price_history_bulk(self, eans: List[str], days: int = 30, aggregation: str = "avg") -> Dict[str, Any]:
        """Max 100 EANs per call per the API docs -- find_discounted_products batches
        every candidate from one swept store into a single call, comfortably staying
        under that limit (a single store query is itself capped at size=100)."""
        resp = requests.post(
            f"{self.base_url}/products/prices-bulk",
            headers=self._headers(),
            json={"eans": eans, "days": days, "aggregation": aggregation},
            timeout=self.timeout,
        )
        self._update_rate_limit(resp)
        resp.raise_for_status()
        return resp.json()


RATE_LIMIT_SAFETY_THRESHOLD = 3
RATE_LIMIT_COOLDOWN_SECONDS = 61.0


def _maybe_wait_for_rate_limit(
    client: KassalappClient,
    threshold: int = RATE_LIMIT_SAFETY_THRESHOLD,
    cooldown: float = RATE_LIMIT_COOLDOWN_SECONDS,
) -> None:
    """Proactively pauses once the tracked budget gets low rather than reactively
    handling 429s after the fact. Guarded with isinstance rather than a plain None
    check so a test double (MagicMock) whose .rate_limit_remaining was never explicitly
    set -- not a real int -- is correctly treated as unknown, not low."""
    remaining = client.rate_limit_remaining
    if isinstance(remaining, int) and remaining <= threshold:
        logger.info(
            f"Kassalapp rate limit budget low ({remaining} remaining) -- "
            f"pausing {cooldown}s to let it reset before continuing the scan"
        )
        time.sleep(cooldown)
        client.rate_limit_remaining = None


def _percent_below(current: float, reference: float) -> float:
    if reference <= 0:
        return 0.0
    return max(0.0, (reference - current) / reference * 100)


def _extract_reference_price(history_response: Dict[str, Any], ean: str) -> Optional[float]:
    """Averages the daily price_history entries for the given EAN, from the dedicated
    /products/prices-bulk response -- never from the price_history sometimes embedded
    directly in /products search results, which was found to span wildly inconsistent
    and often stale date ranges (see module docstring) and must never be used for this
    calculation."""
    try:
        for entry in history_response.get("data", []):
            if entry.get("ean") == ean:
                prices = [p["price"] for p in entry.get("price_history", []) if p.get("price") is not None]
                if prices:
                    return sum(prices) / len(prices)
    except (AttributeError, TypeError, ValueError) as e:
        logger.warning(f"Unexpected prices-bulk response shape for EAN {ean}: {e}")
    return None


_BABY_FOOD_AGE_PATTERN = re.compile(r"\d+\s*mnd\b")


def _is_baby_food(product: Dict[str, Any]) -> bool:
    """Kept as a secondary signal alongside the top-level-category exclusion in
    _is_non_food -- catches baby food that might not be tagged under the
    "Barneprodukter" top-level category."""
    categories = [c.get("name", "") for c in (product.get("category") or [])]
    if any(cat in ("Barnemat", "Barneprodukter") for cat in categories):
        return True
    if "barnemat" in (product.get("brand") or "").lower():
        return True
    return bool(_BABY_FOOD_AGE_PATTERN.search((product.get("name") or "").lower()))


def _top_level_category(product: Dict[str, Any]) -> Optional[str]:
    """The broadest category name for a product -- confirmed live this gives a clean,
    small set of aisle-like buckets (~18 across a real multi-store sample: Kjøtt,
    Frukt & grønt, Meieri & egg, Ost, ...) suitable for grouping discounted products for
    display, unlike the much more granular leaf category (96 distinct leaf names in the
    same sample). Uses whichever entry has the MINIMUM depth, not a hardcoded -2 --
    confirmed live that category hierarchy depth isn't consistent across product types:
    most have 3 levels (-2/-1/0), but e.g. Coca-Cola's only has 2
    ([{"depth": -1, "name": "Drikke"}, {"depth": 0, "name": "Brus"}], no -2 entry at
    all) -- a hardcoded depth=-2 check silently missed these, dumping otherwise
    well-categorized products into the "Annet" fallback."""
    categories = product.get("category") or []
    if not categories:
        return None
    return min(categories, key=lambda c: c.get("depth", 0)).get("name")


def _is_non_food(product: Dict[str, Any]) -> bool:
    """A per-store product listing isn't food-only -- confirmed live that a single
    store query surfaces top-level categories like "Personlige artikler" (personal
    care) and "Hus & hjem" (household goods) alongside real groceries."""
    return _top_level_category(product) in NON_FOOD_TOP_LEVEL_CATEGORIES


def _filter_usable_candidates(products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every non-baby-food, food-category product with a usable ean+current_price --
    the full candidate pool for a store sweep. Every usable candidate here gets
    evaluated for a discount, not just one hand-picked representative."""
    usable = [p for p in products if p.get("ean") and p.get("current_price") is not None]
    return [p for p in usable if not _is_non_food(p) and not _is_baby_food(p)]


def find_discounted_products(
    client: KassalappClient,
    store_groups: List[str] = GROCERY_STORE_GROUPS,
    threshold_pct: float = 15.0,
    history_days: int = 30,
    size: int = 100,
) -> List[Dict[str, Any]]:
    """Sweeps every grocery store group and returns EVERY usable food product each store
    turns up -- not just ones we can confirm are discounted (see module docstring for
    why: no official sale flag exists, and a real fraction of products have no price
    history at all, making "no computable discount" indistinguishable from "genuinely
    not on sale"). Each item is labeled with its own top-level Kassalapp category (e.g.
    "Kjøtt", "Frukt & grønt") for display grouping, since the sweep axis here is the
    store, not a curated ingredient/category roster. A product gets discount_pct/
    reference_price attached only when its current price is at least threshold_pct
    below its own recent (history_days-day) average -- otherwise both are None, so the
    caller can render a badge only where the comparison is real and meaningful rather
    than showing a misleading 0%. The returned list is sorted with confirmed discounts
    first (highest first); everything else follows in sweep order.

    Each swept store costs at most 2 Kassalapp calls regardless of how many candidates
    it turns up -- one search (unique=1 collapses duplicate EANs server-side), plus one
    batched price-history-bulk call covering every candidate's EAN at once (skipped
    entirely if a store turns up no usable candidates at all). Deliberately does NOT
    deduplicate by EAN across different stores -- the same product can be independently
    priced (and independently discounted) at more than one chain, and this is now a
    per-store browse, not a single merged "is this discounted anywhere" list, so every
    store's own listing must be shown in full."""
    discovered: List[Dict[str, Any]] = []

    for i, store in enumerate(store_groups):
        if i > 0:
            time.sleep(0.3)
        _maybe_wait_for_rate_limit(client)

        try:
            products = client.search_products(store=store, size=size, unique=1)
        except requests.RequestException as e:
            logger.error(f"Kassalapp search failed for store {store!r}: {e}")
            continue

        candidates = _filter_usable_candidates(products)
        if not candidates:
            continue
        by_ean = {p["ean"]: p for p in candidates}

        time.sleep(0.3)
        _maybe_wait_for_rate_limit(client)
        history = None
        try:
            history = client.get_price_history_bulk(list(by_ean.keys()), days=history_days, aggregation="avg")
        except requests.RequestException as e:
            logger.error(f"Kassalapp price history failed for store {store!r}: {e}")
            # Still shown below, just without discount info -- a failed price lookup
            # isn't a reason to hide the store's products entirely.

        for ean, product in by_ean.items():
            discount_pct = None
            reference_price = None
            raw_reference = _extract_reference_price(history, ean) if history is not None else None
            if raw_reference is not None:
                pct = _percent_below(product["current_price"], raw_reference)
                if pct >= threshold_pct:
                    discount_pct = round(pct, 1)
                    reference_price = raw_reference

            product_store = product.get("store") or {}
            discovered.append({
                "category": _top_level_category(product) or "Annet",
                "product_name": product.get("name"),
                "current_price": product["current_price"],
                "reference_price": reference_price,
                "discount_pct": discount_pct,
                "unit_price": product.get("current_unit_price"),
                "image_url": product.get("image"),
                "store_name": product_store.get("name"),
                "store_logo_url": product_store.get("logo"),
            })

    discovered.sort(key=lambda d: (d["discount_pct"] is None, -(d["discount_pct"] or 0)))
    return discovered


if __name__ == "__main__":
    import json

    from .config import RecipeRAGConfig

    config = RecipeRAGConfig()
    if not config.KASSALAPP_API_KEY:
        raise SystemExit("KASSALAPP_API_KEY not set -- add it to src/rag/.env")
    client = KassalappClient(config.KASSALAPP_API_KEY, config.KASSALAPP_BASE_URL)

    print(f"Sweeping {len(GROCERY_STORE_GROUPS)} store groups...")
    discovered = find_discounted_products(client)
    print(f"\n--- {len(discovered)} discounted products found ---")
    print(json.dumps(discovered, indent=2, ensure_ascii=False))
