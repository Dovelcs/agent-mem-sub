from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_STATE_PATH = "~/.cache/agent-memory/recall-hook-state.json"
DEFAULT_SESSION_ROOT = "~/.codex/sessions"
DEFAULT_TAIL_BYTES = 256 * 1024
DEFAULT_SESSION_SCAN_LIMIT = 16
DEFAULT_USER_PREFERENCES_LIMIT = 5
DEFAULT_MEMORY_DECISION_PATH = "/home/donovan/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py"
_MEMORY_DECISION_PAYLOAD: Any | None = None
_MEMORY_DECISION_LOAD_ATTEMPTED = False


EXPLICIT_RECALL_PATTERNS = (
    re.compile(r"(召回|查|找|用|检索|搜索).{0,80}记忆"),
    re.compile(r"记忆.{0,80}(召回|查询|查找|检索|搜索)"),
    re.compile(r"\b(recall|search|find|use|check|lookup|look up)\b.{0,80}\b(memory|memories)\b", re.I),
    re.compile(r"\b(memory|memories)\b.{0,80}\b(recall|search|find|use|check|lookup|look up)\b", re.I),
)

ACTION_RECALL_PATTERNS = (
    re.compile(r"(烧录|刷机|升级|镜像|固件|update\.img|fastboot|ota|maskrom|loader|image|firmware)", re.I),
    re.compile(r"(下载|获取).{0,30}(镜像|固件|image|firmware)", re.I),
    re.compile(r"(DTS|device tree|dtsi|驱动|driver|kernel|audio|codec|sai|i2s|mipi|dsi|csi|hdmi|drm|display|camera)", re.I),
    re.compile(r"(rg|find|git log).{0,40}(大范围|广泛|全部|所有|批量|多处|wide|broad|all)", re.I),
    re.compile(r"(连接|登录|ssh|adb|serial|串口|设备|board|transport).{0,40}(选择|切换|验证|确认|排查|定位)", re.I),
    re.compile(r"(vps2|vps|服务器|server|remote|远端).{0,80}(sub2api|windsurfapi|cliproxy|docker|compose|容器|服务|日志|log|硬盘|磁盘|容量|disk|df|du|部署|deploy|路径|path)", re.I),
    re.compile(r"(sub2api|windsurfapi|cliproxy|docker|compose|容器|服务|日志|log|硬盘|磁盘|容量|disk|df|du|部署|deploy|路径|path).{0,80}(vps2|vps|服务器|server|remote|远端)", re.I),
)

REMOTE_OPS_RECALL_PATTERNS = ACTION_RECALL_PATTERNS[-2:]
REMOTE_OPS_RECALL_TERMS = (
    "deployment route deploy path docker compose container service logs log "
    "disk usage df du 部署 路径 容器 服务 日志 磁盘 硬盘 容量"
)
SERVICE_RECALL_TERMS = (
    (
        re.compile(r"sub2api", re.I),
        "Sub2API sub2api /opt/sub2api PostgreSQL Redis 15432 16379 8080 swap-sub2api",
    ),
    (
        re.compile(r"windsurfapi|windsurf-api", re.I),
        "WindsurfAPI windsurf-api /opt/windsurfapi 3003",
    ),
    (
        re.compile(r"cliproxy", re.I),
        "cliproxy proxy gateway routing",
    ),
)


def empty_output() -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "",
        }
    }


def print_empty() -> int:
    print(json.dumps(empty_output(), ensure_ascii=False))
    return 0


def parse_input() -> tuple[dict[str, Any], str]:
    if sys.stdin.isatty():
        return {}, ""
    raw = sys.stdin.read()
    data: dict[str, Any] = {}
    if raw.strip():
        try:
            parsed = json.loads(raw)
            data = parsed if isinstance(parsed, dict) else {"input": raw}
        except json.JSONDecodeError:
            data = {"input": raw}
    return data, raw


def text_from_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(text_from_value(item.get("text") or item.get("content") or ""))
        return "\n".join(p for p in parts if p)
    if isinstance(value, dict):
        return text_from_value(value.get("text") or value.get("content") or "")
    return ""


