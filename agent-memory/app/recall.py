from __future__ import annotations

import argparse
import json
import select
import sys
from typing import Any
from urllib import request as urlrequest


DEFAULT_URL = "http://127.0.0.1:18088/recall"


def read_stdin_json() -> dict[str, Any]:
    if sys.stdin.isatty():
        return {}
    try:
        ready, _, _ = select.select([sys.stdin], [], [], 0.05)
        if not ready:
            return {}
        raw = sys.stdin.read()
        if not raw.strip():
            return {}
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def hook_to_recall_payload(data: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
    prompt = (
        data.get("prompt")
        or data.get("userPrompt")
        or data.get("user_prompt")
        or data.get("message")
        or args.prompt
        or ""
    )
    return {
        "prompt": prompt,
        "cwd": data.get("cwd") or args.cwd or "",
        "repo": data.get("repo") or args.repo or "",
        "branch": data.get("branch") or args.branch or "",
        "trunk_id": data.get("trunk_id") or data.get("conversation_id") or data.get("session_id") or args.trunk_id or "",
        "conversation_id": data.get("conversation_id") or "",
        "session_id": data.get("session_id") or "",
        "limit_memories": args.limit_memories,
        "limit_docs": args.limit_docs,
        "include_user_preferences": args.include_user_preferences,
        "auto_include_docs": args.auto_include_docs,
    }


def empty_output() -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": "",
        }
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", nargs="?", default="")
    parser.add_argument("--cwd", default="")
    parser.add_argument("--repo", default="")
    parser.add_argument("--branch", default="")
    parser.add_argument("--trunk-id", default="")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--timeout", type=float, default=1.8)
    parser.add_argument("--limit-memories", type=int, default=5)
    parser.add_argument("--limit-docs", type=int, default=3)
    parser.add_argument("--include-user-preferences", action="store_true")
    parser.add_argument("--auto-include-docs", action="store_true")
    args = parser.parse_args()

    data = read_stdin_json()
    payload = hook_to_recall_payload(data, args)
    output = empty_output()
    try:
        body = json.dumps(payload).encode("utf-8")
        req = urlrequest.Request(
            args.url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlrequest.urlopen(req, timeout=args.timeout) as resp:
            result = json.loads(resp.read().decode("utf-8"))
        output["hookSpecificOutput"]["additionalContext"] = result.get("additionalContext", "")
    except Exception:
        pass
    print(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
