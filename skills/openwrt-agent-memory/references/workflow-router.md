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
- For former `codex-orchestrator flow`, run: recall when useful, trunk start,
  spec-lite or formal docs-first gate, implementation, review, trunk finish.
- For former `codex-orchestrator doctor/status --watch`, keep observation,
  command, timeout, stall policy, and next poll action in the trunk.
- For former `codex-orchestrator review`, run findings-first review and capture
  residual risk plus verification in the trunk.

## Checkpoints

- Before route choice: search for `decision_policy`, `route_guard`,
  `verified_route`, and `pitfall` memories.
- Before edits: confirm the active repo/path and any local `AGENTS.md`.
- During blockers: if the same command or route fails twice, recall with the
  exact error text plus the goal and cwd.
- Before handoff: run the smallest verification that proves the requested
  behavior, then record reusable lessons with `memory_suggest` when appropriate.

## Intent Router Parity

- Task/spec scaffolding and mirror sync: use `spec-lite.md`; when formal mode is
  required, create PRD, TECH_SPEC, ACTION_PLAN, task checklist, and mirrors.
- Delegation or subagent evidence discipline: use `subagent-execution.md`.
- Stream decomposition: split only into independent bounded work with disjoint
  write scopes.
- Option analysis and tradeoffs: record the decision frame in trunk; use recall
  for prior route guards and pitfalls.
- Long-running checks: use trunk progress notes as the status stream.
- Implementation checkpoint and final handoff: spec review first, code quality
  review second, integrated final review for multi-task work.
- Release/eval helpers are not absorbed here; restore their archived skills
  only when explicitly needed.

## Archived Sources

This router replaces `codex-orchestrator` for the user's local workflow. It does
not require the old orchestrator CLI, but it preserves the workflow semantics:
explicit route choice, MCP/runtime proof when applicable, docs-first gate when
needed, bounded delegation, long-running status checks, and review checkpoints.
