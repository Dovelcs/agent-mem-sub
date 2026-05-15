#!/bin/sh
set -eu

ROOT="${AGENT_MEMORY_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
IMAGE="${AGENT_MEMORY_EMBED_IMAGE:-agent-memory-embedder:local}"
NAME="${AGENT_MEMORY_DRAIN_CONTAINER:-agent-memory-bge-m3-drain}"
CACHE_DIR="${AGENT_MEMORY_BGE_VECTOR_CACHE:-$ROOT/tmep/agent-memory-vector-cache/bge_m3}"
SLEEP_SECONDS="${AGENT_MEMORY_VECTOR_CACHE_SLEEP_SECONDS:-10}"

mkdir -p "$CACHE_DIR"
docker build -t "$IMAGE" "$ROOT/embedding-worker"

exec docker run --rm --name "$NAME" --network host \
  -e PYTHONPATH=/agent-memory/app \
  -v "$ROOT:/agent-memory" \
  -v "$CACHE_DIR:/cache" \
  --entrypoint python \
  "$IMAGE" \
  /agent-memory/scripts/drain_vector_cache.py \
  --cache-dir /cache \
  --provider http \
  --http-url "${AGENT_MEMORY_BGE_HTTP_URL:-http://127.0.0.1:18090}" \
  --qdrant-url "${AGENT_MEMORY_QDRANT_URL:-http://127.0.0.1:6333}" \
  --collection "${AGENT_MEMORY_QDRANT_COLLECTION:-agent_chunks_bge_m3_hybrid}" \
  --profile bge_m3 \
  --batch-size "${AGENT_MEMORY_VECTOR_CACHE_BATCH_SIZE:-1}" \
  --sleep-seconds "$SLEEP_SECONDS" \
  --watch
