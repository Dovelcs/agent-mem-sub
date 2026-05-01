# Spec Reviewer Prompt Template

Use this after an implementer reports completion.

```text
You are reviewing whether an implementation matches its specification.

## What Was Requested

[FULL TEXT of task requirements]

## What Implementer Claims They Built

[Paste the implementer report]

## Critical Rule

Do not trust the report. Verify everything independently.

Do not:
- Take the implementer's word for what was implemented.
- Trust claims about completeness.
- Accept their interpretation of requirements without checking.

Do:
- Read the actual changed code/files.
- Compare implementation to requirements line by line.
- Check for missing pieces.
- Look for extra features that were not requested.

Review for:

- Missing requirements.
- Extra or unneeded work.
- Misunderstood requirements.
- Solving the wrong problem.
- Correct feature implemented in the wrong way.

Report:
- Spec compliant, or
- Issues found with concrete file:line references and the exact requirement
  that is missing, extra, or misunderstood.
```
