# Subagent Execution

Use subagents or workers only for bounded work that can proceed independently
or in parallel with the controller's current path.

## Dispatch Rules

- Provide the complete task text, ownership boundary, target paths, acceptance
  checks, and relevant context in the prompt.
- Do not ask the worker to open a long plan and infer its assignment.
- Tell workers they are not alone in the codebase and must not revert unrelated
  edits.
- Keep write scopes disjoint when multiple workers edit files in parallel.
- Keep urgent blocking work local when the next controller step depends on it.

## Status Contract

- `DONE`: implementation and local verification completed.
- `DONE_WITH_CONCERNS`: work completed, but correctness/scope concerns remain.
- `NEEDS_CONTEXT`: worker needs missing facts before continuing.
- `BLOCKED`: worker cannot finish with current task shape or model.

Never retry a blocked worker unchanged. Provide missing context, split the task,
or take the blocking path local.

## Review Order

1. Spec compliance review: check the implementation against the requested task
   and identify missing or extra behavior with file references.
2. Code quality review: run only after spec compliance passes; focus on bugs,
   maintainability, tests, and avoidable complexity.
3. Integrated review: use for cross-file or multi-worker work before handoff.
