#!/bin/sh
set -eu

ROOT="${AGENT_MEMORY_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
IMAGE="${AGENT_MEMORY_EMBED_IMAGE:-agent-memory-embedder:local}"
DB="${1:-$ROOT/agent.db}"
if [ "$#" -gt 0 ]; then shift; fi
OUT_DIR="${1:-$ROOT/data/vectors}"
if [ "$#" -gt 0 ]; then shift; fi
MODEL="${AGENT_MEMORY_EMBED_MODEL:-intfloat/multilingual-e5-small}"
QUERY_PREFIX="${AGENT_MEMORY_EMBED_QUERY_PREFIX:-passage: }"
THREADS="${AGENT_MEMORY_EMBED_THREADS:-4}"

DB="$(readlink -f "$DB")"
DB_DIR="$(dirname "$DB")"
DB_NAME="$(basename "$DB")"
OUT_DIR="$(mkdir -p "$OUT_DIR" && cd "$OUT_DIR" && pwd)"
mkdir -p "$OUT_DIR" "$ROOT/data/model-cache"
docker build -t "$IMAGE" "$ROOT/embedding-worker"
docker run --rm \
  --user "$(id -u):$(id -g)" \
  -e OMP_NUM_THREADS="$THREADS" \
  -e MKL_NUM_THREADS="$THREADS" \
  -e OPENBLAS_NUM_THREADS="$THREADS" \
  -v "$DB_DIR:/data" \
  -v "$OUT_DIR:/out" \
  -v "$ROOT/data/model-cache:/models" \
  "$IMAGE" \
  --db "/data/$DB_NAME" \
  --output /out/agent_vectors.jsonl \
  --model "$MODEL" \
  --query-prefix "$QUERY_PREFIX" \
  "$@"
