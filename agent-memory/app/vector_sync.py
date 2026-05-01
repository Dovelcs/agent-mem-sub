from __future__ import annotations

from typing import Any

from db import CONFIG
from embedding import Embedder
from qdrant_client import QdrantLite
from rerank import evidence_level, source_kind


def qdrant() -> QdrantLite:
    return QdrantLite(CONFIG.get("qdrant", {}))


def upsert_memory_vector(memory: dict[str, Any]) -> None:
    embedder = Embedder(CONFIG.get("embedding", {}))
    if not embedder.available():
        return
    vector = embedder.embed(f"{memory.get('title','')}\n{memory.get('content','')}")
    if not vector:
        return
    memory_item = {**memory, "source_type": "memory"}
    client = qdrant()
    client.ensure_collection(len(vector))
    client.upsert([{
        "id": 1000000000 + int(memory["id"]),
        "vector": vector,
        "payload": {
            "source_type": "memory",
            "item_id": int(memory["id"]),
            "document_id": None,
            "path": "",
            "title": memory.get("title", ""),
            "heading": "",
            "project": "",
            "platform": "",
            "customer": "",
            "tags": memory.get("tags", []),
            "status": memory.get("status", ""),
            "expires_at": memory.get("expires_at"),
            "source_kind": source_kind(memory_item),
            "evidence_level": evidence_level(memory_item),
            "updated_at": memory.get("updated_at", ""),
        },
    }])


def delete_memory_vector(memory_id: int) -> None:
    qdrant().delete_by_filter({
        "must": [
            {"key": "source_type", "match": {"value": "memory"}},
            {"key": "item_id", "match": {"value": int(memory_id)}},
        ]
    })


def delete_document_vectors(document_id: int) -> None:
    qdrant().delete_by_filter({
        "must": [
            {"key": "source_type", "match": {"value": "doc_chunk"}},
            {"key": "document_id", "match": {"value": int(document_id)}},
        ]
    })
