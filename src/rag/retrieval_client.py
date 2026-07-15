"""HTTP client the pipeline service uses to reach the standalone retrieval service,
implementing the same .retrieve() interface HybridRetriever exposes in-process so
pipeline.py doesn't need to know or care whether retrieval is local or remote. Also
exposes translate_to_norwegian() -- reaches retrieval_server.py's /translate (see
translator.py), the other capability pipeline-service can't host directly since it
deliberately doesn't install torch/transformers (see Dockerfile.pipeline)."""

import logging
from typing import Any, Dict, List

import httpx

logger = logging.getLogger(__name__)


class RemoteRetriever:
    def __init__(self, base_url: str, timeout: float = 30.0):
        self.base_url = base_url.rstrip("/")
        # Translation (a full recipe's title/ingredients/instructions in one batched
        # call) can take longer than a retrieval call, especially cold -- the first
        # request after a container restart also pays the one-time model-load cost
        # (see translator.py's lazy _ensure_loaded()). A separate, longer timeout
        # keeps that from spuriously failing a translation without also loosening
        # the timeout for every ordinary retrieval call.
        self.client = httpx.Client(timeout=timeout)
        self.translate_client = httpx.Client(timeout=max(timeout, 60.0))

    def retrieve(self, query: str, top_k: int = None) -> List[Dict[str, Any]]:
        resp = self.client.post(f"{self.base_url}/retrieve", json={"query": query, "top_k": top_k})
        resp.raise_for_status()
        return resp.json()["retrieved"]

    def translate_to_norwegian(self, texts: List[str]) -> List[str]:
        if not texts:
            return []
        resp = self.translate_client.post(f"{self.base_url}/translate", json={"texts": texts})
        resp.raise_for_status()
        return resp.json()["translations"]
