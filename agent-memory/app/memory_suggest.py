from __future__ import annotations

import re
from typing import Any

from db import search_memories, upsert_memory
from vector_sync import upsert_memory_vector


TYPE_HINTS: list[tuple[str, tuple[str, ...]]] = [
    ("credential_location", ("credential", "password", "密码", "账号", "secret", "凭据")),
    ("decision_policy", ("vs", "选择", "优先级", "fastboot", "upgrade_tool", "ota", "路线选择")),
    ("pitfall", ("error", "failed", "timeout", "permission denied", "踩坑", "失败", "报错")),
    ("route_guard", ("不要", "avoid", "wrong route", "走错", "优先", "先查")),
    ("verified_route", ("verified", "validated", "实测", "验证通过", "known-good", "可用路线")),
    ("doc_index", ("manifest", "summary", "文档", "索引", "来源", "datasheet", "guide")),
    ("hardware_debug", ("dts", "pinctrl", "gpio", "i2c", "spi", "can", "驱动", "外设")),
    ("workflow_policy", ("git", "commit", "jira", "review", "客户", "交付", "文档")),
    ("performance_baseline", ("latency", "ms", "性能", "耗时", "内存", "磁盘")),
]


def compact(text: str, limit: int = 420) -> str:
    value = re.sub(r"\s+", " ", text or "").strip()
    if len(value) <= limit:
        return value
    return value[: max(limit - 3, 0)].rstrip() + "..."


def infer_type(text: str, fallback: str = "project_fact") -> str:
    lowered = (text or "").lower()
    for memory_type, hints in TYPE_HINTS:
        if any(hint.lower() in lowered for hint in hints):
            return memory_type
    return fallback


def infer_title(memory_type: str, text: str) -> str:
    first = compact(text, 96)
    if not first:
        first = "Untitled memory suggestion"
    prefix = memory_type.replace("_", " ").title()
    return f"{prefix}: {first}"


def suggest_memory(payload: dict[str, Any]) -> dict[str, Any]:
    text = str(payload.get("content") or payload.get("observation") or payload.get("text") or "")
    goal = str(payload.get("goal") or "")
    query = compact(" ".join(part for part in (goal, text) if part), 600)
    memory_type = str(payload.get("type") or infer_type(query))
    title = str(payload.get("title") or infer_title(memory_type, query))
    tags = payload.get("tags") or []
    if isinstance(tags, str):
        tags = [item.strip() for item in tags.split(",") if item.strip()]
    tags = [str(tag) for tag in tags]
    if memory_type not in tags:
        tags.insert(0, memory_type)
    suggestion = {
        "type": memory_type,
        "scope": str(payload.get("scope") or payload.get("repo") or payload.get("platform") or "global"),
        "title": title,
        "content": compact(str(payload.get("memory_content") or text or query), 520),
        "tags": tags[:16],
        "source": str(payload.get("source") or "agent-memory/suggest"),
        "confidence": float(payload.get("confidence", 0.85)),
        "importance": float(payload.get("importance", 0.65)),
        "status": str(payload.get("status") or "active"),
    }
    existing = search_memories(query or title, int(payload.get("limit", 5)))
    result: dict[str, Any] = {"ok": True, "suggestion": suggestion, "existing": existing[:5]}
    if bool(payload.get("write", False)):
        for item in existing:
            if item.get("title") == title:
                suggestion["id"] = item.get("id")
                break
        saved = upsert_memory(suggestion)
        try:
            upsert_memory_vector(saved)
        except Exception:
            pass
        result["memory"] = saved
    return result
