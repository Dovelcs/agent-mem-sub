#!/usr/bin/env python3
from __future__ import annotations

import os
import time
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer


MODEL_NAME = os.environ.get("EMBED_MODEL", "intfloat/multilingual-e5-small")
DEVICE = os.environ.get("EMBED_DEVICE") or None
DEFAULT_QUERY_PREFIX = os.environ.get("EMBED_QUERY_PREFIX", "query: ")
PRELOAD_MODEL = os.environ.get("EMBED_PRELOAD", "1").strip().lower() not in {"0", "false", "no"}

app = FastAPI(title="agent-memory-embedding", version="0.1.0")
model: SentenceTransformer | None = None
vector_size: int | None = None
loaded_at: float | None = None
load_seconds: float | None = None


class EmbedRequest(BaseModel):
    text: str
    prefix: str | None = None


def get_model() -> SentenceTransformer:
    global model, vector_size, loaded_at, load_seconds
    if model is None:
        start = time.perf_counter()
        model = SentenceTransformer(MODEL_NAME, device=DEVICE)
        sample = model.encode(["query: health"], normalize_embeddings=True, show_progress_bar=False)[0]
        vector_size = int(len(sample))
        load_seconds = time.perf_counter() - start
        loaded_at = time.time()
    return model


@app.on_event("startup")
def startup() -> None:
    if PRELOAD_MODEL:
        get_model()


@app.get("/health")
def health() -> dict[str, Any]:
    ready = model is not None
    return {
        "ok": True,
        "ready": ready,
        "model": MODEL_NAME,
        "vector_size": vector_size,
        "loaded_at": loaded_at,
        "load_seconds": load_seconds,
    }


@app.post("/embed")
def embed(req: EmbedRequest) -> dict[str, Any]:
    start = time.perf_counter()
    text = " ".join((req.text or "").split())
    if not text:
        return {"ok": False, "error": "empty text", "vector": []}
    prefix = DEFAULT_QUERY_PREFIX if req.prefix is None else req.prefix
    encoded = get_model().encode([f"{prefix}{text}"], normalize_embeddings=True, show_progress_bar=False)[0]
    vector = [float(v) for v in encoded]
    return {
        "ok": True,
        "model": MODEL_NAME,
        "vector_size": len(vector),
        "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
        "vector": vector,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "18089")))
