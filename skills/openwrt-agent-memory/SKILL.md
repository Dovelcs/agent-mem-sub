---
name: openwrt-agent-memory
description: Use when working with the user's OpenWrt soft-router agent-memory system or the unified local workflow entrypoint. Covers recalling or writing durable memories, checking /opt/agent-memory, Qdrant, embedding, Codex Hook behavior, MCP coverage, SSD-backed storage, startup settings, performance, conversation trunk, workflow planning, spec-lite plans, subagent dispatch, spec/code review checkpoints, and archived docs-first/codex-orchestrator/subagent-driven-development rules. Trigger for Chinese or English requests mentioning soft router, OpenWrt memory, agent-memory, Qdrant, embedding, recall, /opt/agent-memory, /mnt/agent-memory-store, persistent project/device facts, 写计划, 主干, trunk, workflow, plan, 子代理, subagent, review, code review, spec review, docs-first, codex-orchestrator, or subagent-driven-development.
metadata:
  short-description: Operate the OpenWrt agent-memory service
---

# OpenWrt Agent Memory

## Memory Source Policy

The database is the only source for durable memory facts. Do not duplicate
runtime topology, credentials, performance baselines, storage layout, or other
recallable facts in this skill or helper scripts. This skill keeps behavior and
workflow rules only; retrieve facts through recall or `/memory/search`.

## Operating Rules

1. Prefer `mcp__ssh_openwrt__.exec` for live checks. The HTTP services bind to
   OpenWrt localhost, so local host curl usually cannot reach them directly.
2. Before claiming the system is healthy, verify `/health`, container status,
   and the SSD mount if storage matters.
3. Do not store raw conversations, large logs, or full documents as memories.
   Store stable facts, decisions, caveats, and verified operational paths.
4. Before writing a summarized memory, search for an existing same-title or
   same-topic memory first. Update the existing memory when the new information
   refines it; create a new memory only when it is a genuinely separate fact.
   Choose the narrowest `type` from the taxonomy below instead of defaulting
   everything to `system` or a driver/debug category.
5. Keep memory content short: one stable fact per memory, 1-3 sentences.
6. Use `status=pinned` for topology/storage facts that should always surface.
   Use `status=active` for performance baselines and caveats that may drift.
7. Include both English and Chinese keywords in tags when the user may ask in
   Chinese, for example `openwrt`, `agent-memory`, `ssd`, `soft-router`,
   `软路由`, `固态硬盘`, `召回`, `降级`.
8. If embedding or Qdrant fails, do not block the task. `/recall` should fall
   back to SQLite FTS; verify this before reporting a hard failure.
9. Automatic recall belongs at `UserPromptSubmit`, not before every shell/tool
   action. Keep the hook timeout short and return empty `additionalContext` on
   tunnel/API errors so Codex is never blocked by memory recall.
10. During execution, run an on-demand memory search when the task hits a
   route or environment blocker instead of repeatedly trying the same path.
   Triggers include the same command/interface failing twice, errors such as
   `timeout`, `permission denied`, `connection reset`, `MCP error`,
   `No such file`, or `ModuleNotFoundError`, a path/device/repo mismatch, or a
   clear decision point between docs, DTS, logs, runtime commands, or reference
   code. Search with the current error text plus the user goal, cwd/repo, and
   platform keywords; use only the top 3 concise `route_guard`, `pitfall`, or
   `verified_route` memories to adjust the route.
11. When a user request can be satisfied through mutually exclusive execution
   routes, first run a route-selection recall before choosing one. Examples:
   fastboot vs Rockchip `upgrade_tool`, OTA vs full `update.img`, adb vs serial,
   host-side USB device vs board-side runtime, or local file edit vs remote
   device operation. Search for the user goal plus all plausible route names,
   current cwd/repo/platform, and observed connection state; prefer
   `decision_policy`, `route_guard`, `verified_route`, and `pitfall` memories
   over generic docs. Treat the selected route as provisional until the current
   transport/environment is verified.
12. At the end of each OpenWrt agent-memory task, do a short maintenance check:
   if the task exposed a reusable operational pitfall, fixed sequence, or stable
   deployment fact, update an existing memory or create a concise new one. Only
   update this skill when the agent's behavior or workflow rules must change.
   Put long evidence in docs/index instead of SKILL.md.

## Unified Workflow Entry

Use this skill as the single local workflow, memory, and conversation-trunk
entrypoint. It now absorbs the useful operating rules from the archived
`codex-orchestrator`, `docs-first`, and `subagent-driven-development` skills;
do not activate those skills separately unless they are restored for rollback.

- Small tasks: execute directly, optionally run a quick recall when route,
  credential, repo, or environment history may matter.
