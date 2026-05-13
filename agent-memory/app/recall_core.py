from __future__ import annotations

import re
from typing import Any

from db import (
    CONFIG,
    get_document_chunks_by_ids,
    get_memories_by_ids,
    get_pinned_memories,
    mark_memories_used,
    search_document_chunks,
    search_memories,
)
from embedding import Embedder
from qdrant_client import QdrantLite
from intent import expand_prompt, expansion_trace
from rerank import rerank


GENERIC_DOC_TOKENS = {
    "server",
    "service",
    "codex",
    "guide",
    "developer",
    "development",
    "linux",
    "android",
    "rockchip",
    "rk",
    "docs",
    "doc",
    "pdf",
    "txt",
    "cn",
    "en",
    "问题",
    "修复",
    "调试",
    "定位",
    "实现",
}
HARDWARE_DOC_TOKENS = {
    "ab",
    "ota",
    "uboot",
    "u-boot",
    "dts",
    "dtsi",
    "kernel",
    "driver",
    "gpio",
    "i2c",
    "spi",
    "uart",
    "usb",
    "adb",
    "audio",
    "codec",
    "sai",
    "i2s",
    "mipi",
    "dsi",
    "csi",
    "edp",
    "hdmi",
    "drm",
    "display",
    "camera",
    "vop",
    "lvds",
    "fastboot",
    "upgrade_tool",
    "rkdeveloptool",
    "loader",
    "maskrom",
    "image",
    "firmware",
    "artifact",
    "download",
    "分区",
    "烧录",
    "升级",
    "镜像",
    "固件",
    "下载",
    "驱动",
    "设备树",
    "文档",
}
HOST_INDEX_SCOPES = {"host-git-checkouts"}
HOST_INDEX_TOKENS = {
    "checkout",
    "origin",
    "remote",
    "git路径",
    "仓库路径",
    "仓库地址",
    "检出路径",
    "本机路径",
    "检出",
}
DOC_INDEX_PATH_SUFFIXES = {"summary.csv", "manifest.json", "meta.yaml", "meta.json"}
DOC_INDEX_PROMPT_TOKENS = {
    "manifest",
    "summary",
    "index",
    "source",
    "provenance",
    "docs",
    "文档",
    "索引",
    "来源",
    "清单",
}
WORKFLOW_PROMPT_TOKENS = {
    "memory",
    "agent-memory",
    "workflow",
    "plan",
    "trunk",
    "subagent",
    "review",
    "commit",
    "jira",
    "git",
    "docs-first",
    "codex-orchestrator",
    "记忆",
    "召回",
    "计划",
    "主干",
    "子代理",
    "评审",
    "提交",
}
ROUTE_MEMORY_TYPES = {"decision_policy", "route_guard", "verified_route", "agent_route", "route", "pitfall"}
GENERIC_ROUTE_TOKENS = GENERIC_DOC_TOKENS | {
    "debug",
    "route",
    "routes",
    "route_guard",
    "verified_route",
    "decision_policy",
    "project_fact",
    "hardware_debug",
    "dts",
    "dtsi",
    "driver",
    "kernel",
    "runtime",
    "probe",
    "reference",
    "code",
    "path",
    "final",
    "progress",
    "status",
    "task",
    "completion",
    "watch",
    "repo",
    "branch",
    "main",
    "调试",
    "定位",
    "外设",
    "路线",
    "路径",
    "项目",
}


def tokens(value: str) -> set[str]:
    result: set[str] = set()
    for token in re.findall(r"[\w./:-]{2,}|[\u4e00-\u9fff]{2,}", value or ""):
        lowered = token.lower()
        result.add(lowered)
        for part in re.split(r"[_./:-]+", lowered):
            if len(part) >= 2:
                result.add(part)
    return result


def item_blob(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key) or "")
        for key in (
            "title",
            "heading",
            "content",
            "path",
            "scope",
            "source",
            "project",
            "platform",
            "customer",
            "tags",
        )
    )


