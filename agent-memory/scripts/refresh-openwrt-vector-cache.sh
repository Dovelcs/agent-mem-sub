#!/bin/sh
set -eu

ROOT="${AGENT_MEMORY_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
LOCK_BASE="${XDG_RUNTIME_DIR:-/tmp}"
LOCK_DIR="$LOCK_BASE/agent-memory-vector-cache-drain.lock"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  printf '{"ok":true,"skipped":"already_running"}\n'
  exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT INT TERM

AGENT_MEMORY_EMBED_MODEL="${AGENT_MEMORY_EMBED_MODEL:-Qwen/Qwen3-Embedding-4B}" \
AGENT_MEMORY_VECTOR_PROFILE="${AGENT_MEMORY_VECTOR_PROFILE:-qwen3_4b}" \
AGENT_MEMORY_QDRANT_COLLECTION="${AGENT_MEMORY_QDRANT_COLLECTION:-agent_chunks_qwen3_4b}" \
AGENT_MEMORY_VECTOR_CACHE_BATCH_SIZE="${AGENT_MEMORY_VECTOR_CACHE_BATCH_SIZE:-1}" \
AGENT_MEMORY_VECTOR_CACHE_SLEEP_SECONDS="${AGENT_MEMORY_VECTOR_CACHE_SLEEP_SECONDS:-1.0}" \
  sh "$ROOT/scripts/docker-drain-openwrt-vector-cache.sh"
