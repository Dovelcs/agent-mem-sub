# Workflow Router

Use `openwrt-agent-memory` as the single local workflow router.

## Routing Rules

- Read-only explanation or tiny one-shot command: answer or run directly.
- Repo, device, or service work with prior context risk: recall first with the
  user goal, cwd/repo, branch, platform, and any route names.
- Multi-step work that can survive compaction: create a trunk before the first
  meaningful edit, then keep it updated.
- High-risk, customer-facing, or ambiguous work: write a spec-lite plan into the
  trunk before implementation.
- Long-running operations: keep the current route, command, timeout, and next
  poll action in the trunk.
- Live OpenWrt work: prefer MCP/runtime proof over static assumptions.

## Checkpoints

- Before route choice: search for `decision_policy`, `route_guard`,
  `verified_route`, and `pitfall` memories.
- Before edits: confirm the active repo/path and any local `AGENTS.md`.
- During blockers: if the same command or route fails twice, recall with the
  exact error text plus the goal and cwd.
- Before handoff: run the smallest verification that proves the requested
  behavior, then record reusable lessons with `memory_suggest` when appropriate.

## Archived Sources

This router keeps the useful ideas from `codex-orchestrator`: explicit routing,
MCP as the preferred control plane for live systems, bounded delegation,
long-running status checks, and review checkpoints. It intentionally avoids
requiring the old orchestrator CLI for normal local work.
