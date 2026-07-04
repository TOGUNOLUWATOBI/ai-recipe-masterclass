"""HTTP client the pipeline service uses to reach the standalone retrieval service,
implementing the same .retrieve() interface HybridRetriever exposes in-process so
pipeline.py doesn't need to know or care whether retrieval is local or remote."""

import logging
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)


class RemoteRetriever:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(timeout=timeout)

    def retrieve(self, query: str, top_k: int = None) -> List[Dict[str, Any]]:
        resp = self.client.post(f"{self.base_url}/retrieve", json={"query": query, "top_k": top_k})
        resp.raise_for_status()
        return resp.json()["retrieved"]
