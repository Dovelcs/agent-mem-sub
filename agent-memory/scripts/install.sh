#!/bin/sh
set -eu

ROOT="${AGENT_MEMORY_ROOT:-/opt/agent-memory}"
VENV="$ROOT/venv"

mkdir -p "$ROOT/docs" "$ROOT/data" "$ROOT/qdrant_storage" "$ROOT/app" "$ROOT/scripts"

need_opkg=0
python3 -m venv --help >/dev/null 2>&1 || need_opkg=1
command -v pip3 >/dev/null 2>&1 || need_opkg=1

if [ "$need_opkg" = "1" ]; then
  opkg update
  opkg install python3 python3-pip python3-venv ca-bundle ca-certificates curl
fi

if ! command -v docker >/dev/null 2>&1; then
  opkg update
  opkg install dockerd docker
fi

if ! command -v docker-compose >/dev/null 2>&1 && ! docker compose version >/dev/null 2>&1; then
  opkg update
  opkg install docker-compose
fi

python3 -m venv "$VENV"
if [ -d "$ROOT/wheels" ] && ls "$ROOT"/wheels/*.whl >/dev/null 2>&1; then
  "$VENV/bin/python" -m pip install --no-index --find-links "$ROOT/wheels" fastapi uvicorn pyyaml requests
else
  "$VENV/bin/python" -m pip install fastapi uvicorn pyyaml requests
fi

"$ROOT/scripts/init_db.sh"

cat >/etc/init.d/agent-memory <<'SERVICE'
#!/bin/sh /etc/rc.common
START=95
STOP=10
USE_PROCD=1

start_service() {
  procd_open_instance
  procd_set_param command /opt/agent-memory/venv/bin/uvicorn server:app --app-dir /opt/agent-memory/app --host 127.0.0.1 --port 18088
  procd_set_param env PYTHONPATH=/opt/agent-memory/app
  procd_set_param env AGENT_MEMORY_CONFIG=/opt/agent-memory/app/config.yaml
  procd_set_param respawn 3600 5 5
  procd_set_param stdout 1
  procd_set_param stderr 1
  procd_close_instance
}
SERVICE
chmod +x /etc/init.d/agent-memory

echo "agent-memory installed at $ROOT"
echo "Start Qdrant: cd $ROOT && docker-compose up -d"
echo "Start API: /etc/init.d/agent-memory enable && /etc/init.d/agent-memory start"
