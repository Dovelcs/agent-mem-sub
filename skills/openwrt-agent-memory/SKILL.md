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
workflow rules only; retrieve facts through the local `memory-decision` gate
and the compact candidate flow below.

## Step-Level Memory Decision

Before each meaningful task step, run a low-cost local score. This is a local
regex decision only; it does not access the network or read memory content.

```sh
python3 /home/donovan/.codex/bin/agent_memory.py memory-decision "<step description>"
```

A meaningful step is an independent goal or route choice, not every shell
command. Score at least these steps before acting: route selection, remote or
device access, service checks, log/path lookup, use of scripts/tools, credential
or login flow, broad `rg`/`find`/`git log`/`git grep`, config change,
deployment, restart, destructive action, and the next step after an error.
Skill-owned routine workflows, such as a generic code commit/push request, do
not require memory lookup unless the step also includes environment-sensitive
signals such as production/staging/customer/online, a named host, ssh route,
credential/login, deployment, restart, container access, or a prior failure.

Always include these in the score when present:

- Nonstandard tools: custom CLI, MCP, factory tools, flashing tools, vendor
  scripts, wrappers, internal APIs.
- Nonstandard scripts: one-off scripts, deploy/fix/collection scripts, hooks,
  bridges, proxies.
- Credentials and login: JIRA/Gerrit/Sub2API admin, tokens, cookies, OAuth,
  SSH keys, web login, API keys.
- Access channels: `ssh-vps2`, `ssh-openwrt`, adb, serial, Tailscale,
  `docker exec`, container-local health checks, host-vs-container choices.

Thresholds:

- `<3`: no memory lookup.
- `>=3`: run compact candidates.
- `>=5`: read 1-3 selected full memories before continuing.
- `>=7`: memory read is mandatory before remote, access, credential, or
  destructive steps.
- `>=9`: make a small plan first, then continue through candidate recall.

## Agent-Facing Candidate Recall

When `memory-decision` reaches a lookup threshold, prefer the compact two-step
CLI flow instead of `/recall` or raw `/memory/search` output:

1. Run `python3 /home/donovan/.codex/bin/agent_memory.py search-candidates "<query>" --limit 15`.
   This prints compact `id | type | score | title | summary` lines only.
2. Select the relevant ids.
3. Run `python3 /home/donovan/.codex/bin/agent_memory.py get-memory <id> [<id> ...]`
   to bring only selected full memories into context.

Do not print full `/memory/search` candidate JSON unless machine-readable
metadata is explicitly needed; it wastes context and defeats candidate
selection.

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
9. The hook is reminder-only. It should not inject full recalled memory content
   or run network recall for Codex. It uses the same local `memory-decision`
   score to decide whether to emit a reminder, then the agent chooses whether
   to run compact candidates and selected `get-memory`.
10. During execution, score each meaningful intermediate step, not just the
   first prompt and not just failures. This prevents mid-route mistakes where
   the remembered pitfall belongs to a substep such as a script, credential
   source, container-local health check, or host-vs-container distinction.
11. When a user request can be satisfied through mutually exclusive execution
   routes, run `memory-decision` on the route choice before choosing one.
   Examples: fastboot vs Rockchip `upgrade_tool`, OTA vs full `update.img`, adb
   vs serial, host-side USB device vs board-side runtime, local file edit vs
   remote device operation, host health check vs container-local health check.
   Prefer `decision_policy`, `route_guard`, `verified_route`, and `pitfall`
   memories over generic docs. Treat the selected route as provisional until
   the current transport/environment is verified.
12. At the end of each OpenWrt agent-memory task, do a maintenance check for
   reusable conclusions. Write or update memory for proven tool/script entries,
   misleading access paths, effective credential locations or login flows,
   required command/API parameters, reliable routes, and failed routes that are
   likely to be retried. Do not store raw passwords, tokens, cookies, or API
   keys; store only the credential location, access flow, and risk boundary.
13. For lookup tasks, an exact memory hit should become the working route. If
   the hit includes enough repo/path/function/command context, continue from
   it and at most do a targeted verification of the remembered path or command.
   Do not re-run broad `rg`, `find`, or `git log` just to rediscover the same
   fact. Re-scan only when the remembered context is incomplete, stale,
   contradicted by targeted verification, or insufficient to continue.
