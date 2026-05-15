#!/bin/sh
set -eu

ROOT="${AGENT_MEMORY_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
IMAGE="${AGENT_MEMORY_EMBED_IMAGE:-agent-memory-embedder:local}"
CACHE_DIR="${1:-$ROOT/tmep/agent-memory-vector-cache/bge_m3}"
if [ "$#" -gt 0 ]; then shift; fi
QDRANT_URL="${1:-http://127.0.0.1:6333}"
if [ "$#" -gt 0 ]; then shift; fi
MODEL="${AGENT_MEMORY_EMBED_MODEL:-/models/bge-m3}"
PROVIDER="${AGENT_MEMORY_VECTOR_CACHE_PROVIDER:-local}"
HTTP_URL="${AGENT_MEMORY_VECTOR_CACHE_HTTP_URL:-}"
PROFILE="${AGENT_MEMORY_VECTOR_PROFILE:-bge_m3}"
COLLECTION="${AGENT_MEMORY_QDRANT_COLLECTION:-agent_chunks_bge_m3_hybrid}"
BATCH_SIZE="${AGENT_MEMORY_VECTOR_CACHE_BATCH_SIZE:-1}"
SLEEP_SECONDS="${AGENT_MEMORY_VECTOR_CACHE_SLEEP_SECONDS:-1.0}"
LIMIT="${AGENT_MEMORY_VECTOR_CACHE_LIMIT:-0}"

CACHE_DIR="$(mkdir -p "$CACHE_DIR" && cd "$CACHE_DIR" && pwd)"
docker build -t "$IMAGE" "$ROOT/embedding-worker"
docker run --rm --network host \
  --user "$(id -u):$(id -g)" \
  -e PYTHONPATH=/agent-memory/app \
  -v "$ROOT:/agent-memory" \
  -v "$CACHE_DIR:/cache" \
  -v "$ROOT/data/model-cache:/models" \
  --entrypoint python \
  "$IMAGE" \
  /agent-memory/scripts/drain_vector_cache.py \
  --cache-dir /cache \
  --provider "$PROVIDER" \
  --model "$MODEL" \
  --http-url "$HTTP_URL" \
  --qdrant-url "$QDRANT_URL" \
  --collection "$COLLECTION" \
  --profile "$PROFILE" \
  --batch-size "$BATCH_SIZE" \
  --sleep-seconds "$SLEEP_SECONDS" \
  --limit "$LIMIT" \
  "$@"