def repo_aliases(request: dict[str, Any]) -> set[str]:
    aliases: set[str] = set()
    for key in ("repo", "cwd"):
        value = str(request.get(key) or "").strip()
        if not value:
            continue
        aliases.add(value.lower())
        parts = [part for part in re.split(r"[/\\]+", value.lower()) if part]
        if key == "repo" and parts:
            aliases.add(parts[-1])
    return aliases


def contains_path_alias(blob: str, alias: str) -> bool:
    start = 0
    while True:
        idx = blob.find(alias, start)
        if idx < 0:
            return False
        next_char = blob[idx + len(alias) : idx + len(alias) + 1]
        if not next_char or next_char in {"/", "\\", " ", "\t", "\n", "\r", ";", ":", ",", ")", "]", "}"}:
            return True
        start = idx + 1


def has_repo_context(item: dict[str, Any], request: dict[str, Any]) -> bool:
    blob = item_blob(item).lower()
    path = str(item.get("path") or "").lower()
    scope = str(item.get("scope") or "").lower()
    tags = " ".join(str(tag).lower() for tag in item.get("tags") or [])
    for alias in repo_aliases(request):
        if not alias:
            continue
        if "/" in alias and contains_path_alias(blob, alias):
            return True
        if alias and alias in {scope}:
            return True
        if alias and (alias in path or alias in tags):
            return True
    return False


def prompt_tokens(request: dict[str, Any]) -> set[str]:
    prompt = str(request.get("original_prompt") or request.get("prompt") or "")
    return tokens(prompt)


def strong_prompt_overlap(item: dict[str, Any], request: dict[str, Any]) -> set[str]:
    useful_prompt_tokens = {
        token for token in prompt_tokens(request) if token not in GENERIC_DOC_TOKENS and len(token) >= 2
    }
    return useful_prompt_tokens & tokens(item_blob(item))


def topic_prompt_tokens(request: dict[str, Any]) -> set[str]:
    useful: set[str] = set()
    for token in prompt_tokens(request):
        if token in GENERIC_ROUTE_TOKENS or len(token) < 2:
            continue
        if re.fullmatch(r"(rk\d{4}[a-z]?|rv\d{4}[a-z]?|qsm\d+|qsc\d+|sg\d+|sh\d+)", token):
            continue
        useful.add(token)
    return useful


def strong_topic_overlap(item: dict[str, Any], request: dict[str, Any]) -> set[str]:
    return topic_prompt_tokens(request) & tokens(item_blob(item))


def has_platform_context(item: dict[str, Any], request: dict[str, Any]) -> bool:
    scope = str(item.get("reuse_scope") or "")
    if scope in {"same_platform", "same_family"}:
        return True
    request_platforms = re.findall(r"(?<![a-z0-9])(rk\d{4}[a-z]?|rv\d{4}[a-z]?|qsm\d+|qsc\d+|sg\d+|sh\d+)(?![a-z0-9])", " ".join(str(request.get(k) or "") for k in ("original_prompt", "prompt", "cwd", "repo", "branch")).lower())
    return bool(request_platforms and request_platforms[0] in item_blob(item).lower())


def memory_applicable(item: dict[str, Any], request: dict[str, Any]) -> bool:
    memory_type = str(item.get("type") or "")
    scope = str(item.get("scope") or "").lower()
    reuse_scope = str(item.get("reuse_scope") or "")
    if scope in HOST_INDEX_SCOPES:
        return bool(prompt_tokens(request) & HOST_INDEX_TOKENS)
    if memory_type == "user_style":
        return True
    if has_repo_context(item, request):
        return True
    if memory_type in {"doc_index", "performance_baseline", "system"}:
        prompt = prompt_tokens(request)
        return bool(prompt & WORKFLOW_PROMPT_TOKENS) or bool(strong_topic_overlap(item, request))
    if memory_type == "workflow_policy" and scope == "global":
        prompt = prompt_tokens(request)
        return bool(prompt & WORKFLOW_PROMPT_TOKENS) or bool(strong_topic_overlap(item, request))
    if memory_type in {"project_fact", "hardware_debug", "project"}:
        if has_platform_context(item, request):
            topics = topic_prompt_tokens(request)
            overlap = strong_topic_overlap(item, request)
            if reuse_scope == "same_family":
                return len(overlap) >= 2
            return not topics or bool(overlap)
        return bool(strong_topic_overlap(item, request))
    if memory_type in ROUTE_MEMORY_TYPES:
        if has_platform_context(item, request):
            topics = topic_prompt_tokens(request)
            overlap = strong_topic_overlap(item, request)
            if reuse_scope == "same_family":
                return len(overlap) >= 2
            return not topics or bool(overlap)
        if scope == "global":
            return bool(strong_topic_overlap(item, request))
        return bool(strong_topic_overlap(item, request))
    return bool(strong_topic_overlap(item, request))


