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
from typing import List, Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .config import RecipeRAGConfig
from .discounts_store import get_latest_snapshot
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


@app.post("/query")
def query(req: QueryRequest):
    return pipeline.run_query(req.question, top_k=req.top_k)


@app.post("/query/stream")
def query_stream(req: QueryRequest):
    def event_gen():
        for event in pipeline.run_query_stream(req.question, top_k=req.top_k):
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


@app.post("/recipes/from-ingredients")
def recipes_from_ingredients(req: IngredientsRequest):
    """Returns real corpus recipes matching the given ingredients (no LLM call) when any
    exist; falls back to several generated suggestions, clearly labeled via "source",
    when the corpus has nothing (e.g. an obscure dish/cuisine not covered). Foundation
    for the v2 discount-driven recipe flow — feed it currently discounted ingredients,
    get back candidates to choose from instead of one generated answer."""
    result = pipeline.find_recipes_or_generate(
        req.ingredients, max_results=req.max_results, normalize=req.is_grocery_product,
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
def recipes_discounted(max_results: int = 10, include_recipes: bool = True):
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
    # own flyer heading), not any category label — confirmed live that the fine-tuned
    # model handles this well: "Kjøttdeig Storfe 14%..." correctly became a
    # "Kjøttballer" (meatballs) recipe. Since the real flyer product name is shown to
    # the user either way, there's no deception even on an unusual heading; the source
    # data itself is a real, officially-published offer, not an inferred or fuzzy match.
    #
    # Capped at 30 — the discount scan now returns every product per store (up to ~1400
    # across all stores), not just discounted ones, and joining all of that into one
    # retrieval query (find_recipes_from_ingredients joins the whole list into a single
    # comma-separated string) would dilute the query into noise rather than actually
    # cost more. discounts is already sorted with confirmed discounts first, so this
    # naturally keeps the real deals.
    product_names = [d["product_name"] for d in discounts[:30]]
    # Always normalize=True here, unconditionally, with no request-side flag needed --
    # unlike /recipes/from-ingredients, this list is always sourced from the real Tjek
    # discounts snapshot (see get_latest_snapshot() above), never arbitrary user input.
    result = pipeline.find_recipes_or_generate(product_names, max_results=max_results, normalize=True)
    return {
        "discounted_ingredients": discounts,
        "source": result["source"],
        "count": len(result["recipes"]),
        "recipes": result["recipes"],
        "generated": result["generated"],
        "error": result["error"],
        "updated_at": updated_at,
    }


@app.get("/health")
def health():
    return {"status": "ok", "model": config.LLM_MODEL}
