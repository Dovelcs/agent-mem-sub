#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


BASE_URL = os.environ.get("AGENT_MEMORY_URL", "http://127.0.0.1:18088").rstrip("/")
DB_PATH = Path(os.environ.get("AGENT_MEMORY_DB", "/opt/agent-memory/agent.db"))
SKILL_DIR = Path(__file__).resolve().parents[1]
PROMPT_DIR = SKILL_DIR / "references" / "prompts"


BASELINE_MEMORIES: list[dict[str, Any]] = [
    {
        "type": "system",
        "scope": "openwrt",
        "title": "OpenWrt soft-router connection profile",
        "content": (
            "Use the ssh_openwrt MCP endpoint to operate the OpenWrt soft router. "
            "The target is reachable over Tailscale at 100.106.225.53 with SSH "
            "user root; credentials are configured in the local ssh-mcp-openwrt "
            "wrapper and should not be printed or injected into recall context."
        ),
        "tags": [
            "openwrt",
            "soft-router",
            "ssh",
            "ssh_openwrt",
            "tailscale",
            "100.106.225.53",
            "root",
            "credential",
            "软路由",
            "连接",
            "密码",
            "凭据",
        ],
        "importance": 0.95,
        "confidence": 1.0,
        "status": "pinned",
    },
    {
        "type": "system",
        "scope": "openwrt",
        "title": "OpenWrt agent-memory runtime topology",
        "content": (
            "OpenWrt agent-memory runs under /opt/agent-memory. FastAPI listens on "
            "127.0.0.1:18088, Qdrant on 127.0.0.1:6333, and the embedding sidecar "
            "on 127.0.0.1:18089. Qdrant and embedding containers use "
            "restart=unless-stopped."
        ),
        "tags": [
            "openwrt",
            "agent-memory",
            "qdrant",
            "embedding",
            "fastapi",
            "soft-router",
            "soft router",
            "软路由",
            "自启动",
        ],
        "importance": 0.95,
        "confidence": 1.0,
        "status": "pinned",
    },
    {
        "type": "system",
        "scope": "openwrt",
        "title": "OpenWrt agent-memory SSD storage layout",
        "content": (
            "The attached Fanxiang PS2000 SSD is /dev/sda. /dev/sda2 is ext4 with "
            "label AGENT_MEMORY and is mounted at /mnt/agent-memory-store. "
            "/opt/agent-memory/agent.db, docs, data, and qdrant_storage are "
            "symlinks into /mnt/agent-memory-store/agent-memory."
        ),
        "tags": [
            "openwrt",
            "agent-memory",
            "ssd",
            "storage",
            "fstab",
            "ext4",
            "AGENT_MEMORY",
            "soft-router",
            "软路由",
            "固态硬盘",
            "自动挂载",
        ],
        "importance": 0.95,
        "confidence": 1.0,
        "status": "pinned",
    },
    {
        "type": "system",
        "scope": "openwrt",
        "title": "OpenWrt agent-memory vector recall behavior",
        "content": (
            "Vector recall is enabled through the HTTP embedding sidecar using "
            "intfloat/multilingual-e5-small. If embedding or Qdrant is unavailable, "
            "/recall falls back to SQLite FTS and still returns context instead of "
            "blocking Codex."
        ),
        "tags": [
            "openwrt",
            "agent-memory",
            "vector",
            "embedding",
            "qdrant",
            "fts",
            "recall",
            "soft-router",
            "召回",
            "向量",
            "降级",
        ],
        "importance": 0.9,
        "confidence": 1.0,
        "status": "pinned",
    },
    {
        "type": "system",
        "scope": "openwrt",
        "title": "OpenWrt agent-memory recall route and aliases",
        "content": (
            "For vague questions about the soft-router memory system, recall route, "
            "old setup notes, long-term records, or how to find previous facts, use "
            "the openwrt-agent-memory skill and the local /recall API. The path is "
            "Codex Hook recall.py to FastAPI /recall, combining pinned memories, "
            "SQLite FTS, embedding sidecar query vectors, and Qdrant vector search."
        ),
        "tags": [
            "openwrt",
            "agent-memory",
            "recall",
            "route",
            "codex-hook",
            "memory",
            "qdrant",
            "embedding",
            "fts",
            "soft-router",
            "软路由",
            "记忆",
            "召回",
            "召回路线",
            "长期记录",
            "以前的记录",
            "怎么查",
            "不记得关键词",
        ],
        "importance": 0.95,
        "confidence": 1.0,
        "status": "pinned",
    },
    {
        "type": "workflow_policy",
        "scope": "global",
        "title": "Agent-memory generalized memory type taxonomy",
        "content": (
            "Use separate memory types for user_style, agent_route, "
            "decision_policy, route_guard, pitfall, verified_route, "
            "project_fact, hardware_debug, doc_index, workflow_policy, "
            "performance_baseline, and credential_location. "
            "Do not force all memories into hardware or driver-debug categories; "
            "choose the narrowest type and scope so unrelated tasks are not "
            "polluted by platform-specific findings."
        ),
        "tags": [
            "agent-memory",
            "memory-taxonomy",
            "user_style",
            "agent_route",
            "decision_policy",
            "route_guard",
            "pitfall",
            "verified_route",
            "project_fact",
            "hardware_debug",
            "doc_index",
            "workflow_policy",
            "performance_baseline",
            "credential_location",
            "记忆分类",
            "召回",
            "泛化",
        ],
        "importance": 0.9,
        "confidence": 1.0,
        "status": "pinned",
    },
    {
        "type": "workflow_policy",
        "scope": "global",
        "title": "OpenWrt agent-memory unified workflow entrypoint",
        "content": (
            "Use openwrt-agent-memory as the single local workflow, memory, "
            "and conversation-trunk entrypoint. The former codex-orchestrator, "
            "docs-first, and subagent-driven-development skills were absorbed "
            "into this skill and archived under skills.disabled for rollback. "
            "For requests about writing plans, maintaining the main trunk, "
            "dispatching subagents, or running spec/code review checkpoints, "
            "use this unified workflow route."
        ),
        "tags": [
            "openwrt-agent-memory",
            "workflow_policy",
            "workflow",
            "trunk",
            "plan",
            "review",
            "code-review",
            "spec-review",
            "subagent",
            "codex-orchestrator",
            "docs-first",
            "subagent-driven-development",
            "skill",
            "技能",
            "计划",
            "写计划",
            "主干",
            "子代理",
            "代码review",
            "规格review",
            "归档",
        ],
        "importance": 0.95,
        "confidence": 1.0,
        "status": "pinned",
    },
    {
        "type": "agent_route",
        "scope": "openwrt",
        "title": "OpenWrt agent-memory recall UX and conversation trunk",
        "content": (
            "Agent-memory expands short prompts with intent aliases, segments "
            "recall context by memory type, supports optional include_trace "
            "diagnostics, offers memory_suggest for low-context typed memory "
            "writes, and exposes memory-backed conversation trunk API/MCP tools "
            "to preserve task direction across compaction. Use "
            "trunk_upsert/update/get for long branching tasks and trunk_cleanup "
            "for stale inactive plans."
        ),
        "tags": [
            "openwrt",
            "agent-memory",
            "recall",
            "intent-expansion",
            "segmented-recall",
            "include_trace",
            "memory_suggest",
            "conversation_trunk",
            "mcp",
            "trunk_cleanup",
            "上下文压缩",
            "主干",
            "召回",
        ],
        "importance": 0.9,
        "confidence": 1.0,
        "status": "pinned",
    },
    {
        "type": "system",
        "scope": "openwrt",
        "title": "OpenWrt agent-memory performance baseline",
        "content": (
            "Hot /recall with vector recall is typically around 150-200 ms. Hot "
            "embedding requests are around 20-30 ms. The embedding container uses "
            "about 600 MiB RAM and Qdrant about 220 MiB RAM."
        ),
        "tags": [
            "openwrt",
            "agent-memory",
            "performance",
            "latency",
            "embedding",
            "qdrant",
            "soft-router",
            "性能",
            "耗时",
        ],
        "importance": 0.85,
        "confidence": 1.0,
        "status": "active",
    },
    {
        "type": "system",
        "scope": "openwrt",
        "title": "OpenWrt agent-memory operational caveats",
        "content": (
            "Do not unplug the SSD while agent-memory is running because the live "
            "database, docs, model cache, and Qdrant storage are symlinked to the "
            "SSD mount. After an embedding container restart, the first embedding "
            "request may cold-load the model; warm it once before judging latency."
        ),
        "tags": [
            "openwrt",
            "agent-memory",
            "ssd",
            "embedding",
            "qdrant",
            "operations",
            "soft-router",
            "软路由",
            "注意事项",
            "冷启动",
        ],
        "importance": 0.8,
        "confidence": 1.0,
        "status": "active",
    },
]


