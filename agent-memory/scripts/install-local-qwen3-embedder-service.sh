#!/bin/sh
set -eu

ROOT="${AGENT_MEMORY_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT="$SYSTEMD_DIR/agent-memory-qwen3-embedder.service"

mkdir -p "$SYSTEMD_DIR"

cat > "$UNIT" <<EOF
[Unit]
Description=Local Qwen3 4B embedding service for OpenWrt agent-memory recall
After=docker.service network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
Environment=AGENT_MEMORY_ROOT=$ROOT
Environment=AGENT_MEMORY_EMBED_MODEL=Qwen/Qwen3-Embedding-4B
Environment=AGENT_MEMORY_EMBED_PORT=18089
Environment=AGENT_MEMORY_EMBED_THREADS=16
Environment=AGENT_MEMORY_EMBED_PRELOAD=1
ExecStart=$ROOT/scripts/run-local-qwen3-embedder.sh
Restart=on-failure
RestartSec=5
TimeoutStartSec=300
TimeoutStopSec=30

[Install]
WantedBy=default.target
EOF

chmod +x "$ROOT/scripts/run-local-qwen3-embedder.sh"
systemctl --user daemon-reload
systemctl --user enable --now agent-memory-qwen3-embedder.service
systemctl --user status agent-memory-qwen3-embedder.service --no-pager
