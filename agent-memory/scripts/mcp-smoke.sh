#!/bin/sh
set -eu

ROOT="${AGENT_MEMORY_ROOT:-/opt/agent-memory}"
PYTHON="$ROOT/venv/bin/python"

{
  printf '%s\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"smoke","version":"1"}}}'
  printf '%s\n' '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
  printf '%s\n' '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'
  printf '%s\n' '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"health","arguments":{}}}'
  printf '%s\n' '{"jsonrpc":"2.0","id":4,"method":"tools/call","params":{"name":"recall","arguments":{"prompt":"OpenWrt agent memory MCP recall","limit_memories":5,"limit_docs":3}}}'
  printf '%s\n' '{"jsonrpc":"2.0","id":5,"method":"resources/list","params":{}}'
} | PYTHONPATH="$ROOT/app" AGENT_MEMORY_CONFIG="$ROOT/app/config.yaml" "$PYTHON" "$ROOT/app/mcp_server.py"

