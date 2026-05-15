from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Any, Callable

from db import (
    CONFIG,
    DB_PATH,
    connect,
    from_json_text,
    get_pinned_memories,
    get_user_preferences,
    init_db,
    row_to_dict,
    search_document_chunks,
    search_memories,
    sqlite_health,
    to_json_text,
    upsert_memory,
)
from embedding import Embedder
from ingest_docs import ingest_path
from memory_suggest import suggest_memory
from qdrant_client import QdrantLite
from recall_core import build_recall, select_bucketed_doc_chunks
from rerank import rerank
from trunk import cleanup_trunks, get_trunk, list_trunks, update_trunk, upsert_trunk
from vector_cache import queue_memory_vector, vector_cache_status
from vector_profiles import default_profile, embedding_config, profile_names, qdrant_config
from vector_sync import delete_document_vectors, delete_memory_vector


PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "agent-memory"
SERVER_VERSION = "0.2.0"
ROOT = Path(__file__).resolve().parent.parent


def jdump(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def as_text(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        text = value
    else:
        text = json.dumps(value, ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}]}


def read_json(row_value: str | None, fallback: Any = None) -> Any:
    return from_json_text(row_value or "", fallback)


def one_row(sql: str, args: tuple[Any, ...] = ()) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(sql, args).fetchone()
        return row_to_dict(row)


def rows(sql: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    with connect() as conn:
        return [row_to_dict(row) or {} for row in conn.execute(sql, args).fetchall()]


def table_count(table: str) -> int:
    with connect() as conn:
        return int(conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0])


def normalize_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(v) for v in parsed]
        except Exception:
            pass
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def snippet(text: str, limit: int) -> str:
    compact = re.sub(r"\s+", " ", text or "").strip()
    if len(compact) <= limit:
        return compact
    return compact[: max(limit - 3, 0)].rstrip() + "..."


def memory_line(item: dict[str, Any]) -> str:
    return f"- {item.get('title') or 'memory ' + str(item.get('id'))}: {snippet(item.get('content', ''), 360)}"


def doc_line(item: dict[str, Any]) -> str:
    path = item.get("path") or ""
    title = item.get("title") or path
    heading = item.get("heading") or ""
    label = title if not heading else f"{title} / {heading}"
    return f"- {path} | {label}: {snippet(item.get('content', ''), 280)}"


def recall_local(args: dict[str, Any]) -> dict[str, Any]:
    return build_recall(args)


def tool_health(args: dict[str, Any]) -> dict[str, Any]:
    vector_profiles = {}
    for profile in profile_names(CONFIG):
        emb_cfg = embedding_config(CONFIG, profile)
        embedder = Embedder(emb_cfg)
        vector_profiles[profile] = {
            "default": profile == default_profile(CONFIG),
            "qdrant": QdrantLite(qdrant_config(CONFIG, profile)).health(),
            "embedding": {"provider": embedder.provider, "available": embedder.available()},
        }
    default = vector_profiles.get(default_profile(CONFIG), {})
    return {
        "ok": True,
        "sqlite": sqlite_health(),
        "qdrant": default.get("qdrant", {}),
        "embedding": default.get("embedding", {}),
        "vector_profiles": vector_profiles,
    }


def tool_stats(args: dict[str, Any]) -> dict[str, Any]:
    profile = default_profile(CONFIG)
    emb_cfg = embedding_config(CONFIG, profile)
    embedder = Embedder(emb_cfg)
    return {
        "database": str(DB_PATH),
        "counts": {
            "memories": table_count("memories"),
            "documents": table_count("documents"),
            "document_chunks": table_count("document_chunks"),
            "key_values": table_count("key_values"),
        },
        "qdrant": QdrantLite(qdrant_config(CONFIG, profile)).health(),
        "embedding": {"provider": embedder.provider, "available": embedder.available()},
    }


def tool_recall(args: dict[str, Any]) -> dict[str, Any]:
    return recall_local(args)


