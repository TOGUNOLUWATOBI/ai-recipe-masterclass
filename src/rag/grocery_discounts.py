"""Grocery discount detection via Kassalapp (kassal.app) — a Norwegian grocery
price-comparison API. Foundation for the v2 discount-driven recipe flow: pull current
discounts on common recipe ingredients, feed them into
RecipeRAGPipeline.find_recipes_or_generate() as the ingredient list.

No dedicated "on sale" endpoint exists (confirmed against the docs at
kassal.app/api/docs) — the site has "Prisfall" (price drop) features but they aren't
exposed via the documented API. So discount detection happens here: fetch a product's
current price plus its recent price history, and flag it as discounted if the current
price sits meaningfully below the recent average.

Product lookup is category-scoped wherever possible, not free-text search on the
translated ingredient name — confirmed live that free-text search is unreliable for
this domain: searching "kylling" (chicken) returned 10/10 baby food and deli-cold-cut
results on the first page (Kassalapp's search does loose substring matching, and short
Norwegian food words are frequently embedded in unrelated brand/product names — "løk"
(onion) matches inside "Hvitløk" (garlic), "mel" (flour) matches inside "karaMEL"). By
contrast, GET /products?category=Kylling (using the real category taxonomy from
GET /categories, ~2000 entries) returned 8/8 genuine raw chicken products with zero
noise. TRACKED_INGREDIENTS maps each ingredient to its Kassalapp category name where one
cleanly exists; a few (garlic, carrots, spinach) have no single-purpose leaf category in
the taxonomy and fall back to translated free-text search plus the heuristics below.

Kassalapp product names are Norwegian; the RAG corpus and recipe generation are English.
For the free-text fallback path, get_norwegian_term() translates on demand via
MyMemory's free translation API (no key required, keeps pipeline-service free of heavy
ML translation libraries) instead of a hand-maintained EN/NO dictionary, which doesn't
scale and is easy to get subtly wrong. Results are cached in-memory for the life of the
process — food-word translations don't change, so there's no reason to re-call the API
every discount scan.

VERIFIED LIVE (2026-07-06) against a real API key — response shapes, category taxonomy,
and the search-quality issues described above are all confirmed empirically, not
assumed from documentation alone.
"""

import logging
import re
import time
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

# English ingredient -> Kassalapp category name, built from the live category taxonomy
# (GET /categories). category=None means no clean single-purpose leaf category exists
# for this ingredient in the ~2000-entry taxonomy (checked, not guessed) — these fall
# back to translated free-text search (get_norwegian_term + _select_representative_product)
# instead.
TRACKED_INGREDIENTS = [
    {"en": "chicken", "category": "Kylling"},
    {"en": "ground beef", "category": "Kjøtt"},
    {"en": "pork", "category": "Kjøtt"},
    {"en": "salmon", "category": "Laks"},
    {"en": "cod", "category": "Torsk"},
    {"en": "shrimp", "category": "Reker"},
    {"en": "bacon", "category": "Bacon"},
    {"en": "sausage", "category": "Pølser"},
    {"en": "eggs", "category": "Egg"},
    {"en": "milk", "category": "Melk"},
    {"en": "butter", "category": "Smør og margarin"},
    {"en": "cheese", "category": "Ost"},
    {"en": "cream", "category": "Fløte"},
    {"en": "sour cream", "category": "Rømme"},
    {"en": "yogurt", "category": "Yoghurt"},
    {"en": "potatoes", "category": "Poteter"},
    {"en": "onions", "category": "Løk"},
    {"en": "garlic", "category": None},
    {"en": "carrots", "category": None},
    {"en": "tomatoes", "category": "Tomater"},
    {"en": "bell peppers", "category": "Paprika"},
    {"en": "cucumber", "category": "Agurk"},
    {"en": "cabbage", "category": "Kål"},
    {"en": "broccoli", "category": "Kål"},
    {"en": "spinach", "category": None},
    {"en": "mushrooms", "category": "Sopp"},
    {"en": "apples", "category": "Epler"},
    {"en": "bananas", "category": "Bananer"},
    {"en": "lemons", "category": "Sitrusfrukt"},
    {"en": "rice", "category": "Ris"},
    {"en": "pasta", "category": "Pasta"},
    {"en": "bread", "category": "Brød"},
    {"en": "flour", "category": "Mel"},
    {"en": "sugar", "category": "Sukker"},
]

