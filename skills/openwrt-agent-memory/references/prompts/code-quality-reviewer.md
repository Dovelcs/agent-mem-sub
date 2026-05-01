# Code Quality Reviewer Prompt Template

Use only after spec compliance passes.

```text
You are reviewing implementation quality.

What was implemented:
[Summary or implementer report]

Plan or requirements:
[Task text]

Diff or target range:
[Base/head SHA, file list, or patch scope]

Review for:
- Bugs and behavioral regressions.
- Missing or weak tests.
- Maintainability and local pattern fit.
- Avoidable complexity or overbuilding.
- File responsibility and interface clarity.
- Risk from interactions with unrelated work.

Report:
- Findings first, ordered by severity, with file:line references.
- Open questions or residual risk.
- Brief change summary only after findings.
```
