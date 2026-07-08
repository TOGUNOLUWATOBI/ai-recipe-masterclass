"""Cron entrypoint: re-scans Kassalapp for currently discounted grocery products and
overwrites the cached snapshot that /recipes/discounted serves. Kassalapp's grocery
offers refresh roughly weekly, but which day varies by chain, and there's no
"has this changed" webhook to react to instead (confirmed against their docs — see
grocery_discounts.py's module docstring) — so a fixed daily cron schedule is the
practical stand-in "we know it's been updated" signal, cheap enough to run that often
(one scan takes well under a minute, see grocery_discounts.py's pacing).

Run with: python -m rag.refresh_discounts
"""

import logging
from datetime import datetime, timezone

from .config import RecipeRAGConfig
from .discounts_store import save_snapshot
from .grocery_discounts import KassalappClient, find_discounted_products

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    config = RecipeRAGConfig()
    if not config.KASSALAPP_API_KEY:
        raise SystemExit("KASSALAPP_API_KEY not set — add it to src/rag/.env")

    client = KassalappClient(config.KASSALAPP_API_KEY, config.KASSALAPP_BASE_URL)
    discounts = find_discounted_products(
        client,
        threshold_pct=config.DISCOUNT_THRESHOLD_PCT,
        history_days=config.DISCOUNT_PRICE_HISTORY_DAYS,
    )
    scanned_at = datetime.now(timezone.utc).isoformat()
    save_snapshot(config.DISCOUNTS_DB_PATH, discounts, scanned_at)
    with_discount = sum(1 for d in discounts if d.get("discount_pct") is not None)
    logger.info(
        f"Discount scan complete: {len(discounts)} products found, "
        f"{with_discount} with a confirmed discount, cached at {scanned_at}"
    )


if __name__ == "__main__":
    main()
