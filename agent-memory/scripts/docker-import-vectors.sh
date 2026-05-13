#!/bin/sh
set -eu

ROOT="${AGENT_MEMORY_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
IMAGE="${AGENT_MEMORY_EMBED_IMAGE:-agent-memory-embedder:local}"
VECTORS="${1:-$ROOT/data/vectors/agent_vectors.jsonl}"
if [ "$#" -gt 0 ]; then shift; fi
QDRANT_URL="${1:-http://127.0.0.1:6333}"
if [ "$#" -gt 0 ]; then shift; fi
COLLECTION="${AGENT_MEMORY_QDRANT_COLLECTION:-agent_chunks_bge_m3}"

VECTORS="$(readlink -f "$VECTORS")"
docker build -t "$IMAGE" "$ROOT/embedding-worker"
docker run --rm --network host \
  --user "$(id -u):$(id -g)" \
  -v "$VECTORS:/out/agent_vectors.jsonl:ro" \
  --entrypoint python \
  "$IMAGE" \
  /work/import_vectors.py \
  --input /out/agent_vectors.jsonl \
  --url "$QDRANT_URL" \
  --collection "$COLLECTION" \
  "$@"
