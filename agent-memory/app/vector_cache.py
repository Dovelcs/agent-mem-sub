from __future__ import annotations

import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from vector_profiles import vector_cache_config, vector_cache_targets


APP_DIR = Path(__file__).resolve().parent
DEFAULT_CACHE_PATH = "../tmep/agent-memory-vector-cache"


def cache_root(config: dict[str, Any] | None = None) -> Path:
    cfg = config or {}
    raw = (
        os.environ.get("AGENT_MEMORY_VECTOR_CACHE_DIR")
        or cfg.get("path")
        or DEFAULT_CACHE_PATH
    )
    path = Path(str(raw)).expanduser()
    if not path.is_absolute():
        path = APP_DIR / path
    return path.resolve()


def queue_dirs(config: dict[str, Any] | None = None) -> dict[str, Path]:
    root = cache_root(config)
    return {
        "root": root,
        "pending": root / "pending",
        "processing": root / "processing",
        "done": root / "done",
        "failed": root / "failed",
    }


def ensure_queue_dirs(config: dict[str, Any] | None = None) -> dict[str, Path]:
    dirs = queue_dirs(config)
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    return dirs


def queue_enabled(config: dict[str, Any] | None = None) -> bool:
    cfg = config or {}
    return bool(cfg.get("enabled", True))


def _queue_memory_vector_one(memory: dict[str, Any], config: dict[str, Any] | None = None, profile: str = "") -> dict[str, Any]:
    if not memory or not memory.get("id"):
        return {"ok": False, "queued": False, "error": "missing memory id"}
    if not queue_enabled(config):
        return {"ok": True, "queued": False, "reason": "disabled"}

    dirs = ensure_queue_dirs(config)
    memory_id = int(memory["id"])
    token = uuid.uuid4().hex
    updated = str(memory.get("updated_at") or "")
    name = f"memory-{memory_id}-{token}.json"
    record = {
        "version": 1,
        "source_type": "memory",
        "memory_id": memory_id,
        "memory": memory,
        "profile": profile,
        "attempts": 0,
        "queued_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "updated_at": updated,
    }
    tmp_path = dirs["pending"] / f".{name}.tmp"
    final_path = dirs["pending"] / name
    tmp_path.write_text(json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    tmp_path.replace(final_path)
    return {"ok": True, "queued": True, "path": str(final_path)}


def queue_memory_vector(memory: dict[str, Any], config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or {}
    if "profiles" not in cfg and "targets" not in cfg:
        return _queue_memory_vector_one(memory, cfg)

    results = []
    for profile in vector_cache_targets({"vector_cache": cfg, "vector_profiles": {"default": "", "profiles": {}}}):
        profile_cfg = vector_cache_config({"vector_cache": cfg}, profile)
        results.append(_queue_memory_vector_one(memory, profile_cfg, profile=profile))

    paths = [item.get("path") for item in results if item.get("path")]
    queued = any(bool(item.get("queued")) for item in results)
    return {"ok": all(bool(item.get("ok")) for item in results), "queued": queued, "paths": paths, "results": results, "path": paths[0] if paths else ""}


def vector_cache_status(config: dict[str, Any] | None = None) -> dict[str, Any]:
    cfg = config or {}
    if "profiles" in cfg or "targets" in cfg:
        profile_status: dict[str, Any] = {}
        totals = {"pending": 0, "processing": 0, "done": 0, "failed": 0}
        for profile in vector_cache_targets({"vector_cache": cfg, "vector_profiles": {"default": "", "profiles": {}}}):
            status = vector_cache_status(vector_cache_config({"vector_cache": cfg}, profile))
            profile_status[profile] = status
            for key in totals:
                totals[key] += int(status.get(key) or 0)
        return {"enabled": queue_enabled(cfg), **totals, "profiles": profile_status}

    dirs = ensure_queue_dirs(config)
    return {
        "enabled": queue_enabled(config),
        "root": str(dirs["root"]),
        "pending": len(list(dirs["pending"].glob("*.json"))),
        "processing": len(list(dirs["processing"].glob("*.json"))),
        "done": len(list(dirs["done"].glob("*.json"))),
        "failed": len(list(dirs["failed"].glob("*.json"))),
    }
