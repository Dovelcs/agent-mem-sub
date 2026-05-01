## Global Defaults
- If a task clearly matches an installed skill, use it automatically.
- For hands-on development, code changes, debugging, implementation, or multi-step repo execution, use `openwrt-agent-memory` as the unified workflow/memory/trunk router.
- For read-only Q&A, explanation, brainstorming, or analysis-only requests, do not start a workflow trunk unless explicitly requested or workflow routing is clearly needed.

## Memory-First Lookup
- For SDK path lookup, build entrypoints, DTS locations, implementation routes, document sources, device access, prior failures, or environment-sensitive choices, query the agent-memory database before broad `rg`, `find`, or `git log` probing.
- If memory returns an exact usable result with repo/path/function/route context, continue from that result. A small targeted verification is allowed, such as reading the remembered file path or checking the remembered command still exists, but do not re-run broad `rg`, `find`, or `git log` scans just to rediscover the same fact.
- Fall back to broad scanning only when the memory hit is missing required context, the remembered path/branch/environment no longer exists, the targeted verification contradicts the memory, or the remembered result is not enough to continue the task.
- When `rg`, `find`, `git log`, or similar scans reveal a reusable result, write the tool purpose plus the verified conclusion into the memory database. The memory should answer: what was the agent trying to find, what entry/path/route was found, and when can that result be reused. Include the actual project/repo path, branch, platform, device, document path, or runtime environment so later recall does not apply a result from the wrong checkout.
- For function, service-entry, build-entry, hook, route, or implementation-location lookups, the reusable result must include the concrete symbol/entry name and file path; include a line number when the lookup output provides a stable line. Do not store vague conclusions such as "found in foo.c" when the function name and location are known.
- Do not write raw scan hit lists, large logs, generated output trees, `dl/downloads`, `output/`, `rockdev/`, or unverified guesses into memory. Use scanning again only when memory has no specific hit, the result is stale, or current files/branches need low-cost verification.

## Mandatory Path-Level Memory Gate
- For hands-on debugging, implementation, or repo investigation, every `rg`, `find`, `git log`, `git grep`, or similar lookup that directly identifies a file/function/route/build-entry used in the solution creates a `MEMORY_WRITE_CANDIDATE`.
- A `MEMORY_WRITE_CANDIDATE` must include: lookup purpose, repo/cwd/branch/environment, file path, symbol/entry/function/route name, line number when available, verified conclusion, and when to reuse it.
- Maintain a running internal `MEMORY_WRITE_CANDIDATES` list during the task. Add a candidate immediately when a lookup result becomes part of the chosen route or patch, instead of trying to reconstruct it at the end.
- Before the final response for any non-trivial repo task, Codex MUST close every `MEMORY_WRITE_CANDIDATE` by either writing it with `agent_memory.py write-found` or `write-found-batch`, or explicitly recording why it is not reusable.
- Codex MUST NOT send the final response after a non-trivial repo task until this memory gate is closed. If any candidate remains unresolved, keep working and close the gate first.
- Do not store raw hit lists. Store only verified path-level conclusions.
- Before final response on non-trivial repo tasks, run `python3 /home/donovan/.codex/bin/memory-gate-check.py --cwd "$PWD"` when available and use its output as a reminder/checklist. A warning from this script must be resolved by writing memory or by stating why the flagged lookup result is not reusable.

## Parallel-First Execution
- Prefer parallel execution for independent reads, probes, builds, checks, and disjoint code changes.
- Use `multi_tool_use.parallel` for independent developer-tool calls in the current session.
- When delegation is available and the active tool policy permits it, use focused workers for independent streams.
- The user explicitly authorizes Codex to spawn focused subagents/workers by default for non-trivial tasks that can be decomposed into independent workstreams.
- Prefer multiple subagents/workers for multi-file, multi-module, investigation, implementation, or verification work when streams are read-only or have disjoint write scopes.
- Fall back to serial execution for simple one-shot tasks, stateful flows, truly sequential dependencies, or concurrent writes that would conflict.

## SDK Bootstrap Default
- Before hands-on SDK/repo work, run `codex-sdk-bootstrap --quiet` from the intended repository root.
- The bootstrap is idempotent: it ensures Codex trust, Task Master `codex-cli` model sync from `~/.codex/config.toml`, project MCP wiring, Serena `--project-from-cwd`, and global Git ignores for local helper files.
- Skip bootstrap for read-only Q&A, transient inspection, generated/vendor directories, rootfs trees, `output/`, `rockdev/`, and `dl/`.

## Skill Maintenance
- Use `skill-boundary-backfill` only after a triggered skill needed more than 6 reusable probe steps and the user task is already unblocked; read that skill for the detailed policy.
- Quectel service credentials are intentionally not kept in global context. Use the relevant Quectel/Gerrit skill, which will read the private credential note only when login is required.

## Final Reporting
- At the end of each non-trivial task, clearly report memory usage: how many memory items were hit/used for the task, and how many durable memories were created or updated during the task. If no memory was used or written, say `memory hits: 0, memory writes: 0`.
- Also report `skipped memory candidates: N`; if nonzero, give the reason for each skipped reusable-looking candidate.
