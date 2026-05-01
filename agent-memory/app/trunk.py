from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from db import connect, from_json_text, to_json_text


NAMESPACE = "conversation_trunk"


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def compact(text: str, limit: int = 600) -> str:
    value = re.sub(r"\s+", " ", text or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(limit - 3, 0)].rstrip() + "..."


def key_for(payload: dict[str, Any]) -> str:
    key = str(payload.get("trunk_id") or payload.get("conversation_id") or payload.get("session_id") or "default")
    return re.sub(r"[^A-Za-z0-9_.:-]+", "_", key)[:120] or "default"


def load_trunk(trunk_id: str) -> dict[str, Any] | None:
    with connect() as conn:
        row = conn.execute(
            "SELECT value_json FROM key_values WHERE namespace = ? AND key = ?",
            (NAMESPACE, trunk_id),
        ).fetchone()
    if not row:
        return None
    return from_json_text(row["value_json"], {})


def save_trunk(trunk_id: str, data: dict[str, Any]) -> dict[str, Any]:
    timestamp = now()
    data["trunk_id"] = trunk_id
    data["updated_at"] = timestamp
    data["last_active_at"] = timestamp
    tags = ["conversation_trunk", str(data.get("status") or "active")]
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
            (NAMESPACE, trunk_id, json.dumps(data, ensure_ascii=False, separators=(",", ":")), to_json_text(tags)),
        )
    return data


def trim_list(items: list[Any], limit: int = 24) -> list[Any]:
    return items[-limit:]


def as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    return [value]


def upsert_trunk(payload: dict[str, Any]) -> dict[str, Any]:
    cleanup_trunks({})
    trunk_id = key_for(payload)
    existing = load_trunk(trunk_id) or {}
    timestamp = now()
    status = str(payload.get("status") or existing.get("status") or "draft")
    data = {
        **existing,
        "trunk_id": trunk_id,
        "title": compact(str(payload.get("title") or existing.get("title") or ""), 160),
        "goal": compact(str(payload.get("goal") or existing.get("goal") or ""), 800),
        "cwd": str(payload.get("cwd") or existing.get("cwd") or ""),
        "repo": str(payload.get("repo") or existing.get("repo") or ""),
        "branch": str(payload.get("branch") or existing.get("branch") or ""),
        "status": status,
        "milestones": as_list(payload.get("milestones", existing.get("milestones", []))),
        "progress": trim_list(as_list(payload.get("progress", existing.get("progress", [])))),
        "branch_notes": trim_list(as_list(payload.get("branch_notes", existing.get("branch_notes", [])))),
        "ttl_hours": int(payload.get("ttl_hours", existing.get("ttl_hours", 168))),
        "draft_ttl_hours": int(payload.get("draft_ttl_hours", existing.get("draft_ttl_hours", 24))),
        "created_at": existing.get("created_at") or timestamp,
        "updated_at": timestamp,
        "last_active_at": timestamp,
    }
    if status == "active" and not data.get("activated_at"):
        data["activated_at"] = timestamp
    return {"ok": True, "trunk": save_trunk(trunk_id, data)}


def get_trunk(payload: dict[str, Any]) -> dict[str, Any]:
    trunk_id = key_for(payload)
    item = load_trunk(trunk_id)
    return {"ok": item is not None, "trunk": item}


def update_trunk(payload: dict[str, Any]) -> dict[str, Any]:
    trunk_id = key_for(payload)
    data = load_trunk(trunk_id) or upsert_trunk(payload).get("trunk", {})
    status = payload.get("status")
    if status:
        data["status"] = str(status)
        if status == "active" and not data.get("activated_at"):
            data["activated_at"] = now()
    if payload.get("goal"):
        data["goal"] = compact(str(payload["goal"]), 800)
    if payload.get("title"):
        data["title"] = compact(str(payload["title"]), 160)
    if "milestones" in payload and payload.get("milestones") is not None:
        data["milestones"] = payload.get("milestones") or []
    if payload.get("milestone_id") and payload.get("milestone_status"):
        milestone_id = str(payload["milestone_id"])
        for milestone in data.get("milestones", []):
            if str(milestone.get("id") or milestone.get("title") or milestone.get("text")) == milestone_id:
                milestone["status"] = str(payload["milestone_status"])
                milestone["updated_at"] = now()
    if payload.get("progress"):
        progress = data.setdefault("progress", [])
        progress.append({"ts": now(), "text": compact(str(payload["progress"]), 500)})
        data["progress"] = trim_list(progress)
    if payload.get("branch_note"):
        notes = data.setdefault("branch_notes", [])
        notes.append({"ts": now(), "text": compact(str(payload["branch_note"]), 500)})
        data["branch_notes"] = trim_list(notes)
    return {"ok": True, "trunk": save_trunk(trunk_id, data)}


def list_trunks(payload: dict[str, Any]) -> dict[str, Any]:
    limit = int(payload.get("limit", 20))
    status = str(payload.get("status") or "")
    cleanup_trunks({})
    with connect() as conn:
        rows = conn.execute(
            "SELECT key, value_json, updated_at FROM key_values WHERE namespace = ? ORDER BY updated_at DESC LIMIT ?",
            (NAMESPACE, limit),
        ).fetchall()
    items = []
    for row in rows:
        data = from_json_text(row["value_json"], {})
        if status and data.get("status") != status:
            continue
        items.append(data)
    return {"ok": True, "items": items[:limit]}


def cleanup_trunks(payload: dict[str, Any]) -> dict[str, Any]:
    draft_hours = int(payload.get("draft_ttl_hours", 24))
    inactive_hours = int(payload.get("inactive_ttl_hours", 168))
    now_dt = datetime.now(timezone.utc)
    delete_keys: list[str] = []
    with connect() as conn:
        rows = conn.execute("SELECT key, value_json FROM key_values WHERE namespace = ?", (NAMESPACE,)).fetchall()
        for row in rows:
            data = from_json_text(row["value_json"], {})
            status = data.get("status") or "draft"
            created = parse_time(data.get("created_at")) or now_dt
            active = parse_time(data.get("last_active_at")) or created
            activated = data.get("activated_at")
            if not activated and now_dt - created > timedelta(hours=draft_hours):
                delete_keys.append(row["key"])
            elif status not in {"done", "archived"} and now_dt - active > timedelta(hours=inactive_hours):
                delete_keys.append(row["key"])
        for key in delete_keys:
            conn.execute("DELETE FROM key_values WHERE namespace = ? AND key = ?", (NAMESPACE, key))
    return {"ok": True, "deleted": len(delete_keys), "keys": delete_keys}
