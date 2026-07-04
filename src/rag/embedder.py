"""Text embedder — adapted from the DAT560 project's BgeTextEmbedder, trimmed to
text-only (no CLIP/multimodal) since recipes are plain text."""

import logging
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer
from tqdm import tqdm

logger = logging.getLogger(__name__)


class TextEmbedder:
    """Sentence-transformers embedder — works with MiniLM, BGE, and similar models."""

    BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        logger.info(f"Loading embedding model: {model_name}")
        self.model = SentenceTransformer(model_name)
        self.dimension = self.model.get_sentence_embedding_dimension()
        self.is_bge = "bge" in model_name.lower()
        logger.info(f"Model loaded. Embedding dimension: {self.dimension}")

    def embed_texts(self, texts: List[str], batch_size: int = 64) -> np.ndarray:
        all_embeddings = []
        for i in tqdm(range(0, len(texts), batch_size), desc="Encoding recipes"):
            batch = texts[i:i + batch_size]
            embeddings = self.model.encode(batch, normalize_embeddings=True)
            all_embeddings.append(embeddings)
        return np.vstack(all_embeddings)

    def embed_query(self, query: str) -> np.ndarray:
        if self.is_bge:
            query = self.BGE_QUERY_PREFIX + query
        return self.model.encode([query], normalize_embeddings=True)[0]
