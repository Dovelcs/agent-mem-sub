#!/usr/bin/env python3
from __future__ import annotations

import os
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel
from sentence_transformers import SentenceTransformer


MODEL_NAME = os.environ.get("EMBED_MODEL", "intfloat/multilingual-e5-small")
DEVICE = os.environ.get("EMBED_DEVICE") or None
DEFAULT_QUERY_PREFIX = os.environ.get("EMBED_QUERY_PREFIX", "query: ")

app = FastAPI(title="agent-memory-embedding", version="0.1.0")
model: SentenceTransformer | None = None
vector_size: int | None = None


class EmbedRequest(BaseModel):
    text: str
    prefix: str | None = None


def get_model() -> SentenceTransformer:
    global model, vector_size
    if model is None:
        model = SentenceTransformer(MODEL_NAME, device=DEVICE)
        sample = model.encode(["query: health"], normalize_embeddings=True, show_progress_bar=False)[0]
        vector_size = int(len(sample))
    return model


@app.get("/health")
def health() -> dict[str, Any]:
    ready = model is not None
    return {"ok": True, "ready": ready, "model": MODEL_NAME, "vector_size": vector_size}


@app.post("/embed")
def embed(req: EmbedRequest) -> dict[str, Any]:
    text = " ".join((req.text or "").split())
    if not text:
        return {"ok": False, "error": "empty text", "vector": []}
    prefix = DEFAULT_QUERY_PREFIX if req.prefix is None else req.prefix
    encoded = get_model().encode([f"{prefix}{text}"], normalize_embeddings=True, show_progress_bar=False)[0]
    vector = [float(v) for v in encoded]
    return {"ok": True, "model": MODEL_NAME, "vector_size": len(vector), "vector": vector}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", "18089")))
