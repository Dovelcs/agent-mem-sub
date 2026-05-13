#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any


APP_PATH = Path(__file__).resolve().parent.parent / "app"
if APP_PATH.exists():
    sys.path.insert(0, str(APP_PATH))


def load_record(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_record(path: Path, record: dict[str, Any]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def move_record(src: Path, dst_dir: Path, record: dict[str, Any]) -> Path:
    dst = dst_dir / src.name
    write_record(src, record)
    src.replace(dst)
    return dst


def claim_pending(dirs: dict[str, Path]) -> Path | None:
    for path in sorted(dirs["pending"].glob("*.json"), key=lambda item: item.stat().st_mtime):
        claimed = dirs["processing"] / path.name
        try:
            path.replace(claimed)
            return claimed
        except FileNotFoundError:
            continue
    return None


def embedding_config(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any]:
    from vector_profiles import default_profile, embedding_config as profile_embedding_config

    cfg = profile_embedding_config(config, args.profile or default_profile(config))
    provider = args.provider or os.environ.get("AGENT_MEMORY_VECTOR_CACHE_PROVIDER")
    model = args.model or os.environ.get("AGENT_MEMORY_VECTOR_CACHE_MODEL")
    http_url = args.http_url or os.environ.get("AGENT_MEMORY_VECTOR_CACHE_HTTP_URL")
    timeout = args.timeout_seconds
    if provider:
        cfg["provider"] = provider
    if model:
        cfg["local_model"] = model
    if http_url:
        cfg["http_url"] = http_url
    if timeout is not None:
        cfg["timeout_seconds"] = timeout
    return cfg


def process_one(path: Path, dirs: dict[str, Path], embedder: Any, qdrant: Any, max_attempts: int) -> dict[str, Any]:
    from vector_sync import memory_vector_point

    record = load_record(path)
    record["attempts"] = int(record.get("attempts") or 0) + 1
    try:
        memory = dict(record.get("memory") or {})
        if not memory.get("id"):
            raise ValueError("record missing memory.id")
        text = f"{memory.get('title','')}\n{memory.get('content','')}"
        vector = embedder.embed(text)
        if not vector:
            raise RuntimeError("embedding returned no vector")
        qdrant.ensure_collection(len(vector))
        qdrant.upsert([memory_vector_point(memory, vector)])
        record["processed_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        done_path = move_record(path, dirs["done"], record)
        return {"ok": True, "memory_id": int(memory["id"]), "path": str(done_path)}
    except Exception as exc:
        record["last_error"] = str(exc)
        record["last_attempt_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        if int(record.get("attempts") or 0) >= max_attempts:
            failed_path = move_record(path, dirs["failed"], record)
            return {"ok": False, "failed": True, "error": str(exc), "path": str(failed_path)}
        retry_path = move_record(path, dirs["pending"], record)
        return {"ok": False, "retry": True, "error": str(exc), "path": str(retry_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Drain pending memory vector cache files into Qdrant at low resource usage.")
    parser.add_argument("--cache-dir", default="")
    parser.add_argument("--provider", default="")
    parser.add_argument("--model", default="")
    parser.add_argument("--http-url", default="")
    parser.add_argument("--qdrant-url", default="")
    parser.add_argument("--collection", default="")
    parser.add_argument("--profile", default="")
    parser.add_argument("--timeout-seconds", type=float, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--sleep-seconds", type=float, default=0.5)
    parser.add_argument("--max-attempts", type=int, default=3)
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()

    from db import CONFIG
    from embedding import Embedder
    from qdrant_client import QdrantLite
    from vector_cache import ensure_queue_dirs, queue_dirs
    from vector_profiles import default_profile, qdrant_config, vector_cache_config

    profile = args.profile or default_profile(CONFIG)
    cache_cfg = vector_cache_config(CONFIG, profile)
    if args.cache_dir:
        cache_cfg["path"] = args.cache_dir
    dirs = ensure_queue_dirs(cache_cfg)

    embedder = Embedder(embedding_config(args, CONFIG))
    if not embedder.available():
        print(json.dumps({"ok": False, "error": "embedding unavailable", "provider": embedder.provider}, ensure_ascii=False))
        return 2

    qdrant_cfg = qdrant_config(CONFIG, profile)
    if args.qdrant_url:
        qdrant_cfg["url"] = args.qdrant_url
    if args.collection:
        qdrant_cfg["collection"] = args.collection
    qdrant = QdrantLite(qdrant_cfg)

    processed = 0
    while True:
        path = claim_pending(dirs)
        if path is None:
            if args.watch:
                time.sleep(max(args.sleep_seconds, 0.1))
                continue
            break
        result = process_one(path, dirs, embedder, qdrant, max(args.max_attempts, 1))
        processed += 1
        print(json.dumps({"processed": processed, **result}, ensure_ascii=False), flush=True)
        if args.limit > 0 and processed >= args.limit:
            break
        if args.batch_size <= 1 or processed % args.batch_size == 0:
            time.sleep(max(args.sleep_seconds, 0.0))

    print(json.dumps({"ok": True, "processed": processed, "cache": {key: str(value) for key, value in queue_dirs(cache_cfg).items()}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
