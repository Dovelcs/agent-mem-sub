from __future__ import annotations

import os
import signal
import threading
from contextlib import contextmanager
from typing import Any

import requests


class TimeoutError(Exception):
    pass


@contextmanager
def time_limit(seconds: float):
    if seconds <= 0:
        yield
        return
    if threading.current_thread() is not threading.main_thread():
        yield
        return

    def handler(signum, frame):
        raise TimeoutError("embedding timed out")

    old = signal.signal(signal.SIGALRM, handler)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old)


class Embedder:
    def __init__(self, config: dict[str, Any]):
        self.config = config or {}
        self.provider = self.config.get("provider", "local")
        self.timeout = float(self.config.get("timeout_seconds", 0.8))
        self._model = None

    def available(self) -> bool:
        if self.provider == "none":
            return False
        if self.provider == "openai":
            return bool(os.environ.get(self.config.get("openai_api_key_env", "OPENAI_API_KEY")))
        if self.provider == "http":
            try:
                resp = requests.get(
                    self.config.get("http_url", "http://127.0.0.1:18090").rstrip("/") + "/health",
                    timeout=min(self.timeout, 0.5),
                )
                return resp.ok and bool(resp.json().get("ok"))
            except Exception:
                return False
        if self.provider == "local":
            try:
                import sentence_transformers  # noqa: F401
                return True
            except Exception:
                return False
        return False

    def embed(self, text: str, prefix: str | None = None) -> list[float] | None:
        payload = self.embed_payload(text, prefix)
        if not payload:
            return None
        return payload.get("vector") or None

    def embed_payload(self, text: str, prefix: str | None = None) -> dict[str, Any] | None:
        text = (text or "").strip()
        if not text or not self.available():
            return None
        try:
            with time_limit(self.timeout):
                if self.provider == "openai":
                    vector = self._embed_openai(text, prefix)
                    return {"vector": vector, "sparse": None} if vector else None
                if self.provider == "http":
                    return self._embed_http(text, prefix)
                if self.provider == "local":
                    vector = self._embed_local(text, prefix)
                    return {"vector": vector, "sparse": None} if vector else None
        except Exception:
            return None
        return None

    def _prefix(self, prefix: str | None) -> str:
        if prefix is not None:
            return prefix
        return str(self.config.get("document_prefix", ""))

    def _embed_local(self, text: str, prefix: str | None = None) -> list[float] | None:
        from sentence_transformers import SentenceTransformer

        if self._model is None:
            self._model = SentenceTransformer(self.config.get("local_model", "sentence-transformers/all-MiniLM-L6-v2"))
        vector = self._model.encode([f"{self._prefix(prefix)}{text}"], normalize_embeddings=True)[0]
        return [float(v) for v in vector]

    def _embed_openai(self, text: str, prefix: str | None = None) -> list[float] | None:
        key = os.environ.get(self.config.get("openai_api_key_env", "OPENAI_API_KEY"))
        if not key:
            return None
        resp = requests.post(
            "https://api.openai.com/v1/embeddings",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={"model": self.config.get("openai_model", "text-embedding-3-small"), "input": f"{self._prefix(prefix)}{text}"},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        return [float(v) for v in data["data"][0]["embedding"]]

    def _embed_http(self, text: str, prefix: str | None = None) -> dict[str, Any] | None:
        url = self.config.get("http_url", "http://127.0.0.1:18090").rstrip("/") + "/embed"
        resp = requests.post(
            url,
            json={"text": text, "prefix": self._prefix(prefix)},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            return None
        vector = [float(v) for v in data.get("vector") or []]
        sparse = data.get("sparse")
        if isinstance(sparse, dict):
            try:
                sparse = {
                    "indices": [int(value) for value in sparse.get("indices") or []],
                    "values": [float(value) for value in sparse.get("values") or []],
                }
            except Exception:
                sparse = None
            if sparse and len(sparse["indices"]) != len(sparse["values"]):
                sparse = None
        else:
            sparse = None
        return {"vector": vector, "sparse": sparse}


def rerank_http(query: str, items: list[dict[str, Any]], config: dict[str, Any]) -> dict[Any, float]:
    if not bool(config.get("enabled", False)) or not query or not items:
        return {}
    if str(config.get("provider", "http")) != "http":
        return {}
    url = str(config.get("http_url", "http://127.0.0.1:18091")).rstrip("/") + "/rerank"
    timeout = float(config.get("timeout_seconds", 3.0))
    payload_items = [
        {"id": item.get("_rerank_id"), "text": item.get("_rerank_text", "")}
        for item in items
        if item.get("_rerank_id") is not None and item.get("_rerank_text")
    ]
    if not payload_items:
        return {}
    try:
        resp = requests.post(url, json={"query": query, "items": payload_items}, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("ok"):
            return {}
        return {score["id"]: float(score.get("score") or 0.0) for score in data.get("scores") or []}
    except Exception:
        return {}
