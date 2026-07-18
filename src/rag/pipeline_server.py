"""Orchestrator service — calls the retrieval service for grounding context, then calls
Ollama directly (colocated on the same Mac mini, native API, no chat.bebs.dev round-trip)
to generate the answer. This is the service recipe.bebs.dev points to. Deliberately thin
and free of ML dependencies (torch/sentence-transformers/qdrant-client) so it stays a
small, fast-building image — this is the layer expected to grow (query rewriting,
multi-step logic) without needing to touch retrieval internals.

Run with: uvicorn rag.pipeline_server:app --host 0.0.0.0 --port 8000
"""

import json
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .classification_report import build_classification_quality_report
from .config import RecipeRAGConfig
from .discounts_store import (
    get_classification_sources,
    get_ingredient_index_rows,
    get_latest_snapshot,
    save_meal_idea_feedback,
)
from .ingredient_index import match_ingredient_offers
from .meal_ideas import generate_meal_ideas_from_cart, generate_meal_ideas_from_store
from .pipeline import RecipeRAGPipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

RAG_SERVICE_URL = os.getenv("RAG_SERVICE_URL", "http://rag-service:8000")

config = RecipeRAGConfig()
pipeline = RecipeRAGPipeline(config)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pipeline.build_index_remote(RAG_SERVICE_URL)
    pipeline.initialize_generator()
    yield


app = FastAPI(title="recipe-rag-pipeline", lifespan=lifespan)

# Permissive by design: this API has no auth, sessions, or cookies (no CSRF-style risk
# CORS restrictions would otherwise guard against), and every endpoint here is already
# reachable by anyone via curl/any HTTP client — CORS only blocks browser JS specifically,
# so restricting it would block legitimate web/mobile-web clients while doing nothing to
# stop the same request made a different way. Needed for the React Native app's web
# preview (Expo web) and any future browser-based client.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class QueryRequest(BaseModel):
    question: str
    top_k: Optional[int] = None
    # "no" only affects the LLM-synthesized answer text itself -- language is not
    # applied to retrieval/grounding, which stays keyed on the English corpus/reranker
    # regardless (see pipeline.py's _translate_answer()).
    language: str = "en"


@app.post("/query")
def query(req: QueryRequest):
    return pipeline.run_query(req.question, top_k=req.top_k, language=req.language)


@app.post("/query/stream")
def query_stream(req: QueryRequest):
    def event_gen():
        for event in pipeline.run_query_stream(req.question, top_k=req.top_k, language=req.language):
            yield f"data: {json.dumps(event)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_gen(), media_type="text/event-stream")


class IngredientsRequest(BaseModel):
    ingredients: List[str]
    max_results: Optional[int] = 10
    # True only when every ingredient is a real Tjek grocery-flyer product name (e.g.
    # sent by DealDetailScreen in the mobile app) -- routes to
    # normalize_grocery_heading() via pipeline.find_recipes_or_generate()'s normalize
    # param. Must stay False (the default) for arbitrary user-typed free text (e.g.
    # IngredientsScreen): an adversarial review confirmed normalize_grocery_heading()
    # corrupts real English phrases (e.g. "extra virgin olive oil" -> "virgin olive
    # oil"), since its glossary/noise-token suffix matching was only validated against
    # real Norwegian Tjek headings, never English vocabulary.
    is_grocery_product: bool = False
    # "no" translates every returned recipe's title/text (both source="corpus" and
    # source="generated") via a dedicated translation model -- see
    # pipeline.find_recipes_or_generate()'s _translate_recipes().
    language: str = "en"


@app.post("/recipes/from-ingredients")
def recipes_from_ingredients(req: IngredientsRequest):
    """Returns real corpus recipes matching the given ingredients (no LLM call) when any
    exist; falls back to several generated suggestions, clearly labeled via "source",
    when the corpus has nothing (e.g. an obscure dish/cuisine not covered). Foundation
    for the v2 discount-driven recipe flow — feed it currently discounted ingredients,
    get back candidates to choose from instead of one generated answer."""
    result = pipeline.find_recipes_or_generate(
        req.ingredients, max_results=req.max_results, normalize=req.is_grocery_product, language=req.language,
    )
    return {
        "ingredients": req.ingredients,
        "source": result["source"],
        "count": len(result["recipes"]),
        "recipes": result["recipes"],
        "generated": result["generated"],
        "error": result["error"],
    }


