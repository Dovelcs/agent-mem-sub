#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams


def batched(items: list[dict], size: int):
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


def main() -> int:
    parser = argparse.ArgumentParser(description="Import agent-memory JSONL vectors into Qdrant.")
    parser.add_argument("--input", default="/out/agent_vectors.jsonl")
    parser.add_argument("--url", default="http://127.0.0.1:6333")
    parser.add_argument("--collection", default="agent_chunks_bge_m3")
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    path = Path(args.input)
    points = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not points:
        print(json.dumps({"ok": False, "error": "no points"}, ensure_ascii=False))
        return 2

    vector_size = len(points[0]["vector"])
    client = QdrantClient(url=args.url, timeout=args.timeout)
    collections = {item.name for item in client.get_collections().collections}
    if args.collection not in collections:
        client.create_collection(args.collection, vectors_config=VectorParams(size=vector_size, distance=Distance.COSINE))
    for field in ("source_type", "project", "platform", "customer", "path", "tags", "source_kind", "evidence_level"):
        try:
            client.create_payload_index(args.collection, field_name=field, field_schema="keyword")
        except Exception:
            pass
    total = 0
    for batch in batched(points, args.batch_size):
        client.upsert(args.collection, points=batch)
        total += len(batch)
        print(json.dumps({"imported": total}, ensure_ascii=False), flush=True)
    info = client.get_collection(args.collection)
    print(json.dumps({"ok": True, "points_attempted": total, "points_count": info.points_count}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
