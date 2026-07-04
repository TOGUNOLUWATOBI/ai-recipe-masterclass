"""Tests for generator.py — no real network/model calls; chat() is monkeypatched to
simulate success/failure so these run fast and don't depend on chat.bebs.dev being up."""

import threading

import pytest

from rag.generator import RecipeGenerator


@pytest.fixture
def generator(tmp_path):
    return RecipeGenerator(
        base_url="http://localhost:11434",
        model="test-model",
        api_style="ollama",
        max_retries=1,
        cache_db_path=tmp_path / "cache.db",
    )


def test_generate_raises_instead_of_returning_error_string(generator, monkeypatch):
    """Regression test for the exact bug found this session: generate() used to catch
    the exception and return f"Error generating response: {e}" — a string a caller
    displaying it as the answer couldn't distinguish from a real (bad) recipe."""
    def broken_chat(messages, **kwargs):
        raise ConnectionError("simulated network failure")

    monkeypatch.setattr(generator, "chat", broken_chat)

    with pytest.raises(ConnectionError):
        generator.generate("jollof rice", "some context", "system prompt")


def test_generate_returns_answer_on_success(generator, monkeypatch):
    monkeypatch.setattr(generator, "chat", lambda messages, **kwargs: "a real recipe")
    assert generator.generate("jollof rice", "context", "system prompt") == "a real recipe"


def test_generate_requires_system_prompt(generator):
    with pytest.raises(ValueError):
        generator.generate("jollof rice", "context", "")


def test_cache_round_trip(generator):
    generator._save_cache("key1", "msg-json", "cached answer")
    assert generator._get_cached("key1") == "cached answer"


def test_cache_miss_returns_none(generator):
    assert generator._get_cached("nonexistent-key") is None


def test_cache_survives_concurrent_writes(generator):
    """Lighter version of the manual stress test that validated the WAL mode + lock fix
    for the SQLite "database is locked" risk under concurrent access."""
    errors = []

    def hammer(thread_id):
        for i in range(20):
            try:
                key = f"key-{thread_id}-{i % 3}"
                generator._save_cache(key, f"msg-{i}", f"answer-{thread_id}-{i}")
                generator._get_cached(key)
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=hammer, args=(t,)) for t in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert errors == []