- Medium tasks: create or activate a compact trunk with `workflow-start`, then
  update it at meaningful milestones with `workflow-update`.
- Complex, customer-facing, or high-risk tasks: create a light plan in the
  trunk before editing. Use the spec-lite shape from
  `references/spec-lite.md`, but generate standalone PRD/TECH_SPEC/ACTION_PLAN
  files only when the deliverable or repo process truly requires them.
- Decomposable implementation tasks: split into bounded streams with disjoint
  ownership. Give each worker the complete task text and needed context; do not
  ask workers to read a large plan by themselves. Treat `DONE`,
  `DONE_WITH_CONCERNS`, `NEEDS_CONTEXT`, and `BLOCKED` as explicit states.
- Review checkpoints: verify spec compliance before code quality. For risky
  changes, run a final integrated review before handoff.
- MCP and runtime checks remain preferred for live systems. Keep execution mode
  explicit when work can happen locally, on OpenWrt, through MCP, or through a
  long-running background process.
- Long tasks must keep the trunk current enough that a new or compacted session
  can recover the goal, current route, finished milestones, open blockers, and
  next action without rereading the whole conversation.

Memory recall and workflow execution are separate responsibilities:

- Use recall for fast route correction: prior environment failures, blocked
  commands, wrong device assumptions, credentials/source locations, route
  guards, and verified shortcuts.
- Do not use recall as a replacement for workflow mechanics. Long task
  planning, trunk updates, worker dispatch, status handling, spec review, code
  review, and final handoff must follow the process below even when recall is
  fast.
- When a route fails twice or an environment assumption is uncertain, pause the
  current route, run recall with the exact failure plus goal/cwd/repo/platform,
  update the trunk with the route pivot, then continue with the workflow.

## Absorbed Skill Parity

This section is the canonical replacement for the archived workflow skills.
Treat it as capability parity, not a loose summary.

### Codex-Orchestrator Parity

- This skill is the default workflow router for hands-on development,
  debugging, implementation, long tasks, and multi-step repo/device execution.
- Keep MCP or other runtime tools as the control plane when they are the
  shortest live proof path. Keep execution lanes explicit: local shell,
  OpenWrt/MCP, background process, browser, or remote service.
- Equivalent flow for former `codex-orchestrator flow`:
  1. Run route-selection recall when prior facts may matter.
  2. Start or activate a trunk.
  3. Choose direct, spec-lite, formal docs-first, or subagent execution mode.
  4. Execute with milestone updates.
  5. Run spec/review checkpoints.
  6. Finish the trunk and suggest durable memory only for reusable lessons.
- Equivalent flow for former `doctor/status --watch`: put the command, timeout,
  last observation, stall threshold, and next poll action into the trunk; report
  progress without rereading the whole task.
- Equivalent flow for former `review`: findings-first code review, then
  residual risk and verification summary.
- Intent routing:
  - Task/spec scaffolding: use the docs-first parity below.
  - Delegation/subagents: use the subagent parity below.
  - Option analysis: keep the decision frame in the trunk and use recall for
    prior route guards.
  - Long-running checks: keep status and polling state in the trunk.
  - Final handoff: run spec compliance before code quality, then a concise
    final result.

### Docs-First Parity

Use docs-first mode when the user asks for formal planning docs, the repo
requires task/spec artifacts, the work is customer-facing, or the change is
high-risk enough that a stable written contract is needed.

Formal docs-first mode must do all of the following before implementation:

1. Draft or refresh PRD, TECH_SPEC, and ACTION_PLAN.
   - PRD captures user intent and a concise translation of the request.
   - TECH_SPEC captures technical requirements, constraints, interfaces, and
     acceptance criteria.
   - ACTION_PLAN captures milestones, sequencing, verification, and rollback.
2. Register the task/spec when the repo has a task system:
   - Add or update `tasks/index.json` when present.
   - Create or refresh a task checklist such as `tasks/tasks-*.md`.
   - Mirror to `.agent/task/` and update `docs/TASKS.md` when those paths
     already exist in the repo.
3. Run a docs/spec review before implementation. If no external docs-review
   command exists, perform the review inline: check that requirements,
   non-goals, acceptance tests, affected files, and risks are explicit.
4. Keep docs aligned as understanding changes. If implementation discovers a
   new constraint, update the spec/trunk before continuing.

Micro-task shortcut:

- For small low-risk edits, use spec-lite in the trunk instead of full docs.
- The shortcut still needs goal, constraints, milestones, verification, risks,
  and next action.

### Subagent-Driven Development Parity

Use this mode when there is an implementation plan, tasks are mostly
independent, and the active tool policy allows focused workers/subagents.

