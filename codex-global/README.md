# Codex Global Memory Gate Assets

This directory versions the global Codex prompt and hook scripts used to make
path-level lookup results become durable agent-memory candidates.

## Files

- `AGENTS.override.md` - global behavior rules for memory-first lookup,
  path-level memory gates, and final memory reporting.
- `bin/memory-gate-reminder-hook.py` - `UserPromptSubmit` hook that injects a
  short reminder for repo/debug prompts.
- `bin/memory-gate-check.py` - best-effort final checklist that scans recent
  Codex logs for lookup commands and memory writes.

The live Codex installation still reads the files from `~/.codex`. Keep those
runtime files in place; sync from this directory when changing the policy.

## Install Or Sync

```bash
mkdir -p ~/.codex/bin
cp codex-global/AGENTS.override.md ~/.codex/AGENTS.override.md
cp codex-global/bin/memory-gate-reminder-hook.py ~/.codex/bin/memory-gate-reminder-hook.py
cp codex-global/bin/memory-gate-check.py ~/.codex/bin/memory-gate-check.py
chmod +x ~/.codex/bin/memory-gate-reminder-hook.py ~/.codex/bin/memory-gate-check.py
```

Add this hook alongside the existing recall hook in `~/.codex/config.toml`:

```toml
[[hooks.UserPromptSubmit.hooks]]
type = "command"
command = "python3 /home/donovan/.codex/bin/memory-gate-reminder-hook.py"
timeout = 1
statusMessage = "Memory gate reminder"
```

Before final handoff on non-trivial repo tasks, run:

```bash
python3 ~/.codex/bin/memory-gate-check.py --cwd "$PWD"
```
