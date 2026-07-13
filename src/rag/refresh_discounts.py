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

Run with: python -m rag.refresh_discounts
"""

import logging
from datetime import datetime, timedelta, timezone

from .config import RecipeRAGConfig
from .discounts_store import get_latest_snapshot, save_snapshot
from .grocery_discounts import TjekClient, find_discounted_products

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
    scanned_at = datetime.now(timezone.utc).isoformat()
    save_snapshot(config.DISCOUNTS_DB_PATH, discounts, scanned_at)
    with_discount = sum(1 for d in discounts if d.get("discount_pct") is not None)
    logger.info(
        f"Discount scan complete: {len(discounts)} products found, "
        f"{with_discount} with a confirmed discount, cached at {scanned_at}"
    )


if __name__ == "__main__":
    main()
