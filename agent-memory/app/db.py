from __future__ import annotations

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import yaml


APP_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = Path(os.environ.get("AGENT_MEMORY_CONFIG", APP_ROOT / "app" / "config.yaml"))


def load_config() -> dict[str, Any]:
    with CONFIG_PATH.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


CONFIG = load_config()
DB_PATH = Path(CONFIG.get("database", {}).get("path", APP_ROOT / "agent.db"))


def now_sql() -> str:
    return "datetime('now')"


def to_json_text(value: Any, default: str = "[]") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def from_json_text(value: str, fallback: Any = None) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except Exception:
        return fallback


@contextmanager
def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=5)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 3000")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    schema = (APP_ROOT / "app" / "schema.sql").read_text(encoding="utf-8")
    with connect() as conn:
        conn.executescript(schema)
        existing = {row[1] for row in conn.execute("PRAGMA table_info(document_chunks)").fetchall()}
        if "source_kind" not in existing:
            conn.execute("ALTER TABLE document_chunks ADD COLUMN source_kind TEXT NOT NULL DEFAULT ''")
        if "evidence_level" not in existing:
            conn.execute("ALTER TABLE document_chunks ADD COLUMN evidence_level TEXT NOT NULL DEFAULT ''")
        conn.execute(
            """
            DELETE FROM document_chunks
            WHERE NOT EXISTS (
                SELECT 1 FROM documents WHERE documents.id = document_chunks.document_id
            )
            """
        )
        needs_backfill = conn.execute(
            "SELECT 1 FROM document_chunks WHERE source_kind = '' OR evidence_level = '' LIMIT 1"
        ).fetchone()
        if needs_backfill:
            from rerank import evidence_level as infer_evidence_level
            from rerank import source_kind as infer_source_kind

            rows = conn.execute(
                """
                SELECT document_chunks.id, document_chunks.heading, document_chunks.content,
                       document_chunks.path, document_chunks.tags,
                       documents.title, documents.project, documents.platform, documents.customer
                FROM document_chunks
                JOIN documents ON documents.id = document_chunks.document_id
                WHERE document_chunks.source_kind = '' OR document_chunks.evidence_level = ''
                """
            ).fetchall()
            for row in rows:
                item = dict(row)
                kind = infer_source_kind(item) or "generic_doc"
                evidence = infer_evidence_level({**item, "source_kind": kind}) or "inferred"
                conn.execute(
                    "UPDATE document_chunks SET source_kind = ?, evidence_level = ? WHERE id = ?",
                    (kind, evidence, int(row["id"])),
                )


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    for field in ("tags", "related_doc_ids"):
        if field in data:
            data[field] = from_json_text(data[field], [])
    return data


def make_fts_query(text: str) -> str:
    terms = re.findall(r"[\w./:-]{2,}|[\u4e00-\u9fff]{2,}", text or "")
    cleaned: list[str] = []
    for term in terms[:16]:
        term = term.strip().replace('"', '""')
        if not term:
            continue
        suffix = "*" if re.match(r"^[A-Za-z0-9_./:-]+$", term) else ""
        cleaned.append(f'"{term}"{suffix}')
    return " OR ".join(cleaned)


def upsert_memory(payload: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "type": payload.get("type", "note"),
        "scope": payload.get("scope", "global"),
        "title": payload.get("title", ""),
        "content": payload.get("content", ""),
        "tags": to_json_text(payload.get("tags", [])),
        "source": payload.get("source", ""),
        "related_doc_ids": to_json_text(payload.get("related_doc_ids", [])),
        "confidence": float(payload.get("confidence", 0.8)),
        "importance": float(payload.get("importance", 0.5)),
        "expires_at": payload.get("expires_at"),
        "status": payload.get("status", "active"),
    }
    with connect() as conn:
        if payload.get("id"):
            fields["updated_at"] = None
            assignments = ", ".join(
                f"{key} = ?" for key in fields.keys() if key != "updated_at"
            ) + ", updated_at = datetime('now')"
            values = [value for key, value in fields.items() if key != "updated_at"]
            values.append(payload["id"])
            conn.execute(f"UPDATE memories SET {assignments} WHERE id = ?", values)
            memory_id = int(payload["id"])
        else:
            columns = ", ".join(fields.keys())
            placeholders = ", ".join("?" for _ in fields)
            cur = conn.execute(
                f"INSERT INTO memories ({columns}) VALUES ({placeholders})",
                list(fields.values()),
            )
            memory_id = int(cur.lastrowid)
        row = conn.execute("SELECT * FROM memories WHERE id = ?", (memory_id,)).fetchone()
        return row_to_dict(row) or {}


