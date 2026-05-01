#!/bin/sh
set -eu

ROOT="${AGENT_MEMORY_ROOT:-/opt/agent-memory}"
BACKUP_DIR="$ROOT/data/backups"
TS="$(date +%Y%m%d-%H%M%S)"

mkdir -p "$BACKUP_DIR"

if [ -f "$ROOT/agent.db" ]; then
  "$ROOT/venv/bin/python" - "$ROOT/agent.db" "$BACKUP_DIR/agent-$TS.db" <<'PY'
import sqlite3
import sys

src_path, dst_path = sys.argv[1], sys.argv[2]
src = sqlite3.connect(src_path)
dst = sqlite3.connect(dst_path)
with dst:
    src.backup(dst)
src.close()
dst.close()
PY
fi

tar -C "$ROOT" -czf "$BACKUP_DIR/config-docs-$TS.tar.gz" app/config.yaml docs README.md 2>/dev/null || true
echo "$BACKUP_DIR"
