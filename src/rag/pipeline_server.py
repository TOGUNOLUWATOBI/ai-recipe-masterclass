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
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from .config import RecipeRAGConfig
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


@app.post("/recipes/from-ingredients")
def recipes_from_ingredients(req: IngredientsRequest):
    """Returns real corpus recipes matching the given ingredients (no LLM call) when any
    exist; falls back to several generated suggestions, clearly labeled via "source",
    when the corpus has nothing (e.g. an obscure dish/cuisine not covered). Foundation
    for the v2 discount-driven recipe flow — feed it currently discounted ingredients,
    get back candidates to choose from instead of one generated answer."""
    result = pipeline.find_recipes_or_generate(req.ingredients, max_results=req.max_results)
    return {
        "ingredients": req.ingredients,
        "source": result["source"],
        "count": len(result["recipes"]),
        "recipes": result["recipes"],
        "generated": result["generated"],
        "error": result["error"],
    }


@app.get("/health")
def health():
    return {"status": "ok", "model": config.LLM_MODEL}
