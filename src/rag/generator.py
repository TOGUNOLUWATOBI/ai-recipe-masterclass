"""LLM answer generator — supports two backends:

- "ollama": native Ollama server, via the ollama Python client (e.g. local Ollama).
- "openwebui": OpenWebUI's OpenAI-compatible /chat/completions endpoint, streamed.
  chat.bebs.dev is OpenWebUI, not raw Ollama — confirmed via /api/tags returning the
  OpenWebUI web app's HTML instead of Ollama's native JSON tags response, so the
  ollama Python client's requests don't land on the right paths there. Streaming
  matches the working pattern from synthetic_data.ipynb (non-streamed requests hit a
  Cloudflare 524 timeout on this host).

Adapted from the DAT560 project's BaselineGenerator. api_key is optional (local Ollama
needs no auth, unlike the university's/chat.bebs.dev's authenticated servers).
"""

import hashlib
import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Dict, Iterator, List, Optional

import requests
from ollama import Client, ResponseError

logger = logging.getLogger(__name__)


class RecipeGenerator:
    """LLM-based answer generator, backed by either native Ollama or OpenWebUI."""

    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        api_style: str = "ollama",
        temperature: float = 0.15,
        top_p: float = 0.9,
        max_tokens: int = 1024,
        max_retries: int = 3,
        retry_delay: int = 5,
        cache_db_path: Optional[Path] = None,
    ):
        if not base_url:
            raise ValueError("base_url is required (e.g. http://localhost:11434)")
        if not model:
            raise ValueError("model is required (the Ollama tag of your fine-tuned model)")
        if api_style not in ("ollama", "openwebui"):
            raise ValueError(f"api_style must be 'ollama' or 'openwebui', got {api_style!r}")

        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.api_style = api_style
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        if api_style == "ollama":
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else None
            self._client = Client(host=self.base_url, headers=headers, timeout=300)
        logger.info(f"Initialized {api_style} generator for model '{self.model}' at {self.base_url}")

        self._init_cache_db(cache_db_path or Path(__file__).resolve().parent / "query_cache.db")

    def _init_cache_db(self, db_path: Path):
        """check_same_thread=False alone only lets Python hand the same connection to
        other threads — it doesn't make SQLite's locking behavior safe under real
        concurrent access. Three additions needed for that: WAL mode (readers don't block
        writers and vice versa, instead of every write taking an exclusive file lock),
        busy_timeout (retry internally for a bit on lock contention instead of raising
        "database is locked" immediately), and a Lock around writes (a single
        sqlite3.Connection object isn't safe for concurrent use from multiple threads
        without external synchronization, regardless of journal mode)."""
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self.cache_conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self.cache_conn.execute("PRAGMA journal_mode=WAL")
        self.cache_conn.execute("PRAGMA busy_timeout=5000")
        self.cache_conn.execute("""
            CREATE TABLE IF NOT EXISTS generator_cache (
                cache_key TEXT PRIMARY KEY,
                model TEXT,
                messages_json TEXT,
                answer TEXT
            )
        """)
        self.cache_conn.commit()
        self._cache_lock = threading.Lock()

    def _cache_key(self, messages_json: str) -> str:
        return hashlib.sha256(f"{self.model}|{messages_json}".encode("utf-8")).hexdigest()

    def _get_cached(self, cache_key: str) -> Optional[str]:
        with self._cache_lock:
            row = self.cache_conn.execute(
                "SELECT answer FROM generator_cache WHERE cache_key = ?", (cache_key,)
            ).fetchone()
        return row[0] if row else None

    def _save_cache(self, cache_key: str, messages_json: str, answer: str):
        try:
            with self._cache_lock, self.cache_conn:
                self.cache_conn.execute(
                    "INSERT OR REPLACE INTO generator_cache VALUES (?, ?, ?, ?)",
                    (cache_key, self.model, messages_json, answer),
                )
        except Exception as e:
            logger.warning(f"Failed to cache answer: {e}")

    def _call_with_retries(self, func):
        import time as _time
        last_exc = None
        for attempt in range(self.max_retries):
            try:
                return func(attempt)
            except Exception as e:
                last_exc = e
                logger.warning(f"Attempt {attempt + 1}/{self.max_retries} failed ({type(e).__name__}): {e}")
                if attempt < self.max_retries - 1:
                    _time.sleep(self.retry_delay * (2 ** attempt))
        raise last_exc

    def chat(self, messages: List[Dict[str, str]], **kwargs) -> str:
        options = {"temperature": self.temperature, "top_p": self.top_p, "num_predict": self.max_tokens}
        options.update(kwargs.pop("options", {}))

        messages_json = json.dumps({"messages": messages, "options": options}, ensure_ascii=False, sort_keys=True)
        cache_key = self._cache_key(messages_json)
        cached = self._get_cached(cache_key)
        if cached:
            logger.info("Cache hit.")
            return cached

        if self.api_style == "openwebui":
            content = self._call_with_retries(lambda attempt: self._chat_openwebui(messages, options))
        else:
            content = self._call_with_retries(lambda attempt: self._chat_ollama(messages, options, **kwargs))

        if not content:
            raise ValueError("Empty response from chat API")

        self._save_cache(cache_key, messages_json, content)
        return content

    def _chat_ollama(self, messages, options, **kwargs) -> str:
        try:
            resp = self._client.chat(model=self.model, messages=messages, options=options, stream=False, **kwargs)
        except ResponseError as e:
            if getattr(e, "status_code", None) == 404:
                logger.warning(f"Model {self.model} not found, pulling...")
                self._client.pull(self.model)
            raise
        return getattr(getattr(resp, "message", None), "content", "")

    def _chat_openwebui(self, messages, options) -> str:
        """Non-streaming wrapper over the streaming implementation — collects the full
        response, used by chat()/generate() for callers that just want the final text
        (e.g. run_eval.py, or anything that doesn't need progressive output)."""
        return "".join(self._stream_openwebui(messages, options))

    def _stream_openwebui(self, messages, options) -> Iterator[str]:
        """OpenAI-compatible /chat/completions, streamed via SSE — non-streamed requests
        hit a Cloudflare 524 timeout on chat.bebs.dev (per synthetic_data.ipynb)."""
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "temperature": options.get("temperature", self.temperature),
            "top_p": options.get("top_p", self.top_p),
        }

        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=payload,
            stream=True,
            timeout=300,
        )
        response.raise_for_status()

        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue
            data = line[len("data: "):]
            if data.strip() == "[DONE]":
                break
            try:
                delta = json.loads(data)["choices"][0]["delta"].get("content", "")
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            if delta:
                yield delta

    def _stream_ollama(self, messages, options, **kwargs) -> Iterator[str]:
        try:
            for chunk in self._client.chat(model=self.model, messages=messages, options=options, stream=True, **kwargs):
                content = getattr(getattr(chunk, "message", None), "content", "")
                if content:
                    yield content
        except ResponseError as e:
            if getattr(e, "status_code", None) == 404:
                logger.warning(f"Model {self.model} not found, pulling...")
                self._client.pull(self.model)
            raise

    def chat_stream(self, messages: List[Dict[str, str]], **kwargs) -> Iterator[str]:
        """Yields text chunks as they arrive instead of buffering the full response —
        callers see output immediately rather than waiting the full 15-40s generation
        time with nothing shown. No retry wrapping here: retrying mid-stream would mean
        either duplicating already-yielded output or discarding it, neither of which a
        caller displaying chunks live can recover from cleanly — a failure here should
        just surface to the caller like any other stream error.

        Still writes to the same cache as chat()/generate() once the stream completes,
        so a repeated identical query is instant on the second call either way."""
        options = {"temperature": self.temperature, "top_p": self.top_p, "num_predict": self.max_tokens}
        options.update(kwargs.pop("options", {}))

        messages_json = json.dumps({"messages": messages, "options": options}, ensure_ascii=False, sort_keys=True)
        cache_key = self._cache_key(messages_json)
        cached = self._get_cached(cache_key)
        if cached:
            logger.info("Cache hit.")
            yield cached
            return

        stream = self._stream_openwebui(messages, options) if self.api_style == "openwebui" \
            else self._stream_ollama(messages, options, **kwargs)

        chunks = []
        for chunk in stream:
            chunks.append(chunk)
            yield chunk

        content = "".join(chunks)
        if not content:
            raise ValueError("Empty response from chat API")
        self._save_cache(cache_key, messages_json, content)

    def generate(self, question: str, context: str, system_prompt: str, **kwargs) -> str:
        """Raises on failure instead of returning an error string — a caller that just
        displays the return value as the answer must not be handed "Error: ..." text
        indistinguishable from a real recipe. Callers should catch and handle explicitly
        (see RecipeRAGPipeline.run_query). **kwargs forwards to chat() — e.g.
        options={"num_predict": N} to raise the token cap when asking for multiple
        recipes in one completion, which needs more room than a single answer."""
        return self.chat(self._build_messages(question, context, system_prompt), **kwargs)

    def generate_stream(self, question: str, context: str, system_prompt: str) -> Iterator[str]:
        """Streaming counterpart to generate() — see chat_stream() for error-handling notes."""
        return self.chat_stream(self._build_messages(question, context, system_prompt))

    @staticmethod
    def _build_messages(question: str, context: str, system_prompt: str) -> List[Dict[str, str]]:
        if not system_prompt:
            raise ValueError("system_prompt is required")
        user_message = f"Reference recipe(s), if any are relevant:\n{context}\n\nRequest: {question}"
        return [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
