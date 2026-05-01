#!/usr/bin/env python3
"""Best-effort reminder for Codex path-level memory cleanup.

This script scans recent Codex TUI log lines for lookup commands such as
`rg`, `find`, and `git log`, and compares them with agent-memory write
commands. It is intentionally conservative: it does not decide correctness,
but it gives a visible final-check reminder before handoff.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from pathlib import Path


DEFAULT_LOG = Path.home() / ".codex" / "log" / "codex-tui.log"
LOOKUP_RE = re.compile(r"(^|[;&|({]\s*)(rg|find|git\s+(?:log|grep|show))(\s|$)")
MEMORY_WRITE_RE = re.compile(r"agent_memory\.py\s+(write-found|write-found-batch|write-fact)\b|/memory/write")
COMMAND_RE = re.compile(r'ToolCall:\s+\w+\s+(\{.*\})')
TIMESTAMP_RE = re.compile(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cwd", default=os.getcwd(), help="Current repo/work directory to match in recent tool calls.")
    parser.add_argument("--log", default=str(DEFAULT_LOG), help="Codex TUI log path.")
    parser.add_argument("--since-minutes", type=float, default=240.0, help="How far back to scan.")
    parser.add_argument("--strict", action="store_true", help="Exit 2 when lookup commands appear without memory writes.")
    return parser.parse_args()


def line_is_recent(line: str, cutoff: dt.datetime) -> bool:
    match = TIMESTAMP_RE.match(line)
    if not match:
        return True
    try:
        when = dt.datetime.fromisoformat(match.group(1).replace("Z", "+00:00"))
    except ValueError:
        return True
    return when >= cutoff


def extract_cmd(line: str) -> str:
    if '"cmd":"' not in line and '"command":' not in line:
        return ""
    # The log stores JSON inside tracing text. Full JSON decoding is brittle
    # here, so keep a readable best-effort extraction for reminder purposes.
    for key in ('"cmd":"', '"command":"'):
        start = line.find(key)
        if start < 0:
            continue
        start += len(key)
        out: list[str] = []
        escaped = False
        for ch in line[start:]:
            if escaped:
                out.append(ch)
                escaped = False
                continue
            if ch == "\\":
                escaped = True
                continue
            if ch == '"':
                break
            out.append(ch)
        return "".join(out)
    return ""


def main() -> int:
    args = parse_args()
    log_path = Path(args.log)
    if not log_path.exists():
        print(f"memory-gate-check: log not found: {log_path}")
        return 0

    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(minutes=max(args.since_minutes, 1))
    cwd = str(Path(args.cwd).resolve())
    lookup_cmds: list[str] = []
    memory_writes: list[str] = []

    with log_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if not line_is_recent(line, cutoff):
                continue
            if cwd not in line and "/home/donovan/.codex" not in line:
                continue
            cmd = extract_cmd(line)
            haystack = cmd or line
            if LOOKUP_RE.search(haystack):
                lookup_cmds.append(haystack[:240])
            if MEMORY_WRITE_RE.search(haystack):
                memory_writes.append(haystack[:240])

    print("memory-gate-check:")
    print(f"  cwd: {cwd}")
    print(f"  recent lookup commands: {len(lookup_cmds)}")
    print(f"  recent memory writes: {len(memory_writes)}")
    if lookup_cmds:
        print("  lookup samples:")
        for sample in lookup_cmds[-5:]:
            print(f"    - {sample}")
    if memory_writes:
        print("  memory write samples:")
        for sample in memory_writes[-5:]:
            print(f"    - {sample}")
    if lookup_cmds and not memory_writes:
        print("  WARNING: lookups were seen but no recent memory write was detected.")
        print("  Close MEMORY_WRITE_CANDIDATES with write-found/write-found-batch or explicitly skip them.")
        return 2 if args.strict else 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