def get_pinned_memories(limit: int = 5) -> list[dict[str, Any]]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM memories
            WHERE status IN ('active','pinned') AND (status = 'pinned' OR scope = 'global')
              AND (expires_at IS NULL OR expires_at > datetime('now'))
            ORDER BY importance DESC, confidence DESC, updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [row_to_dict(row) or {} for row in rows]


def search_memories(query: str, limit: int = 20) -> list[dict[str, Any]]:
    fts = make_fts_query(query)
    with connect() as conn:
        if not fts:
            rows = conn.execute(
                """
                SELECT memories.*, 0.0 AS text_score
                FROM memories
                WHERE status IN ('active','pinned')
                ORDER BY importance DESC, updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT memories.*, -bm25(memories_fts) AS text_score
                FROM memories_fts
                JOIN memories ON memories_fts.rowid = memories.id
                WHERE memories_fts MATCH ?
                  AND memories.status IN ('active','pinned')
                  AND (memories.expires_at IS NULL OR memories.expires_at > datetime('now'))
                ORDER BY bm25(memories_fts)
                LIMIT ?
                """,
                (fts, limit),
            ).fetchall()
        return [row_to_dict(row) or {} for row in rows]


def get_memories_by_ids(ids: list[int]) -> list[dict[str, Any]]:
    unique_ids = [int(item_id) for item_id in dict.fromkeys(ids) if int(item_id) > 0]
    if not unique_ids:
        return []
    placeholders = ",".join("?" for _ in unique_ids)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT memories.*, 0.0 AS text_score
            FROM memories
            WHERE id IN ({placeholders})
              AND status IN ('active','pinned')
              AND (expires_at IS NULL OR expires_at > datetime('now'))
            """,
            unique_ids,
        ).fetchall()
    by_id = {int(row["id"]): row_to_dict(row) or {} for row in rows}
    return [by_id[item_id] for item_id in unique_ids if item_id in by_id]


def search_document_chunks(query: str, limit: int = 20) -> list[dict[str, Any]]:
    fts = make_fts_query(query)
    with connect() as conn:
        if not fts:
            rows = conn.execute(
                """
                SELECT document_chunks.*, documents.title AS title, documents.project,
                       documents.platform, documents.customer, 0.0 AS text_score
                FROM document_chunks
                JOIN documents ON documents.id = document_chunks.document_id
                ORDER BY document_chunks.updated_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT document_chunks.*, documents.title AS title, documents.project,
                       documents.platform, documents.customer,
                       -bm25(document_chunks_fts) AS text_score
                FROM document_chunks_fts
                JOIN document_chunks ON document_chunks_fts.rowid = document_chunks.id
                JOIN documents ON documents.id = document_chunks.document_id
                WHERE document_chunks_fts MATCH ?
                ORDER BY bm25(document_chunks_fts)
                LIMIT ?
                """,
                (fts, limit),
            ).fetchall()
        return [row_to_dict(row) or {} for row in rows]


def get_document_chunks_by_ids(ids: list[int]) -> list[dict[str, Any]]:
    unique_ids = [int(item_id) for item_id in dict.fromkeys(ids) if int(item_id) > 0]
    if not unique_ids:
        return []
    placeholders = ",".join("?" for _ in unique_ids)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT document_chunks.*, documents.title AS title, documents.project,
                   documents.platform, documents.customer, 0.0 AS text_score
            FROM document_chunks
            JOIN documents ON documents.id = document_chunks.document_id
            WHERE document_chunks.id IN ({placeholders})
            """,
            unique_ids,
        ).fetchall()
    by_id = {int(row["id"]): row_to_dict(row) or {} for row in rows}
    return [by_id[item_id] for item_id in unique_ids if item_id in by_id]


def mark_memories_used(ids: list[int]) -> None:
    if not ids:
        return
    placeholders = ",".join("?" for _ in ids)
    with connect() as conn:
        conn.execute(
            f"""
            UPDATE memories
            SET use_count = use_count + 1, last_used_at = datetime('now')
            WHERE id IN ({placeholders})
            """,
            ids,
        )


def sqlite_health() -> dict[str, Any]:
    with connect() as conn:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        fts = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name IN ('memories_fts','document_chunks_fts')"
        ).fetchall()
        return {"ok": True, "db": str(DB_PATH), "journal_mode": journal_mode, "fts_tables": [r[0] for r in fts]}


if __name__ == "__main__":
    init_db()
    print(json.dumps(sqlite_health(), ensure_ascii=False))