# Manual overrides for terms where automatic translation is technically correct but
# returns an overly formal/rare synonym instead of the everyday grocery-shelf word —
# found via live testing, not guessed. Used for BOTH the free-text fallback path
# (garlic/carrots/spinach) and as the disambiguating term within category-scoped
# results for everything else — a bad translation breaks both equally.
TRANSLATION_OVERRIDES = {
    "salmon": "laks",  # MyMemory: "atlanterhavslaks" ("Atlantic salmon") matched zero products
    "butter": "smør",  # MyMemory: "påleggssalat og smørepålegg" (a nonsense compound phrase)
}

_translation_cache: Dict[str, str] = {}


def get_norwegian_term(english_term: str, timeout: float = 10.0) -> str:
    """Translates an English ingredient name to Norwegian via MyMemory's free
    translation API (checking TRANSLATION_OVERRIDES first). Falls back to the English
    term unchanged on any failure — Kassalapp just won't find a match for an
    untranslated English search term, which is a quieter failure than raising and
    aborting the whole discount scan over one bad translation."""
    if english_term in _translation_cache:
        return _translation_cache[english_term]

    if english_term in TRANSLATION_OVERRIDES:
        translated = TRANSLATION_OVERRIDES[english_term]
        _translation_cache[english_term] = translated
        return translated

    try:
        resp = requests.get(
            "https://api.mymemory.translated.net/get",
            params={"q": english_term, "langpair": "en|no"},
            timeout=timeout,
        )
        resp.raise_for_status()
        translated = resp.json()["responseData"]["translatedText"].strip().lower()
    except (requests.RequestException, KeyError, ValueError) as e:
        logger.warning(f"Translation failed for {english_term!r}, using English term as-is: {e}")
        translated = english_term

    _translation_cache[english_term] = translated
    return translated


