from __future__ import annotations

import re
from typing import Any

from db import (
    CONFIG,
    get_pinned_memories,
    mark_memories_used,
    search_document_chunks,
    search_memories,
)
from embedding import Embedder
from qdrant_client import QdrantLite
from intent import expand_prompt, expansion_trace
from rerank import rerank


def snippet(text: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)].rstrip() + "..."


def memory_line(item: dict[str, Any]) -> str:
    title = item.get("title") or f"memory {item.get('id')}"
    content = snippet(item.get("content", ""), 360)
    return f"- {title}: {content}"


def doc_line(item: dict[str, Any]) -> str:
    path = item.get("path") or ""
    title = item.get("title") or path
    heading = item.get("heading") or ""
    text = snippet(item.get("content", ""), 280)
    label = title if not heading else f"{title} / {heading}"
    return f"- {path} | {label}: {text}"


def trunk_section(payload: dict[str, Any]) -> str:
    trunk_id = str(payload.get("trunk_id") or payload.get("conversation_id") or payload.get("session_id") or "")
    if not trunk_id:
        return ""
    try:
        from trunk import get_trunk

        item = (get_trunk({"trunk_id": trunk_id}).get("trunk") or {})
    except Exception:
        return ""
    if not item:
        return ""
    lines = []
    goal = snippet(str(item.get("goal") or ""), 280)
    if goal:
        lines.append(f"- Goal: {goal}")
    milestones = item.get("milestones") or []
    if milestones:
        compact_milestones = []
        for milestone in milestones[:6]:
            if isinstance(milestone, dict):
                label = milestone.get("text") or milestone.get("title") or milestone.get("id")
                status = milestone.get("status") or "pending"
                compact_milestones.append(f"{status}:{label}")
            else:
                compact_milestones.append(str(milestone))
        lines.append("- Milestones: " + snippet("; ".join(compact_milestones), 360))
    progress = item.get("progress") or []
    if progress:
        last = progress[-1]
        text = last.get("text") if isinstance(last, dict) else str(last)
        lines.append("- Last progress: " + snippet(str(text or ""), 240))
    return "Current trunk:\n" + "\n".join(lines) if lines else ""


def memory_bucket(item: dict[str, Any]) -> str:
    memory_type = str(item.get("type") or "")
    if memory_type == "user_style":
        return "User style"
    if memory_type in {"decision_policy", "route_guard", "verified_route", "agent_route", "route"}:
        return "Route decisions"
    if memory_type == "pitfall":
        return "Pitfalls"
    if memory_type in {"project_fact", "hardware_debug", "project"}:
        return "Project facts"
    if memory_type in {"workflow_policy", "credential_location"}:
        return "Workflow and access"
    if memory_type in {"doc_index", "performance_baseline", "system"}:
        return "System context"
    return "Other memory"


def select_typed_memories(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    bucket_order = [
        "User style",
        "Route decisions",
        "Pitfalls",
        "Workflow and access",
        "Project facts",
        "System context",
        "Other memory",
    ]
    quotas = {
        "User style": 1,
        "Route decisions": 2,
        "Pitfalls": 1,
        "Workflow and access": 1,
        "Project facts": 2,
        "System context": 1,
        "Other memory": 1,
    }
    buckets: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in bucket_order}
    for item in items:
        buckets.setdefault(memory_bucket(item), []).append(item)
    selected: list[dict[str, Any]] = []
    seen: set[int] = set()

    def take(bucket: str, count: int) -> None:
        for item in buckets.get(bucket, []):
            if len(selected) >= limit or count <= 0:
                return
            item_id = int(item.get("id") or item.get("item_id") or 0)
            if item_id and item_id in seen:
                continue
            selected.append(item)
            if item_id:
                seen.add(item_id)
            count -= 1

    for bucket in bucket_order:
        take(bucket, quotas.get(bucket, 1))
        if len(selected) >= limit:
            return selected
    for item in items:
        if len(selected) >= limit:
            break
        item_id = int(item.get("id") or item.get("item_id") or 0)
        if item_id and item_id in seen:
            continue
        selected.append(item)
        if item_id:
            seen.add(item_id)
    return selected