def extract_prompt(data: dict[str, Any], fallback: str = "") -> str:
    for key in ("prompt", "userPrompt", "user_prompt", "input", "message", "text", "content"):
        text = text_from_value(data.get(key))
        if text.strip():
            return text.strip()
    messages = data.get("messages")
    if isinstance(messages, list):
        for msg in reversed(messages):
            if isinstance(msg, dict) and msg.get("role") == "user":
                text = text_from_value(msg.get("content"))
                if text.strip():
                    return text.strip()
    return fallback.strip()


def git_value(args: list[str], cwd: str) -> str:
    try:
        return subprocess.check_output(
            args,
            cwd=cwd or None,
            stderr=subprocess.DEVNULL,
            timeout=0.2,
            text=True,
        ).strip()
    except Exception:
        return ""


def explicit_recall_requested(prompt: str) -> bool:
    return any(pattern.search(prompt or "") for pattern in EXPLICIT_RECALL_PATTERNS)


def action_recall_requested(prompt: str) -> bool:
    return any(pattern.search(prompt or "") for pattern in ACTION_RECALL_PATTERNS)


def load_memory_decision_payload() -> Any | None:
    global _MEMORY_DECISION_LOAD_ATTEMPTED, _MEMORY_DECISION_PAYLOAD
    if _MEMORY_DECISION_LOAD_ATTEMPTED:
        return _MEMORY_DECISION_PAYLOAD
    _MEMORY_DECISION_LOAD_ATTEMPTED = True

    path = Path(os.environ.get("AGENT_MEMORY_DECISION_PATH", DEFAULT_MEMORY_DECISION_PATH)).expanduser()
    try:
        if not path.exists():
            return None
        spec = importlib.util.spec_from_file_location("agent_memory_decision_local", path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        payload_fn = getattr(module, "memory_decision_payload", None)
        if callable(payload_fn):
            _MEMORY_DECISION_PAYLOAD = payload_fn
    except Exception:
        _MEMORY_DECISION_PAYLOAD = None
    return _MEMORY_DECISION_PAYLOAD


def memory_decision_recall_requested(prompt: str) -> bool:
    payload_fn = load_memory_decision_payload()
    if payload_fn is None:
        return action_recall_requested(prompt)
    try:
        payload = payload_fn(prompt or "")
        return int(payload.get("score") or 0) >= 3
    except Exception:
        return action_recall_requested(prompt)


def enrich_prompt_for_recall(prompt: str) -> str:
    if any(pattern.search(prompt or "") for pattern in REMOTE_OPS_RECALL_PATTERNS):
        service_terms = [
            terms for pattern, terms in SERVICE_RECALL_TERMS if pattern.search(prompt or "")
        ]
        focus = " ".join([REMOTE_OPS_RECALL_TERMS, *service_terms])
        return f"{prompt}\nRecall focus: {focus}"
    return prompt


def recall_url_base(url: str) -> str:
    parsed = urllib.parse.urlsplit(url or "http://127.0.0.1:18088/recall")
    path = parsed.path or ""
    if path.endswith("/recall"):
        path = path[: -len("/recall")]
    base = urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, path.rstrip("/"), "", ""))
    return base or "http://127.0.0.1:18088"


def default_recall_url() -> str:
    urls = os.environ.get("AGENT_MEMORY_URLS", "")
    for candidate in urls.split(","):
        candidate = candidate.strip()
        if candidate:
            return candidate if candidate.endswith("/recall") else candidate.rstrip("/") + "/recall"
    url = os.environ.get("AGENT_MEMORY_URL", "http://127.0.0.1:18088/recall").strip()
    return url if url.endswith("/recall") else url.rstrip("/") + "/recall"


def fetch_user_preferences(url: str, timeout: float, limit: int) -> list[dict[str, Any]]:
    endpoint = f"{recall_url_base(url)}/memory/user_preferences?{urllib.parse.urlencode({'limit': max(1, limit)})}"
    try:
        with urllib.request.urlopen(endpoint, timeout=max(0.1, timeout)) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return []
    items = payload.get("items") if isinstance(payload, dict) else []
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def compact_line(text: str, limit: int = 260) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