@app.get("/recipes/discounted")
def recipes_discounted(max_results: int = 10, include_recipes: bool = True, language: str = "en"):
    """v2 discount-driven recipe flow: reads the latest cached Tjek (etilbudsavis.dk)
    flyer-offer scan (see discounts_store.py — populated by a cron-triggered
    refresh_discounts.py, not a live call on every request) and, unless
    include_recipes=false, feeds whichever products are currently on offer into the same
    find_recipes_or_generate() used by /recipes/from-ingredients — same corpus-first,
    LLM-fallback behavior, just with the ingredient list sourced from real grocery flyer
    prices instead of a user-supplied list.

    include_recipes=false skips that generation pass entirely and returns just the
    discount list (fast — no LLM call). Built for a deals-browsing UI that needs the
    price/store/image list immediately and only wants a recipe for the one item a user
    actually taps, fetched on demand via /recipes/from-ingredients instead."""
    discounts, updated_at = get_latest_snapshot(config.DISCOUNTS_DB_PATH)

    if not discounts or not include_recipes:
        return {
            "discounted_ingredients": discounts, "source": None, "count": 0, "recipes": [],
            "generated": None, "error": None, "updated_at": updated_at,
        }

    # Uses the real discovered product_name (Norwegian, as returned directly by Tjek's
    # own flyer heading) as the query text — confirmed live that the fine-tuned model
    # handles this well: "Kjøttdeig Storfe 14%..." correctly became a "Kjøttballer"
    # (meatballs) recipe. Since the real flyer product name is shown to the user either
    # way, there's no deception even on an unusual heading; the source data itself is a
    # real, officially-published offer, not an inferred or fuzzy match.
    #
    # Only recipe_eligible items go into the recipe query (Epic A) — non-food (soap,
    # batteries, ...), beverages, snacks/treats, and ready meals/ready-to-eat products
    # (frozen pizza, ready-made lasagne, chocolate, Coca-Cola, ...) are still returned
    # in discounted_ingredients below for the app's own tabs/menus, but none of them
    # make for a sensible recipe ingredient (see product_classification.py). This
    # replaces the old `category == "main_food"` gate, which had no way to tell a
    # frozen pizza or a chocolate bar apart from a real ingredient — both used to slip
    # through as "main_food" since neither matched the old keyword-only non-food/snack
    # checks.
    #
    # Rows written before Epic A existed have recipe_eligible=False (see
    # discounts_store.get_latest_snapshot()) until the next scan reclassifies them, so
    # they're excluded here rather than wrongly treated as eligible.
    #
    # Capped at 30 after that filter — the discount scan now returns every product per
    # store (up to ~1400 across all stores), not just discounted ones, and joining all
    # of that into one retrieval query (find_recipes_from_ingredients joins the whole
    # list into a single comma-separated string) would dilute the query into noise
    # rather than actually cost more. discounts is already sorted with confirmed
    # discounts first, so this naturally keeps the real deals.
    eligible = [d for d in discounts if d.get("recipe_eligible")]
    product_names = [d["product_name"] for d in eligible[:30]]

    if not product_names:
        return {
            "discounted_ingredients": discounts, "source": None, "count": 0, "recipes": [],
            "generated": None, "error": None, "updated_at": updated_at,
        }

    # Always normalize=True here, unconditionally, with no request-side flag needed --
    # unlike /recipes/from-ingredients, this list is always sourced from the real Tjek
    # discounts snapshot (see get_latest_snapshot() above), never arbitrary user input.
    result = pipeline.find_recipes_or_generate(
        product_names, max_results=max_results, normalize=True, language=language,
    )
    return {
        "discounted_ingredients": discounts,
        "source": result["source"],
        "count": len(result["recipes"]),
        "recipes": result["recipes"],
        "generated": result["generated"],
        "error": result["error"],
        "updated_at": updated_at,
    }


class MealIdeasFromCartRequest(BaseModel):
    discount_item_ids: List[str]
    max_results: Optional[int] = 5
    language: str = "en"


@app.post("/meal-ideas/from-cart")
def meal_ideas_from_cart(req: MealIdeasFromCartRequest):
    """Epic C: generates practical meal ideas from a set of cart items, identified by
    the same `f"{store_name}::{product_name}"` ids the mobile cart already uses (see
    mobile-app/src/types/cart.ts's cartItemIdFor() and meal_ideas.py's
    _discount_item_id() -- kept in sync by convention, not a shared runtime value,
    since there's no real per-offer id yet).

    Ids are resolved against the latest cached discount snapshot server-side and
    independently re-checked for recipe eligibility -- the request never trusts
    whatever classification the client might send, only the id itself (see
    meal_ideas.generate_meal_ideas_from_cart() for the full pipeline: resolve -> filter
    -> normalize -> retrieve-or-generate -> score coverage -> rank)."""
    discounts, scanned_at = get_latest_snapshot(config.DISCOUNTS_DB_PATH)
    return generate_meal_ideas_from_cart(
        pipeline, discounts, req.discount_item_ids, max_results=req.max_results, language=req.language,
        discount_snapshot_id=scanned_at,
    )


class MealIdeasFromStoreRequest(BaseModel):
    # Task H3: a store name, not a product payload -- the client never sends the full
    # discount catalogue, only the id of which store it picked. The store's offers are
    # looked up server-side from the same cached snapshot /recipes/discounted reads.
    store_name: str
    max_results: Optional[int] = 5
    language: str = "en"


@app.post("/meal-ideas/from-store")
def meal_ideas_from_store(req: MealIdeasFromStoreRequest):
    """Epic E (Task E2/E4): generates practical meal ideas from one store's current
    cached offers, the same corpus-first/generation-fallback pipeline
    /meal-ideas/from-cart uses (see meal_ideas.generate_meal_ideas_from_store()). Never
    triggers a new Tjek scan, reclassification, or discount re-analysis -- store_name is
    matched against the latest cached snapshot exactly like /recipes/discounted itself
    already does, just filtered down to one store first (Task E2's hard rule)."""
    discounts, scanned_at = get_latest_snapshot(config.DISCOUNTS_DB_PATH)
    return generate_meal_ideas_from_store(
        pipeline, discounts, req.store_name, max_results=req.max_results, language=req.language,
        discount_snapshot_id=scanned_at,
    )


