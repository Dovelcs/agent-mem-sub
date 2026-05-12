# Agent Memory MCP Repair Plan

Date: 2026-05-12

## Goal

Make `agent-memory` available to Codex through MCP without replacing the current
fast path: direct HTTP over Tailscale to `http://100.106.225.53:18088`.

## Current State

- Codex uses the HTTP CLI path for memory operations.
- `agent_memory.py` defaults to `http://100.106.225.53:18088`.
- The prompt hook is reminder-only and does not inject full memory content.
- `agent-memory` has a stdio MCP server in `agent-memory/app/mcp_server.py`.
- Codex does not currently register an `agent-memory` MCP server.
- Running the MCP server on the local Codex host is not reliable today:
  - default `python3` imports fail because user-site `cryptography` conflicts
    with system `pyOpenSSL`;
  - `PYTHONNOUSERSITE=1` fixes imports but the local host does not own the
    OpenWrt `/opt/agent-memory` runtime path.

## Repair Route

1. Keep direct Tailscale HTTP as the primary recall/write route.
2. Add an MCP wrapper that runs against the OpenWrt runtime, not the local
   stale source copy.
3. Prefer one of these implementations:
   - Remote stdio wrapper: SSH to OpenWrt and exec
     `/opt/agent-memory/venv/bin/python /opt/agent-memory/app/mcp_server.py`.
   - Local HTTP MCP bridge: implement a small stdio MCP server that proxies
     MCP tool calls to `http://100.106.225.53:18088`.
4. Use the HTTP bridge if minimizing persistent SSH sessions is more important
   than direct SQLite access. Use the remote stdio wrapper if full MCP coverage
   must match `app/mcp_server.py` exactly.
5. Register the wrapper in `~/.codex/config.toml` only after JSONL stdio smoke
   tests pass.

## Validation

- `codex mcp list` shows `agent-memory`.
- JSONL stdio smoke test returns `initialize`, `tools/list`, and `health`.
- `health` reports SQLite WAL, Qdrant green, and embedding available.
- `recall` returns bounded memory/doc context for an agent-memory prompt.
- `memory_search` and `memory_get` work without exposing raw credentials.

## Non-Goals For This Pass

- Do not change Qdrant indexing or enable embedding during recall.
- Do not change recall bucket quotas.
- Do not prune memories except the explicit duplicate-title cleanup requested
  with this task.