def memory_sections(items: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for section in (
        "User style",
        "Route decisions",
        "Pitfalls",
        "Workflow and access",
        "Project facts",
        "System context",
        "Other memory",
    ):
        group = [item for item in items if memory_bucket(item) == section]
        if group:
            parts.append(section + ":\n" + "\n".join(memory_line(item) for item in group))
    return "\n\n".join(parts)


def vector_items(request: dict[str, Any]) -> list[dict[str, Any]]:
    emb_cfg = CONFIG.get("embedding", {})
    if not bool(emb_cfg.get("allow_during_recall", False)):
        return []
    embedder = Embedder(emb_cfg)
    vector = embedder.embed(str(request.get("prompt") or ""))
    if not vector:
        return []
    qdrant = QdrantLite(CONFIG.get("qdrant", {}))
    results = qdrant.search(vector, limit=int(CONFIG.get("recall", {}).get("vector_limit", 20)))
    items = []
    for hit in results:
        payload = dict(hit.get("payload") or {})
        payload["source_type"] = payload.get("source_type") or "vector"
        payload["id"] = payload.get("item_id")
        payload["vector_score"] = float(hit.get("score") or 0.0)
        items.append(payload)
    return items


def diversify_doc_chunks(
    items: list[dict[str, Any]], limit: int, max_per_document: int = 1, allow_overflow: bool = False
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    per_doc: dict[int, int] = {}
    overflow: list[dict[str, Any]] = []
    for item in items:
        document_id = item.get("document_id")
        if document_id is None:
            selected.append(item)
        else:
            key = int(document_id)
            if per_doc.get(key, 0) < max_per_document:
                selected.append(item)
                per_doc[key] = per_doc.get(key, 0) + 1
            else:
                overflow.append(item)
        if len(selected) >= limit:
            return selected
    if not allow_overflow:
        return selected
    for item in overflow:
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def doc_bucket(item: dict[str, Any]) -> str:
    kind = str(item.get("source_kind") or "")
    scope = str(item.get("reuse_scope") or "")
    if scope == "same_platform" and kind in {"dts", "config", "repo_code"}:
        return "same_platform_code"
    if scope == "same_platform" and kind == "official_doc":
        return "same_platform_docs"
    if kind == "official_doc":
        return "official_docs"
    if scope == "same_family" and kind in {"dts", "config", "repo_code"}:
        return "similar_platform_code"
    if scope == "same_family":
        return "similar_platform_docs"
    if kind in {"dts", "config", "repo_code"}:
        return "repo_code"
    return "generic_docs"


def select_bucketed_doc_chunks(items: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []
    bucket_order = [
        "same_platform_code",
        "same_platform_docs",
        "official_docs",
        "similar_platform_code",
        "similar_platform_docs",
        "repo_code",
        "generic_docs",
    ]
    buckets: dict[str, list[dict[str, Any]]] = {bucket: [] for bucket in bucket_order}
    for item in items:
        buckets.setdefault(doc_bucket(item), []).append(item)

    selected: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    seen_documents: set[int] = set()
    seen_titles: set[str] = set()

    def title_key(item: dict[str, Any]) -> str:
        title = str(item.get("title") or "")
        if not title:
            return ""
        return re.sub(r"\s+", " ", title).strip().lower()

    def take_from(bucket: str, count: int = 1) -> None:
        for item in buckets.get(bucket, []):
            if len(selected) >= limit or count <= 0:
                return
            item_id = int(item.get("id") or 0)
            document_id = int(item.get("document_id") or 0)
            if item_id and item_id in seen_ids:
                continue
            if document_id and document_id in seen_documents:
                continue
            title = title_key(item)
            if title and title in seen_titles:
                continue
            selected.append(item)
            if item_id:
                seen_ids.add(item_id)
            if document_id:
                seen_documents.add(document_id)
            if title:
                seen_titles.add(title)
            count -= 1

    bucket_quotas = {
        "same_platform_code": 2,
        "same_platform_docs": max(3, limit),
        "official_docs": 1,
        "similar_platform_code": 1,
        "similar_platform_docs": 1,
        "repo_code": 1,
        "generic_docs": 1,
    }

    for bucket in bucket_order:
        take_from(bucket, bucket_quotas.get(bucket, 1))
        if len(selected) >= limit:
            return selected

    for item in items:
        if len(selected) >= limit:
            break
        item_id = int(item.get("id") or 0)
        document_id = int(item.get("document_id") or 0)
        if item_id and item_id in seen_ids:
            continue
        if document_id and document_id in seen_documents:
            continue
        title = title_key(item)
        if title and title in seen_titles:
            continue
        selected.append(item)
        if item_id:
            seen_ids.add(item_id)
        if document_id:
            seen_documents.add(document_id)
        if title:
            seen_titles.add(title)
    return selected


def build_recall(payload: dict[str, Any]) -> dict[str, Any]:
    original_prompt = str(payload.get("prompt", ""))
    expanded_prompt = expand_prompt(payload)
    request = {
        "prompt": expanded_prompt,
        "original_prompt": original_prompt,
        "cwd": str(payload.get("cwd", "")),
        "repo": str(payload.get("repo", "")),
        "branch": str(payload.get("branch", "")),
    }
    limit_memories = max(3, min(int(payload.get("limit_memories", 5)), 5))
    limit_docs = max(2, min(int(payload.get("limit_docs", 3)), 3))
    fts_limit = int(CONFIG.get("recall", {}).get("fts_limit", 20))

    memory_map: dict[int, dict[str, Any]] = {}
    for item in get_pinned_memories(limit=max(limit_memories, 5)) + search_memories(expanded_prompt, fts_limit):
        item["source_type"] = "memory"
        key = int(item["id"])
        if key not in memory_map or item.get("text_score", 0) > memory_map[key].get("text_score", 0):
            memory_map[key] = item

    doc_map: dict[int, dict[str, Any]] = {}
    for item in search_document_chunks(expanded_prompt, fts_limit):
        item["source_type"] = "doc_chunk"
        doc_map[int(item["id"])] = item

    for item in vector_items(request):
        if item.get("source_type") == "memory" and item.get("item_id"):
            key = int(item["item_id"])
            memory_map.setdefault(key, item)
            memory_map[key]["vector_score"] = max(
                float(memory_map[key].get("vector_score") or 0), float(item.get("vector_score") or 0)
            )
        elif item.get("source_type") == "doc_chunk" and item.get("item_id"):
            key = int(item["item_id"])
            doc_map.setdefault(key, item)
            doc_map[key]["vector_score"] = max(
                float(doc_map[key].get("vector_score") or 0), float(item.get("vector_score") or 0)
            )

    ranked_memory_candidates = rerank(list(memory_map.values()), request)
    ranked_memories = select_typed_memories(ranked_memory_candidates, limit_memories)
    ranked_doc_candidates = rerank(list(doc_map.values()), request)
    ranked_docs = select_bucketed_doc_chunks(ranked_doc_candidates, limit_docs)

    mark_memories_used([int(item["id"]) for item in ranked_memories if item.get("id")])

    parts: list[str] = []
    trunk_text = trunk_section(payload)
    if trunk_text:
        parts.append(trunk_text)
    if ranked_memories:
        parts.append(memory_sections(ranked_memories))
    if ranked_docs:
        parts.append("Relevant docs:\n" + "\n".join(doc_line(item) for item in ranked_docs))
    result = {
        "additionalContext": "\n\n".join(part for part in parts if part),
        "items": ranked_memories + ranked_docs,
    }
    if bool(payload.get("include_trace") or payload.get("trace")):
        result["trace"] = {
            "intent": expansion_trace(original_prompt, expanded_prompt),
            "memory_candidates": len(ranked_memory_candidates),
            "doc_candidates": len(ranked_doc_candidates),
            "selected_memory_types": [item.get("type") for item in ranked_memories],
            "selected_doc_buckets": [doc_bucket(item) for item in ranked_docs],
        }
    return result
