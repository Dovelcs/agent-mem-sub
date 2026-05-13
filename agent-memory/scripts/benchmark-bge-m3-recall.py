#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import time
from typing import Any

import requests


def timed_post(url: str, payload: dict[str, Any], count: int) -> tuple[list[float], dict[str, Any]]:
    elapsed: list[float] = []
    last: dict[str, Any] = {}
    for _ in range(count):
        start = time.perf_counter()
        resp = requests.post(url, json=payload, timeout=20)
        resp.raise_for_status()
        elapsed.append((time.perf_counter() - start) * 1000)
        last = resp.json()
    return elapsed, last


def summarize(values: list[float]) -> dict[str, float]:
    if not values:
        return {}
    ordered = sorted(values)
    p95 = ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))]
    return {"avg_ms": round(statistics.mean(values), 3), "min_ms": round(min(values), 3), "p95_ms": round(p95, 3), "max_ms": round(max(values), 3)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark bge-m3 embedding and recall latency.")
    parser.add_argument("--embed-url", default="http://127.0.0.1:18090/embed")
    parser.add_argument("--recall-url", default="http://127.0.0.1:18088/recall")
    parser.add_argument("--query", default="rk3562 是否支持 ab 分区以及支持最低硬盘大小")
    parser.add_argument("--count", type=int, default=5)
    args = parser.parse_args()

    embed_times, embed_last = timed_post(args.embed_url, {"text": args.query, "prefix": ""}, args.count)
    recall_times, recall_last = timed_post(args.recall_url, {"prompt": args.query, "limit_memories": 5, "limit_docs": 3}, args.count)
    docs = recall_last.get("docs") or recall_last.get("document_chunks") or []
    memories = recall_last.get("memories") or []
    print(json.dumps({
        "ok": True,
        "query": args.query,
        "embed": {**summarize(embed_times), "vector_size": embed_last.get("vector_size"), "model": embed_last.get("model")},
        "recall": {**summarize(recall_times), "docs": len(docs), "memories": len(memories)},
        "top_docs": [
            {
                "title": item.get("title"),
                "heading": item.get("heading"),
                "path": item.get("path"),
                "vector_score": item.get("vector_score"),
                "text_score": item.get("text_score"),
            }
            for item in docs[:3]
        ],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
