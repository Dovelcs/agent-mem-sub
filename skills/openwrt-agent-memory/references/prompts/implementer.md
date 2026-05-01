# Implementer Prompt Template

Use this template when dispatching a bounded implementation worker.

```text
You are implementing: [task name]

Task:
[Paste the complete task text here. Do not require the worker to read a large plan.]

Context:
[cwd/repo/branch, ownership boundary, relevant files, dependencies, constraints]

Before starting:
Ask now if requirements, acceptance criteria, dependencies, or assumptions are
unclear. Pause if you hit unexpected ambiguity during work.

Responsibilities:
1. Implement exactly the requested task.
2. Follow existing patterns and avoid unrelated refactors.
3. Add or update focused tests when appropriate.
4. Verify the implementation with the smallest meaningful check.
5. Do not revert unrelated edits; other work may be happening in parallel.
6. Self-review before reporting back.

Escalate with NEEDS_CONTEXT or BLOCKED when the task needs missing information,
architectural decisions, broader system knowledge, or a smaller split.

Report:
- Status: DONE | DONE_WITH_CONCERNS | NEEDS_CONTEXT | BLOCKED
- What changed
- Files changed
- Tests/checks run and results
- Self-review notes
- Concerns or blockers
```
