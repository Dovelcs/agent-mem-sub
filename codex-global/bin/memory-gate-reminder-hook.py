#!/usr/bin/env python3
"""Inject a concise memory-gate reminder for repo/debug prompts."""

from __future__ import annotations

import json
import re
import sys
from typing import Any


KEYWORDS = re.compile(
    r"(debug|fix|bug|implement|repo|代码|修|查|定位|调试|实现|改|部署|OpenWrt|SDK|rg|find|git log|路径|入口|函数|route|hook)",
    re.I,
)


def text_from_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(text_from_value(item) for item in value)
    if isinstance(value, dict):
        return text_from_value(value.get("text") or value.get("content") or "")
    return ""


def extract_prompt(data: dict[str, Any], raw: str) -> str:
    for key in ("prompt", "userPrompt", "user_prompt", "input", "message", "text", "content"):
        text = text_from_value(data.get(key))
        if text.strip():
            return text.strip()
    return raw.strip()


def output(additional_context: str) -> int:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": additional_context,
        }
    }, ensure_ascii=False))
    return 0


def main() -> int:
    raw = sys.stdin.read()
    try:
        parsed = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        parsed = {"input": raw}
    data = parsed if isinstance(parsed, dict) else {"input": raw}
    prompt = extract_prompt(data, raw)
    if not KEYWORDS.search(prompt):
        return output("")
    return output(
        "Memory gate reminder: for repo/debug tasks, every rg/find/git-log result used as a route or patch location is a MEMORY_WRITE_CANDIDATE. Before final, close all candidates with agent_memory.py write-found/write-found-batch or explicitly skip them, run `python3 /home/donovan/.codex/bin/memory-gate-check.py --cwd \"$PWD\"`, and report memory hits/writes/skipped candidates."
    )


if __name__ == "__main__":
    raise SystemExit(main())
