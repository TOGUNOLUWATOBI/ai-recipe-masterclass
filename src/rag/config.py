"""Configuration for the recipe RAG pipeline."""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List

from dotenv import load_dotenv

RAG_DIR = Path(__file__).resolve().parent
SRC_DIR = RAG_DIR.parent
PROJECT_ROOT = SRC_DIR.parent

# Secrets live in .env (not hardcoded here) — see src/rag/.env for OLLAMA_API_KEY.
load_dotenv(RAG_DIR / ".env")

# Local, on-disk Qdrant store — no server/Docker needed.
VECTOR_DB_DIR = RAG_DIR / "local_qdrant"


@dataclass
class RecipeRAGConfig:
    """Single source of truth for the recipe RAG pipeline."""

    # ===== RECIPE SOURCES =====
    # Each file must be a JSON array of {title, ingredients: [...], instructions: [...], ...}.
    # Add more curated recipe files here as new cuisines get covered (e.g. Nordic dishes)
    # without needing to retrain the model — that's the whole point of RAG over fine-tuning.
    RECIPE_SOURCES: List[Path] = field(
        default_factory=lambda: [
            SRC_DIR / "notebooks" / "synthetic_african_recipes.json",
            SRC_DIR / "notebooks" / "synthetic_scandi_recipes.json",
            SRC_DIR / "notebooks" / "web_recipe_corpus.json",
        ]
    )

    # ===== EMBEDDING SETTINGS =====
    # BGE is purpose-built for retrieval (asymmetric query/passage encoding — embedder.py
    # already handles the query-prefix requirement), and noticeably stronger than MiniLM
    # at actually distinguishing "same dish" from "shares food vocabulary". Slower than
    # MiniLM but still fine for a ~20k-recipe corpus on CPU/MPS.
    EMBEDDING_MODEL: str = "BAAI/bge-base-en-v1.5"
    # Overwritten at runtime with embedder.dimension once the model is loaded — this
    # default just matches bge-base-en-v1.5 so the config is valid before that happens.
    EMBEDDING_DIMENSION: int = 768

    # ===== VECTOR DATABASE SETTINGS =====
    # Local embedded mode (file-based) is used by default for dev iteration on this
    # machine. Set VECTOR_DB_URL (e.g. via QDRANT_URL env var) to instead talk to a
    # Qdrant server — required once the corpus is past ~20,000 points (see the
    # UserWarning vector_database.py already surfaces) and for the production deploy,
    # where Qdrant runs in Docker on the Mac mini alongside Ollama and the RAG app.
    VECTOR_DB_PATH: str = str(VECTOR_DB_DIR)
    VECTOR_DB_URL: str = os.getenv("QDRANT_URL", "")
    VECTOR_DB_API_KEY: str = os.getenv("QDRANT_API_KEY", "")
    VECTOR_DB_COLLECTION: str = "recipes"
    VECTOR_DB_DISTANCE: str = "COSINE"

    # ===== RETRIEVAL SETTINGS =====
    TOP_K: int = 3
    USE_HYBRID_RETRIEVAL: bool = True
    # Minimum dense (cosine) similarity for a retrieved recipe to be trusted as a real
    # match rather than injected as noise. Only used as the relevance gate when
    # USE_RERANKER=False — recalibrated for bge-base-en-v1.5, whose absolute similarity
    # scale sits higher than MiniLM's (thresholds don't transfer across embedding models).
    # Still not a clean cutoff even so: true positives range ~0.56-0.80 and false
    # positives ~0.50-0.64, overlapping in the middle regardless of model — e.g. this
    # produces one known false negative ("moi moi" scores 0.56) to reject known false
    # positives ("briyani" typo, "norwegian ribbe") in the same band. The reranker below
    # is the real fix for this; keep MIN_DENSE_SCORE as the fallback gate if the reranker
    # is ever disabled (e.g. for latency).
    MIN_DENSE_SCORE: float = 0.60

    # Cross-encoder reranking as a second-stage relevance judge over the small candidate
    # set hybrid retrieval already narrowed down — empirically confirmed to separate true
    # from false positives far more cleanly than embedding similarity alone (true matches
    # scored +5 to +8.5, clear false positives -4 to -11, no overlap — vs. the overlapping
    # 0.50-0.65 band above). See reranker.py for why title-only, not full recipe text.
    USE_RERANKER: bool = True
    RERANKER_MODEL: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    # Recalibrated after adding the Scandinavian corpus: ms-marco-MiniLM has never seen
    # words like "ribbe", "kjøttkaker", "fenalår" and scores the whole vocabulary domain
    # lower even for a correct match — "norwegian ribbe" against the real Ribbe recipe
    # scores -2.07, well below the old 0.0 cutoff, despite being the clear best candidate
    # (next-best wrong candidate for the same query: -2.43). -2.3 keeps that true positive
    # while staying comfortably above confirmed false positives elsewhere (Norwegian
    # Flatbreads -4.13 on an unrelated query; -6.3 and -10.7 for genuinely uncovered
    # dishes like Finnish karjalanpiirakka / Icelandic hákarl).
    MIN_RERANK_SCORE: float = -2.3

    # ===== LLM / GENERATOR SETTINGS =====
    # chat.bebs.dev is OpenWebUI, not raw Ollama — confirmed via /api/tags returning the
    # OpenWebUI web app HTML instead of Ollama's native JSON. Default here talks to it via
    # OpenWebUI's OpenAI-compatible /api/chat/completions endpoint (LLM_API_STYLE="openwebui"),
    # which is what local Mac dev (this repo, run outside Docker) uses. The containerized
    # pipeline_server.py runs colocated with Ollama on the Mac mini and overrides these via
    # env vars to talk to it directly (LLM_API_STYLE=ollama, OLLAMA_BASE_URL=
    # http://host.docker.internal:11434) instead of round-tripping through the public
    # internet to reach a service running on the same machine.
    LLM_API_STYLE: str = os.getenv("LLM_API_STYLE", "openwebui")  # "openwebui" or "ollama"
    LLM_MODEL: str = os.getenv("LLM_MODEL", "toriko3:latest")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "https://chat.bebs.dev/api")
    OLLAMA_API_KEY: str = os.getenv("OLLAMA_API_KEY", "")
    LLM_TEMPERATURE: float = 0.15
    LLM_TOP_P: float = 0.9
    LLM_MAX_TOKENS: int = 1024
    LLM_MAX_RETRIES: int = 3
    LLM_RETRY_DELAY: int = 5

    # Separate model for grocery-item classification (see product_classifier.py) --
    # deliberately NOT LLM_MODEL (toriko3, fine-tuned specifically for recipe
    # generation/QA) since a recipe-fine-tuned model is a poor fit for a generic
    # structured-classification task. qwen3:8b with think=False (see
    # product_classifier.py) was confirmed live to classify real flyer headings
    # correctly, including several the keyword heuristic in grocery_discounts.py
    # missed (e.g. "SØRLANDSIS", "FACE CONTROL CREAM", "KRONE-IS").
    CATEGORY_LLM_MODEL: str = os.getenv("CATEGORY_LLM_MODEL", "qwen3:8b")

    # Cache the scheduled scan (refresh_discounts.py) populates and /recipes/discounted
    # reads from — see discounts_store.py for why this is a real scan-once-serve-many
    # cache rather than a live Tjek call per request.
    DISCOUNTS_DB_PATH: str = os.getenv("DISCOUNTS_DB_PATH", str(RAG_DIR / "discounts_cache" / "discounts.db"))

    # Minimum age (hours) the cached snapshot must reach before refresh_discounts.py will
    # do another full Tjek sweep. Deliberately under the 24h normal cadence -- a healthy
    # once-a-day cron still refreshes every time it fires, but this also lets a *more
    # frequent* cron (e.g. hourly) act as a self-healing catch-up mechanism: standard cron
    # doesn't retry a missed fixed-time firing (e.g. the host asleep/offline at 5am), so
    # without this the cache could silently sit stale for days until a human noticed. With
    # a stale-check gate + hourly cron, any wake-up within the window catches up
    # automatically instead of waiting up to 24h for the next exact firing.
    DISCOUNT_REFRESH_MIN_INTERVAL_HOURS: float = 20

    RANDOM_SEED: int = 42
