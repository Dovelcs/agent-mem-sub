#!/bin/sh
set -eu

ROOT="${AGENT_MEMORY_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
IMAGE="${AGENT_MEMORY_EMBED_IMAGE:-agent-memory-embedder:local}"
DB="${1:-$ROOT/agent.db}"
OUT_DIR="${2:-$ROOT/data/vectors}"
MODEL="${AGENT_MEMORY_EMBED_MODEL:-intfloat/multilingual-e5-small}"

DB="$(readlink -f "$DB")"
DB_DIR="$(dirname "$DB")"
DB_NAME="$(basename "$DB")"
OUT_DIR="$(mkdir -p "$OUT_DIR" && cd "$OUT_DIR" && pwd)"
mkdir -p "$OUT_DIR" "$ROOT/data/model-cache"
docker build -t "$IMAGE" "$ROOT/embedding-worker"
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -v "$DB_DIR:/data" \
  -v "$OUT_DIR:/out" \
  -v "$ROOT/data/model-cache:/models" \
  "$IMAGE" \
  --db "/data/$DB_NAME" \
  --output /out/agent_vectors.jsonl \
  --model "$MODEL"