def doc_applicable(item: dict[str, Any], request: dict[str, Any]) -> bool:
    path_name = str(item.get("path") or "").rsplit("/", 1)[-1].lower()
    if path_name in DOC_INDEX_PATH_SUFFIXES and not (prompt_tokens(request) & DOC_INDEX_PROMPT_TOKENS):
        return False
    if has_repo_context(item, request):
        return True
    overlap = strong_prompt_overlap(item, request)
    kind = str(item.get("source_kind") or "")
    if has_platform_context(item, request):
        topics = topic_prompt_tokens(request)
        if kind in {"official_doc", "dts", "config", "repo_code"}:
            return not topics or bool(overlap)
        return bool(overlap) or not topics
    if not overlap:
        return False
    prompt = prompt_tokens(request)
    if prompt & HARDWARE_DOC_TOKENS:
        return True
    return kind not in {"official_doc", "dts", "config", "repo_code"}


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
    vector = embedder.embed(str(request.get("prompt") or ""), prefix=str(emb_cfg.get("query_prefix", "")))
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


def merge_candidate(
    target: dict[int, dict[str, Any]],
    item: dict[str, Any],
    key: int,
    source_type: str,
    vector_score: float = 0.0,
) -> None:
    item["source_type"] = source_type
    existing = target.get(key)
    if not existing:
        if vector_score:
            item["vector_score"] = vector_score
        target[key] = item
        return
    if float(item.get("text_score") or 0) > float(existing.get("text_score") or 0):
        preserved_vector = max(float(existing.get("vector_score") or 0), vector_score)
        existing.update(item)
        if preserved_vector:
            existing["vector_score"] = preserved_vector
    elif vector_score:
        existing["vector_score"] = max(float(existing.get("vector_score") or 0), vector_score)


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
        merge_candidate(memory_map, item, int(item["id"]), "memory")

    doc_map: dict[int, dict[str, Any]] = {}
    for item in search_document_chunks(expanded_prompt, fts_limit):
        merge_candidate(doc_map, item, int(item["id"]), "doc_chunk")

    vector_memory_scores: dict[int, float] = {}
    vector_doc_scores: dict[int, float] = {}
    for item in vector_items(request):
        if item.get("source_type") == "memory" and item.get("item_id"):
            key = int(item["item_id"])
            vector_memory_scores[key] = max(vector_memory_scores.get(key, 0.0), float(item.get("vector_score") or 0))
        elif item.get("source_type") == "doc_chunk" and item.get("item_id"):
            key = int(item["item_id"])
            vector_doc_scores[key] = max(vector_doc_scores.get(key, 0.0), float(item.get("vector_score") or 0))

    for item in get_memories_by_ids(list(vector_memory_scores.keys())):
        key = int(item["id"])
        merge_candidate(memory_map, item, key, "memory", vector_memory_scores.get(key, 0.0))

    for item in get_document_chunks_by_ids(list(vector_doc_scores.keys())):
        key = int(item["id"])
        merge_candidate(doc_map, item, key, "doc_chunk", vector_doc_scores.get(key, 0.0))

    ranked_memory_candidates = [
        item for item in rerank(list(memory_map.values()), request) if memory_applicable(item, request)
    ]
    ranked_memories = select_typed_memories(ranked_memory_candidates, limit_memories)
    ranked_doc_candidates = [
        item for item in rerank(list(doc_map.values()), request) if doc_applicable(item, request)
    ]
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
