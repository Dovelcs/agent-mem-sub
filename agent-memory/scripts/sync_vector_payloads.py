#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import requests

ROOT = Path(os.environ.get("AGENT_MEMORY_ROOT", "/opt/agent-memory"))
sys.path.insert(0, str(ROOT / "app"))

from db import CONFIG, connect, init_db  # noqa: E402
from qdrant_client import QdrantLite  # noqa: E402
from rerank import evidence_level  # noqa: E402


def batched(items: list[int], size: int = 256):
    for idx in range(0, len(items), size):
        yield items[idx : idx + size]


def set_payload(client: QdrantLite, point_ids: list[int], payload: dict[str, Any]) -> int:
    updated = 0
    for batch in batched(point_ids):
        response = requests.post(
            f"{client.url}/collections/{client.collection}/points/payload",
            json={"points": batch, "payload": payload},
            timeout=max(client.timeout, 2.0),
        )
        response.raise_for_status()
        updated += len(batch)
    return updated


def main() -> int:
    init_db()
    client = QdrantLite(CONFIG.get("qdrant", {}))
    groups: dict[tuple[str, str, str], list[int]] = defaultdict(list)
    with connect() as conn:
        for row in conn.execute("SELECT id, source_kind, evidence_level FROM document_chunks").fetchall():
            groups[("doc_chunk", row["source_kind"] or "generic_doc", row["evidence_level"] or "inferred")].append(int(row["id"]))
        memories = conn.execute("SELECT id, title, content, tags, updated_at FROM memories WHERE status IN ('active','pinned')").fetchall()
        for row in memories:
            item = {**dict(row), "source_type": "memory"}
            groups[("memory", "memory", evidence_level(item) or "inferred")].append(1000000000 + int(row["id"]))

    updated = 0
    for (source_type, source_kind, level), point_ids in groups.items():
        updated += set_payload(client, point_ids, {
            "source_type": source_type,
            "source_kind": source_kind,
            "evidence_level": level,
        })
    print(json.dumps({"ok": True, "points_touched": updated, "groups": len(groups)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
