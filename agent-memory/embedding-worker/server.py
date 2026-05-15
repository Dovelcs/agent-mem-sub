#!/usr/bin/env python3
from __future__ import annotations

import os
import time
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel

from backend import EmbeddingBackend, RerankBackend


MODEL_NAME = os.environ.get("EMBED_MODEL", "intfloat/multilingual-e5-small")
DEVICE = os.environ.get("EMBED_DEVICE") or None
DEFAULT_QUERY_PREFIX = os.environ.get("EMBED_QUERY_PREFIX", "query: ")
PRELOAD_MODEL = os.environ.get("EMBED_PRELOAD", "1").strip().lower() not in {"0", "false", "no"}
SPARSE_ENABLED = os.environ.get("EMBED_SPARSE", "").strip().lower() in {"1", "true", "yes"} or "bge-m3" in MODEL_NAME.lower()
MAX_LENGTH = int(os.environ.get("EMBED_MAX_LENGTH", "1024") or "1024")
RERANK_MODEL_NAME = os.environ.get("RERANK_MODEL", "")
RERANK_DEVICE = os.environ.get("RERANK_DEVICE") or DEVICE
RERANK_PRELOAD = os.environ.get("RERANK_PRELOAD", "0").strip().lower() in {"1", "true", "yes"}
RERANK_BATCH_SIZE = int(os.environ.get("RERANK_BATCH_SIZE", "8") or "8")
RERANK_MAX_LENGTH = int(os.environ.get("RERANK_MAX_LENGTH", "512") or "512")

app = FastAPI(title="agent-memory-embedding", version="0.1.0")
model: EmbeddingBackend | None = None
reranker: RerankBackend | None = None
vector_size: int | None = None
loaded_at: float | None = None
load_seconds: float | None = None
reranker_loaded_at: float | None = None
reranker_load_seconds: float | None = None


class EmbedRequest(BaseModel):
    text: str
    prefix: str | None = None


class RerankItem(BaseModel):
    id: int | str
    text: str


class RerankRequest(BaseModel):
    query: str
    items: list[RerankItem]


def get_model() -> EmbeddingBackend:
    global model, vector_size, loaded_at, load_seconds
    if model is None:
        start = time.perf_counter()
        model = EmbeddingBackend(MODEL_NAME, device=DEVICE, sparse=SPARSE_ENABLED, max_length=MAX_LENGTH)
        sample = model.encode(["query: health"], batch_size=1)[0]
        vector_size = int(len(sample["vector"]))
        load_seconds = time.perf_counter() - start
        loaded_at = time.time()
    return model


def get_reranker() -> RerankBackend:
    global reranker, reranker_loaded_at, reranker_load_seconds
    if not RERANK_MODEL_NAME:
        raise RuntimeError("RERANK_MODEL is not configured")
    if reranker is None:
        start = time.perf_counter()
        reranker = RerankBackend(
            RERANK_MODEL_NAME,
            device=RERANK_DEVICE,
            batch_size=RERANK_BATCH_SIZE,
            max_length=RERANK_MAX_LENGTH,
        )
        reranker.load()
        reranker_load_seconds = time.perf_counter() - start
        reranker_loaded_at = time.time()
    return reranker


@app.on_event("startup")
def startup() -> None:
    if PRELOAD_MODEL:
        get_model()
    if RERANK_PRELOAD:
        get_reranker()


@app.get("/health")
def health() -> dict[str, Any]:
    embedding_ready = model is not None
    reranker_ready = reranker is not None
    ready = embedding_ready or (bool(RERANK_MODEL_NAME) and reranker_ready)
    return {
        "ok": True,
        "ready": ready,
        "model": MODEL_NAME,
        "backend": model.backend_name if model else None,
        "sparse": SPARSE_ENABLED,
        "max_length": MAX_LENGTH,
        "vector_size": vector_size,
        "loaded_at": loaded_at,
        "load_seconds": load_seconds,
        "embedding": {
            "configured": PRELOAD_MODEL or bool(MODEL_NAME),
            "ready": embedding_ready,
            "model": MODEL_NAME,
            "backend": model.backend_name if model else None,
            "sparse": SPARSE_ENABLED,
            "max_length": MAX_LENGTH,
            "vector_size": vector_size,
            "loaded_at": loaded_at,
            "load_seconds": load_seconds,
        },
        "reranker": {
            "configured": bool(RERANK_MODEL_NAME),
            "ready": reranker_ready,
            "model": RERANK_MODEL_NAME,
            "batch_size": RERANK_BATCH_SIZE,
            "max_length": RERANK_MAX_LENGTH,
            "loaded_at": reranker_loaded_at,
            "load_seconds": reranker_load_seconds,
        },
    }


@app.post("/embed")
def embed(req: EmbedRequest) -> dict[str, Any]:
    start = time.perf_counter()
    text = " ".join((req.text or "").split())
    if not text:
        return {"ok": False, "error": "empty text", "vector": []}
    prefix = DEFAULT_QUERY_PREFIX if req.prefix is None else req.prefix
    encoded = get_model().encode([f"{prefix}{text}"], batch_size=1)[0]
    vector = encoded["vector"]
    return {
        "ok": True,
        "model": MODEL_NAME,
        "backend": get_model().backend_name,
        "sparse": encoded.get("sparse"),
        "vector_size": len(vector),
        "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
        "vector": vector,
    }


@app.post("/rerank")
def rerank(req: RerankRequest) -> dict[str, Any]:
    start = time.perf_counter()
    query = " ".join((req.query or "").split())
    items = [{"id": item.id, "text": " ".join((item.text or "").split())} for item in req.items]
    pairs = [[query, item["text"]] for item in items if query and item["text"]]
    if not query or not pairs:
        return {"ok": False, "error": "empty query or items", "scores": []}
    scores = get_reranker().compute_score(pairs)
    ranked = [
        {"id": item["id"], "score": score}
        for item, score in zip([item for item in items if item["text"]], scores)
    ]
    return {
        "ok": True,
        "model": RERANK_MODEL_NAME,
        "elapsed_ms": round((time.perf_counter() - start) * 1000, 3),
        "scores": ranked,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "18089")))
