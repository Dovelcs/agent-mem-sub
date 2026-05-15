# Remote Client Setup

This guide is for another machine that only needs to access the existing
OpenWrt-hosted agent-memory service. The client does not need to run SQLite,
Qdrant, bge-m3, or the reranker locally.

## Network Model

The live memory API is:

```text
http://100.106.225.53:18088
```

Access is expected through Tailscale. The OpenWrt host listens on `0.0.0.0:18088`,
while nft limits access to loopback and `tailscale0`. Do not expose this service
directly to the public internet.

Check connectivity from the client:

```sh
export AGENT_MEMORY_URL=http://100.106.225.53:18088
curl -s "$AGENT_MEMORY_URL/health"
```

Expected health fields:

- `ok: true`
- `qdrant.collection: agent_chunks_bge_m3_hybrid`
- `qdrant.hybrid: true`
- `embedding.available: true`
- `vector_profiles.bge_m3.default: true`

## Install The Client Helper

Clone this repository on the client:

```sh
git clone git@github.com:Dovelcs/agent-mem-sub.git
cd agent-mem-sub
```

Run the helper directly:

```sh
export AGENT_MEMORY_URL=http://100.106.225.53:18088
python3 skills/openwrt-agent-memory/scripts/agent_memory.py health
```

Optional convenience symlink for Codex-style workflows:

```sh
mkdir -p ~/.codex/skills ~/.codex/bin
ln -sfn "$PWD/skills/openwrt-agent-memory" ~/.codex/skills/openwrt-agent-memory
cat > ~/.codex/bin/agent_memory.py <<'PY'
#!/usr/bin/env python3
from __future__ import annotations

import runpy
from pathlib import Path

SCRIPT = Path.home() / ".codex/skills/openwrt-agent-memory/scripts/agent_memory.py"

if __name__ == "__main__":
    runpy.run_path(str(SCRIPT), run_name="__main__")
PY
chmod +x ~/.codex/bin/agent_memory.py
```

## Recall Workflow

Use `search-candidates` first. It calls `/recall`, uses Qdrant bge-m3 hybrid as
the primary candidate source, applies the reranker, and returns lightweight
candidate cards for agent selection.

```sh
export AGENT_MEMORY_URL=http://100.106.225.53:18088
python3 ~/.codex/bin/agent_memory.py search-candidates \
  "rk3562 是否支持 ab 分区以及支持最低硬盘大小" \
  --limit 5
```

The output uses refs:

```text
memory:326 | project_fact | 0.9888 | project_fact: ...
doc_chunk:28639 | official_doc | 0.5436 | official_doc: ...
```

Expand selected memory refs:

```sh
python3 ~/.codex/bin/agent_memory.py get-memory memory:326
```

Expand selected document chunk refs:

```sh
curl -s "$AGENT_MEMORY_URL/docs/chunk/get" \
  -H 'Content-Type: application/json' \
  -d '{"ref":"doc_chunk:28639"}'
```

The server also accepts integer forms:

```json
{"id": 28639}
{"ids": [28639]}
{"refs": ["doc_chunk:28639"]}
```

## Direct API Contract

Health:

```sh
curl -s "$AGENT_MEMORY_URL/health"
```

Candidate recall:

```sh
curl -s "$AGENT_MEMORY_URL/recall" \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "vps2 下 sub2api 的容器",
    "limit_candidates": 5,
    "include_candidate_context": false,
    "auto_include_memories": false,
    "auto_include_docs": false
  }'
```

Important response fields:

- `recall_candidates`: unified candidates for both `memory` and `doc_chunk`.
- `ref`: stable expansion handle such as `memory:181` or `doc_chunk:28639`.
- `label`, `tags`, `summary`: deterministic candidate card fields.
- `rerank_score`: bge-reranker-v2-m3 relevance score.
- `items`: empty by default unless automatic inclusion is explicitly enabled.

Full expansion:

```sh
curl -s "$AGENT_MEMORY_URL/memory/get" \
  -H 'Content-Type: application/json' \
  -d '{"ref":"memory:181"}'

curl -s "$AGENT_MEMORY_URL/docs/chunk/get" \
  -H 'Content-Type: application/json' \
  -d '{"ref":"doc_chunk:28639"}'
```

## Write Memories From A Client

Stable facts can be written remotely. SQLite is updated first; bge-m3 vector
sync is queued by default.

```sh
python3 ~/.codex/bin/agent_memory.py write-fact \
  "Sub2API is deployed on vps2 under /opt/sub2api." \
  --type verified_route \
  --scope vps2 \
  --title "vps2 Sub2API deployment path" \
  --tag vps2 \
  --tag sub2api \
  --vector async
```

Use `write-found` for verified path/function/route lookup results:

```sh
python3 ~/.codex/bin/agent_memory.py write-found \
  "RK3562 Android A/B parameter generation uses device/rockchip/common/build/rockchip/RebuildParameter.mk." \
  --kind rg \
  --path device/rockchip/common/build/rockchip/RebuildParameter.mk \
  --scope rk3562-android \
  --tag rk3562 \
  --tag ab
```

Do not store raw logs, full command output, generated build trees, downloaded
archives, or secrets. Store the verified conclusion, route, path, and reuse
condition.

## Optional Codex Hook

The hook is reminder-oriented. It injects mandatory user preferences once per
session and tells Codex when it should run candidate recall; it does not dump
large memory content into every prompt.

Example `~/.codex/config.toml`:

```toml
[features]
codex_hooks = true

[[hooks.UserPromptSubmit]]
[[hooks.UserPromptSubmit.hooks]]
type = "command"
command = "AGENT_MEMORY_URL=http://100.106.225.53:18088 python3 /path/to/agent-mem-sub/agent-memory/app/recall_hook.py"
timeout = 2
statusMessage = "Checking memory"
```

For hands-on work, Codex should still run:

```sh
python3 ~/.codex/bin/agent_memory.py memory-decision "<next step>"
python3 ~/.codex/bin/agent_memory.py search-candidates "<query>" --limit 15
```

Then expand only selected refs with `get-memory` or `/docs/chunk/get`.

## Troubleshooting

If health fails:

- Confirm the client is connected to the same Tailscale network.
- Confirm `AGENT_MEMORY_URL=http://100.106.225.53:18088`.
- Try `curl -v "$AGENT_MEMORY_URL/health"`.

If recall is slow or empty:

- Check `/health` first.
- Confirm `qdrant.hybrid=true` and `embedding.available=true`.
- Retry with a more specific query including project, platform, host, path, or
  symbol names.
- If Qdrant or embedding is unavailable, the service should still have SQLite
  FTS fallback, but semantic recall quality will be lower.
