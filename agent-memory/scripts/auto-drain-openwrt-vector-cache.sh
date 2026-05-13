#!/bin/sh
set -eu

ROOT="${AGENT_MEMORY_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
API="${AGENT_MEMORY_API_URL:-http://100.106.225.53:18088}"
PROFILE="${AGENT_MEMORY_VECTOR_PROFILE:-qwen3_4b}"
STATUS="$(curl -fsS --max-time 5 "$API/memory/vector_cache")"
PENDING="$(printf '%s' "$STATUS" | PROFILE="$PROFILE" python3 -c 'import json,os,sys; data=json.load(sys.stdin); profile=os.environ["PROFILE"]; print(int(((data.get("profiles") or {}).get(profile) or data).get("pending") or 0))')"

if [ "$PENDING" -le 0 ]; then
  printf '{"ok":true,"skipped":"empty","pending":0}\n'
  exit 0
fi

printf '{"ok":true,"action":"drain","pending":%s}\n' "$PENDING"
exec env AGENT_MEMORY_VECTOR_PROFILE="$PROFILE" sh "$ROOT/scripts/refresh-openwrt-vector-cache.sh"
