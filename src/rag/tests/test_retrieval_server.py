"""Tests for retrieval_server.py's /translate route handler -- the counterpart to
test_pipeline_server.py's route-handler-function tests (calling the handler directly,
no running app/TestClient needed since neither route touches request/response
plumbing FastAPI itself would add value testing here).

Skipped entirely (not failed) in any environment without fastapi installed, same
reasoning as test_pipeline_server.py."""

import pytest

pytest.importorskip("fastapi")

from rag import retrieval_server  # noqa: E402
from rag.retrieval_server import TranslateRequest, translate  # noqa: E402


def test_translate_forwards_texts_to_the_translator(monkeypatch):
    seen = {}

    class _FakeTranslator:
        def translate_to_norwegian(self, texts):
            seen["texts"] = texts
            return [t.upper() for t in texts]

    monkeypatch.setattr(retrieval_server, "translator", _FakeTranslator())

    result = translate(TranslateRequest(texts=["chicken", "rice"]))

    assert seen["texts"] == ["chicken", "rice"]
    assert result == {"translations": ["CHICKEN", "RICE"]}


def test_translate_request_requires_a_texts_field():
    with pytest.raises(Exception):
        TranslateRequest()