def tool_memory_upsert(args: dict[str, Any]) -> dict[str, Any]:
    payload = dict(args)
    payload["tags"] = normalize_tags(payload.get("tags", []))
    memory = upsert_memory(payload)
    queued = queue_memory_vector(memory, CONFIG.get("vector_cache", {}))
    result = {"ok": True, "memory": memory, "vector": "queued" if queued.get("queued") else "skipped"}
    if queued.get("path"):
        result["vector_cache_path"] = queued.get("path")
    if queued.get("paths"):
        result["vector_cache_paths"] = queued.get("paths")
    return result


def tool_memory_get(args: dict[str, Any]) -> dict[str, Any]:
    memory_id = int(args["id"])
    memory = one_row("SELECT * FROM memories WHERE id = ?", (memory_id,))
    return {"ok": memory is not None, "memory": memory}


def tool_memory_search(args: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "items": search_memories(str(args.get("query", "")), int(args.get("limit", 20)))}


def tool_memory_suggest(args: dict[str, Any]) -> dict[str, Any]:
    payload = dict(args)
    payload["tags"] = normalize_tags(payload.get("tags", []))
    return suggest_memory(payload)


def tool_memory_list(args: dict[str, Any]) -> dict[str, Any]:
    status = str(args.get("status", "active"))
    limit = int(args.get("limit", 50))
    if status == "all":
        items = rows("SELECT * FROM memories ORDER BY updated_at DESC LIMIT ?", (limit,))
    else:
        items = rows("SELECT * FROM memories WHERE status = ? ORDER BY importance DESC, updated_at DESC LIMIT ?", (status, limit))
    return {"ok": True, "items": items}


def tool_memory_archive(args: dict[str, Any]) -> dict[str, Any]:
    memory_id = int(args["id"])
    with connect() as conn:
        conn.execute("UPDATE memories SET status='archived', updated_at=datetime('now') WHERE id=?", (memory_id,))
    return tool_memory_get({"id": memory_id})


def tool_memory_delete(args: dict[str, Any]) -> dict[str, Any]:
    memory_id = int(args["id"])
    delete_memory_vector(memory_id)
    with connect() as conn:
        cur = conn.execute("DELETE FROM memories WHERE id=?", (memory_id,))
        deleted = cur.rowcount
    return {"ok": True, "deleted": deleted}


def tool_pinned(args: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "items": get_pinned_memories(int(args.get("limit", 5)))}


def tool_user_preferences(args: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, "items": get_user_preferences(int(args.get("limit", 8)))}


def tool_docs_ingest(args: dict[str, Any]) -> dict[str, Any]:
    docs_path = str(args.get("docs_path") or CONFIG.get("ingest", {}).get("docs_path", ROOT / "docs"))
    return ingest_path(docs_path, {
        "project": str(args.get("project", "")),
        "platform": str(args.get("platform", "")),
        "customer": str(args.get("customer", "")),
        "tags": normalize_tags(args.get("tags", [])),
    })


def tool_docs_search(args: dict[str, Any]) -> dict[str, Any]:
    limit = int(args.get("limit", 20))
    query = str(args.get("query", ""))
    candidates = search_document_chunks(query, max(limit * 4, limit))
    request = {
        "prompt": query,
        "cwd": str(args.get("cwd", "")),
        "repo": str(args.get("repo", "")),
        "branch": str(args.get("branch", "")),
    }
    return {"ok": True, "items": select_bucketed_doc_chunks(rerank(candidates, request), limit)}


def tool_docs_list(args: dict[str, Any]) -> dict[str, Any]:
    limit = int(args.get("limit", 50))
    project = str(args.get("project", ""))
    if project:
        items = rows("SELECT * FROM documents WHERE project = ? ORDER BY updated_at DESC LIMIT ?", (project, limit))
    else:
        items = rows("SELECT * FROM documents ORDER BY updated_at DESC LIMIT ?", (limit,))
    return {"ok": True, "items": items}


