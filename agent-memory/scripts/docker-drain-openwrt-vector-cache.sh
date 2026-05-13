#!/bin/sh
set -eu

ROOT="${AGENT_MEMORY_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
REMOTE="${AGENT_MEMORY_OPENWRT:-root@100.106.225.53}"
SSH_KEY="${AGENT_MEMORY_OPENWRT_KEY:-/home/donovan/.ssh/id_rsa_openwrt_agent_memory}"
PROFILE="${AGENT_MEMORY_VECTOR_PROFILE:-qwen3_4b}"
REMOTE_CACHE="${AGENT_MEMORY_REMOTE_VECTOR_CACHE:-/opt/agent-memory/tmep/agent-memory-vector-cache/$PROFILE}"
LOCAL_CACHE="${1:-$ROOT/tmep/openwrt-vector-cache/$PROFILE}"
LOCAL_QDRANT_PORT="${AGENT_MEMORY_QDRANT_TUNNEL_PORT:-16333}"
COLLECTION="${AGENT_MEMORY_QDRANT_COLLECTION:-agent_chunks_qwen3_4b}"

ssh_base() {
  ssh -i "$SSH_KEY" -o BatchMode=yes -o ConnectTimeout=5 "$REMOTE" "$@"
}

LOCAL_CACHE="$(mkdir -p "$LOCAL_CACHE" && cd "$LOCAL_CACHE" && pwd)"
mkdir -p "$LOCAL_CACHE/pending" "$LOCAL_CACHE/processing" "$LOCAL_CACHE/done" "$LOCAL_CACHE/failed"

ssh_base "mkdir -p '$REMOTE_CACHE/pending' '$REMOTE_CACHE/processing' '$REMOTE_CACHE/done' '$REMOTE_CACHE/failed' && tar -C '$REMOTE_CACHE' -czf - pending 2>/dev/null" \
  | tar -C "$LOCAL_CACHE" -xzf -

ssh -i "$SSH_KEY" -o BatchMode=yes -o ExitOnForwardFailure=yes \
  -N -L "$LOCAL_QDRANT_PORT:127.0.0.1:6333" "$REMOTE" &
tunnel_pid=$!
trap 'kill "$tunnel_pid" 2>/dev/null || true' EXIT
sleep 1

AGENT_MEMORY_VECTOR_CACHE_LIMIT="${AGENT_MEMORY_VECTOR_CACHE_LIMIT:-0}" \
AGENT_MEMORY_VECTOR_PROFILE="$PROFILE" \
AGENT_MEMORY_QDRANT_COLLECTION="$COLLECTION" \
  sh "$ROOT/scripts/docker-drain-vector-cache.sh" "$LOCAL_CACHE" "http://127.0.0.1:$LOCAL_QDRANT_PORT"

tar -C "$LOCAL_CACHE" -czf - done failed \
  | ssh_base "tar -C '$REMOTE_CACHE' -xzf -"

find "$LOCAL_CACHE/done" "$LOCAL_CACHE/failed" -type f -name '*.json' -printf '%f\n' \
  | ssh -i "$SSH_KEY" -o BatchMode=yes "$REMOTE" "while IFS= read -r name; do [ -n \"\$name\" ] && rm -f '$REMOTE_CACHE/pending/'\"\$name\"; done"