14. For function, service-entry, build-entry, hook, route, or implementation
   location lookups, the reusable result must include the symbol/entry name and
   file path. Include the line number when the lookup output provides a stable
   line. A memory such as "found in foo.c" is too weak; write "entry
   `foo_start()` is at `path/foo.c:123` and is reached from ...".

## Difficulty Scoring

`memory-decision` implements this local scoring model:

- `+2` remote, device, production, or staging environment.
- `+1` explicit production/staging/customer/online risk marker.
- `+2` service, deployment, logs, disk, build entry, DTS, driver path, or
  container health.
- `+2` route choice.
- `+2` nonstandard tool, script, wrapper, MCP, hook, bridge, proxy, or internal
  API.
- `+2` credential, password, login, token, cookie, OAuth, admin backend, API
  key, JIRA, Gerrit, or Sub2API admin.
- `+2` special access channel: ssh, adb, serial, Tailscale, `docker exec`,
  container-local health, web login, or host-vs-container decision.
- `+1` historical entity: `vps2`, `sub2api`, OpenWrt, a concrete SDK, board,
  customer project, or known service name.
- `+1` broad scan: `rg`, `find`, `git log`, `git grep`, or equivalent.
- `+1` first failure.
- `+2` second failure on the same path.
- `+2` high-signal error: `timeout`, `permission denied`, `No such file`,
  `MCP error`, `connection reset`, `ModuleNotFoundError`, `401/403`, or login
  redirect anomaly.
- `+3` destructive or service-impacting action: write config, deploy, restart,
  delete, migrate, flash, upgrade, or reboot.

If the selected memory returns an exact usable path, command, device route,
credential source, login flow, script entry, or document source, continue from
it with only targeted verification. If it is empty, stale, vague, or
contradicted by current state, probe the repo/device/docs. Any probe that
becomes a chosen route, patch location, reusable command, credential location,
or tool access route is a MEMORY_WRITE_CANDIDATE and must be closed before the
final response.

## Unified Workflow Entry

Use this skill as the single local workflow, memory, and conversation-trunk
entrypoint. It now absorbs the useful operating rules from the archived
`codex-orchestrator`, `docs-first`, and `subagent-driven-development` skills;
do not activate those skills separately unless they are restored for rollback.

- Small tasks: execute directly; run `memory-decision` when route, credential,
  repo, or environment history may matter, then follow the threshold result.
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
- After successfully resolving a target that took a long detour, multiple route
  pivots, repeated failures, or hard-won investigation to reach the conclusion,
  fork/copy the current task context to a small summarizer model or lightweight
  worker for experience distillation. This is a background sidecar step: the
  main conversation must continue with verification, handoff, or the next user
  action and must not be blocked or redirected by the summarizer. The
  summarizer's only job is to turn the current-context evidence, route pivots,
  small tool pitfalls, and verified candidates into compact structured memory
  candidates; it must not discover new facts, edit repo files, decide the main
  route, or write durable memory directly. The main agent reviews the distilled
  JSON before any memory write.

Memory recall and workflow execution are separate responsibilities:

- Use `memory-decision` plus candidate recall for fast route correction: prior
  environment failures, blocked commands, wrong device assumptions,
  credentials/source locations, route guards, and verified shortcuts.
- Do not use memory lookup as a replacement for workflow mechanics. Long task
  planning, trunk updates, worker dispatch, status handling, spec review, code
  review, and final handoff must follow the process below even when memory
  lookup is fast.
