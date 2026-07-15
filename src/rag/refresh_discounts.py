"""Cron entrypoint: re-fetches every current Tjek (etilbudsavis.dk) flyer offer for each
known Norwegian store and overwrites the cached snapshot that /recipes/discounted serves.
Tjek's flyer offers refresh roughly weekly, but which day varies by chain, and there's no
"has this changed" webhook to react to instead (see grocery_discounts.py's module
docstring) -- so a fixed daily cron schedule is the practical stand-in "we know it's been
updated" signal, cheap enough to run that often (one sweep takes well under a minute, see
grocery_discounts.py's pacing).

Self-healing staleness gate: standard cron does not retry a missed fixed-time firing --
if the host is asleep/offline at exactly the scheduled time, that day's run simply never
happens, with no built-in retry or alert. To guard against the cache silently sitting
stale for days, main() checks the existing snapshot's age before doing a sweep and skips
it if the snapshot is still younger than DISCOUNT_REFRESH_MIN_INTERVAL_HOURS (see
config.py). Pairing this with a *more frequent* cron (e.g. hourly instead of daily) means
any wake-up catches up automatically within that shorter window, while a healthy daily
cron still refreshes once a day exactly as before -- the gate makes the extra invocations
a cheap no-op rather than redundant Tjek sweeps.

Also runs LLM-based category classification (product_classifier.py) for any product
name discounts_store's product_categories cache hasn't seen before -- see that
module's docstring for why this is a same-run-only latency cost (never touches
/recipes/discounted's request path) and why it never permanently sticks a product with
a worse fallback classification just because Ollama was briefly unreachable.

Run with: python -m rag.refresh_discounts
"""

import logging
from datetime import datetime, timedelta, timezone

from .config import RecipeRAGConfig
from .discounts_store import get_cached_categories, get_latest_snapshot, save_categories, save_snapshot
from .grocery_discounts import TjekClient, find_discounted_products
from .generator import RecipeGenerator
from .product_classifier import classify_new_products

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    config = RecipeRAGConfig()

    _, last_scanned_at = get_latest_snapshot(config.DISCOUNTS_DB_PATH)
    if last_scanned_at is not None:
        try:
            last_scanned = datetime.fromisoformat(last_scanned_at)
            if last_scanned.tzinfo is None:
                last_scanned = last_scanned.replace(tzinfo=timezone.utc)
            age = datetime.now(timezone.utc) - last_scanned
            min_interval = timedelta(hours=config.DISCOUNT_REFRESH_MIN_INTERVAL_HOURS)
            if age < min_interval:
                age_hours = age.total_seconds() / 3600
                logger.info(
                    f"Cache still fresh (age {age_hours:.1f}h, threshold "
                    f"{config.DISCOUNT_REFRESH_MIN_INTERVAL_HOURS}h) -- skipping sweep."
                )
                return
        except ValueError:
            # A corrupt/unparseable scanned_at should never wedge the self-healing
            # gate itself into a permanent crash loop -- that's exactly the kind of
            # failure this gate exists to route around. Treat it as "no valid
            # snapshot" and fall through to a fresh sweep.
            logger.warning(f"Unparseable scanned_at {last_scanned_at!r} in cache -- treating as stale.")

    client = TjekClient()
    discounts = find_discounted_products(client)

    # Every item already has a keyword-heuristic category from find_discounted_products()
    # (classify_product() in grocery_discounts.py) -- the LLM classifier below only
    # *upgrades* whichever product names it can confidently classify, cached forever so
    # each name only ever costs one LLM call across all future refreshes. Anything the
    # LLM step can't cover this run (Ollama down, new names beyond what got classified,
    # ...) simply keeps its keyword-heuristic category for now.
    product_names = [d["product_name"] for d in discounts]
    cached_categories = get_cached_categories(config.DISCOUNTS_DB_PATH, product_names)
    uncached_names = [name for name in product_names if name not in cached_categories]

    if uncached_names:
        logger.info(f"Classifying {len(uncached_names)} new product name(s) via {config.CATEGORY_LLM_MODEL}...")
        generator = RecipeGenerator(
            base_url=config.OLLAMA_BASE_URL,
            model=config.CATEGORY_LLM_MODEL,
            api_key=config.OLLAMA_API_KEY,
            api_style=config.LLM_API_STYLE,
        )
        newly_classified = classify_new_products(generator, uncached_names)
        if newly_classified:
            save_categories(config.DISCOUNTS_DB_PATH, newly_classified)
            cached_categories.update(newly_classified)
        logger.info(f"LLM classified {len(newly_classified)}/{len(uncached_names)} new product name(s).")

    for d in discounts:
        llm_category = cached_categories.get(d["product_name"])
        if llm_category:
            d["category"] = llm_category

    scanned_at = datetime.now(timezone.utc).isoformat()
    save_snapshot(config.DISCOUNTS_DB_PATH, discounts, scanned_at)
    with_discount = sum(1 for d in discounts if d.get("discount_pct") is not None)
    logger.info(
        f"Discount scan complete: {len(discounts)} products found, "
        f"{with_discount} with a confirmed discount, cached at {scanned_at}"
    )


if __name__ == "__main__":
    main()
