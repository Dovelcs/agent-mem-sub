#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


BASE_URL = os.environ.get("AGENT_MEMORY_URL", "http://127.0.0.1:18088").rstrip("/")
SKILL_DIR = Path(__file__).resolve().parents[1]
PROMPT_DIR = SKILL_DIR / "references" / "prompts"




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



def upsert_baseline() -> int:
    print(
        json.dumps(
            {
                "ok": True,
                "deprecated": True,
                "message": "Baseline memories now live only in the database; this command no longer writes memory seeds.",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
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
