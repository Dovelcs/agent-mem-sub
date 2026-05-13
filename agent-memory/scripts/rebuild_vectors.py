#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
import argparse
from pathlib import Path

ROOT = Path(os.environ.get("AGENT_MEMORY_ROOT", "/opt/agent-memory"))
sys.path.insert(0, str(ROOT / "app"))

from db import CONFIG, connect, from_json_text, init_db  # noqa: E402
from embedding import Embedder  # noqa: E402
from qdrant_client import QdrantLite  # noqa: E402
from rerank import evidence_level, source_kind  # noqa: E402
from vector_profiles import default_profile, embedding_config, qdrant_config  # noqa: E402


def batched(items: list[dict], size: int = 64):
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


def main() -> None:
    parser = argparse.ArgumentParser(description="Rebuild Qdrant vectors from the live SQLite database.")
    parser.add_argument("--profile", default="")
    parser.add_argument("--collection", default="")
    parser.add_argument("--qdrant-url", default="")
    args = parser.parse_args()

    init_db()
    profile = args.profile or default_profile(CONFIG)
    embedder = Embedder(embedding_config(CONFIG, profile))
    if not embedder.available():
        print(json.dumps({"ok": False, "error": "embedding unavailable", "provider": embedder.provider}, ensure_ascii=False))
        return

    points: list[dict] = []
    vector_size = None
    with connect() as conn:
        memories = conn.execute("SELECT * FROM memories WHERE status IN ('active','pinned')").fetchall()
        chunks = conn.execute(
            """
            SELECT document_chunks.*, documents.title, documents.project, documents.platform, documents.customer
            FROM document_chunks
            JOIN documents ON documents.id = document_chunks.document_id
            """
        ).fetchall()

    for row in memories:
        data = dict(row)
        vector = embedder.embed(f"{data.get('title','')}\n{data.get('content','')}")
        if not vector:
            continue
        vector_size = len(vector)
        memory_item = {**data, "source_type": "memory"}
        points.append({
            "id": 1000000000 + int(data["id"]),
            "vector": vector,
            "payload": {
                "source_type": "memory",
                "item_id": int(data["id"]),
                "document_id": None,
                "path": "",
                "title": data.get("title", ""),
                "heading": "",
                "project": "",
                "platform": "",
                "customer": "",
                "tags": from_json_text(data.get("tags", ""), []),
                "source_kind": source_kind(memory_item),
                "evidence_level": evidence_level(memory_item),
                "updated_at": data.get("updated_at", ""),
            },
        })

    for row in chunks:
        data = dict(row)
        vector = embedder.embed(f"{data.get('heading','')}\n{data.get('content','')}")
        if not vector:
            continue
        vector_size = len(vector)
        points.append({
            "id": int(data["id"]),
            "vector": vector,
            "payload": {
                "source_type": "doc_chunk",
                "item_id": int(data["id"]),
                "document_id": int(data["document_id"]),
                "path": data.get("path", ""),
                "title": data.get("title", ""),
                "heading": data.get("heading", ""),
                "project": data.get("project", ""),
                "platform": data.get("platform", ""),
                "customer": data.get("customer", ""),
                "tags": from_json_text(data.get("tags", ""), []),
                "source_kind": data.get("source_kind", ""),
                "evidence_level": data.get("evidence_level", ""),
                "updated_at": data.get("updated_at", ""),
            },
        })

    qdrant_cfg = qdrant_config(CONFIG, profile)
    if args.collection:
        qdrant_cfg["collection"] = args.collection
    if args.qdrant_url:
        qdrant_cfg["url"] = args.qdrant_url
    qdrant = QdrantLite(qdrant_cfg)
    if vector_size:
        qdrant.ensure_collection(vector_size)
    for batch in batched(points):
        qdrant.upsert(batch)
    print(json.dumps({"ok": True, "points_attempted": len(points), "qdrant": qdrant.health()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
