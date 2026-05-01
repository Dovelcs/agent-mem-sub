#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from qdrant_client import QdrantLite


def batched(items: list[dict[str, Any]], size: int):
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


def main() -> int:
    parser = argparse.ArgumentParser(description="Import JSONL vectors through the lightweight REST Qdrant client.")
    parser.add_argument("input", nargs="?", default="/opt/agent-memory/data/vectors/agent_vectors.jsonl")
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--collection", default="agent_chunks")
    parser.add_argument("--url", default="http://127.0.0.1:6333")
    args = parser.parse_args()

    path = Path(args.input)
    points = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not points:
        print(json.dumps({"ok": False, "error": "no points"}, ensure_ascii=False))
        return 2

    vector_size = len(points[0]["vector"])
    qdrant = QdrantLite({
        "enabled": True,
        "url": args.url,
        "collection": args.collection,
        "timeout_seconds": 10,
        "vector_size": vector_size,
    })
    qdrant.ensure_collection(vector_size)
    total = 0
    for batch in batched(points, args.batch_size):
        qdrant.upsert(batch)
        total += len(batch)
        print(json.dumps({"imported": total}, ensure_ascii=False), flush=True)
    print(json.dumps({"ok": True, "points_attempted": total, "qdrant": qdrant.health()}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
