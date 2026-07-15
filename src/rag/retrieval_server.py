"""Standalone retrieval service — embedder + Qdrant + BM25 + reranker, no LLM involved.
Internal-only: reached by pipeline_server.py over the Docker network, never exposed
through the Cloudflare Tunnel directly.

Also hosts /translate (see translator.py) -- EN->Norwegian translation needs
torch/transformers, which pipeline-service deliberately doesn't install (see
Dockerfile.pipeline), so it lives here alongside the embedder/reranker that already
need the same dependencies, reached the same way /retrieve is.

Run with: uvicorn rag.retrieval_server:app --host 0.0.0.0 --port 8000
"""

import logging
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI
from pydantic import BaseModel

from .config import RecipeRAGConfig
from .pipeline import RecipeRAGPipeline
from .translator import RecipeTranslator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

config = RecipeRAGConfig()
pipeline = RecipeRAGPipeline(config)
translator = RecipeTranslator()


@asynccontextmanager
async def lifespan(app: FastAPI):
    pipeline.build_index(force_rebuild=False)
    yield


app = FastAPI(title="recipe-rag-retrieval", lifespan=lifespan)


class RetrieveRequest(BaseModel):
    query: str
    top_k: Optional[int] = None


@app.post("/retrieve")
def retrieve(req: RetrieveRequest):
    results = pipeline.retrieve(req.query, top_k=req.top_k)
    return {"retrieved": results}


class TranslateRequest(BaseModel):
    texts: List[str]


@app.post("/translate")
def translate(req: TranslateRequest):
    return {"translations": translator.translate_to_norwegian(req.texts)}


@app.get("/health")
def health():
    count = pipeline.vector_db.count_documents() if pipeline.vector_db else 0
    return {"status": "ok", "recipes_indexed": count}
