from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any


PLATFORM_RE = re.compile(r"(?<![a-z0-9])(rk\d{4}[a-z]?|rv\d{4}[a-z]?|qsm\d+|qsc\d+|sg\d+|sh\d+)(?![a-z0-9])", re.IGNORECASE)
ROCKCHIP_PLATFORMS = {"rk3562", "rk3568", "rk3576", "rk3588", "rk3566", "rv1126", "rv1106", "rv1103"}


def _parse_time(value: str | None) -> float:
    if not value:
        return 0.0
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age_days = max((datetime.now(timezone.utc) - dt).total_seconds() / 86400.0, 0.0)
        return 1.0 / (1.0 + age_days / 30.0)
    except Exception:
        return 0.0


def _tokens(value: str) -> set[str]:
    tokens: set[str] = set()
    for token in re.findall(r"[\w./:-]{2,}|[\u4e00-\u9fff]{2,}", value or ""):
        lowered = token.lower()
        tokens.add(lowered)
        for part in re.split(r"[_./:-]+", lowered):
            if len(part) >= 2:
                tokens.add(part)
    return tokens


def _tags(value: Any) -> set[str]:
    if isinstance(value, list):
        return {str(v).lower() for v in value}
    if isinstance(value, str):
        return set(_tokens(value))
    return set()


def item_text(item: dict[str, Any]) -> str:
    return " ".join(
        str(item.get(k) or "")
        for k in (
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


def infer_request_platforms(request: dict[str, Any]) -> list[str]:
    text = " ".join(str(request.get(k) or "") for k in ("prompt", "cwd", "repo", "branch")).lower()
    found: list[str] = []
    for match in PLATFORM_RE.findall(text):
        platform = match.lower()
        if platform not in found:
            found.append(platform)
    return found


def item_platforms(item: dict[str, Any]) -> set[str]:
    title_text = " ".join(str(item.get(k) or "") for k in ("title", "heading")).lower()
    platforms = {match.lower() for match in PLATFORM_RE.findall(title_text)}
    if not platforms:
        text = item_text(item).lower()
        platforms = {match.lower() for match in PLATFORM_RE.findall(text)}
    platforms |= {p[:6] for p in list(platforms) if p.startswith("rk") and len(p) > 6}
    explicit = str(item.get("platform") or "").lower()
    if explicit:
        platforms |= {match.lower() for match in PLATFORM_RE.findall(explicit)}
        if explicit in ROCKCHIP_PLATFORMS:
            platforms.add(explicit)
    return platforms


def source_kind(item: dict[str, Any]) -> str:
    stored = str(item.get("source_kind") or "")
    if stored:
        return stored
    if item.get("source_type") == "memory" or item.get("type"):
        return "memory"
    text = item_text(item).lower()
    path = str(item.get("path") or "").lower()
    if any(part in path for part in ("/kernel/arch/", ".dts", ".dtsi", "/dts/")):
        return "dts"
    if any(part in path for part in ("defconfig", ".config", "/configs/", "buildroot/package/", "device/rockchip/")):
        return "config"
    if any(part in path for part in ("/kernel/drivers/", "/u-boot/", "/external/", "/hardware/", "/vendor/", "/app/")):
        return "repo_code"
    official_markers = (
        "developer_guide",
        "develop_guide",
        "driver_guide",
        "datasheet",
        "application_notes",
        "application_note",
        "sdk_release",
        "sdk_note",
        "user_guide",
        "rockchip_",
    )
    if any(marker in text for marker in official_markers):
        return "official_doc"
    if any(marker in text for marker in ("rollout", "debug", "validation", "verified", "踩坑", "验证")):
        return "debug_note"
    return "generic_doc"


def evidence_level(item: dict[str, Any]) -> str:
    stored = str(item.get("evidence_level") or "")
    if stored:
        return stored
    kind = source_kind(item)
    text = item_text(item).lower()
    if kind == "memory" and any(marker in text for marker in ("verified", "validated", "实机", "验证", "passed")):
        return "verified"
    if kind in {"dts", "config", "repo_code"}:
        return "code_reference"
    if kind == "official_doc":
        return "official_doc"
    if kind == "debug_note":
        return "debug_note"
    return "inferred"


def reuse_scope(item: dict[str, Any], request: dict[str, Any]) -> str:
    req_platforms = infer_request_platforms(request)
    platforms = item_platforms(item)
    if req_platforms and platforms:
        if req_platforms[0] in platforms:
            return "same_platform"
        if req_platforms[0].startswith("rk") and any(p.startswith("rk") for p in platforms):
            return "same_family"
        return "other_platform"
    if not req_platforms:
        return "unknown"
    if source_kind(item) == "official_doc" and "rockchip" in item_text(item).lower():
        return "generic"
    return "unknown"


def annotate_item(item: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    item["source_kind"] = source_kind(item)
    item["evidence_level"] = evidence_level(item)
    item["reuse_scope"] = reuse_scope(item, request)
    return item


def hint_score(item: dict[str, Any], request: dict[str, Any]) -> float:
    score = 0.0
    repo = str(request.get("repo") or "")
    cwd = str(request.get("cwd") or "")
    branch = str(request.get("branch") or "")
    path = str(item.get("path") or "")
    text = item_text(item)
    title_path = " ".join(str(item.get(k) or "") for k in ("title", "heading", "path"))
    if repo and repo in text:
        score += 0.8
    if branch and branch in text:
        score += 0.4
    if cwd and path and (path.startswith(cwd) or cwd in path):
        score += 0.8
    prompt_tags = _tokens(str(request.get("prompt") or "")) | _tokens(repo) | _tokens(cwd)
    overlap = prompt_tags & (_tokens(text) | _tags(item.get("tags")))
    score += min(len(overlap) * 0.12, 0.8)
    title_overlap = prompt_tags & _tokens(title_path)
    score += min(len(title_overlap) * 0.25, 1.2)
    if "ab" in prompt_tags and "ab" in _tokens(title_path):
        score += 1.2
    scope = reuse_scope(item, request)
    if scope == "same_platform":
        score += 1.0
    elif scope == "same_family":
        score += 0.45
    elif scope == "other_platform":
        score -= 0.25
    kind = source_kind(item)
    if kind in {"dts", "config", "repo_code"}:
        score += 0.25
    elif kind == "official_doc":
        score += 0.15
    return score


def score_item(item: dict[str, Any], request: dict[str, Any]) -> float:
    text_score = float(item.get("text_score") or 0.0)
    vector_score = float(item.get("vector_score") or 0.0)
    importance = float(item.get("importance") or 0.0)
    confidence = float(item.get("confidence") or 0.0)
    recency = _parse_time(item.get("updated_at"))
    return (
        min(text_score, 8.0) * 0.45
        + vector_score * 1.8
        + hint_score(item, request) * 1.2
        + importance * 1.0
        + confidence * 0.5
        + recency * 0.4
    )


def rerank(items: list[dict[str, Any]], request: dict[str, Any]) -> list[dict[str, Any]]:
    for item in items:
        annotate_item(item, request)
        item["rank_score"] = score_item(item, request)
    return sorted(items, key=lambda x: x.get("rank_score", 0.0), reverse=True)