def request_json(method: str, path: str, payload: dict[str, Any] | None = None, timeout: float = 5.0) -> dict[str, Any]:
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode()
    req = urllib.request.Request(
        BASE_URL + path,
        data=data,
        method=method,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def find_memory_by_title(title: str) -> dict[str, Any] | None:
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(DB_PATH)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM memories WHERE title = ? ORDER BY updated_at DESC, id DESC LIMIT 1",
                (title,),
            ).fetchone()
            conn.close()
            if row:
                return dict(row)
        except Exception:
            pass
    result = request_json("POST", "/memory/search", {"query": title, "limit": 20})
    for item in result.get("items", []):
        if item.get("title") == title:
            return item
    return None


def upsert_baseline() -> int:
    written = []
    for memory in BASELINE_MEMORIES:
        payload = dict(memory)
        payload["source"] = "codex-skill/openwrt-agent-memory"
        existing = find_memory_by_title(str(payload["title"]))
        if existing and existing.get("id"):
            payload["id"] = existing["id"]
        response = request_json("POST", "/memory/upsert", payload)
        saved = response.get("memory", response)
        written.append({"id": saved.get("id"), "title": saved.get("title"), "status": saved.get("status")})
    print(json.dumps({"ok": True, "written": written}, ensure_ascii=False, indent=2))
    return 0