def user_preferences_context(preferences: list[dict[str, Any]]) -> str:
    if not preferences:
        return ""
    lines = ["Mandatory user preferences:"]
    for item in preferences:
        title = str(item.get("title") or f"memory {item.get('id') or ''}").strip()
        content = compact_line(str(item.get("content") or ""))
        if content:
            lines.append(f"- {title}: {content}")
    return "\n".join(lines) if len(lines) > 1 else ""


def memory_selection_reminder(prompt: str) -> str:
    enriched = enrich_prompt_for_recall(prompt)
    lines = [
        "Memory routing reminder:",
        "- The hook injected only mandatory user preferences; task-specific memories still require explicit selection.",
        "- Before each meaningful step, score it locally: python3 /home/donovan/.codex/bin/agent_memory.py memory-decision \"<step>\"",
        "- Thresholds: <3 none; >=3 search compact candidates; >=5 read 1-3 selected memories; >=7 mandatory before remote/access/credential/destructive steps; >=9 make a small plan first.",
        "- Candidate flow: python3 /home/donovan/.codex/bin/agent_memory.py search-candidates \"<query>\" --limit 15",
        "- Select relevant ids, then read only those full memories: python3 /home/donovan/.codex/bin/agent_memory.py get-memory <id> [<id> ...]",
    ]
    if enriched != prompt and "Recall focus:" in enriched:
        lines.append(f"- Suggested search focus: {enriched.split('Recall focus:', 1)[1].strip()}")
    return "\n".join(lines)


