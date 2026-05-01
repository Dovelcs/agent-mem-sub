# Subagent Execution

Use subagents or workers only for bounded work that can proceed independently
or in parallel with the controller's current path. This file is the parity
replacement for the archived `subagent-driven-development` skill.

Core principle: fresh worker per task plus two-stage review after each task.
Spec compliance review always comes before code quality review.

## When To Use

- There is an implementation plan or a clear set of tasks.
- Tasks are mostly independent or can be given disjoint write scopes.
- The work stays coordinated in the current session/trunk.
- The active tool policy allows subagents/workers for this task.

Use manual execution when there is no plan, tasks are tightly coupled, or the
next controller step is blocked on the result.

## Dispatch Rules

- Provide the complete task text, ownership boundary, target paths, acceptance
  checks, and relevant context in the prompt.
- Do not ask the worker to open a long plan and infer its assignment.
- Tell workers they are not alone in the codebase and must not revert unrelated
  edits.
- Keep write scopes disjoint when multiple workers edit files in parallel.
- Keep urgent blocking work local when the next controller step depends on it.
- Prefer `fork_context=false` for bounded streams. Use context forking only
  when the worker genuinely needs prior thread history.

## Controller Process

1. Read the plan once and extract every task with full text.
2. Record tasks and current status in the trunk.
3. Dispatch an implementer worker with the implementer template.
4. Answer worker questions before implementation continues.
5. Handle the worker status.
6. Dispatch spec compliance reviewer.
7. If spec issues are found, send them back to the implementer and re-review.
8. Dispatch code quality reviewer only after spec compliance passes.
9. If quality issues are found, send them back to the implementer and re-review.
10. Mark the task complete only after both reviews pass.
11. Repeat for remaining tasks.
12. Run final integrated review for the whole implementation.

## Status Contract

- `DONE`: implementation and local verification completed.
- `DONE_WITH_CONCERNS`: work completed, but correctness/scope concerns remain.
- `NEEDS_CONTEXT`: worker needs missing facts before continuing.
- `BLOCKED`: worker cannot finish with current task shape or model.

Never retry a blocked worker unchanged. Provide missing context, split the task,
or take the blocking path local.

## Model Selection

- Mechanical tasks touching 1-2 files with a complete spec: fast worker.
- Multi-file coordination, pattern matching, or debugging: standard/strong
  worker.
- Architecture, design, and review: strongest available reviewer.

Prefer cheaper/faster models only when the task is fully specified and isolated.

## Review Order

1. Spec compliance review: check the implementation against the requested task
   and identify missing or extra behavior with file references.
2. Code quality review: run only after spec compliance passes; focus on bugs,
   maintainability, tests, and avoidable complexity.
3. Integrated review: use for cross-file or multi-worker work before handoff.

## Red Lines

- Never skip spec compliance review.
- Never skip code quality review.
- Never run code quality review before spec compliance passes.
- Never proceed with unfixed review issues.
- Never ask workers to infer their task from a long plan file.
- Never ignore worker questions.
- Never accept `BLOCKED` without changing context, task split, route, or model.
- Never let implementer self-review replace independent review.
