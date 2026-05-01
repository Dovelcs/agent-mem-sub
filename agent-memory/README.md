# Agent Memory on OpenWrt

This is a local personal memory and document recall service for Codex and other
agents. It uses SQLite WAL + FTS5 for durable lexical recall, optional Qdrant
vectors for semantic recall, and FastAPI for local HTTP access.

## Layout

```text
/opt/agent-memory/
  agent.db
  docs/
  data/
  qdrant_storage/
  app/
  scripts/
  docker-compose.yml
  README.md
```

## Install

```sh
cd /opt/agent-memory
sh scripts/install.sh
docker-compose up -d
/etc/init.d/agent-memory enable
/etc/init.d/agent-memory restart
```

The API uses port `18088` on this OpenWrt target because `8088` is already
occupied by an existing local service. The deployed procd service listens on
`0.0.0.0:18088` so Codex can call it directly over Tailscale, while nft limits
access to `lo` and `tailscale0`. Qdrant still binds to `127.0.0.1:6333`.

## Initialize And Check

```sh
cd /opt/agent-memory
sh scripts/init_db.sh
curl -s http://127.0.0.1:18088/health
```

## Ingest Documents

Supported in v1: `md`, `txt`, `log`, `json`, `yaml`, `yml`, and `csv`.

```sh
cp your-file.md /opt/agent-memory/docs/
cd /opt/agent-memory
sh scripts/ingest.sh /opt/agent-memory/docs --project personal --tags codex,openwrt
```

Ingestion is checksum-based and incremental. Unchanged files are skipped.

PDF, docx, and OCR are not included in v1. They can be added later as offline
preprocessing steps that emit text chunks before recall.

## Upsert Memory

```sh
curl -s http://127.0.0.1:18088/memory/upsert \
  -H 'Content-Type: application/json' \
  -d '{
    "type": "note",
    "scope": "global",
    "title": "OpenWrt agent memory",
    "content": "Agent memory runs locally under /opt/agent-memory. Qdrant is optional and recall falls back to SQLite FTS5.",
    "tags": ["openwrt", "codex", "memory"],
    "importance": 0.9,
    "confidence": 0.95,
    "status": "pinned"
  }'
```

## Smart Fact Write

For facts discovered by `find`, `rg`, or `git log`, prefer one server-side
smart write request. The client sends the verified conclusion and binding
context once; OpenWrt decides whether to create, update, or skip the memory.
SQLite is written before the response and vector sync is queued by default.

```sh
curl -s http://100.106.225.53:18088/memory/write_fact \
  -H 'Content-Type: application/json' \
  -d '{
    "fact": "RK3568 R62 build entry is source build-quec.sh, then select the Yocto route.",
    "type": "project_fact",
    "scope": "rk3568-r62",
    "title": "RK3568 R62 build entrypoint",
    "cwd": "/home/donovan/samba/RK3568/RK3568_Linux6.1_R62_rkr5",
    "repo": "RK3568_Linux6.1_R62_rkr5",
    "branch": "QSM368ZP_rl",
    "tags": ["rk3568", "r62", "build-entry", "find-result"],
    "source": "codex/find-result",
    "vector": "async"
  }'
```

Responses include `action: created|updated|skipped`, `memory_id`, `vector:
queued|updated|skipped`, and `ms`.

For agent-side use, prefer the bundled thin formatter. It records the
conclusion plus cwd/repo/branch/path context without storing raw command output:

```sh
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py write-found \
  "RK3568 R62 build entry is source build-quec.sh, then select the Yocto route." \
  --kind rg \
  --path build-quec.sh \
  --scope RK3568_Linux6.1_R62_rkr5 \
  --tag build-entry
```

Batch JSONL writes use `/memory/write_facts` so the OpenWrt service still owns
dedupe and update decisions:

```jsonl
{"fact":"SDK A build entry is ./build.sh in the repo root.","kind":"find","path":"build.sh","title":"SDK A build entry"}
{"fact":"SDK A packaging helper is scripts/repack.sh for arm64 camera packages.","kind":"rg","path":"scripts/repack.sh","title":"SDK A package helper"}
```

```sh
python3 ~/.codex/skills/openwrt-agent-memory/scripts/agent_memory.py write-found-batch /tmp/facts.jsonl
```

## Recall Test

```sh
curl -s http://127.0.0.1:18088/recall \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "检查 OpenWrt 上 Codex memory 系统怎么使用",
    "cwd": "/home/donovan/samba/codex-database",
    "repo": "codex-database",
    "branch": "openwrt-agent-memory",
    "limit_memories": 5,
    "limit_docs": 3
  }'
```

## Qdrant Fallback Test

```sh
cd /opt/agent-memory
docker-compose stop qdrant
curl -s http://127.0.0.1:18088/recall \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"OpenWrt agent memory fallback", "limit_memories":5, "limit_docs":3}'
docker-compose start qdrant
```

Recall returns an empty `additionalContext` on timeout or unexpected error
instead of blocking Codex.

