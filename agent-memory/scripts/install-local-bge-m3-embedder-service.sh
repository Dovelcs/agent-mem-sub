#!/bin/sh
set -eu

ROOT="${AGENT_MEMORY_ROOT:-$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)}"
SYSTEMD_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
UNIT="$SYSTEMD_DIR/agent-memory-bge-m3-embedder.service"

mkdir -p "$SYSTEMD_DIR"

cat > "$UNIT" <<EOF
[Unit]
Description=Local bge-m3 embedding fallback for OpenWrt agent-memory recall
After=docker.service network-online.target

[Service]
Type=simple
WorkingDirectory=$ROOT
Environment=AGENT_MEMORY_ROOT=$ROOT
Environment=AGENT_MEMORY_EMBED_MODEL=/models/bge-m3
Environment=AGENT_MEMORY_EMBED_PORT=18090
Environment=AGENT_MEMORY_EMBED_THREADS=4
Environment=AGENT_MEMORY_EMBED_PRELOAD=1
Environment=AGENT_MEMORY_EMBED_MEMORY=6g
Environment=AGENT_MEMORY_EMBED_CPUS=2
ExecStart=$ROOT/scripts/run-bge-m3-embedder.sh
Restart=on-failure
RestartSec=5
TimeoutStartSec=300
TimeoutStopSec=30
MemoryMax=6G
CPUQuota=200%
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7

[Install]
WantedBy=default.target
EOF

chmod +x "$ROOT/scripts/run-bge-m3-embedder.sh"
systemctl --user daemon-reload
systemctl --user disable --now agent-memory-bge-m3-embedder.service >/dev/null 2>&1 || true
printf '{"ok":true,"unit":"%s","enabled":false}\n' "$UNIT"
