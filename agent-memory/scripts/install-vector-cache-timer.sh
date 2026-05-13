#!/bin/sh
set -eu

ROOT="${AGENT_MEMORY_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$SYSTEMD_DIR"

cat > "$SYSTEMD_DIR/agent-memory-vector-cache-drain.service" <<EOF
[Unit]
Description=Nightly Qwen3 drain for OpenWrt agent-memory vector cache
After=network-online.target docker.service

[Service]
Type=oneshot
WorkingDirectory=$ROOT
Environment=AGENT_MEMORY_ROOT=$ROOT
Environment=AGENT_MEMORY_EMBED_MODEL=Qwen/Qwen3-Embedding-4B
Environment=AGENT_MEMORY_VECTOR_PROFILE=qwen3_4b
Environment=AGENT_MEMORY_QDRANT_COLLECTION=agent_chunks_qwen3_4b
Environment=AGENT_MEMORY_VECTOR_CACHE_BATCH_SIZE=1
Environment=AGENT_MEMORY_VECTOR_CACHE_SLEEP_SECONDS=1.0
ExecStart=$ROOT/scripts/auto-drain-openwrt-vector-cache.sh
EOF

cat > "$SYSTEMD_DIR/agent-memory-vector-cache-drain.timer" <<'EOF'
[Unit]
Description=Run OpenWrt agent-memory Qwen3 vector cache drain at 02:00

[Timer]
OnCalendar=*-*-* 02:00:00
AccuracySec=5min
Persistent=false
Unit=agent-memory-vector-cache-drain.service

[Install]
WantedBy=timers.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now agent-memory-vector-cache-drain.timer
systemctl --user list-timers agent-memory-vector-cache-drain.timer --no-pager
