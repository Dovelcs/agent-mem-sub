#!/bin/sh
set -eu

ROOT="${AGENT_MEMORY_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
IMAGE="${AGENT_MEMORY_EMBED_IMAGE:-agent-memory-embedder:local}"
NAME="${AGENT_MEMORY_EMBED_CONTAINER:-agent-memory-qwen3-embedder}"
MODEL="${AGENT_MEMORY_EMBED_MODEL:-Qwen/Qwen3-Embedding-4B}"
PORT="${AGENT_MEMORY_EMBED_PORT:-18089}"
THREADS="${AGENT_MEMORY_EMBED_THREADS:-16}"

docker build -t "$IMAGE" "$ROOT/embedding-worker"

exec docker run --rm --name "$NAME" --network host \
  --user "$(id -u):$(id -g)" \
  -e EMBED_MODEL="$MODEL" \
  -e EMBED_PRELOAD="${AGENT_MEMORY_EMBED_PRELOAD:-1}" \
  -e PORT="$PORT" \
  -e OMP_NUM_THREADS="$THREADS" \
  -e MKL_NUM_THREADS="$THREADS" \
  -e OPENBLAS_NUM_THREADS="$THREADS" \
  -v "$ROOT/data/model-cache:/models" \
  --entrypoint python \
  "$IMAGE" \
  /work/server.py
