from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
from pathlib import Path
from typing import Any

from db import CONFIG, connect, init_db, to_json_text
from embedding import Embedder
from qdrant_client import QdrantLite
from rerank import evidence_level as infer_evidence_level
from rerank import source_kind as infer_source_kind
from vector_sync import delete_document_vectors


SUPPORTED = set(CONFIG.get("ingest", {}).get("supported_extensions", [".md", ".txt", ".log", ".json", ".yaml", ".yml", ".csv"]))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_document(path: Path) -> str:
    raw = path.read_bytes()
    text = raw.decode("utf-8", errors="replace")
    if path.suffix.lower() == ".json":
        try:
            return json.dumps(json.loads(text), ensure_ascii=False, indent=2)
        except Exception:
            return text
    if path.suffix.lower() == ".csv":
        try:
            rows = list(csv.reader(text.splitlines()))
            return "\n".join(", ".join(cell.strip() for cell in row) for row in rows)
        except Exception:
            return text
    return text


def title_from_text(path: Path, text: str) -> str:
    for line in text.splitlines()[:40]:
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            return line.lstrip("#").strip()[:180]
        return line[:180]
    return path.name


def chunk_text(path: str, text: str, max_chars: int, overlap: int) -> list[dict[str, str]]:
    chunks: list[dict[str, str]] = []
    heading = ""
    current: list[str] = []
    current_len = 0

    def flush() -> None:
        nonlocal current, current_len
        content = "\n".join(current).strip()
        if content:
            chunks.append({"heading": heading, "content": content})
        if overlap > 0 and content:
            tail = content[-overlap:]
            current = [tail]
            current_len = len(tail)
        else:
            current = []
            current_len = 0

    for line in text.splitlines():
        if re.match(r"^\s{0,3}#{1,6}\s+", line):
            if current_len >= max_chars // 3:
                flush()
            heading = line.lstrip("#").strip()
        if current_len + len(line) + 1 > max_chars and current:
            flush()
        current.append(line)
        current_len += len(line) + 1
    flush()
    if not chunks and text.strip():
        chunks.append({"heading": Path(path).name, "content": text[:max_chars]})
    return chunks


def upsert_document(path: Path, root: Path, metadata: dict[str, Any]) -> dict[str, Any]:
    checksum = sha256_file(path)
    rel_path = str(path.resolve())
    text = read_document(path)
    title = metadata.get("title") or title_from_text(path, text)
    doc_type = path.suffix.lower().lstrip(".")
    tags = metadata.get("tags", [])
    project = metadata.get("project", "")
    platform = metadata.get("platform", "")
    customer = metadata.get("customer", "")
    max_chars = int(CONFIG.get("ingest", {}).get("chunk_chars", 1200))
    overlap = int(CONFIG.get("ingest", {}).get("chunk_overlap", 160))

    with connect() as conn:
        existing = conn.execute("SELECT id, checksum FROM documents WHERE path = ?", (rel_path,)).fetchone()
        if existing and existing["checksum"] == checksum:
            return {"path": rel_path, "status": "unchanged", "document_id": existing["id"], "chunks": 0}
        if existing:
            document_id = int(existing["id"])
            delete_document_vectors(document_id)
            conn.execute(
                """
                UPDATE documents
                SET title=?, doc_type=?, project=?, platform=?, customer=?, tags=?,
                    checksum=?, updated_at=datetime('now')
                WHERE id=?
                """,
                (title, doc_type, project, platform, customer, to_json_text(tags), checksum, document_id),
            )
            conn.execute("DELETE FROM document_chunks WHERE document_id = ?", (document_id,))
        else:
            cur = conn.execute(
                """
                INSERT INTO documents(path, title, doc_type, project, platform, customer, tags, checksum)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (rel_path, title, doc_type, project, platform, customer, to_json_text(tags), checksum),
            )
            document_id = int(cur.lastrowid)

        chunks = chunk_text(rel_path, text, max_chars, overlap)
        inserted: list[dict[str, Any]] = []
        for idx, chunk in enumerate(chunks):
            classification_item = {
                "title": title,
                "heading": chunk["heading"],
                "content": chunk["content"],
                "path": rel_path,
                "project": project,
                "platform": platform,
                "customer": customer,
                "tags": tags,
            }
            source_kind = infer_source_kind(classification_item) or "generic_doc"
            evidence_level = infer_evidence_level({**classification_item, "source_kind": source_kind}) or "inferred"
            cur = conn.execute(
                """
                INSERT INTO document_chunks(document_id, chunk_index, heading, content, path, tags, source_kind, evidence_level)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (document_id, idx, chunk["heading"], chunk["content"], rel_path, to_json_text(tags), source_kind, evidence_level),
            )
            inserted.append({
                "id": int(cur.lastrowid),
                "document_id": document_id,
                "chunk_index": idx,
                "heading": chunk["heading"],
                "content": chunk["content"],
                "path": rel_path,
                "title": title,
                "project": project,
                "platform": platform,
                "customer": customer,
                "tags": tags,
                "source_kind": source_kind,
                "evidence_level": evidence_level,
            })

    upsert_vectors(inserted)
    return {"path": rel_path, "status": "updated", "document_id": document_id, "chunks": len(inserted)}


def upsert_vectors(chunks: list[dict[str, Any]]) -> None:
    embedder = Embedder(CONFIG.get("embedding", {}))
    if not embedder.available():
        return
    qdrant = QdrantLite(CONFIG.get("qdrant", {}))
    points = []
    vector_size = None
    for chunk in chunks:
        vector = embedder.embed(f"{chunk.get('heading','')}\n{chunk.get('content','')}")
        if not vector:
            continue
        vector_size = len(vector)
        points.append({
            "id": int(chunk["id"]),
            "vector": vector,
            "payload": {
                "source_type": "doc_chunk",
                "item_id": int(chunk["id"]),
                "document_id": int(chunk["document_id"]),
                "path": chunk.get("path", ""),
                "title": chunk.get("title", ""),
                "heading": chunk.get("heading", ""),
                "project": chunk.get("project", ""),
                "platform": chunk.get("platform", ""),
                "customer": chunk.get("customer", ""),
                "tags": chunk.get("tags", []),
                "source_kind": chunk.get("source_kind", ""),
                "evidence_level": chunk.get("evidence_level", ""),
                "updated_at": "",
            },
        })
    if points:
        qdrant.ensure_collection(vector_size=vector_size)
        qdrant.upsert(points)


def ingest_path(docs_path: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    init_db()
    root = Path(docs_path).resolve()
    metadata = metadata or {}
    results = []
    if not root.exists():
        return {"ok": False, "error": f"docs path not found: {root}", "results": []}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED:
            continue
        try:
            results.append(upsert_document(path, root, metadata))
        except Exception as exc:
            results.append({"path": str(path), "status": "error", "error": str(exc)})
    return {
        "ok": True,
        "docs_path": str(root),
        "updated": sum(1 for r in results if r.get("status") == "updated"),
        "unchanged": sum(1 for r in results if r.get("status") == "unchanged"),
        "errors": sum(1 for r in results if r.get("status") == "error"),
        "results": results,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("docs_path", nargs="?", default=CONFIG.get("ingest", {}).get("docs_path", "/opt/agent-memory/docs"))
    parser.add_argument("--project", default="")
    parser.add_argument("--platform", default="")
    parser.add_argument("--customer", default="")
    parser.add_argument("--tags", default="")
    args = parser.parse_args()
    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    result = ingest_path(args.docs_path, {
        "project": args.project,
        "platform": args.platform,
        "customer": args.customer,
        "tags": tags,
    })
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