Controller process:

1. Read the plan once. Extract every task with complete task text, context,
   ownership boundary, target files, and acceptance checks.
2. Keep the task list in the trunk or active plan state.
3. Dispatch a fresh worker per task. Do not make the worker read a large plan
   file; paste the complete task and curated context into the prompt.
4. If the worker asks questions, answer before implementation continues.
5. After implementation, handle status exactly:
   - `DONE`: proceed to spec compliance review.
   - `DONE_WITH_CONCERNS`: inspect concerns; resolve correctness/scope concerns
     before review.
   - `NEEDS_CONTEXT`: provide missing context and re-dispatch.
   - `BLOCKED`: change something: add context, use a stronger model, split the
     task, fix the plan, or escalate.
6. Run spec compliance review first. If issues are found, send them back to the
   implementer and re-review.
7. Run code quality review only after spec compliance passes. If issues are
   found, fix and re-review.
8. Mark the task complete only after both reviews pass.
9. After all tasks, run an integrated final review for cross-task regressions.

Model and dispatch guidance:

- Mechanical isolated tasks can use faster workers.
- Multi-file integration/debugging needs a stronger worker.
- Architecture and review tasks need the strongest available reviewer.
- Keep worker write scopes disjoint. Do not dispatch parallel writers to the
  same files.

Red lines:

- Do not skip spec review or code quality review.
- Do not start code quality review before spec compliance passes.
- Do not ignore `BLOCKED` or retry unchanged.
- Do not accept "close enough" when review found issues.
- Do not let implementer self-review replace independent review.
- Do not move to the next task while review issues remain open.

Reference files:

- `references/workflow-router.md` - task routing and checkpoint rules.
- `references/spec-lite.md` - compact spec fields mapped to trunk data.
- `references/subagent-execution.md` - bounded worker and review discipline.
- `references/prompts/` - implementer, spec reviewer, and code quality reviewer
  prompt templates for `agent_memory.py prompt-template`.

## Memory Type Taxonomy

Use these `type` values consistently so recall can separate user behavior,
agent execution routes, engineering facts, and document knowledge. Keep each
memory narrow: one fact, one route, or one preference.

| Type | Scope | Use For | Recall Behavior |
| --- | --- | --- | --- |
| `user_style` | `global` | Stable user preferences, output style, execution expectations, and disliked answer patterns. | Treat as broad behavior guidance; do not attach platform or chip tags unless the preference is domain-specific. |
| `agent_route` | `codex`, `openwrt`, tool name | How Codex should operate a tool, service, MCP, hook, or local environment. | Recall at task start and on environment/tool blockers. |
| `decision_policy` | workflow, platform, repo | Which route to choose when several valid methods exist, and what current-state checks decide between them. | Recall before choosing between mutually exclusive routes such as fastboot, RK tool, OTA, adb, serial, or host-side operations. |
| `route_guard` | repo, platform, workflow | A route that should be tried first, plus routes that repeatedly wasted time. | Recall on task start and when the agent reaches a route decision. |
| `pitfall` | tool, repo, platform | Reproducible errors, command caveats, bad assumptions, or failure signatures. | Recall on repeated failure or matching error text. |
| `verified_route` | repo, platform, workflow | A proven shortest path, validation sequence, or known-good command flow. | Prefer over exploratory search when the same problem shape appears. |
| `project_fact` | repo or product | Stable repository, branch, build, packaging, service, or customer-deliverable facts. | Recall only when cwd/repo/product/customer matches. |
| `hardware_debug` | platform, board, peripheral | Board, DTS, pinctrl, driver, peripheral chip, runtime probe, and bring-up findings. | Recall for matching platform/peripheral; do not let it dominate non-hardware tasks. |
| `doc_index` | docs set or repo | Where documents live, how they were deduped, source manifests, and which files answer which topics. | Recall when finding docs or explaining source provenance. |
| `workflow_policy` | workflow or organization | Commit, JIRA, review, customer-document, sync, and delivery rules. | Recall for matching workflow even when no hardware keywords appear. |
| `performance_baseline` | service, repo, device | Measured latency, memory/disk use, throughput, and startup behavior. | Treat as drift-prone unless just verified. |
| `credential_location` | service or device | Where credentials or wrappers are configured, without exposing secrets in recall output. | Recall only enough to route to the credential source; never print raw secrets. |

Tagging rules:

- Always include domain-neutral tags for cross-task recall, for example
  `user_style`, `agent_route`, `decision_policy`, `route_guard`, `pitfall`,
  `verified_route`, `doc_index`, or `workflow_policy`.
- Add platform/repo/peripheral tags only when they are true constraints, not
  just words that appeared in a log.
