"""Epic J1: structured recommendation-event logging. Every meal-ideas recommendation
request (Epic C's from-cart, Epic E's from-store) logs one event with enough detail to
trace a bad result back to exactly what the pipeline saw and decided -- no personal
data at all, since everything here is about products/coverage/system state, never a
user identifier.

Logged as a single grep-able JSON line via the standard `logging` module (this
codebase's existing convention -- see logging.basicConfig(level=logging.INFO) in every
entrypoint -- rather than `extra=`, whose fields silently never appear in the actual
log output without a custom JSON formatter this codebase doesn't have) rather than a
dedicated events table/analytics pipeline -- that's future work once real usage volume
justifies the extra infrastructure; grepping/aggregating from log files is enough for
a v1."""

import json
import logging
import uuid

logger = logging.getLogger("rag.recommendations")


def new_request_id() -> str:
    """A short, opaque id for tracing one recommendation request through the logs --
    not a user identifier, just unique enough to correlate this one event."""
    return uuid.uuid4().hex[:12]


def log_recommendation_event(**fields) -> None:
    """Task J1: one structured log line per recommendation request. Callers pass
    exactly the fields the story calls for (request_id, recommendation_type,
    selected_product_ids, eligible_product_ids, excluded_product_ids,
    retrieved_candidate_count, generated_fallback_used, meal_ideas_returned,
    ingredient_coverage, missing_ingredient_count, discount_snapshot_id,
    latency_seconds, validation_failure) as keyword arguments -- kept as **fields
    rather than named parameters here so this stays a thin, schema-agnostic logging
    sink; the caller (meal_ideas.py) is the one place that actually knows and enforces
    the field list."""
    logger.info("recommendation_event %s", json.dumps(fields, default=str))
