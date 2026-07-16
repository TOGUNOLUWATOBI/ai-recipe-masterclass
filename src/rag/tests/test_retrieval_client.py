"""Tests for retrieval_client.py's RemoteRetriever -- specifically
translate_to_norwegian(), using httpx.MockTransport (built into httpx, no extra test
dependency needed) to fake the HTTP round-trip to retrieval_server.py's /translate
without a real running server."""

import json

import httpx
import pytest

from rag.retrieval_client import RemoteRetriever


def _mock_transport(handler):
    return httpx.MockTransport(handler)


def test_translate_to_norwegian_posts_texts_and_returns_translations():
    seen_request = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_request["url"] = str(request.url)
        seen_request["body"] = json.loads(request.content)
        return httpx.Response(200, json={"translations": ["KYLLING", "RIS"]})

    retriever = RemoteRetriever("http://rag-service:8000")
    retriever.translate_client = httpx.Client(transport=_mock_transport(handler))

    result = retriever.translate_to_norwegian(["chicken", "rice"])

    assert seen_request["url"] == "http://rag-service:8000/translate"
    assert seen_request["body"] == {"texts": ["chicken", "rice"]}
    assert result == ["KYLLING", "RIS"]


def test_translate_to_norwegian_returns_empty_list_without_a_network_call():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("should not make a network call for an empty list")

    retriever = RemoteRetriever("http://rag-service:8000")
    retriever.translate_client = httpx.Client(transport=_mock_transport(handler))

    assert retriever.translate_to_norwegian([]) == []


def test_translate_to_norwegian_raises_on_a_server_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "model failed to load"})

    retriever = RemoteRetriever("http://rag-service:8000")
    retriever.translate_client = httpx.Client(transport=_mock_transport(handler))

    with pytest.raises(httpx.HTTPStatusError):
        retriever.translate_to_norwegian(["chicken"])


def test_translate_client_uses_a_longer_timeout_than_the_retrieve_client():
    """Translation (a full recipe in one batched call, plus a possible cold model
    load right after a container restart) can take longer than a retrieval call --
    see retrieval_client.py's comment on why these use separate timeouts."""
    retriever = RemoteRetriever("http://rag-service:8000", timeout=10.0)

    assert retriever.translate_client.timeout.read > retriever.client.timeout.read
