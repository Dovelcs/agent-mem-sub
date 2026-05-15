#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Iterable

from backend import EmbeddingBackend


def read_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


def rows_for_source(conn: sqlite3.Connection, source_type: str, limit: int, min_id: int = 0, max_id: int = 0) -> list[dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    limit_sql = "" if limit <= 0 else " LIMIT ?"
    args: tuple[Any, ...] = () if limit <= 0 else (limit,)
    if source_type == "memory":
        where = "WHERE status IN ('active','pinned')"
        if min_id > 0:
            where += " AND id >= ?"
            args = (min_id,) + args
        if max_id > 0:
            where += " AND id <= ?"
            args = args + (max_id,)
        rows = conn.execute(
            f"""
            SELECT id, title, content, tags, status, expires_at, updated_at
            FROM memories
            {where}
            ORDER BY id
            """ + limit_sql,
            args,
        ).fetchall()
        return [dict(row) for row in rows]
    if source_type == "doc_chunk":
        where = ""
        if min_id > 0:
            where = "WHERE document_chunks.id >= ?"
            args = (min_id,) + args
        if max_id > 0:
            where += " AND " if where else "WHERE "
            where += "document_chunks.id <= ?"
            args = args + (max_id,)
        rows = conn.execute(
            f"""
            SELECT document_chunks.id, document_chunks.document_id,
                   document_chunks.heading, document_chunks.content,
                   document_chunks.path, document_chunks.tags,
                   document_chunks.source_kind, document_chunks.evidence_level,
                   document_chunks.updated_at,
                   documents.title, documents.project, documents.platform,
                   documents.customer
            FROM document_chunks
            JOIN documents ON documents.id = document_chunks.document_id
            {where}
            ORDER BY document_chunks.id
            """ + limit_sql,
            args,
        ).fetchall()
        return [dict(row) for row in rows]
    raise ValueError(f"unsupported source_type: {source_type}")


def batched(items: list[dict[str, Any]], size: int) -> Iterable[list[dict[str, Any]]]:
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


def text_for_item(source_type: str, item: dict[str, Any], prefix: str) -> str:
    if source_type == "memory":
        text = f"{item.get('title','')}\n{item.get('content','')}"
    else:
        text = f"{item.get('title','')}\n{item.get('heading','')}\n{item.get('content','')}"
    text = " ".join(text.split())
    return f"{prefix}{text}" if prefix else text


def point_for_item(source_type: str, item: dict[str, Any], vector: dict[str, Any]) -> dict[str, Any]:
    if source_type == "memory":
        item_id = int(item["id"])
        return {
            "id": 1000000000 + item_id,
            "vector": vector,
            "payload": {
                "source_type": "memory",
                "item_id": item_id,
                "document_id": None,
                "path": "",
                "title": item.get("title", ""),
                "heading": "",
                "project": "",
                "platform": "",
                "customer": "",
                "tags": read_json(item.get("tags"), []),
                "status": item.get("status", ""),
                "expires_at": item.get("expires_at"),
                "source_kind": "memory",
                "evidence_level": "inferred",
                "updated_at": item.get("updated_at", ""),
            },
        }
    item_id = int(item["id"])
    return {
        "id": item_id,
        "vector": vector,
        "payload": {
            "source_type": "doc_chunk",
            "item_id": item_id,
            "document_id": int(item["document_id"]),
            "path": item.get("path", ""),
            "title": item.get("title", ""),
            "heading": item.get("heading", ""),
            "project": item.get("project", ""),
            "platform": item.get("platform", ""),
            "customer": item.get("customer", ""),
            "tags": read_json(item.get("tags"), []),
            "source_kind": item.get("source_kind", ""),
            "evidence_level": item.get("evidence_level", ""),
            "updated_at": item.get("updated_at", ""),
        },
    }


def point_id_for_item(source_type: str, item: dict[str, Any]) -> int:
    item_id = int(item["id"])
    if source_type == "memory":
        return 1000000000 + item_id
    return item_id


def read_existing_point_ids(paths: list[str]) -> set[int]:
    ids: set[int] = set()
    for value in paths:
        for path in Path(value).parent.glob(Path(value).name):
            if not path.exists():
                continue
            with path.open("r", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        point_id = json.loads(line).get("id")
                    except Exception:
                        continue
                    if point_id is not None:
                        ids.add(int(point_id))
    return ids


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Qdrant JSONL vectors from agent-memory SQLite.")
    parser.add_argument("--db", default="/data/agent.db")
    parser.add_argument("--output", default="/out/agent_vectors.jsonl")
    parser.add_argument("--model", default="intfloat/multilingual-e5-small")
    parser.add_argument("--source-type", choices=["memory", "doc_chunk", "all"], default="all")
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--min-id", type=int, default=0)
    parser.add_argument("--max-id", type=int, default=0)
    parser.add_argument("--sort-by-length", action="store_true")
    parser.add_argument("--device", default=None)
    parser.add_argument("--query-prefix", default="passage: ")
    parser.add_argument("--sparse", action="store_true")
    parser.add_argument("--max-length", type=int, default=1024)
    parser.add_argument("--skip-existing", action="append", default=[])
    parser.add_argument("--shard-count", type=int, default=1)
    parser.add_argument("--shard-index", type=int, default=0)
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(json.dumps({"ok": False, "error": f"db not found: {db_path}"}, ensure_ascii=False), file=sys.stderr)
        return 2

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    model = EmbeddingBackend(
        args.model,
        device=args.device,
        sparse=args.sparse or "bge-m3" in args.model.lower(),
        max_length=args.max_length,
    )
    conn = sqlite3.connect(db_path)
    sources = ["memory", "doc_chunk"] if args.source_type == "all" else [args.source_type]
    existing_ids = read_existing_point_ids(args.skip_existing)

    count = 0
    vector_size = None
    with out_path.open("w", encoding="utf-8") as out:
        for source_type in sources:
            items = rows_for_source(conn, source_type, args.limit, args.min_id, args.max_id)
            if existing_ids:
                items = [item for item in items if point_id_for_item(source_type, item) not in existing_ids]
            if args.sort_by_length:
                items.sort(key=lambda item: len(text_for_item(source_type, item, args.query_prefix)))
            if args.shard_count > 1:
                if args.shard_index < 0 or args.shard_index >= args.shard_count:
                    raise ValueError("--shard-index must be in [0, --shard-count)")
                items = [item for idx, item in enumerate(items) if idx % args.shard_count == args.shard_index]
            for batch in batched(items, args.batch_size):
                texts = [text_for_item(source_type, item, args.query_prefix) for item in batch]
                vectors = model.encode(texts, batch_size=args.batch_size)
                for item, vector in zip(batch, vectors):
                    vector_size = len(vector["vector"])
                    out.write(json.dumps(point_for_item(source_type, item, vector), ensure_ascii=False, separators=(",", ":")) + "\n")
                    count += 1
                print(json.dumps({"source_type": source_type, "points": count}, ensure_ascii=False), flush=True)
    conn.close()
    print(json.dumps({"ok": True, "output": str(out_path), "points": count, "vector_size": vector_size}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
