# Spec-Lite

Use spec-lite for complex or risky work without forcing heavyweight PRD,
TECH_SPEC, and ACTION_PLAN files.

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
