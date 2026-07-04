"""Local, on-disk Qdrant vector store — adapted from the DAT560 project's
QdrantVectorDB, trimmed to single-vector text-only mode (no multi-vector/Docker
support needed here)."""

import logging
from typing import Dict, List, Optional

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

logger = logging.getLogger(__name__)

_DISTANCE_MAP = {
    "COSINE": Distance.COSINE,
    "DOT": Distance.DOT,
    "MANHATTAN": Distance.MANHATTAN,
    "EUCLID": Distance.EUCLID,
}


class QdrantVectorDB:
    """Local on-disk Qdrant store for recipe embeddings."""

    def __init__(self, config):
        self.config = config
        if getattr(config, "VECTOR_DB_URL", None):
            self.client = QdrantClient(url=config.VECTOR_DB_URL, api_key=getattr(config, "VECTOR_DB_API_KEY", None) or None)
            logger.info(f"Connected to Qdrant server at {config.VECTOR_DB_URL}")
        else:
            self.client = QdrantClient(path=config.VECTOR_DB_PATH)
            logger.info(f"Local Qdrant initialized at {config.VECTOR_DB_PATH}")

    def create_collection(self, force_recreate: bool = False) -> None:
        name = self.config.VECTOR_DB_COLLECTION
        try:
            self.client.get_collection(name)
            if force_recreate:
                logger.info(f"Deleting existing collection '{name}'...")
                self.client.delete_collection(name)
            else:
                logger.info(f"Collection '{name}' already exists.")
                return
        except Exception:
            pass

        distance = _DISTANCE_MAP.get(self.config.VECTOR_DB_DISTANCE.upper(), Distance.COSINE)
        self.client.create_collection(
            collection_name=name,
            vectors_config=VectorParams(size=self.config.EMBEDDING_DIMENSION, distance=distance),
        )
        logger.info(f"Collection '{name}' created ({self.config.EMBEDDING_DIMENSION}D, {self.config.VECTOR_DB_DISTANCE})")

    def index_documents(self, documents: List[Dict], batch_size: int = 100) -> int:
        """Each document needs: id, embedding, text, metadata."""
        name = self.config.VECTOR_DB_COLLECTION
        points, total_indexed = [], 0

        for idx, doc in enumerate(documents):
            embedding = doc["embedding"]
            if isinstance(embedding, np.ndarray):
                embedding = embedding.tolist()

            points.append(PointStruct(
                id=doc.get("id", idx),
                vector=embedding,
                payload={"text": doc.get("text", ""), **doc.get("metadata", {})},
            ))

            if (idx + 1) % batch_size == 0:
                self.client.upsert(collection_name=name, points=points)
                total_indexed += len(points)
                points = []

        if points:
            self.client.upsert(collection_name=name, points=points)
            total_indexed += len(points)

        logger.info(f"Indexed {total_indexed} recipes into '{name}'")
        return total_indexed

    def retrieve(self, query_embedding, top_k: int = None) -> List[Dict]:
        name = self.config.VECTOR_DB_COLLECTION
        top_k = top_k or self.config.TOP_K
        if isinstance(query_embedding, np.ndarray):
            query_embedding = query_embedding.tolist()

        try:
            results = self.client.query_points(
                collection_name=name, query=query_embedding, limit=top_k
            ).points
        except Exception as e:
            logger.error(f"Error retrieving from Qdrant: {e}")
            return []

        return [
            {"id": r.id, "score": r.score, "payload": r.payload, "text": r.payload.get("text", "")}
            for r in results
        ]

    def count_documents(self) -> int:
        try:
            info = self.client.get_collection(self.config.VECTOR_DB_COLLECTION)
            return info.points_count if info else 0
        except Exception:
            return 0

    def delete_collection(self) -> None:
        try:
            self.client.delete_collection(self.config.VECTOR_DB_COLLECTION)
            logger.info(f"Collection '{self.config.VECTOR_DB_COLLECTION}' deleted")
        except Exception as e:
            logger.warning(f"Error deleting collection: {e}")