def load_json_file(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_json_file(path: Path, data: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        tmp_path.replace(path)
    except Exception:
        pass


def read_session_meta(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for _ in range(8):
                line = f.readline()
                if not line:
                    break
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict) and record.get("type") == "session_meta":
                    payload = record.get("payload")
                    return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}
    return {}


def recent_session_files(root: Path, limit: int) -> list[Path]:
    if not root.exists():
        return []
    try:
        files = [path for path in root.glob("**/*.jsonl") if path.is_file()]
        files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
        return files[: max(limit, 1)]
    except Exception:
        return []


def latest_compaction_timestamp(path: Path, tail_bytes: int) -> str:
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            start = max(0, size - max(tail_bytes, 4096))
            f.seek(start)
            text = f.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""

    lines = text.splitlines()
    if start > 0 and lines:
        lines = lines[1:]
    for line in reversed(lines):
        if "context_compacted" not in line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        payload = record.get("payload") if isinstance(record, dict) else {}
        if isinstance(payload, dict) and payload.get("type") == "context_compacted":
            return str(record.get("timestamp") or "")
    return ""


def state_session_key(data: dict[str, Any]) -> str:
    for key in ("session_id", "conversation_id", "trunk_id"):
        value = str(data.get(key) or "").strip()
        if value:
            return value
    return ""


def discover_session(
    data: dict[str, Any],
    cwd: str,
    state: dict[str, Any],
    session_root: Path,
    scan_limit: int,
) -> tuple[str, Path | None]:
    requested_key = state_session_key(data)
    sessions = state.get("sessions") if isinstance(state.get("sessions"), dict) else {}
    if requested_key:
        existing = sessions.get(requested_key)
        if isinstance(existing, dict):
            path_text = str(existing.get("session_path") or "")
            if path_text:
                existing_path = Path(path_text).expanduser()
                if existing_path.exists():
                    return requested_key, existing_path

    for path in recent_session_files(session_root, scan_limit):
        meta = read_session_meta(path)
        meta_cwd = str(meta.get("cwd") or "")
        if cwd and meta_cwd and os.path.abspath(meta_cwd) != os.path.abspath(cwd):
            continue
        session_id = requested_key or str(meta.get("id") or "") or str(path)
        return session_id, path
    return requested_key, None


def compaction_allows_recall(data: dict[str, Any], cwd: str, state_path: Path) -> bool:
    session_root = Path(os.environ.get("AGENT_MEMORY_SESSION_ROOT", DEFAULT_SESSION_ROOT)).expanduser()
    scan_limit = int(os.environ.get("AGENT_MEMORY_SESSION_SCAN_LIMIT", str(DEFAULT_SESSION_SCAN_LIMIT)))
    tail_bytes = int(os.environ.get("AGENT_MEMORY_SESSION_TAIL_BYTES", str(DEFAULT_TAIL_BYTES)))
    state = load_json_file(state_path)
    sessions = state.setdefault("sessions", {})
    if not isinstance(sessions, dict):
        sessions = {}
        state["sessions"] = sessions

    session_key, session_path = discover_session(data, cwd, state, session_root, scan_limit)
    if not session_key or not session_path:
        return False

    compaction_timestamp = latest_compaction_timestamp(session_path, tail_bytes)
    if not compaction_timestamp:
        return False

    entry = sessions.get(session_key)
    if not isinstance(entry, dict):
        entry = {}
    if entry.get("last_compaction_timestamp") == compaction_timestamp:
        return False

    entry.update(
        {
            "cwd": cwd,
            "session_path": str(session_path),
            "last_compaction_timestamp": compaction_timestamp,
        }
    )
    sessions[session_key] = entry
    save_json_file(state_path, state)
    return True


def should_recall(prompt: str, data: dict[str, Any], cwd: str, mode: str, state_path: Path) -> bool:
    normalized_mode = (mode or "action_or_compact_or_explicit").strip().lower()
    if normalized_mode == "off":
        return False
    if normalized_mode == "always":
        return True
    if explicit_recall_requested(prompt):
        return True
    if normalized_mode == "action_or_compact_or_explicit" and memory_decision_recall_requested(prompt):
        return True
    if normalized_mode not in {"compact_or_explicit", "action_or_compact_or_explicit"}:
        normalized_mode = "action_or_compact_or_explicit"
    return compaction_allows_recall(data, cwd, state_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", nargs="?", default="")
    parser.add_argument("--cwd", default="")
    parser.add_argument("--repo", default="")
    parser.add_argument("--branch", default="")
    parser.add_argument("--trunk-id", default="")
    parser.add_argument("--url", default=default_recall_url())
    parser.add_argument("--timeout", type=float, default=float(os.environ.get("AGENT_MEMORY_HOOK_TIMEOUT", "1.4")))
    parser.add_argument("--limit-memories", type=int, default=5)
    parser.add_argument("--limit-docs", type=int, default=3)
    parser.add_argument("--limit-user-preferences", type=int, default=int(os.environ.get("AGENT_MEMORY_USER_PREFERENCES_LIMIT", str(DEFAULT_USER_PREFERENCES_LIMIT))))
    args = parser.parse_args()

    data, raw = parse_input()
    fallback_prompt = args.prompt or raw
    prompt = extract_prompt(data, fallback_prompt)
    if not prompt:
        return print_empty()

    cwd = str(data.get("cwd") or args.cwd or os.getcwd())
    repo = str(data.get("repo") or args.repo or git_value(["git", "rev-parse", "--show-toplevel"], cwd))
    branch = str(data.get("branch") or args.branch or git_value(["git", "branch", "--show-current"], cwd))
    state_path = Path(os.environ.get("AGENT_MEMORY_RECALL_STATE", DEFAULT_STATE_PATH)).expanduser()
    mode = os.environ.get("AGENT_MEMORY_RECALL_MODE", "action_or_compact_or_explicit")
    preferences = fetch_user_preferences(args.url, args.timeout, args.limit_user_preferences)
    should_include_reminder = should_recall(prompt, data, cwd, mode, state_path)

    if not preferences and not should_include_reminder:
        return print_empty()

    output = empty_output()
    parts = [user_preferences_context(preferences)]
    if should_include_reminder:
        parts.append(memory_selection_reminder(prompt))
    output["hookSpecificOutput"]["additionalContext"] = "\n\n".join(part for part in parts if part)
    print(json.dumps(output, ensure_ascii=False))
    return 0
