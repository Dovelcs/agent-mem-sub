# Spec-Lite

Use spec-lite for complex or risky work without forcing heavyweight PRD,
TECH_SPEC, and ACTION_PLAN files. Use formal docs-first mode when the user or
repo process requires stable artifacts.

## Trunk Mapping

- `title`: short task name.
- `goal`: user-visible success condition and any non-goals.
- `cwd`, `repo`, `branch`: current execution target.
- `milestones`: ordered work units with compact acceptance checks.
- `progress`: completed steps, verified facts, and current result.
- `branch_notes`: route pivots, rejected approaches, blockers, and subtask
  results.
- `status`: `draft`, `active`, `blocked`, `done`, or `archived`.

## When To Create Real Docs

Create standalone PRD/TECH_SPEC/ACTION_PLAN-style documents only when:

- The user asks for formal docs.
- The repo process requires task/spec artifacts.
- The work is customer-facing and needs a deliverable trail.
- Multiple independent contributors need a stable written contract.

Otherwise keep the spec in the trunk to reduce context and filesystem noise.

## Formal Docs-First Mode

When formal docs-first mode is active, do this before implementation:

1. Draft or refresh PRD.
   - Capture user intent and a concise translation of the request.
   - State goals, non-goals, stakeholders, and acceptance criteria.
2. Draft or refresh TECH_SPEC.
   - Capture requirements, affected modules/files, interfaces, data flows,
     constraints, risks, and verification.
   - Store under `tasks/specs/<id>-<slug>.md` when the repo has that layout.
3. Draft or refresh ACTION_PLAN.
   - Capture sequencing, milestones, ownership, validation, rollback, and open
     questions.
4. Register and mirror when the repo supports it.
   - Update `tasks/index.json` with the TECH_SPEC and review status.
   - Create or refresh `tasks/tasks-*.md`.
   - Mirror to `.agent/task/` and update `docs/TASKS.md` when those paths exist.
5. Run docs/spec review before implementation.
   - If an external docs-review command exists, run it.
   - Otherwise do an inline review for missing requirements, stale assumptions,
     unclear acceptance tests, and unresolved risks.
6. Keep PRD/TECH_SPEC/ACTION_PLAN and trunk aligned when constraints change.

Do not create repo-specific scaffolding paths that do not already exist unless
the user asks for formal project setup.

## Minimum Spec-Lite Fields

```text
Goal:
Constraints:
Milestones:
Verification:
Risks / route decisions:
Next action:
```

Keep each field short enough that the trunk can be injected into recall without
crowding the prompt.

## Minimal Formal Templates

PRD:

```text
# PRD: <title>

## User Request
<original intent and concise translation>

## Goals

## Non-Goals

## Acceptance Criteria

## Risks / Open Questions
```

TECH_SPEC:

```text
# TECH_SPEC: <title>

## Requirements

## Affected Areas

## Design / Implementation Notes

## Interfaces / Data

## Verification

## Risks
```

ACTION_PLAN:

```text
# ACTION_PLAN: <title>

## Milestones

## Execution Order

## Review Gates

## Validation

## Rollback / Recovery
```
