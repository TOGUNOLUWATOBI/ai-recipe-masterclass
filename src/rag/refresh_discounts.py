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

Epic A classification pipeline (Task A3's processing order), applied once per scan:
  1. Manual overrides (product_classification.load_manual_overrides()) -- always win,
     re-applied and re-cached every run so an override added today takes effect
     immediately even for products already cached under a different classification.
  2. Deterministic keyword heuristic (grocery_discounts.classify_product()) -- already
     computed inline for every item by find_discounted_products(); the baseline used
     for anything the two steps below don't upgrade.
  3. Permanent classification cache (discounts_store.product_classifications) -- a
     product already classified by the LLM (or previously overridden) is never
     re-sent to it.
  4. The LLM classifier (product_classifier.py) for whatever's left: names that are
     neither manually overridden nor already cached. Its response is schema-validated
     before it's trusted (see product_classification.validate_llm_entry()) and a
     genuinely uncertain verdict (confidence="low") collapses to food_usage_class=
     "unknown", which recipe_eligible is always False for -- see product_classification
     .build_classification() for why this is computed once, not decided per-caller.
  5. Whatever the LLM classified successfully is stored permanently; a call failure or
     invalid entry is simply left uncached so it's retried on the next refresh instead
     of poisoning the cache with a low-confidence guess (see product_classifier.py).

Run with: python -m rag.refresh_discounts
"""

import logging
from datetime import datetime, timedelta, timezone

from .config import RecipeRAGConfig
from .discounts_store import (
    get_cached_classifications,
    get_latest_snapshot,
    open_connection,
    save_classifications,
    save_snapshot,
)
from .generator import RecipeGenerator
from .grocery_discounts import TjekClient, find_discounted_products
from .product_classification import CLASSIFIER_VERSION, ProductClassification, legacy_category, load_manual_overrides
from .product_classifier import classify_new_products

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _apply_classification(item: dict, classification: ProductClassification) -> None:
    """Overwrites a discovered item's classification fields (in place) with a more
    trustworthy result than the keyword heuristic already attached, including the
    legacy `category` label so it never drifts out of sync with the richer fields
    underneath it (e.g. a heuristic false-negative the LLM catches as a snack must
    also flip `category` from "main_food" to "snack")."""
    item["shopping_group"] = classification["shopping_group"]
    item["food_usage_class"] = classification["food_usage_class"]
    item["meal_role"] = classification["meal_role"]
    item["recipe_eligible"] = classification["recipe_eligible"]
    item["recipe_exclusion_reason"] = classification["recipe_exclusion_reason"]
    item["category"] = legacy_category(classification)


def main() -> None:
    config = RecipeRAGConfig()

    # One connection for the whole run -- every discounts_store call below threads it
    # through via `conn=` instead of each opening (and schema-checking) its own, since
    # a single refresh already makes 3-5 of these calls back to back.
    with open_connection(config.DISCOUNTS_DB_PATH) as conn:
        _, last_scanned_at = get_latest_snapshot(config.DISCOUNTS_DB_PATH, conn=conn)
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

        # Step 1: manual overrides -- always win, re-applied to every matching item
        # every run. Only re-cached (source="manual_override") for names whose cached
        # classification actually differs from the override -- a name already cached
        # with the exact same override values (the common case: the override file
        # rarely changes between runs) needs no DB write, just the in-memory apply
        # below, so J2's "percentage manually overridden" tracking still reflects the
        # true classified_at of when that override actually took effect rather than
        # being bumped to "now" on every single scan.
        overrides = load_manual_overrides()
        product_names = [d["product_name"] for d in discounts]
        matched_overrides = {name: overrides[name] for name in product_names if name in overrides}
        if matched_overrides:
            already_cached = get_cached_classifications(config.DISCOUNTS_DB_PATH, list(matched_overrides), conn=conn)
            changed_overrides = {
                name: c for name, c in matched_overrides.items() if already_cached.get(name) != c
            }
            if changed_overrides:
                save_classifications(
                    config.DISCOUNTS_DB_PATH, changed_overrides,
                    classification_source="manual_override", classified_at=scanned_at,
                    classifier_version=CLASSIFIER_VERSION, classification_confidence="high",
                    conn=conn,
                )
            for d in discounts:
                if d["product_name"] in matched_overrides:
                    _apply_classification(d, matched_overrides[d["product_name"]])

        # Step 2 already happened inline: find_discounted_products() ran the keyword
        # heuristic (grocery_discounts.classify_product()) for every item. That's the
        # baseline for anything not covered by an override or the steps below.

        # Step 3: permanent classification cache -- skip the LLM entirely for anything
        # already classified by a previous run (whether that earlier run used the LLM
        # or a manual override that's since been removed from the override file).
        remaining_names = [name for name in product_names if name not in matched_overrides]
        cached = get_cached_classifications(config.DISCOUNTS_DB_PATH, remaining_names, conn=conn)
        for d in discounts:
            name = d["product_name"]
            if name in cached:
                _apply_classification(d, cached[name])

        # Step 4: send whatever's left -- never manually overridden, never cached -- to
        # the LLM classifier.
        uncached_names = [name for name in remaining_names if name not in cached]
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
                # Step 5: store permanently (source="llm"). Confidence isn't tracked
                # per-item here since classify_new_products() already folded a
                # self-reported "low" confidence into food_usage_class="unknown" (see
                # product_classification.validate_llm_entry()) before returning --
                # anything that reaches this point was at least medium-confidence.
                save_classifications(
                    config.DISCOUNTS_DB_PATH, newly_classified,
                    classification_source="llm", classified_at=scanned_at,
                    classifier_version=CLASSIFIER_VERSION, classification_confidence="medium",
                    conn=conn,
                )
                for d in discounts:
                    if d["product_name"] in newly_classified:
                        _apply_classification(d, newly_classified[d["product_name"]])
            logger.info(f"LLM classified {len(newly_classified)}/{len(uncached_names)} new product name(s).")

        save_snapshot(config.DISCOUNTS_DB_PATH, discounts, scanned_at, conn=conn)

    with_discount = sum(1 for d in discounts if d.get("discount_pct") is not None)
    eligible = sum(1 for d in discounts if d.get("recipe_eligible"))
    logger.info(
        f"Discount scan complete: {len(discounts)} products found, "
        f"{with_discount} with a confirmed discount, {eligible} recipe-eligible, "
        f"cached at {scanned_at}"
    )


if __name__ == "__main__":
    main()
