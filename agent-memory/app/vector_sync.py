from __future__ import annotations

from typing import Any

from db import CONFIG
from embedding import Embedder
from qdrant_client import QdrantLite
from rerank import evidence_level, source_kind
from vector_profiles import default_profile, embedding_config, qdrant_config


def qdrant(profile: str | None = None) -> QdrantLite:
    return QdrantLite(qdrant_config(CONFIG, profile or default_profile(CONFIG)))


def dense_vector_size(vector: Any) -> int:
    if isinstance(vector, dict):
        return len(vector.get("vector") or [])
    return len(vector or [])


def memory_vector_point(memory: dict[str, Any], vector: Any) -> dict[str, Any]:
    memory_item = {**memory, "source_type": "memory"}
    return {
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
    }


def upsert_memory_vector(memory: dict[str, Any], profile: str | None = None) -> None:
    selected = profile or default_profile(CONFIG)
    embedder = Embedder(embedding_config(CONFIG, selected))
    if not embedder.available():
        return
    vector = embedder.embed_payload(f"{memory.get('title','')}\n{memory.get('content','')}")
    if not vector:
        return
    client = qdrant(selected)
    client.ensure_collection(dense_vector_size(vector))
    client.upsert([memory_vector_point(memory, vector)])


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
