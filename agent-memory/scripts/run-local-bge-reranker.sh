#!/bin/sh
set -eu

ROOT="${AGENT_MEMORY_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
IMAGE="${AGENT_MEMORY_EMBED_IMAGE:-agent-memory-embedder:local}"
MODEL_CACHE="${AGENT_MEMORY_MODEL_CACHE:-$ROOT/data/model-cache}"
HOST="${AGENT_MEMORY_RERANK_HOST:-100.114.74.111}"
PORT="${AGENT_MEMORY_RERANK_PORT:-18091}"
CPUS="${AGENT_MEMORY_RERANK_CPUS:-}"
MEMORY="${AGENT_MEMORY_RERANK_MEMORY:-6g}"
THREADS="${AGENT_MEMORY_RERANK_THREADS:-$(getconf _NPROCESSORS_ONLN 2>/dev/null || nproc 2>/dev/null || echo 4)}"
CPU_ARGS=""
case "$CPUS" in
  ""|0|none|unlimited)
    ;;
  *)
    CPU_ARGS="--cpus $CPUS"
    ;;
esac

docker rm -f agent-memory-local-reranker >/dev/null 2>&1 || true
docker run -d \
  --name agent-memory-local-reranker \
  --restart unless-stopped \
  $CPU_ARGS \
  --memory "$MEMORY" \
  -p "$HOST:$PORT:18091" \
  -e EMBED_MODEL= \
  -e EMBED_PRELOAD=0 \
  -e RERANK_MODEL=/models/bge-reranker-v2-m3 \
  -e RERANK_PRELOAD=1 \
  -e RERANK_BATCH_SIZE="${AGENT_MEMORY_RERANK_BATCH_SIZE:-8}" \
  -e RERANK_MAX_LENGTH="${AGENT_MEMORY_RERANK_MAX_LENGTH:-512}" \
  -e PORT=18091 \
  -e OMP_NUM_THREADS="$THREADS" \
  -e MKL_NUM_THREADS="$THREADS" \
  -e OPENBLAS_NUM_THREADS="$THREADS" \
  -e HF_HOME=/models/huggingface \
  -e TRANSFORMERS_CACHE=/models/huggingface \
  -e SENTENCE_TRANSFORMERS_HOME=/models/sentence-transformers \
  -v "$MODEL_CACHE:/models:ro" \
  --entrypoint python \
  "$IMAGE" /work/server.py