class KassalappClient:
    def __init__(self, api_key: str, base_url: str, timeout: float = 15.0):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}

    def search_products(
        self, search: Optional[str] = None, category: Optional[str] = None, size: int = 5
    ) -> List[Dict[str, Any]]:
        """search and category are independent filters — pass category alone for a
        clean category-scoped listing (the preferred path, see module docstring), or
        search alone for free-text search (the noisier fallback for ingredients with no
        clean category)."""
        params: Dict[str, Any] = {"size": size}
        if search:
            params["search"] = search
        if category:
            params["category"] = category
        resp = requests.get(
            f"{self.base_url}/products",
            headers=self._headers(),
            params=params,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json().get("data", [])

    def get_price_history_bulk(self, eans: List[str], days: int = 30, aggregation: str = "avg") -> Dict[str, Any]:
        """Max 100 EANs per call per the API docs — not enforced here since
        TRACKED_INGREDIENTS is far below that, but a future broader sweep would need to
        batch this."""
        resp = requests.post(
            f"{self.base_url}/products/prices-bulk",
            headers=self._headers(),
            json={"eans": eans, "days": days, "aggregation": aggregation},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()


def _percent_below(current: float, reference: float) -> float:
    """Non-negative by contract — a price at or above the reference isn't "below" it at
    all, so it reports 0%, not a negative discount."""
    if reference <= 0:
        return 0.0
    return max(0.0, (reference - current) / reference * 100)


def _extract_reference_price(history_response: Dict[str, Any], ean: str) -> Optional[float]:
    """Averages the daily price_history entries for the given EAN. Verified live against
    the real API: /products/prices-bulk returns data[].price_history[] (a full list of
    {price, date, store} entries), not a single pre-aggregated value — the "aggregation"
    request param does not collapse this server-side despite what the docs implied, so
    aggregation happens here instead. Falls back to "no data" (returns None) rather than
    raising on a shape mismatch, so one product's unexpected response degrades gracefully
    instead of crashing the whole discount scan."""
    try:
        for entry in history_response.get("data", []):
            if entry.get("ean") == ean:
                prices = [p["price"] for p in entry.get("price_history", []) if p.get("price") is not None]
                if prices:
                    return sum(prices) / len(prices)
    except (AttributeError, TypeError, ValueError) as e:
        logger.warning(f"Unexpected prices-bulk response shape for EAN {ean}: {e}")
    return None


_BABY_FOOD_AGE_PATTERN = re.compile(r"\d+\s*mnd\b")  # "6mnd", "8 mnd" — Norwegian for "N months"


def _is_baby_food(product: Dict[str, Any]) -> bool:
    """Only relevant to the free-text fallback path (category-scoped search doesn't
    surface baby food at all). Confirmed live that a plain category check isn't enough
    on its own: searching "kylling" (chicken) returned 10/10 baby food results, from at
    least three different signals depending on the brand — some tag category
    (Barnemat/Barneprodukter), some don't but follow the "Nmnd" age-in-months naming
    convention (Hipp/Nestle/Semper), and at least one (Alex&Phil) has neither but
    states it right in the brand field ("Alex&phil barnemat"). Checking all three
    catches more real cases than any one alone."""
    categories = [c.get("name", "") for c in (product.get("category") or [])]
    if any(cat in ("Barnemat", "Barneprodukter") for cat in categories):
        return True
    if "barnemat" in (product.get("brand") or "").lower():
        return True
    return bool(_BABY_FOOD_AGE_PATTERN.search((product.get("name") or "").lower()))


def _name_matches_term(name: str, term: str) -> bool:
    """True if any individual word in the product name starts with term — not the same
    as checking whether the whole name starts with it (misses brand-first names like
    "Prior Egg 12stk" for "egg" — confirmed live that's a common Norwegian retail
    naming pattern) and not the same as a plain substring check either (which is what
    caused the original problem: "løk" matching inside "Hvitløk", a different
    vegetable). Checking each word's prefix threads both needles: "kyllingfilet"
    (one word) still matches "kylling", "prior egg 12stk" matches "egg" via its second
    word, and "hvitløkspate" still correctly does NOT match "løk" (no word starts with
    it)."""
    words = re.findall(r"\w+", name.lower())
    return any(word.startswith(term) for word in words)


def _select_representative_product(products: List[Dict[str, Any]], search_term: str) -> Optional[Dict[str, Any]]:
    """Prefers a non-baby-food product with a usable ean+current_price where some word
    in the name matches the search term (see _name_matches_term), over one where the
    search term is just a minor ingredient mention in an unrelated prepared product.
    Used for both the category-scoped path (to disambiguate ingredients sharing a
    broad category, e.g. pork vs. ground beef both under "Kjøtt") and the free-text
    fallback path. Requiring ean+price upfront (rather than the caller discovering a
    missing one after selection) avoids picking an otherwise-good-looking match that
    can't actually be priced. Falls back to the first usable non-baby-food result, then
    the first usable result of any kind, then None if nothing has a usable price at
    all."""
    usable = [p for p in products if p.get("ean") and p.get("current_price") is not None]
    candidates = [p for p in usable if not _is_baby_food(p)] or usable
    search_lower = search_term.lower()
    for product in candidates:
        if _name_matches_term(product.get("name") or "", search_lower):
            return product
    return candidates[0] if candidates else None


def find_discounted_ingredients(
    client: KassalappClient,
    tracked: List[Dict[str, Optional[str]]] = TRACKED_INGREDIENTS,
    threshold_pct: float = 15.0,
    history_days: int = 30,
) -> List[Dict[str, Any]]:
    """Returns tracked ingredients currently priced at least threshold_pct below their
    recent average — the discount candidates to feed into the recipe pipeline. Checks
    only one representative product per ingredient (category-scoped listing when a
    clean category exists, translated free-text search otherwise) rather than every
    matching product/store — good enough for "is this ingredient generally on sale
    right now," not a precise multi-store comparison."""
    discounted = []
    for i, ingredient in enumerate(tracked):
        ingredient_en = ingredient["en"]
        category = ingredient.get("category")
        # Used to disambiguate WITHIN the candidate pool (category listing or free-text
        # results), not necessarily as the search query itself — confirmed live that a
        # shared broad category isn't enough alone: "pork" and "ground beef" both map
        # to "Kjøtt" and naively taking the first result picked the identical beef
        # product for both, same for "cabbage"/"broccoli" both under "Kål". Matching
        # each ingredient's own translated term against candidate names, even within an
        # already category-narrowed pool, is what actually tells them apart.
        ingredient_no = get_norwegian_term(ingredient_en)

        if i > 0:
            time.sleep(0.3)  # observed a 429 (rate limit) partway through an unpaced sweep of 33 ingredients

        try:
            if category:
                products = client.search_products(category=category, size=20)
            else:
                products = client.search_products(search=ingredient_no, size=20)
            product = _select_representative_product(products, ingredient_no)
        except requests.RequestException as e:
            logger.error(f"Kassalapp search failed for {ingredient_en!r}: {e}")
            continue

        if product is None:
            continue
        ean = product["ean"]
        current_price = product["current_price"]

        time.sleep(0.3)
        try:
            history = client.get_price_history_bulk([ean], days=history_days, aggregation="avg")
        except requests.RequestException as e:
            logger.error(f"Kassalapp price history failed for EAN {ean}: {e}")
            continue

        reference_price = _extract_reference_price(history, ean)
        if reference_price is None:
            continue

        pct = _percent_below(current_price, reference_price)
        if pct >= threshold_pct:
            discounted.append({
                "ingredient_en": ingredient_en,
                "product_name": product.get("name"),
                "current_price": current_price,
                "reference_price": reference_price,
                "discount_pct": round(pct, 1),
            })

    return discounted


if __name__ == "__main__":
    # Live verification script — prints every tracked ingredient's resolved product and
    # price, not just ones that clear the discount threshold, so you can sanity-check
    # the lookup itself (right product? real price?) independent of whether anything
    # happens to be on sale today.
    import json

    from .config import RecipeRAGConfig  # loads src/rag/.env as a side effect

    config = RecipeRAGConfig()
    if not config.KASSALAPP_API_KEY:
        raise SystemExit("KASSALAPP_API_KEY not set — add it to src/rag/.env")
    client = KassalappClient(config.KASSALAPP_API_KEY, config.KASSALAPP_BASE_URL)

    import time

    print(f"{'ingredient':14} {'lookup':20} {'product':45} {'current':>8} {'ref_avg':>8} {'pct_below':>10}")
    for ingredient in TRACKED_INGREDIENTS:
        ingredient_en = ingredient["en"]
        category = ingredient.get("category")
        ingredient_no = get_norwegian_term(ingredient_en)
        lookup = f"category={category}" if category else f"search={ingredient_no}"

        if category:
            products = client.search_products(category=category, size=20)
        else:
            products = client.search_products(search=ingredient_no, size=20)
        product = _select_representative_product(products, ingredient_no)

        if product is None:
            print(f"{ingredient_en:14} {lookup:20} NO USABLE PRODUCT FOUND")
            continue

        time.sleep(0.3)  # observed a 429 (rate limit) partway through an unpaced sweep of 33 ingredients
        history = client.get_price_history_bulk([product["ean"]], days=30, aggregation="avg")
        ref = _extract_reference_price(history, product["ean"])
        pct = _percent_below(product["current_price"], ref) if ref else None
        print(
            f"{ingredient_en:14} {lookup:20} {product.get('name', '')!r:45} "
            f"{product['current_price']:>8} {round(ref, 2) if ref else 'None':>8} "
            f"{round(pct, 1) if pct is not None else 'None':>10}"
        )

    print("\n--- find_discounted_ingredients (threshold_pct=15.0) ---")
    discounts = find_discounted_ingredients(client)
    print(json.dumps(discounts, indent=2, ensure_ascii=False))
