# Agent Memory and Workflow Skills

This repository snapshots the user's local agent-memory implementation and the
merged workflow skill set.

## Layout

- `agent-memory/` - OpenWrt-deployable FastAPI + SQLite FTS5 + Qdrant memory
  service, document ingest pipeline, recall hook, MCP server, embedding worker,
  and operation scripts.
- `skills/openwrt-agent-memory/` - active Codex skill for operating the memory
  service and the unified workflow/trunk/subagent/review route.
- `codex-global/` - versioned global Codex prompt override and lightweight
  memory-gate hooks that make reusable lookup results become memory-write
  candidates before final handoff.
- `skills.disabled/openwrt-agent-memory-absorbed-20260501/` - archived
  third-party workflow skills absorbed into `openwrt-agent-memory`, kept for
  rollback and reference.

Runtime databases, vector dumps, document indexes, Qdrant storage, vendored
wheels, and Python caches are intentionally excluded from git.
