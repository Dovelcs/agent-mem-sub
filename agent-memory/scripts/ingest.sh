#!/bin/sh
set -eu

ROOT="${AGENT_MEMORY_ROOT:-/opt/agent-memory}"
DOCS_PATH="${1:-$ROOT/docs}"
shift || true

PYTHONPATH="$ROOT/app" AGENT_MEMORY_CONFIG="$ROOT/app/config.yaml" \
  "$ROOT/venv/bin/python" "$ROOT/app/ingest_docs.py" "$DOCS_PATH" "$@"

