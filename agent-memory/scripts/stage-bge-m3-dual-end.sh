#!/bin/sh
set -eu

ROOT="${AGENT_MEMORY_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
REMOTE="${AGENT_MEMORY_OPENWRT:-root@100.106.225.53}"
SSH_KEY="${AGENT_MEMORY_OPENWRT_KEY:-/home/donovan/.ssh/id_rsa_openwrt_agent_memory}"
MODEL_CACHE="${AGENT_MEMORY_MODEL_CACHE:-$ROOT/data/model-cache}"
REMOTE_ROOT="${AGENT_MEMORY_REMOTE_ROOT:-/opt/agent-memory}"
WORK_DIR="${AGENT_MEMORY_BGE_WORK_DIR:-$ROOT/.work/bge-m3}"
DB="${AGENT_MEMORY_DB:-$ROOT/agent.db}"

mkdir -p "$WORK_DIR"

stage_openwrt() {
  ssh -i "$SSH_KEY" -o BatchMode=yes "$REMOTE" \
    "mkdir -p '$REMOTE_ROOT/data/model-cache' '$REMOTE_ROOT/tmep/agent-memory-vector-cache/bge_m3'"
  rsync -a --delete \
    -e "ssh -i $SSH_KEY -o BatchMode=yes" \
    "$MODEL_CACHE/bge-m3" \
    "$REMOTE:$REMOTE_ROOT/data/model-cache/"
  ssh -i "$SSH_KEY" -o BatchMode=yes "$REMOTE" \
    "cd '$REMOTE_ROOT' && docker compose build bge-m3 && docker compose up -d bge-m3"
}

stage_local() {
  "$ROOT/scripts/install-local-bge-m3-embedder-service.sh"
  docker build -t "${AGENT_MEMORY_EMBED_IMAGE:-agent-memory-embedder:local}" "$ROOT/embedding-worker"
}

build_vectors() {
  AGENT_MEMORY_EMBED_MODEL=/models/bge-m3 \
  AGENT_MEMORY_EMBED_QUERY_PREFIX= \
    "$ROOT/scripts/docker-build-vectors.sh" "$DB" "$WORK_DIR/vectors" --sort-by-length
}

stage_openwrt >"$WORK_DIR/stage-openwrt.log" 2>&1 &
pid_openwrt=$!
stage_local >"$WORK_DIR/stage-local.log" 2>&1 &
pid_local=$!
build_vectors >"$WORK_DIR/build-vectors.log" 2>&1 &
pid_vectors=$!

status=0
for pid in "$pid_openwrt" "$pid_local" "$pid_vectors"; do
  if ! wait "$pid"; then
    status=1
  fi
done

printf '{"ok":%s,"work_dir":"%s","logs":["stage-openwrt.log","stage-local.log","build-vectors.log"]}\n' \
  "$([ "$status" -eq 0 ] && printf true || printf false)" "$WORK_DIR"
exit "$status"
