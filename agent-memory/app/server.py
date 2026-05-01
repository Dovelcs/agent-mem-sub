from __future__ import annotations

import json
from typing import Any

from fastapi import FastAPI
from pydantic import BaseModel, Field

from db import (
    CONFIG,
    init_db,
    search_document_chunks,
    search_memories,
    sqlite_health,
    upsert_memory,
)
from embedding import Embedder
from ingest_docs import ingest_path
from memory_suggest import suggest_memory
from qdrant_client import QdrantLite
from recall_core import build_recall as build_recall_payload
from recall_core import select_bucketed_doc_chunks
from rerank import rerank
from trunk import cleanup_trunks, get_trunk, list_trunks, update_trunk, upsert_trunk
from vector_sync import upsert_memory_vector


app = FastAPI(title="Agent Memory", version="0.1.0")


class MemoryUpsert(BaseModel):
    id: int | None = None
    type: str = "note"
    scope: str = "global"
    title: str = ""
    content: str = ""
    tags: list[str] | str = Field(default_factory=list)
    source: str = ""
    related_doc_ids: list[int] | str = Field(default_factory=list)
    confidence: float = 0.8
    importance: float = 0.5
    expires_at: str | None = None
    status: str = "active"


class SearchRequest(BaseModel):
    query: str = ""
    limit: int = 20
    cwd: str = ""
    repo: str = ""
    branch: str = ""


class DocsIngestRequest(BaseModel):
    docs_path: str | None = None
    project: str = ""
    platform: str = ""
    customer: str = ""
    tags: list[str] | str = Field(default_factory=list)


class RecallRequest(BaseModel):
    prompt: str = ""
    cwd: str = ""
    repo: str = ""
    branch: str = ""
    trunk_id: str = ""
    conversation_id: str = ""
    session_id: str = ""
    limit_memories: int = 5
    limit_docs: int = 3
    include_trace: bool = False


class MemorySuggestRequest(BaseModel):
    observation: str = ""
    text: str = ""
    goal: str = ""
    type: str = ""
    scope: str = ""
    title: str = ""
    memory_content: str = ""
    tags: list[str] | str = Field(default_factory=list)
    source: str = ""
    repo: str = ""
    platform: str = ""
    confidence: float = 0.85
    importance: float = 0.65
    status: str = "active"
    write: bool = False
    limit: int = 5


class TrunkRequest(BaseModel):
    trunk_id: str = ""
    conversation_id: str = ""
    session_id: str = ""
    title: str = ""
    goal: str = ""
    cwd: str = ""
    repo: str = ""
    branch: str = ""
    status: str = ""
    milestones: list[Any] = Field(default_factory=list)
    progress: str = ""
    branch_note: str = ""
    milestone_id: str = ""
    milestone_status: str = ""
    ttl_hours: int = 168
    draft_ttl_hours: int = 24
    inactive_ttl_hours: int = 168
    limit: int = 20


def _as_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return [str(v) for v in parsed]
        except Exception:
            pass
        return [v.strip() for v in value.split(",") if v.strip()]
    return []


def _model_data(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _model_data_set(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump(exclude_unset=True)
    return model.dict(exclude_unset=True)


def build_recall(request: RecallRequest) -> dict[str, Any]:
    return build_recall_payload(_model_data(request))


@app.on_event("startup")
def startup() -> None:
    init_db()
    QdrantLite(CONFIG.get("qdrant", {})).ensure_collection()


@app.get("/health")
def health() -> dict[str, Any]:
    qdrant = QdrantLite(CONFIG.get("qdrant", {})).health()
    embedder = Embedder(CONFIG.get("embedding", {}))
    return {"ok": True, "sqlite": sqlite_health(), "qdrant": qdrant, "embedding": {"provider": embedder.provider, "available": embedder.available()}}


@app.post("/memory/upsert")
def memory_upsert(req: MemoryUpsert) -> dict[str, Any]:
    data = _model_data(req)
    data["tags"] = _as_list(data.get("tags"))
    memory = upsert_memory(data)
    try:
        upsert_memory_vector(memory)
    except Exception:
        pass
    return {"ok": True, "memory": memory}


@app.post("/memory/search")
def memory_search(req: SearchRequest) -> dict[str, Any]:
    return {"ok": True, "items": search_memories(req.query, req.limit)}


@app.post("/memory/suggest")
def memory_suggest(req: MemorySuggestRequest) -> dict[str, Any]:
    data = _model_data(req)
    data["tags"] = _as_list(data.get("tags"))
    return suggest_memory(data)


@app.post("/docs/ingest")
def docs_ingest(req: DocsIngestRequest) -> dict[str, Any]:
    docs_path = req.docs_path or CONFIG.get("ingest", {}).get("docs_path", "/opt/agent-memory/docs")
    return ingest_path(docs_path, {
        "project": req.project,
        "platform": req.platform,
        "customer": req.customer,
        "tags": _as_list(req.tags),
    })


@app.post("/docs/search")
def docs_search(req: SearchRequest) -> dict[str, Any]:
    candidates = search_document_chunks(req.query, max(req.limit * 4, req.limit))
    request = {"prompt": req.query, "cwd": req.cwd, "repo": req.repo, "branch": req.branch}
    ranked = rerank(candidates, request)
    return {"ok": True, "items": select_bucketed_doc_chunks(ranked, req.limit)}


@app.post("/recall")
def recall(req: RecallRequest) -> dict[str, Any]:
    try:
        return build_recall(req)
    except Exception:
        return {"additionalContext": "", "items": []}


@app.post("/trunk/upsert")
def trunk_upsert(req: TrunkRequest) -> dict[str, Any]:
    return upsert_trunk(_model_data(req))


@app.post("/trunk/get")
def trunk_get(req: TrunkRequest) -> dict[str, Any]:
    return get_trunk(_model_data(req))


@app.post("/trunk/update")
def trunk_update(req: TrunkRequest) -> dict[str, Any]:
    return update_trunk(_model_data_set(req))


@app.post("/trunk/list")
def trunk_list(req: TrunkRequest) -> dict[str, Any]:
    return list_trunks(_model_data(req))


@app.post("/trunk/cleanup")
def trunk_cleanup(req: TrunkRequest) -> dict[str, Any]:
    return cleanup_trunks(_model_data(req))