# Epic J3's fixed reason set -- exactly the six the change spec calls out, so a
# malformed/typo'd reason string is rejected at the API boundary (a 422) rather than
# silently accepted and polluting the feedback table with free-text noise.
MealIdeaFeedbackReason = Literal[
    "strange_combination",
    "too_many_missing_ingredients",
    "too_complicated",
    "incorrect_product",
    "not_an_everyday_meal",
    "ingredient_availability_was_wrong",
]


class MealIdeaFeedbackRequest(BaseModel):
    request_id: str
    recommendation_type: Literal["cart", "store"]
    idea_title: Optional[str] = None
    helpful: bool
    reasons: List[MealIdeaFeedbackReason] = []
    selected_items_used: List[str] = []
    missing_required_ingredients: List[str] = []
    source_type: Optional[Literal["retrieved", "generated"]] = None


@app.post("/meal-ideas/feedback")
def meal_ideas_feedback(req: MealIdeaFeedbackRequest):
    """Epic J3: a quick "Helpful"/"Not helpful" tap on one returned meal idea, stored
    alongside that idea's own output (title, what it used, what it was missing,
    retrieved vs. generated) so real usage feeds back into what gets fixed next.
    `request_id` (echoed back in every /meal-ideas/from-cart and /meal-ideas/from-store
    response, see meal_ideas.py) correlates this back to that request's own Epic J1 log
    line for deeper debugging without the app having to resend the full cart/store
    inputs here. Fire-and-forget from the app's point of view -- no response body
    beyond a plain acknowledgement, nothing here should ever block or retry the user's
    flow."""
    save_meal_idea_feedback(
        config.DISCOUNTS_DB_PATH,
        request_id=req.request_id,
        recommendation_type=req.recommendation_type,
        idea_title=req.idea_title,
        helpful=req.helpful,
        reasons=list(req.reasons),
        selected_items_used=req.selected_items_used,
        missing_required_ingredients=req.missing_required_ingredients,
        source_type=req.source_type,
        submitted_at=datetime.now(timezone.utc).isoformat(),
    )
    return {"status": "ok"}


class IngredientOffersRequest(BaseModel):
    ingredients: List[str]
    max_offers_per_ingredient: Optional[int] = 5


@app.post("/ingredient-offers")
def ingredient_offers(req: IngredientOffersRequest):
    """Epic F4/F5: for each ingredient (a recipe's required/optional ingredient name,
    not a raw flyer heading), returns the current matching offers from the precomputed
    discount_ingredient_index (see ingredient_index.match_ingredient_offers()) --
    empty `offers` when nothing matches, never "unavailable" (Task F5). A fast index
    lookup only: never a live Tjek scan, a reclassification, or an LLM call (Task F3),
    so opening a recipe page costs the same regardless of how large the current
    catalogue is. `snapshot_updated_at` mirrors /recipes/discounted's own freshness
    signal -- the index is rebuilt in the same refresh that stamps that snapshot (see
    refresh_discounts.py)."""
    _, updated_at = get_latest_snapshot(config.DISCOUNTS_DB_PATH)
    index_rows = get_ingredient_index_rows(config.DISCOUNTS_DB_PATH)
    # `or 5` would treat an explicitly-requested 0 the same as "not sent" (Python
    # falsy-zero) and silently override it -- check for None specifically, and floor
    # at 0 so a negative value can't produce a Python negative-slice surprise in
    # match_ingredient_offers's `ranked[:max_offers]`.
    max_offers = req.max_offers_per_ingredient if req.max_offers_per_ingredient is not None else 5
    max_offers = max(0, max_offers)
    return {
        "snapshot_updated_at": updated_at,
        "ingredients": [
            {"ingredient": name, "offers": match_ingredient_offers(name, index_rows, max_offers=max_offers)}
            for name in req.ingredients
        ],
    }


@app.get("/admin/classification-quality")
def classification_quality():
    """Epic J2: visibility into classification quality for the team maintaining the
    classifier -- percentage of the current catalogue classified by the keyword
    heuristic vs. the LLM tier vs. a manual override vs. left genuinely uncertain, plus
    which specific products are excluded and manually corrected most often (see
    classification_report.py for exactly what "most often" means here). Read-only,
    no personal data at all -- same no-auth posture as every other route on this API
    (see the CORS comment above)."""
    discounts, _ = get_latest_snapshot(config.DISCOUNTS_DB_PATH)
    product_names = list({row["product_name"] for row in discounts if row.get("product_name")})
    classification_sources = get_classification_sources(config.DISCOUNTS_DB_PATH, product_names)
    return build_classification_quality_report(discounts, classification_sources)


@app.get("/health")
def health():
    return {"status": "ok", "model": config.LLM_MODEL}