- When a route fails twice or an environment assumption is uncertain, pause the
  current route, score the next step with the exact failure plus
  goal/cwd/repo/platform, read selected memories when the threshold requires
  it, update the trunk with the route pivot, then continue with the workflow.

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
  1. Run `memory-decision` for route selection when prior facts may matter.
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
| `user_style` | `global` or `user_preferences` | Stable user preferences, output style, execution expectations, and disliked answer patterns. | This is the user preference space. `type=user_style` or `scope=user_preferences` memories are mandatory recall items; keep them short, pinned when stable, and domain-neutral unless the preference is domain-specific. |
| `agent_route` | `codex`, `openwrt`, tool name | How Codex should operate a tool, service, MCP, hook, or local environment. | Score at task start and environment/tool blockers; read when threshold requires it. |
| `decision_policy` | workflow, platform, repo | Which route to choose when several valid methods exist, and what current-state checks decide between them. | Score before choosing between mutually exclusive routes such as fastboot, RK tool, OTA, adb, serial, or host-side operations. |
| `route_guard` | repo, platform, workflow | A route that should be tried first, plus routes that repeatedly wasted time. | Score at task start and when the agent reaches a route decision. |
| `pitfall` | tool, repo, platform | Reproducible errors, command caveats, bad assumptions, or failure signatures. | Score on repeated failure or matching error text. |
| `verified_route` | repo, platform, workflow | A proven shortest path, validation sequence, or known-good command flow. | Prefer over exploratory search when the same problem shape appears. |
| `project_fact` | repo or product | Stable repository, branch, build, packaging, service, or customer-deliverable facts. | Recall only when cwd/repo/product/customer matches. |
| `hardware_debug` | platform, board, peripheral | Board, DTS, pinctrl, driver, peripheral chip, runtime probe, and bring-up findings. | Recall for matching platform/peripheral; do not let it dominate non-hardware tasks. |
| `doc_index` | docs set or repo | Where documents live, how they were deduped, source manifests, and which files answer which topics. | Recall when finding docs or explaining source provenance. |
| `workflow_policy` | workflow or organization | Commit, JIRA, review, customer-document, sync, and delivery rules. | Recall for matching workflow even when no hardware keywords appear. |
| `performance_baseline` | service, repo, device | Measured latency, memory/disk use, throughput, and startup behavior. | Treat as drift-prone unless just verified. |
| `credential_location` | service or device | Where credentials or wrappers are configured, without exposing secrets in recall output. | Score credential/login steps; read only enough to route to the credential source and never print raw secrets. |

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
- User preferences are a dedicated mandatory-recall space. The hook may inject
  only `type=user_style` or `scope=user_preferences` items automatically; all
  other task-specific memories still require compact candidate selection before
  use.
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
- When a tool explicitly uses `/recall` with `trunk_id`, keep any returned
  trunk context compact. Normal Codex routing still uses `memory-decision`
  followed by compact candidates and selected `get-memory`.
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

For facts discovered by `find`, `rg`, `git log`, or a focused inspection, send
the tool purpose plus the verified conclusion to the server-side smart writer.
Do not paste raw search output into memory, and do not make the memory about
which tool was used. The reusable fact is the human task shape: what question
the tool was answering, what entry/path/route was found, and when that result
can be reused. Bind the conclusion to the actual cwd/repo/branch, path,
platform, device, or environment so future recall can prefer the known answer
over another SDK scan. The client should not spend extra round trips deciding
create vs update; OpenWrt performs the same-topic check and returns `created`,
`updated`, or `skipped`.

For function, service-entry, build-entry, hook, route, or implementation
location lookups, make the `Result` carry the concrete symbol/entry plus path.
If a stable line number is available, include it in the result and pass
`--symbol` and `--line` to `write-found`.

When memory already returns an exact conclusion for a lookup, use it as the
starting point. A targeted read of the remembered file or command is acceptable
when current-state proof matters, but a new broad scan is only justified after
the remembered route fails or lacks enough detail to proceed.

```sh
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py write-found \
  "verified conclusion with the actual path and reuse condition" \
  --kind rg \
  --goal "what this lookup was trying to find" \
  --symbol "entry_or_function_name" \
  --line 123 \
  --path path/that/was/verified \
  --scope repo-or-platform \
  --tag build-entry
```

Use `write-found-batch facts.jsonl` when several conclusions are ready. Each
JSONL row should be a small object with fields such as `fact`, `title`, `kind`,
`path`, `tags`, `repo`, `branch`, `platform`, or `device`; the helper fills
missing repo/branch context once and sends a single batch request.

Use explicit `--title` when a later write should refine the same memory.
Different titles are treated as separate facts even within the same scope. Use
lower-level `write-fact` only when you already have the full payload shape.

Use the bundled script when available:

```sh
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py smoke
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py workflow-start --trunk-id current --goal "..."
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py workflow-update --trunk-id current --progress "..."
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py workflow-get --trunk-id current
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py write-fact "..."
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py write-found "..." --kind find --path ./file
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
