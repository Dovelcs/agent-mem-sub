from __future__ import annotations

import re
import time
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


def tokens(text: str) -> set[str]:
    values: set[str] = set()
    for token in re.findall(r"[\w./:-]{2,}|[\u4e00-\u9fff]{2,}", text or ""):
        lowered = token.lower()
        values.add(lowered)
        for part in re.split(r"[_./:-]+", lowered):
            if len(part) >= 2:
                values.add(part)
    return values


def normalized(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip().lower()


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


def as_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def context_parts(payload: dict[str, Any]) -> list[str]:
    parts = []
    for key in ("cwd", "repo", "branch", "platform", "device", "document_path", "environment"):
        value = str(payload.get(key) or "").strip()
        if value:
            parts.append(f"{key}={value}")
    return parts


def symbol_location_parts(payload: dict[str, Any]) -> list[str]:
    parts = []
    for key, label in (("symbol", "symbol"), ("function", "function"), ("entry", "entry")):
        value = str(payload.get(key) or "").strip()
        if value:
            parts.append(f"{label}={value}")
            break
    line = str(payload.get("line") or payload.get("line_number") or "").strip()
    if line:
        parts.append(f"line={line}")
    return parts


def scoped_content(fact: str, payload: dict[str, Any]) -> str:
    goal = str(payload.get("goal") or payload.get("purpose") or "").strip()
    extra = symbol_location_parts(payload)
    result = compact(fact, 560)
    if extra:
        result = compact(f"{result} Location: {'; '.join(extra)}.", 620)
    if goal:
        body = f"Purpose: {compact(goal, 220)}. Result: {result}"
    else:
        body = f"Result: {result}"
    parts = context_parts(payload)
    if not parts:
        return compact(body, 760)
    return compact(f"{body} Context: {'; '.join(parts)}.", 900)


def scoped_tags(memory_type: str, payload: dict[str, Any]) -> list[str]:
    tags = as_tags(payload.get("tags"))
    for tag in (memory_type, "verified-conclusion", "scope-bound"):
        if tag not in tags:
            tags.insert(0, tag)
    for key in ("repo", "branch", "platform", "device", "source"):
        value = str(payload.get(key) or "").strip()
        if value and value not in tags:
            tags.append(value)
    cwd = str(payload.get("cwd") or "").strip()
    if cwd and cwd not in tags:
        tags.append(cwd)
    return tags[:24]


def candidate_score(candidate: dict[str, Any], suggestion: dict[str, Any], query: str) -> float:
    score = 0.0
    if candidate.get("type") == suggestion.get("type"):
        score += 0.2
    if candidate.get("scope") == suggestion.get("scope"):
        score += 0.2
    candidate_text = " ".join(
        str(candidate.get(key) or "") for key in ("title", "content", "scope", "source", "tags")
    )
    suggestion_text = " ".join(
        str(suggestion.get(key) or "") for key in ("title", "content", "scope", "source", "tags")
    )
    query_tokens = tokens(query) | tokens(suggestion_text)
    candidate_tokens = tokens(candidate_text)
    if query_tokens and candidate_tokens:
        overlap = query_tokens & candidate_tokens
        score += min(len(overlap) / max(len(query_tokens), 1), 0.45)
        score += min(len(overlap) / max(len(candidate_tokens), 1), 0.25)
    if normalized(candidate.get("title", "")) == normalized(suggestion.get("title", "")):
        score += 0.25
    if normalized(candidate.get("content", "")) == normalized(suggestion.get("content", "")):
        score += 1.0
    return score


def merge_eligible(candidate: dict[str, Any], suggestion: dict[str, Any]) -> bool:
    if candidate.get("type") != suggestion.get("type"):
        return False
    if normalized(candidate.get("content", "")) == normalized(suggestion.get("content", "")):
        return True
    if normalized(candidate.get("title", "")) == normalized(suggestion.get("title", "")):
        return True
    return False


def choose_existing(existing: list[dict[str, Any]], suggestion: dict[str, Any], query: str, threshold: float) -> tuple[dict[str, Any] | None, float]:
    best: dict[str, Any] | None = None
    best_score = 0.0
    for item in existing:
        if not merge_eligible(item, suggestion):
            continue
        score = candidate_score(item, suggestion, query)
        if score > best_score:
            best = item
            best_score = score
    if best and best_score >= threshold:
        return best, best_score
    return None, best_score


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


def write_fact(payload: dict[str, Any]) -> dict[str, Any]:
    started = time.perf_counter()
    fact = str(payload.get("fact") or payload.get("content") or payload.get("observation") or "").strip()
    if not fact:
        return {"ok": False, "error": "empty fact", "action": "skipped", "ms": 0.0}

    query_context = " ".join(
        str(payload.get(key) or "") for key in ("goal", "cwd", "repo", "branch", "platform", "device", "environment")
    )
    query = compact(" ".join(part for part in (fact, query_context) if part), 800)
    memory_type = str(payload.get("type") or infer_type(query))
    scope = str(payload.get("scope") or payload.get("repo") or payload.get("platform") or "global")
    title = str(payload.get("title") or infer_title(memory_type, fact))
    content = scoped_content(fact, payload)
    suggestion = {
        "type": memory_type,
        "scope": scope,
        "title": compact(title, 160),
        "content": content,
        "tags": scoped_tags(memory_type, payload),
        "source": str(payload.get("source") or "agent-memory/write_fact"),
        "confidence": float(payload.get("confidence", 0.85)),
        "importance": float(payload.get("importance", 0.65)),
        "status": str(payload.get("status") or "active"),
        "expires_at": payload.get("expires_at"),
    }

    existing = search_memories(query or title, int(payload.get("limit", 8)))
    threshold = float(payload.get("update_threshold", 0.75))
    selected, selected_score = choose_existing(existing, suggestion, query, threshold)
    action = "created"
    vector = "queued"
    if selected:
        if normalized(selected.get("content", "")) == normalized(suggestion["content"]):
            memory = selected
            action = "skipped"
            vector = "skipped"
        else:
            suggestion["id"] = selected.get("id")
            suggestion["importance"] = max(float(selected.get("importance") or 0), suggestion["importance"])
            suggestion["confidence"] = max(float(selected.get("confidence") or 0), suggestion["confidence"])
            memory = upsert_memory(suggestion)
            action = "updated"
    else:
        memory = upsert_memory(suggestion)

    return {
        "ok": True,
        "action": action,
        "memory": memory,
        "memory_id": memory.get("id"),
        "vector": vector,
        "existing": existing[:5],
        "selected_existing_id": selected.get("id") if selected else None,
        "selected_score": round(selected_score, 4),
        "ms": round((time.perf_counter() - started) * 1000, 2),
    }
