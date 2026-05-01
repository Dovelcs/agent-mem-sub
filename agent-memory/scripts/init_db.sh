#!/bin/sh
set -eu

ROOT="${AGENT_MEMORY_ROOT:-/opt/agent-memory}"
PYTHON="$ROOT/venv/bin/python"

if [ ! -x "$PYTHON" ]; then
  PYTHON="$(command -v python3)"
fi

PYTHONPATH="$ROOT/app" AGENT_MEMORY_CONFIG="$ROOT/app/config.yaml" "$PYTHON" "$ROOT/app/db.py"

