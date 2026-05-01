---
name: openwrt-agent-memory
description: Use when working with the user's OpenWrt soft-router agent-memory system or the unified local workflow entrypoint. Covers recalling or writing durable memories, checking /opt/agent-memory, Qdrant, embedding, Codex Hook behavior, MCP coverage, SSD-backed storage, startup settings, performance, conversation trunk, workflow planning, spec-lite plans, subagent dispatch, spec/code review checkpoints, and archived docs-first/codex-orchestrator/subagent-driven-development rules. Trigger for Chinese or English requests mentioning soft router, OpenWrt memory, agent-memory, Qdrant, embedding, recall, /opt/agent-memory, /mnt/agent-memory-store, persistent project/device facts, 写计划, 主干, trunk, workflow, plan, 子代理, subagent, review, code review, spec review, docs-first, codex-orchestrator, or subagent-driven-development.
metadata:
  short-description: Operate the OpenWrt agent-memory service
---

# OpenWrt Agent Memory

## Runtime Facts

- Target: OpenWrt soft router reachable through the `ssh_openwrt` MCP.
- Root: `/opt/agent-memory`.
- API: `http://127.0.0.1:18088`.
- Qdrant: `http://127.0.0.1:6333`, collection `agent_chunks`.
- Embedding sidecar: `http://127.0.0.1:18089`, model `intfloat/multilingual-e5-small`.
- Local Codex hook: `~/.codex/config.toml` has a `UserPromptSubmit`
  command hook that runs `~/.codex/bin/agent-memory-recall-hook.py`.
- Local tunnel: `agent-memory-forward.service` maps host
  `127.0.0.1:18088` to the OpenWrt API over SSH.
- Storage mount: `/dev/sda2` ext4 label `AGENT_MEMORY`, mounted at `/mnt/agent-memory-store`.
- Storage links:
  - `/opt/agent-memory/agent.db`
  - `/opt/agent-memory/docs`
  - `/opt/agent-memory/data`
  - `/opt/agent-memory/qdrant_storage`
  all resolve under `/mnt/agent-memory-store/agent-memory`.

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
   if the task exposed a reusable operational pitfall, fixed sequence, or safety
   rule, update this skill directly; if it produced a stable deployment fact,
   update an existing memory or create a concise new one; if it produced long
   evidence, put it in docs/index instead of SKILL.md.

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
- Run `trunk_cleanup` periodically. Draft trunks that were never activated and
  inactive trunks are deleted after their TTLs, so stale plans do not pollute
  future sessions.

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

Run on OpenWrt:

```sh
curl -s http://127.0.0.1:18088/health
curl -s --max-time 3 http://127.0.0.1:18089/health
systemctl --user is-active agent-memory-forward.service
printf '%s' '{"prompt":"RK3568 CAN1 I2C3 复用冲突","cwd":"/tmp"}' | \
  python3 ~/.codex/bin/agent-memory-recall-hook.py
docker inspect -f '{{.Name}} restart={{.HostConfig.RestartPolicy.Name}} status={{.State.Status}}' \
  agent-memory-qdrant agent-memory-embedding
mount | grep /mnt/agent-memory-store
df -h /mnt/agent-memory-store /overlay
```

Expected steady state:

- `embedding.provider=http`, `embedding.available=true`.
- Qdrant `points_count` is nonzero.
- `agent-memory-qdrant` and `agent-memory-embedding` are running with
  `restart=unless-stopped`.
- `/mnt/agent-memory-store` is mounted from `/dev/sda2` as ext4.

## Recall Test

Use this to prove vector recall participates:

```sh
/opt/agent-memory/venv/bin/python -c "import json,time,urllib.request; P={'prompt':'AB分区 升级失败 回滚 boot_a boot_b update_engine','limit_memories':5,'limit_docs':3}; d=json.dumps(P,ensure_ascii=False).encode(); r=urllib.request.Request('http://127.0.0.1:18088/recall',data=d,headers={'Content-Type':'application/json'}); t=time.perf_counter(); x=json.loads(urllib.request.urlopen(r,timeout=5).read().decode()); print(json.dumps({'ms':round((time.perf_counter()-t)*1000,2),'items':len(x.get('items',[])),'vector_scores':[round(float(i.get('vector_score') or 0),4) for i in x.get('items',[])]},ensure_ascii=False))"
```

If vector recall is active, doc items should have nonzero `vector_score`.

## Writing Durable Memories

Always check for an existing equivalent memory before writing:

```sh
curl -s http://127.0.0.1:18088/memory/search \
  -H 'Content-Type: application/json' \
  -d '{"query":"OpenWrt agent-memory SSD storage layout","limit":10}'
```

If a matching memory exists, include its `id` in `/memory/upsert` so the write
updates that memory instead of creating another one.

Use the bundled script when available:

```sh
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py upsert-baseline
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py smoke
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py workflow-start --trunk-id current --goal "..."
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py workflow-update --trunk-id current --progress "..."
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py workflow-get --trunk-id current
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py prompt-template implementer
```

When running on OpenWrt, the script defaults to `http://127.0.0.1:18088`. From
another host, set `AGENT_MEMORY_URL` only if the API is explicitly forwarded.

Manual upsert payload shape:

```json
{
  "type": "system",
  "scope": "openwrt",
  "title": "OpenWrt agent-memory SSD storage layout",
  "content": "One short verified fact.",
  "tags": ["openwrt", "agent-memory", "ssd", "软路由"],
  "source": "codex-skill/openwrt-agent-memory",
  "confidence": 1.0,
  "importance": 0.95,
  "status": "pinned"
}
```

## Common Fixes

- Startup:
  ```sh
  /etc/init.d/fstab enable
  /etc/init.d/dockerd enable
  /etc/init.d/agent-memory enable
  docker update --restart unless-stopped agent-memory-qdrant agent-memory-embedding
  ```
- Restart runtime:
  ```sh
  cd /opt/agent-memory
  docker compose up -d --no-build qdrant embedding
  /etc/init.d/agent-memory restart
  ```
- Warm embedding after restart:
  ```sh
  curl -s -X POST http://127.0.0.1:18089/embed \
    -H 'Content-Type: application/json' \
    -d '{"text":"AB partition boot_a boot_b update_engine"}' >/dev/null
  ```