def health() -> int:
    print(json.dumps(request_json("GET", "/health"), ensure_ascii=False, indent=2))
    return 0


def recall(prompt: str) -> int:
    started = time.perf_counter()
    result = request_json(
        "POST",
        "/recall",
        {"prompt": prompt, "limit_memories": 5, "limit_docs": 3},
        timeout=5.0,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "ms": round((time.perf_counter() - started) * 1000, 2),
                "items": len(result.get("items", [])),
                "vector_scores": [round(float(i.get("vector_score") or 0), 4) for i in result.get("items", [])],
                "additionalContext": result.get("additionalContext", ""),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def parse_milestones(values: list[str]) -> list[Any]:
    milestones: list[Any] = []
    for value in values:
        value = value.strip()
        if not value:
            continue
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            parsed = {"title": value, "status": "pending"}
        if isinstance(parsed, list):
            milestones.extend(parsed)
        else:
            milestones.append(parsed)
    return milestones


def workflow_start(args: argparse.Namespace) -> int:
    payload = {
        "trunk_id": args.trunk_id,
        "title": args.title,
        "goal": args.goal,
        "cwd": args.cwd or os.getcwd(),
        "repo": args.repo,
        "branch": args.branch,
        "status": args.status,
        "milestones": parse_milestones(args.milestone),
        "ttl_hours": args.ttl_hours,
        "draft_ttl_hours": args.draft_ttl_hours,
    }
    result = request_json("POST", "/trunk/upsert", payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def workflow_update(args: argparse.Namespace) -> int:
    payload = {
        "trunk_id": args.trunk_id,
        "status": args.status,
        "goal": args.goal,
        "title": args.title,
        "progress": args.progress,
        "branch_note": args.branch_note,
        "milestone_id": args.milestone_id,
        "milestone_status": args.milestone_status,
    }
    result = request_json("POST", "/trunk/update", payload)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def workflow_get(args: argparse.Namespace) -> int:
    result = request_json("POST", "/trunk/get", {"trunk_id": args.trunk_id})
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def workflow_finish(args: argparse.Namespace) -> int:
    result = request_json(
        "POST",
        "/trunk/update",
        {"trunk_id": args.trunk_id, "status": "done", "progress": args.summary},
    )
    suggestion: dict[str, Any] | None = None
    observation = args.lesson or args.summary
    if observation:
        suggestion = request_json(
            "POST",
            "/memory/suggest",
            {
                "observation": observation,
                "goal": args.goal,
                "type": "workflow_policy",
                "scope": "global",
                "tags": ["agent-memory", "workflow_policy", "trunk", "主干"],
                "source": "codex-skill/openwrt-agent-memory workflow-finish",
                "write": bool(args.write_memory),
            },
            timeout=5.0,
        )
    print(json.dumps({"ok": result.get("ok", False), "trunk": result.get("trunk"), "memory_suggest": suggestion}, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def workflow_cleanup(args: argparse.Namespace) -> int:
    result = request_json(
        "POST",
        "/trunk/cleanup",
        {"draft_ttl_hours": args.draft_ttl_hours, "inactive_ttl_hours": args.inactive_ttl_hours},
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def prompt_template(name: str) -> int:
    mapping = {
        "implementer": PROMPT_DIR / "implementer.md",
        "spec-reviewer": PROMPT_DIR / "spec-reviewer.md",
        "code-quality-reviewer": PROMPT_DIR / "code-quality-reviewer.md",
    }
    path = mapping[name]
    sys.stdout.write(path.read_text(encoding="utf-8"))
    return 0


def smoke() -> int:
    h = request_json("GET", "/health")
    r = request_json(
        "POST",
        "/recall",
        {"prompt": "OpenWrt agent-memory SSD storage embedding qdrant 自启动 软路由", "limit_memories": 5, "limit_docs": 2},
    )
    print(
        json.dumps(
            {
                "ok": bool(h.get("ok")) and len(r.get("items", [])) > 0,
                "health": h,
                "recall_items": len(r.get("items", [])),
                "titles": [i.get("title") for i in r.get("items", [])],
                "vector_scores": [round(float(i.get("vector_score") or 0), 4) for i in r.get("items", [])],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Operate the OpenWrt agent-memory API.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("health")
    sub.add_parser("upsert-baseline")
    sub.add_parser("smoke")
    recall_parser = sub.add_parser("recall")
    recall_parser.add_argument("prompt")

    start_parser = sub.add_parser("workflow-start")
    start_parser.add_argument("--trunk-id", required=True)
    start_parser.add_argument("--title", default="")
    start_parser.add_argument("--goal", required=True)
    start_parser.add_argument("--cwd", default="")
    start_parser.add_argument("--repo", default="")
    start_parser.add_argument("--branch", default="")
    start_parser.add_argument("--status", default="active", choices=["draft", "active", "blocked", "done", "archived"])
    start_parser.add_argument("--milestone", action="append", default=[], help="Repeatable text or JSON milestone/list.")
    start_parser.add_argument("--ttl-hours", type=int, default=168)
    start_parser.add_argument("--draft-ttl-hours", type=int, default=24)

    update_parser = sub.add_parser("workflow-update")
    update_parser.add_argument("--trunk-id", required=True)
    update_parser.add_argument("--status", default="", choices=["", "draft", "active", "blocked", "done", "archived"])
    update_parser.add_argument("--goal", default="")
    update_parser.add_argument("--title", default="")
    update_parser.add_argument("--progress", default="")
    update_parser.add_argument("--branch-note", default="")
    update_parser.add_argument("--milestone-id", default="")
    update_parser.add_argument("--milestone-status", default="")

    get_parser = sub.add_parser("workflow-get")
    get_parser.add_argument("--trunk-id", required=True)

    finish_parser = sub.add_parser("workflow-finish")
    finish_parser.add_argument("--trunk-id", required=True)
    finish_parser.add_argument("--summary", default="Workflow finished.")
    finish_parser.add_argument("--lesson", default="")
    finish_parser.add_argument("--goal", default="")
    finish_parser.add_argument("--write-memory", action="store_true")

    cleanup_parser = sub.add_parser("workflow-cleanup")
    cleanup_parser.add_argument("--draft-ttl-hours", type=int, default=24)
    cleanup_parser.add_argument("--inactive-ttl-hours", type=int, default=168)

    template_parser = sub.add_parser("prompt-template")
    template_parser.add_argument("name", choices=["implementer", "spec-reviewer", "code-quality-reviewer"])

    args = parser.parse_args()

    try:
        if args.cmd == "health":
            return health()
        if args.cmd == "upsert-baseline":
            return upsert_baseline()
        if args.cmd == "smoke":
            return smoke()
        if args.cmd == "recall":
            return recall(args.prompt)
        if args.cmd == "workflow-start":
            return workflow_start(args)
        if args.cmd == "workflow-update":
            return workflow_update(args)
        if args.cmd == "workflow-get":
            return workflow_get(args)
        if args.cmd == "workflow-finish":
            return workflow_finish(args)
        if args.cmd == "workflow-cleanup":
            return workflow_cleanup(args)
        if args.cmd == "prompt-template":
            return prompt_template(args.name)
    except urllib.error.URLError as exc:
        print(json.dumps({"ok": False, "error": str(exc), "base_url": BASE_URL}, ensure_ascii=False), file=sys.stderr)
        return 2
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