def tool_doc_get(args: dict[str, Any]) -> dict[str, Any]:
    doc_id = int(args["id"])
    doc = one_row("SELECT * FROM documents WHERE id = ?", (doc_id,))
    limit = int(args.get("chunk_limit", 20))
    chunks = rows(
        "SELECT * FROM document_chunks WHERE document_id = ? ORDER BY chunk_index LIMIT ?",
        (doc_id, limit),
    )
    return {"ok": doc is not None, "document": doc, "chunks": chunks}


def tool_doc_delete(args: dict[str, Any]) -> dict[str, Any]:
    doc_id = int(args["id"])
    delete_document_vectors(doc_id)
    with connect() as conn:
        cur = conn.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        deleted = cur.rowcount
    return {"ok": True, "deleted": deleted}


def tool_chunk_get(args: dict[str, Any]) -> dict[str, Any]:
    chunk_id = int(args["id"])
    chunk = one_row(
        """
        SELECT document_chunks.*, documents.title AS title, documents.project,
               documents.platform, documents.customer
        FROM document_chunks
        JOIN documents ON documents.id = document_chunks.document_id
        WHERE document_chunks.id = ?
        """,
        (chunk_id,),
    )
    return {"ok": chunk is not None, "chunk": chunk}


def tool_kv_upsert(args: dict[str, Any]) -> dict[str, Any]:
    namespace = str(args.get("namespace", "default"))
    key = str(args["key"])
    value = args.get("value_json", args.get("value", {}))
    tags = normalize_tags(args.get("tags", []))
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO key_values(namespace, key, value_json, tags, updated_at)
            VALUES (?, ?, ?, ?, datetime('now'))
            ON CONFLICT(namespace, key) DO UPDATE SET
              value_json=excluded.value_json,
              tags=excluded.tags,
              updated_at=datetime('now')
            """,
            (namespace, key, jdump(value), to_json_text(tags)),
        )
    return tool_kv_get({"namespace": namespace, "key": key})


def tool_kv_get(args: dict[str, Any]) -> dict[str, Any]:
    item = one_row(
        "SELECT * FROM key_values WHERE namespace = ? AND key = ?",
        (str(args.get("namespace", "default")), str(args["key"])),
    )
    if item:
        item["value_json"] = read_json(item.get("value_json"), {})
    return {"ok": item is not None, "item": item}


def tool_kv_list(args: dict[str, Any]) -> dict[str, Any]:
    namespace = str(args.get("namespace", "default"))
    limit = int(args.get("limit", 50))
    items = rows("SELECT * FROM key_values WHERE namespace = ? ORDER BY updated_at DESC LIMIT ?", (namespace, limit))
    for item in items:
        item["value_json"] = read_json(item.get("value_json"), {})
    return {"ok": True, "items": items}


def tool_kv_delete(args: dict[str, Any]) -> dict[str, Any]:
    with connect() as conn:
        cur = conn.execute(
            "DELETE FROM key_values WHERE namespace = ? AND key = ?",
            (str(args.get("namespace", "default")), str(args["key"])),
        )
        deleted = cur.rowcount
    return {"ok": True, "deleted": deleted}


def tool_backup(args: dict[str, Any]) -> dict[str, Any]:
    script = ROOT / "scripts" / "backup.sh"
    proc = subprocess.run([str(script)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
    return {"ok": proc.returncode == 0, "returncode": proc.returncode, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}


def tool_qdrant_status(args: dict[str, Any]) -> dict[str, Any]:
    profile = str(args.get("profile") or default_profile(CONFIG))
    return QdrantLite(qdrant_config(CONFIG, profile)).health()


def tool_qdrant_ensure(args: dict[str, Any]) -> dict[str, Any]:
    profile = str(args.get("profile") or default_profile(CONFIG))
    qdrant_cfg = qdrant_config(CONFIG, profile)
    qdrant = QdrantLite(qdrant_cfg)
    qdrant.ensure_collection(int(args.get("vector_size") or qdrant_cfg.get("vector_size", 384)))
    return qdrant.health()


def tool_vector_cache_status(args: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True, **vector_cache_status(CONFIG.get("vector_cache", {}))}


def tool_trunk_upsert(args: dict[str, Any]) -> dict[str, Any]:
    return upsert_trunk(dict(args))


def tool_trunk_get(args: dict[str, Any]) -> dict[str, Any]:
    return get_trunk(dict(args))


def tool_trunk_update(args: dict[str, Any]) -> dict[str, Any]:
    return update_trunk(dict(args))


def tool_trunk_list(args: dict[str, Any]) -> dict[str, Any]:
    return list_trunks(dict(args))


def tool_trunk_cleanup(args: dict[str, Any]) -> dict[str, Any]:
    return cleanup_trunks(dict(args))


def schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


TOOLS: dict[str, dict[str, Any]] = {
    "health": {"description": "Check SQLite, FTS5, and Qdrant status.", "handler": tool_health, "inputSchema": schema({})},
    "stats": {"description": "Return lightweight database counts and Qdrant status.", "handler": tool_stats, "inputSchema": schema({})},
    "recall": {"description": "Recall top relevant memories and document chunks for a prompt.", "handler": tool_recall, "inputSchema": schema({
        "prompt": {"type": "string"},
        "cwd": {"type": "string"},
        "repo": {"type": "string"},
        "branch": {"type": "string"},
        "limit_memories": {"type": "integer", "default": 5},
        "limit_docs": {"type": "integer", "default": 3},
        "limit_candidates": {"type": "integer", "default": 8},
        "trunk_id": {"type": "string"},
        "conversation_id": {"type": "string"},
        "include_user_preferences": {"type": "boolean", "default": False},
        "auto_include_memories": {"type": "boolean", "default": False},
        "auto_include_docs": {"type": "boolean", "default": False},
        "include_candidate_context": {"type": "boolean", "default": True},
        "include_trace": {"type": "boolean", "default": False},
    }, ["prompt"])},
    "memory_upsert": {"description": "Create or update a memory.", "handler": tool_memory_upsert, "inputSchema": schema({
        "id": {"type": "integer"},
        "type": {"type": "string"},
        "scope": {"type": "string"},
        "title": {"type": "string"},
        "content": {"type": "string"},
        "tags": {"type": ["array", "string"], "items": {"type": "string"}},
        "source": {"type": "string"},
        "related_doc_ids": {"type": ["array", "string"], "items": {"type": "integer"}},
        "confidence": {"type": "number"},
        "importance": {"type": "number"},
        "expires_at": {"type": ["string", "null"]},
        "status": {"type": "string"},
    }, ["title", "content"])},
    "memory_get": {"description": "Get one memory by id.", "handler": tool_memory_get, "inputSchema": schema({"id": {"type": "integer"}}, ["id"])},
    "memory_search": {"description": "Search active/pinned memories with SQLite FTS5.", "handler": tool_memory_search, "inputSchema": schema({"query": {"type": "string"}, "limit": {"type": "integer", "default": 20}}, ["query"])},
    "memory_suggest": {"description": "Suggest or write a short typed memory after checking existing matches.", "handler": tool_memory_suggest, "inputSchema": schema({
        "observation": {"type": "string"},
        "text": {"type": "string"},
        "goal": {"type": "string"},
        "type": {"type": "string"},
        "scope": {"type": "string"},
        "title": {"type": "string"},
        "memory_content": {"type": "string"},
        "tags": {"type": ["array", "string"], "items": {"type": "string"}},
        "write": {"type": "boolean", "default": False},
        "limit": {"type": "integer", "default": 5},
    })},
    "memory_list": {"description": "List memories by status, or all.", "handler": tool_memory_list, "inputSchema": schema({"status": {"type": "string", "default": "active"}, "limit": {"type": "integer", "default": 50}})},
    "memory_archive": {"description": "Archive a memory by id.", "handler": tool_memory_archive, "inputSchema": schema({"id": {"type": "integer"}}, ["id"])},
    "memory_delete": {"description": "Permanently delete a memory by id.", "handler": tool_memory_delete, "inputSchema": schema({"id": {"type": "integer"}}, ["id"])},
    "pinned_memories": {"description": "List pinned/global high-importance memories.", "handler": tool_pinned, "inputSchema": schema({"limit": {"type": "integer", "default": 5}})},
    "user_preferences": {"description": "List mandatory user preference memories from type=user_style or scope=user_preferences.", "handler": tool_user_preferences, "inputSchema": schema({"limit": {"type": "integer", "default": 8}})},
    "docs_ingest": {"description": "Incrementally ingest supported text documents from docs_path.", "handler": tool_docs_ingest, "inputSchema": schema({
        "docs_path": {"type": "string"},
        "project": {"type": "string"},
        "platform": {"type": "string"},
        "customer": {"type": "string"},
        "tags": {"type": ["array", "string"], "items": {"type": "string"}},
    })},
    "docs_search": {"description": "Search document chunks with platform-aware bucketed rerank.", "handler": tool_docs_search, "inputSchema": schema({"query": {"type": "string"}, "limit": {"type": "integer", "default": 20}, "cwd": {"type": "string"}, "repo": {"type": "string"}, "branch": {"type": "string"}}, ["query"])},
    "docs_list": {"description": "List indexed documents.", "handler": tool_docs_list, "inputSchema": schema({"project": {"type": "string"}, "limit": {"type": "integer", "default": 50}})},
    "doc_get": {"description": "Get a document and its first chunks by document id.", "handler": tool_doc_get, "inputSchema": schema({"id": {"type": "integer"}, "chunk_limit": {"type": "integer", "default": 20}}, ["id"])},
    "doc_delete": {"description": "Delete a document and its chunks by document id.", "handler": tool_doc_delete, "inputSchema": schema({"id": {"type": "integer"}}, ["id"])},
    "chunk_get": {"description": "Get one document chunk by id.", "handler": tool_chunk_get, "inputSchema": schema({"id": {"type": "integer"}}, ["id"])},
    "kv_upsert": {"description": "Create or update a namespaced JSON key-value item.", "handler": tool_kv_upsert, "inputSchema": schema({"namespace": {"type": "string"}, "key": {"type": "string"}, "value_json": {}, "tags": {"type": ["array", "string"], "items": {"type": "string"}}}, ["key"])},
    "kv_get": {"description": "Get a namespaced key-value item.", "handler": tool_kv_get, "inputSchema": schema({"namespace": {"type": "string"}, "key": {"type": "string"}}, ["key"])},
    "kv_list": {"description": "List namespaced key-value items.", "handler": tool_kv_list, "inputSchema": schema({"namespace": {"type": "string"}, "limit": {"type": "integer", "default": 50}})},
    "kv_delete": {"description": "Delete a namespaced key-value item.", "handler": tool_kv_delete, "inputSchema": schema({"namespace": {"type": "string"}, "key": {"type": "string"}}, ["key"])},
    "backup": {"description": "Run the lightweight backup script.", "handler": tool_backup, "inputSchema": schema({})},
    "qdrant_status": {"description": "Check Qdrant readiness.", "handler": tool_qdrant_status, "inputSchema": schema({"profile": {"type": "string", "default": ""}})},
    "qdrant_ensure_collection": {"description": "Ensure Qdrant collection and payload indexes exist.", "handler": tool_qdrant_ensure, "inputSchema": schema({"profile": {"type": "string", "default": ""}, "vector_size": {"type": "integer", "default": 384}})},
    "vector_cache_status": {"description": "Check pending memory vector cache jobs.", "handler": tool_vector_cache_status, "inputSchema": schema({})},
    "trunk_upsert": {"description": "Create or replace a compact conversation trunk in the memory key-value store.", "handler": tool_trunk_upsert, "inputSchema": schema({
        "trunk_id": {"type": "string"},
        "conversation_id": {"type": "string"},
        "title": {"type": "string"},
        "goal": {"type": "string"},
        "cwd": {"type": "string"},
        "repo": {"type": "string"},
        "branch": {"type": "string"},
        "status": {"type": "string"},
        "milestones": {"type": "array"},
        "ttl_hours": {"type": "integer", "default": 168},
        "draft_ttl_hours": {"type": "integer", "default": 24},
    })},
    "trunk_get": {"description": "Get one compact conversation trunk.", "handler": tool_trunk_get, "inputSchema": schema({"trunk_id": {"type": "string"}, "conversation_id": {"type": "string"}})},
    "trunk_update": {"description": "Append progress or branch notes and update status/milestones for a conversation trunk.", "handler": tool_trunk_update, "inputSchema": schema({
        "trunk_id": {"type": "string"},
        "conversation_id": {"type": "string"},
        "title": {"type": "string"},
        "goal": {"type": "string"},
        "status": {"type": "string"},
        "milestones": {"type": "array"},
        "milestone_id": {"type": "string"},
        "milestone_status": {"type": "string"},
        "progress": {"type": "string"},
        "branch_note": {"type": "string"},
    })},
    "trunk_list": {"description": "List compact conversation trunks.", "handler": tool_trunk_list, "inputSchema": schema({"status": {"type": "string"}, "limit": {"type": "integer", "default": 20}})},
    "trunk_cleanup": {"description": "Delete stale draft or inactive conversation trunks.", "handler": tool_trunk_cleanup, "inputSchema": schema({"draft_ttl_hours": {"type": "integer", "default": 24}, "inactive_ttl_hours": {"type": "integer", "default": 168}})},
}


def tool_defs() -> list[dict[str, Any]]:
    return [
        {"name": name, "description": spec["description"], "inputSchema": spec["inputSchema"]}
        for name, spec in TOOLS.items()
    ]


def resource_list() -> list[dict[str, Any]]:
    return [
        {"uri": "agent-memory://health", "name": "Agent Memory Health", "mimeType": "application/json"},
        {"uri": "agent-memory://stats", "name": "Agent Memory Stats", "mimeType": "application/json"},
        {"uri": "agent-memory://memories/pinned", "name": "Pinned Memories", "mimeType": "application/json"},
        {"uri": "agent-memory://documents", "name": "Indexed Documents", "mimeType": "application/json"},
        {"uri": "agent-memory://trunks", "name": "Conversation Trunks", "mimeType": "application/json"},
    ]


def resource_read(uri: str) -> Any:
    if uri == "agent-memory://health":
        return tool_health({})
    if uri == "agent-memory://stats":
        return tool_stats({})
    if uri == "agent-memory://memories/pinned":
        return tool_pinned({"limit": 20})
    if uri == "agent-memory://documents":
        return tool_docs_list({"limit": 100})
    if uri == "agent-memory://trunks":
        return tool_trunk_list({"limit": 20})
    raise ValueError(f"unknown resource uri: {uri}")


def handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    msg_id = message.get("id")
    if msg_id is None:
        return None

    try:
        if method == "initialize":
            result = {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}, "resources": {"subscribe": False, "listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            }
        elif method == "tools/list":
            result = {"tools": tool_defs()}
        elif method == "tools/call":
            params = message.get("params") or {}
            name = params.get("name")
            args = params.get("arguments") or {}
            if name not in TOOLS:
                raise ValueError(f"unknown tool: {name}")
            result = as_text(TOOLS[name]["handler"](args))
        elif method == "resources/list":
            result = {"resources": resource_list()}
        elif method == "resources/read":
            uri = (message.get("params") or {}).get("uri")
            data = resource_read(str(uri))
            result = {"contents": [{"uri": uri, "mimeType": "application/json", "text": json.dumps(data, ensure_ascii=False, indent=2)}]}
        elif method == "prompts/list":
            result = {"prompts": []}
        elif method == "ping":
            result = {}
        else:
            raise ValueError(f"unsupported method: {method}")
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}
    except Exception as exc:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32000, "message": str(exc)},
        }


def serve() -> None:
    init_db()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
            response = handle_request(message)
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": str(exc)},
            }
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False, separators=(",", ":")) + "\n")
            sys.stdout.flush()


if __name__ == "__main__":
    try:
        serve()
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc(file=sys.stderr)
        sys.exit(1)