- For negative lessons, include both the bad route and the good route in tags,
  for example `wrong-route`, `prefer-docs`, `prefer-dts`, `avoid-driver-scan`.
- Use `status=pinned` only for global user style, topology, or critical routing
  facts. Use `status=active` for project facts and debug findings that may age.

## Recall UX Rules

- Recall output is intentionally segmented by memory type. Inspect route
  decisions, pitfalls, workflow/access, project facts, and docs separately
  before choosing a path.
- Short prompts are expanded with intent aliases before search. For example,
  "烧录" also searches for fastboot, `upgrade_tool`, `rkdeveloptool`, OTA,
  `update.img`, Loader, Maskrom, route selection, and transport checks.
- Use `include_trace=true` only when debugging recall quality. Trace is for
  diagnostics and should not be injected into normal Codex hook context.
- Use `memory_suggest` for concise candidate memories after a task exposes a
  reusable lesson. It checks existing matches first; set `write=true` only when
  the suggestion is short, stable, and useful beyond the current turn.

## Conversation Trunk

Use the memory-backed trunk for long or branching tasks that are likely to
survive context compaction. It is stored in the agent-memory key-value store,
not in local plan text.

- Create or activate a trunk with `trunk_upsert` at the start of a multi-step
  task. Include `trunk_id` or `conversation_id`, goal, cwd/repo/branch, status,
  and compact milestones.
- Update with `trunk_update` after each meaningful milestone, route pivot, or
  subtask branch result. Keep each progress or branch note one short sentence.
- Use `trunk_get` after compaction/resume to recover the current goal and last
  progress before continuing.
- Pass `trunk_id` into `/recall` when available; recall will inject only a
  compact "Current trunk" section.
- Run `trunk_cleanup` periodically. By default, draft trunks that were never
  activated are deleted after 24 hours, inactive unfinished trunks are deleted
  after 168 hours, and `done`/`archived` trunks are retained. Adjust TTLs with
  `workflow-cleanup --draft-ttl-hours ... --inactive-ttl-hours ...` when needed.

## SSH MCP Caveats

- Keep `mcp__ssh_openwrt__.exec` commands short. Long commands can hit the MCP
  command-length limit or become hard to recover from.
- Avoid heredocs through `ssh_openwrt`; the terminator can be forwarded into the
  remote interpreter and cause errors such as `NameError: name 'PY' is not
  defined`.
- For multi-line Python or shell, create a temporary script via a small tarball,
  a short downloaded file, or several simple commands, then execute the file on
  OpenWrt.
- For benchmarks, put the benchmark body in `/tmp/*.py` or an existing helper
  script. Do not compress complex loops into a single fragile `python -c` unless
  the command is genuinely short.
- If a timed command exceeds the MCP timeout, check for leftover remote
  processes with `pgrep -af` and clean up only the processes started for the
  test.

## Quick Checks

Use helper commands first; retrieve concrete topology, container names, storage
paths, and tunnel details from memory before running low-level checks.

```sh
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py health
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py smoke
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py recall \
  "agent-memory runtime facts storage vector hook"
```

Treat the recalled runtime topology as the source for any lower-level command
you run next.

## Recall Test

Use the helper to check recall behavior without duplicating service topology in
this file:

```sh
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py recall \
  "AB分区 升级失败 回滚 boot_a boot_b update_engine"
```

If vector recall is active, doc items should have nonzero `vector_score`.

## Writing Durable Memories

Always check for an existing equivalent memory before writing:

```sh
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py recall \
  "memory title or topic to check before writing"
```

If a matching memory exists, include its `id` in `/memory/upsert` so the write
updates that memory instead of creating another one.

Use the bundled script when available:

```sh
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py smoke
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py workflow-start --trunk-id current --goal "..."
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py workflow-update --trunk-id current --progress "..."
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py workflow-get --trunk-id current
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py prompt-template implementer
```

When running from a host that does not use the default local API forwarding, set
`AGENT_MEMORY_URL` from the runtime topology recalled from the database.

Manual memory upsert payload shape:

```json
{
  "type": "system",
  "scope": "openwrt",
  "title": "Short stable memory title",
  "content": "One short verified fact.",
  "tags": ["openwrt", "agent-memory", "ssd", "软路由"],
  "source": "codex-skill/openwrt-agent-memory",
  "confidence": 1.0,
  "importance": 0.95,
  "status": "pinned"
}
```

## Common Fixes

- Before applying a common fix, recall the relevant runtime topology and
  operational caveat memory.
- Startup, restart, and embedding warmup commands are environment facts; keep
  their concrete command lines in the memory database or runbook documents, not
  duplicated in this skill file.