## Codex Hook Example

Add this to `~/.codex/config.toml` on the machine that runs Codex:

```toml
[features]
codex_hooks = true

[[hooks.UserPromptSubmit]]
[[hooks.UserPromptSubmit.hooks]]
type = "command"
command = "python3 /opt/agent-memory/app/recall.py"
timeout = 2
statusMessage = "Recalling memory"
```

The hook command reads JSON from stdin when available. It also accepts command
line arguments:

```sh
python3 /opt/agent-memory/app/recall.py "OpenWrt memory recall" --cwd /tmp --repo demo
```

## MCP Server

The MCP server is a low-overhead stdio process implemented in
`app/mcp_server.py`. It uses direct SQLite/module calls instead of going through
HTTP, so it can keep working even if the FastAPI service is not used by a
client.

Codex MCP config example:

```toml
[mcp_servers.agent-memory]
command = "/opt/agent-memory/venv/bin/python"
args = ["/opt/agent-memory/app/mcp_server.py"]
env = { PYTHONPATH = "/opt/agent-memory/app", AGENT_MEMORY_CONFIG = "/opt/agent-memory/app/config.yaml" }
startup_timeout_sec = 5
tool_timeout_sec = 30
```

Smoke test:

```sh
cd /opt/agent-memory
sh scripts/mcp-smoke.sh
```

Coverage test:

```sh
/opt/agent-memory/venv/bin/python /opt/agent-memory/scripts/mcp-coverage.py
```

Rebuild Qdrant vectors after enabling an embedding provider:

```sh
AGENT_MEMORY_ROOT=/opt/agent-memory \
  /opt/agent-memory/venv/bin/python /opt/agent-memory/scripts/rebuild_vectors.py
```

## Docker Embedding Worker

To avoid installing PyTorch or sentence-transformers on the host/OpenWrt, build
vectors in a local Docker container:

```sh
cd /home/donovan/samba/codex-database/agent-memory
sh scripts/docker-build-vectors.sh ./agent.db ./data/vectors
```

The default model is `intfloat/multilingual-e5-small`. Override it with:

```sh
AGENT_MEMORY_EMBED_MODEL=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 \
  sh scripts/docker-build-vectors.sh ./agent.db ./data/vectors
```

If Qdrant is reachable from the Docker host, import directly:

```sh
sh scripts/docker-import-vectors.sh ./data/vectors/agent_vectors.jsonl http://127.0.0.1:6333
```

On the OpenWrt deployment Qdrant is intentionally bound to `127.0.0.1`, so a
safer workflow is to generate `agent_vectors.jsonl` locally, copy it to
`/opt/agent-memory/data/vectors/`, and import from the OpenWrt side.

MCP tools:

- `health`, `stats`, `recall`
- `memory_upsert`, `memory_get`, `memory_search`, `memory_list`,
  `memory_archive`, `memory_delete`, `pinned_memories`
- `docs_ingest`, `docs_search`, `docs_list`, `doc_get`, `doc_delete`,
  `chunk_get`
- `kv_upsert`, `kv_get`, `kv_list`, `kv_delete`
- `backup`, `qdrant_status`, `qdrant_ensure_collection`

MCP resources:

- `agent-memory://health`
- `agent-memory://stats`
- `agent-memory://memories/pinned`
- `agent-memory://documents`

## API

- `GET /health`
- `POST /memory/upsert`
- `POST /memory/search`
- `POST /memory/write_fact`
- `POST /memory/write_facts`
- `POST /docs/ingest`
- `POST /docs/search`
- `POST /recall`

## Systemd Service Example

OpenWrt uses procd; `scripts/install.sh` installs `/etc/init.d/agent-memory`.
For a systemd-based Linux host, use:

```ini
[Unit]
Description=Agent Memory FastAPI
After=network-online.target

[Service]
WorkingDirectory=/opt/agent-memory/app
Environment=PYTHONPATH=/opt/agent-memory/app
Environment=AGENT_MEMORY_CONFIG=/opt/agent-memory/app/config.yaml
ExecStart=/opt/agent-memory/venv/bin/uvicorn server:app --app-dir /opt/agent-memory/app --host 127.0.0.1 --port 18088
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

## Embeddings

`app/config.yaml` can use an HTTP embedding sidecar. The OpenWrt deployment uses
`intfloat/multilingual-e5-small`, matching the existing Qdrant vectors:

```sh
cd /opt/agent-memory
docker compose up -d --build embedding
curl -s http://127.0.0.1:18089/health
/etc/init.d/agent-memory restart
```

The embedding service is bound to `127.0.0.1:18089`. If it is unavailable or
too slow, recall falls back to SQLite FTS5.

To use OpenAI embeddings, set:

```yaml
embedding:
  provider: openai
  openai_model: text-embedding-3-small
  openai_api_key_env: OPENAI_API_KEY
```

For low-resource deployments, set `embedding.allow_during_recall: false` to keep
recall FTS-only.
