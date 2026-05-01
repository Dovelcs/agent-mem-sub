#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(os.environ.get("AGENT_MEMORY_ROOT", "/opt/agent-memory"))


class McpClient:
    def __init__(self) -> None:
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT / "app")
        env["AGENT_MEMORY_CONFIG"] = str(ROOT / "app" / "config.yaml")
        self.proc = subprocess.Popen(
            [str(ROOT / "venv" / "bin" / "python"), str(ROOT / "app" / "mcp_server.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        self.next_id = 1

    def close(self) -> None:
        self.proc.terminate()

    def call(self, method: str, params: dict | None = None) -> dict:
        msg_id = self.next_id
        self.next_id += 1
        assert self.proc.stdin is not None
        assert self.proc.stdout is not None
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": msg_id, "method": method, "params": params or {}}, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        line = self.proc.stdout.readline()
        if not line:
            err = self.proc.stderr.read() if self.proc.stderr else ""
            raise RuntimeError(f"no MCP response: {err}")
        response = json.loads(line)
        if "error" in response:
            raise RuntimeError(response["error"])
        return response["result"]

    def notify(self, method: str, params: dict | None = None) -> None:
        assert self.proc.stdin is not None
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method, "params": params or {}}, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def tool(self, name: str, arguments: dict | None = None) -> dict:
        result = self.call("tools/call", {"name": name, "arguments": arguments or {}})
        return json.loads(result["content"][0]["text"])


def main() -> None:
    client = McpClient()
    try:
        client.call("initialize", {})
        client.notify("notifications/initialized", {})
        tools = client.call("tools/list", {})["tools"]
        print("tools_count", len(tools))
        print("tools_names", ",".join(tool["name"] for tool in tools))

        print("health_ok", client.tool("health")["ok"])
        memory = client.tool("memory_upsert", {
            "title": "mcp exhaustive smoke",
            "content": "temporary MCP CRUD smoke",
            "tags": ["mcp", "smoke"],
            "status": "active",
        })["memory"]
        print("memory_id", memory["id"])
        print("memory_get_ok", client.tool("memory_get", {"id": memory["id"]})["ok"])
        print("memory_search_count", len(client.tool("memory_search", {"query": "mcp exhaustive smoke", "limit": 5})["items"]))
        print("memory_suggest_ok", client.tool("memory_suggest", {"observation": "timeout on repeated test route", "goal": "mcp coverage", "write": False})["ok"])
        print("memory_archive_status", client.tool("memory_archive", {"id": memory["id"]})["memory"]["status"])
        print("memory_delete_count", client.tool("memory_delete", {"id": memory["id"]})["deleted"])

        print("kv_upsert_ok", client.tool("kv_upsert", {"namespace": "smoke", "key": "mcp", "value_json": {"ok": True}, "tags": ["mcp"]})["ok"])
        print("kv_get_ok", client.tool("kv_get", {"namespace": "smoke", "key": "mcp"})["ok"])
        print("kv_list_count", len(client.tool("kv_list", {"namespace": "smoke"})["items"]))
        print("kv_delete_count", client.tool("kv_delete", {"namespace": "smoke", "key": "mcp"})["deleted"])

        trunk_id = "mcp-smoke"
        print("trunk_upsert_ok", client.tool("trunk_upsert", {
            "trunk_id": trunk_id,
            "title": "MCP smoke trunk",
            "goal": "Verify trunk MCP tools",
            "status": "active",
            "milestones": [{"id": "smoke", "text": "Run smoke", "status": "pending"}],
        })["ok"])
        print("trunk_update_ok", client.tool("trunk_update", {"trunk_id": trunk_id, "progress": "MCP trunk update worked"})["ok"])
        print("trunk_get_ok", client.tool("trunk_get", {"trunk_id": trunk_id})["ok"])
        print("trunk_list_count", len(client.tool("trunk_list", {"limit": 5})["items"]))
        print("trunk_cleanup_deleted", client.tool("trunk_cleanup", {"draft_ttl_hours": 0, "inactive_ttl_hours": 999999})["deleted"])

        docs = client.tool("docs_list", {"limit": 3})["items"]
        print("docs_count", len(docs))
        print("docs_search_count", len(client.tool("docs_search", {"query": "OpenWrt agent memory", "limit": 3})["items"]))
        if docs:
            doc = client.tool("doc_get", {"id": docs[0]["id"], "chunk_limit": 1})
            print("doc_get_ok", doc["ok"], "chunks", len(doc["chunks"]))
            if doc["chunks"]:
                print("chunk_get_ok", client.tool("chunk_get", {"id": doc["chunks"][0]["id"]})["ok"])

        print("qdrant_ok", client.tool("qdrant_status").get("ok"))
        print("qdrant_ensure_ok", client.tool("qdrant_ensure_collection").get("ok"))
        print("backup_ok", client.tool("backup")["ok"])
        resource = client.call("resources/read", {"uri": "agent-memory://stats"})
        print("resource_read_ok", bool(resource["contents"][0]["text"]))
        recall = client.tool("recall", {"prompt": "OpenWrt agent memory MCP recall", "limit_memories": 5, "limit_docs": 3, "include_trace": True})
        print("recall_context", bool(recall.get("additionalContext")))
        print("recall_trace", bool(recall.get("trace")))
    finally:
        client.close()


if __name__ == "__main__":
    main()
