from __future__ import annotations

from typing import Any

import requests


class QdrantLite:
    def __init__(self, config: dict[str, Any]):
        self.enabled = bool(config.get("enabled", True))
        self.url = str(config.get("url", "http://127.0.0.1:6333")).rstrip("/")
        self.collection = str(config.get("collection", "agent_chunks_bge_m3"))
        self.timeout = float(config.get("timeout_seconds", 0.5))
        self.vector_size = int(config.get("vector_size", 384))

    def health(self) -> dict[str, Any]:
        if not self.enabled:
            return {"ok": False, "enabled": False}
        try:
            r = requests.get(f"{self.url}/readyz", timeout=self.timeout)
            info = self.collection_info() if r.status_code == 200 else {}
            return {"ok": r.status_code == 200, "status_code": r.status_code, **info}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def collection_info(self) -> dict[str, Any]:
        if not self.enabled:
            return {}
        try:
            r = requests.get(f"{self.url}/collections/{self.collection}", timeout=self.timeout)
            if r.status_code == 404:
                return {"collection": self.collection, "exists": False, "points_count": 0, "indexed_vectors_count": 0}
            r.raise_for_status()
            result = r.json().get("result") or {}
            return {
                "collection": self.collection,
                "exists": True,
                "points_count": int(result.get("points_count") or 0),
                "indexed_vectors_count": int(result.get("indexed_vectors_count") or 0),
            }
        except Exception as exc:
            return {"collection": self.collection, "exists": None, "info_error": str(exc)}

    def ensure_collection(self, vector_size: int | None = None) -> None:
        if not self.enabled:
            return
        size = int(vector_size or self.vector_size)
        try:
            r = requests.get(f"{self.url}/collections/{self.collection}", timeout=self.timeout)
            if r.status_code == 404:
                requests.put(
                    f"{self.url}/collections/{self.collection}",
                    json={"vectors": {"size": size, "distance": "Cosine"}},
                    timeout=self.timeout,
                ).raise_for_status()
            for field in ("source_type", "project", "platform", "customer", "path", "tags", "source_kind", "evidence_level"):
                requests.put(
                    f"{self.url}/collections/{self.collection}/index",
                    json={"field_name": field, "field_schema": "keyword"},
                    timeout=self.timeout,
                )
        except Exception:
            return

    def upsert(self, points: list[dict[str, Any]]) -> None:
        if not self.enabled or not points:
            return
        try:
            requests.put(
                f"{self.url}/collections/{self.collection}/points",
                json={"points": points},
                timeout=max(self.timeout, 2.0),
            ).raise_for_status()
        except Exception:
            return

    def delete_points(self, point_ids: list[int]) -> None:
        if not self.enabled or not point_ids:
            return
        try:
            requests.post(
                f"{self.url}/collections/{self.collection}/points/delete",
                json={"points": [int(point_id) for point_id in point_ids]},
                timeout=max(self.timeout, 2.0),
            ).raise_for_status()
        except Exception:
            return

    def delete_by_filter(self, query_filter: dict[str, Any]) -> None:
        if not self.enabled or not query_filter:
            return
        try:
            requests.post(
                f"{self.url}/collections/{self.collection}/points/delete",
                json={"filter": query_filter},
                timeout=max(self.timeout, 2.0),
            ).raise_for_status()
        except Exception:
            return

    def search(self, vector: list[float], limit: int = 20, source_type: str | None = None) -> list[dict[str, Any]]:
        if not self.enabled or not vector:
            return []
        payload: dict[str, Any] = {"vector": vector, "limit": limit, "with_payload": True}
        if source_type:
            payload["filter"] = {"must": [{"key": "source_type", "match": {"value": source_type}}]}
        try:
            r = requests.post(
                f"{self.url}/collections/{self.collection}/points/search",
                json=payload,
                timeout=self.timeout,
            )
            r.raise_for_status()
            return r.json().get("result", [])
        except Exception:
            return []
