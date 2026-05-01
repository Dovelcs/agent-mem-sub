#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


BASE_URL = os.environ.get("AGENT_MEMORY_URL", "http://100.106.225.53:18088").rstrip("/")
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


def write_fact(args: argparse.Namespace) -> int:
    payload = {
        "fact": args.fact,
        "type": args.type,
        "scope": args.scope,
        "title": args.title,
        "tags": args.tag,
        "source": args.source,
        "goal": args.goal,
        "cwd": args.cwd or os.getcwd(),
        "repo": args.repo,
        "branch": args.branch,
        "platform": args.platform,
        "device": args.device,
        "document_path": args.document_path,
        "environment": args.environment,
        "confidence": args.confidence,
        "importance": args.importance,
        "status": args.status,
        "update_threshold": args.update_threshold,
        "vector": args.vector,
    }
    result = request_json("POST", "/memory/write_fact", payload, timeout=5.0)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def compact(text: str, limit: int = 140) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: max(limit - 3, 0)].rstrip() + "..."


def as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return [str(value)]


def run_git(cwd: str, git_args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *git_args],
            cwd=cwd,
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=0.8,
        )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def infer_repo_context(cwd: str) -> tuple[str, str, str]:
    root = run_git(cwd, ["rev-parse", "--show-toplevel"])
    branch = run_git(cwd, ["branch", "--show-current"])
    if not branch:
        branch = run_git(cwd, ["rev-parse", "--short", "HEAD"])
    repo = Path(root).name if root else Path(cwd).resolve().name
    return repo, branch, root


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        item = str(value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def default_found_title(kind: str, fact: str, paths: list[str]) -> str:
    if paths:
        return f"{kind} result: {Path(paths[0]).name}"
    return f"{kind} result: {compact(fact, 96)}"


def build_found_payload(args: argparse.Namespace, record: dict[str, Any] | None = None) -> dict[str, Any]:
    record = record or {}
    fact = str(record.get("fact") or record.get("content") or getattr(args, "fact", "") or "").strip()
    if not fact:
        raise ValueError("empty fact")

    kind = str(record.get("kind") or args.kind)
    cwd = str(record.get("cwd") or args.cwd or os.getcwd())
    paths = as_list(record.get("paths") or record.get("path") or record.get("document_path") or getattr(args, "path", []))
    repo, branch, root = infer_repo_context(cwd)
    repo = str(record.get("repo") or args.repo or repo)
    branch = str(record.get("branch") or args.branch or branch)
    platform = str(record.get("platform") or args.platform)
    device = str(record.get("device") or args.device)
    scope = str(record.get("scope") or args.scope or repo or platform or Path(cwd).resolve().name)
    source = str(record.get("source") or args.source or f"codex/{kind}-result")
    title = str(record.get("title") or args.title or default_found_title(kind, fact, paths))
    tags = dedupe(
        as_list(getattr(args, "tag", []))
        + as_list(record.get("tags") or record.get("tag"))
        + [kind, f"{kind}-result", "verified-conclusion", "scope-bound", repo, branch, platform, device]
    )
    environment = str(record.get("environment") or args.environment)
    if root and root != cwd and "repo_root=" not in environment:
        environment = "; ".join(part for part in (environment, f"repo_root={root}") if part)
    if len(paths) > 1:
        joined = ",".join(paths[:8])
        environment = "; ".join(part for part in (environment, f"paths={joined}") if part)

    return {
        "fact": fact,
        "type": str(record.get("type") or args.type),
        "scope": scope,
        "title": title,
        "tags": tags,
        "source": source,
        "goal": str(record.get("goal") or args.goal),
        "cwd": cwd,
        "repo": repo,
        "branch": branch,
        "platform": platform,
        "device": device,
        "document_path": paths[0] if paths else "",
        "environment": environment,
        "confidence": float(record.get("confidence") or args.confidence),
        "importance": float(record.get("importance") or args.importance),
        "status": str(record.get("status") or args.status),
        "update_threshold": float(record.get("update_threshold") or args.update_threshold),
        "vector": str(record.get("vector") or args.vector),
    }


def write_found(args: argparse.Namespace) -> int:
    payload = build_found_payload(args)
    result = request_json("POST", "/memory/write_fact", payload, timeout=5.0)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


def write_found_batch(args: argparse.Namespace) -> int:
    facts: list[dict[str, Any]] = []
    with open(args.file, "r", encoding="utf-8") as handle:
        for lineno, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{args.file}:{lineno}: invalid JSON: {exc}") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{args.file}:{lineno}: expected JSON object")
            facts.append(build_found_payload(args, record))
    result = request_json("POST", "/memory/write_facts", {"facts": facts, "vector": args.vector}, timeout=max(5.0, len(facts) * 0.5))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


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

    write_fact_parser = sub.add_parser("write-fact")
    write_fact_parser.add_argument("fact")
    write_fact_parser.add_argument("--type", default="project_fact")
    write_fact_parser.add_argument("--scope", default="")
    write_fact_parser.add_argument("--title", default="")
    write_fact_parser.add_argument("--tag", action="append", default=[])
    write_fact_parser.add_argument("--source", default="agent-memory/write_fact")
    write_fact_parser.add_argument("--goal", default="")
    write_fact_parser.add_argument("--cwd", default="")
    write_fact_parser.add_argument("--repo", default="")
    write_fact_parser.add_argument("--branch", default="")
    write_fact_parser.add_argument("--platform", default="")
    write_fact_parser.add_argument("--device", default="")
    write_fact_parser.add_argument("--document-path", default="")
    write_fact_parser.add_argument("--environment", default="")
    write_fact_parser.add_argument("--confidence", type=float, default=0.85)
    write_fact_parser.add_argument("--importance", type=float, default=0.65)
    write_fact_parser.add_argument("--status", default="active")
    write_fact_parser.add_argument("--update-threshold", type=float, default=0.75)
    write_fact_parser.add_argument("--vector", choices=["async", "sync", "none"], default="async")

    def add_found_options(found_parser: argparse.ArgumentParser) -> None:
        found_parser.add_argument("--kind", choices=["find", "rg", "git-log", "manual"], default="find")
        found_parser.add_argument("--type", default="project_fact")
        found_parser.add_argument("--scope", default="")
        found_parser.add_argument("--title", default="")
        found_parser.add_argument("--path", action="append", default=[])
        found_parser.add_argument("--tag", action="append", default=[])
        found_parser.add_argument("--source", default="")
        found_parser.add_argument("--goal", default="")
        found_parser.add_argument("--cwd", default="")
        found_parser.add_argument("--repo", default="")
        found_parser.add_argument("--branch", default="")
        found_parser.add_argument("--platform", default="")
        found_parser.add_argument("--device", default="")
        found_parser.add_argument("--environment", default="")
        found_parser.add_argument("--confidence", type=float, default=0.85)
        found_parser.add_argument("--importance", type=float, default=0.65)
        found_parser.add_argument("--status", default="active")
        found_parser.add_argument("--update-threshold", type=float, default=0.75)
        found_parser.add_argument("--vector", choices=["async", "sync", "none"], default="async")

    write_found_parser = sub.add_parser("write-found", help="Write one verified find/rg/git-log conclusion with repo/path context.")
    write_found_parser.add_argument("fact")
    add_found_options(write_found_parser)

    write_found_batch_parser = sub.add_parser("write-found-batch", help="Write JSONL verified conclusions in one server-side batch.")
    write_found_batch_parser.add_argument("file")
    add_found_options(write_found_batch_parser)

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
        if args.cmd == "write-fact":
            return write_fact(args)
        if args.cmd == "write-found":
            return write_found(args)
        if args.cmd == "write-found-batch":
            return write_found_batch(args)
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
