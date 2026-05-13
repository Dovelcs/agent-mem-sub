#!/bin/sh
set -eu

ROOT="${AGENT_MEMORY_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
API="${AGENT_MEMORY_API_URL:-http://100.106.225.53:18088}"
STATUS="$(curl -fsS --max-time 5 "$API/memory/vector_cache")"
PENDING="$(printf '%s' "$STATUS" | python3 -c 'import json,sys; print(int(json.load(sys.stdin).get("pending") or 0))')"

if [ "$PENDING" -le 0 ]; then
  printf '{"ok":true,"skipped":"empty","pending":0}\n'
  exit 0
fi

printf '{"ok":true,"action":"drain","pending":%s}\n' "$PENDING"
exec sh "$ROOT/scripts/refresh-openwrt-vector-cache.sh"
