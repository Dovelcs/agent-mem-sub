#!/bin/sh
set -eu

ROOT="${AGENT_MEMORY_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
IMAGE="${AGENT_MEMORY_EMBED_IMAGE:-agent-memory-embedder:local}"
CACHE_DIR="${1:-$ROOT/tmep/agent-memory-vector-cache}"
QDRANT_URL="${2:-http://127.0.0.1:6333}"
MODEL="${AGENT_MEMORY_EMBED_MODEL:-Qwen/Qwen3-Embedding-4B}"
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
  --provider local \
  --model "$MODEL" \
  --qdrant-url "$QDRANT_URL" \
  --batch-size "$BATCH_SIZE" \
  --sleep-seconds "$SLEEP_SECONDS" \
  --limit "$LIMIT"
