from __future__ import annotations

from typing import Any

import requests


class QdrantLite:
    def __init__(self, config: dict[str, Any]):
        self.enabled = bool(config.get("enabled", True))
        self.url = str(config.get("url", "http://127.0.0.1:6333")).rstrip("/")
        self.collection = str(config.get("collection", "agent_chunks_bge_m3_hybrid"))
        self.timeout = float(config.get("timeout_seconds", 0.5))
        self.vector_size = int(config.get("vector_size", 384))
        self.hybrid = bool(config.get("hybrid", False))
        self.dense_vector_name = str(config.get("dense_vector_name", "dense"))
        self.sparse_vector_name = str(config.get("sparse_vector_name", "sparse"))

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
                "hybrid": self.hybrid,
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
                if self.hybrid:
                    collection_config: dict[str, Any] = {
                        "vectors": {self.dense_vector_name: {"size": size, "distance": "Cosine"}},
                        "sparse_vectors": {self.sparse_vector_name: {}},
                        "on_disk_payload": True,
                    }
                else:
                    collection_config = {"vectors": {"size": size, "distance": "Cosine"}}
                requests.put(
                    f"{self.url}/collections/{self.collection}",
                    json=collection_config,
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

    def _dense_from_vector(self, vector: Any) -> list[float]:
        if isinstance(vector, dict):
            return [float(value) for value in vector.get("vector") or vector.get(self.dense_vector_name) or []]
        return [float(value) for value in vector or []]

    def _sparse_from_vector(self, vector: Any) -> dict[str, list[int] | list[float]] | None:
        sparse = vector.get("sparse") if isinstance(vector, dict) else None
        if not isinstance(sparse, dict):
            return None
        indices = [int(value) for value in sparse.get("indices") or []]
        values = [float(value) for value in sparse.get("values") or []]
        if not indices or len(indices) != len(values):
            return None
        return {"indices": indices, "values": values}

    def _point_for_upsert(self, point: dict[str, Any]) -> dict[str, Any]:
        if not self.hybrid:
            return point
        formatted = dict(point)
        vector = point.get("vector")
        dense = self._dense_from_vector(vector)
        sparse = self._sparse_from_vector(vector)
        named: dict[str, Any] = {self.dense_vector_name: dense}
        if sparse:
            named[self.sparse_vector_name] = sparse
        formatted["vector"] = named
        return formatted

    def upsert(self, points: list[dict[str, Any]]) -> None:
        if not self.enabled or not points:
            return
        try:
            requests.put(
                f"{self.url}/collections/{self.collection}/points",
                json={"points": [self._point_for_upsert(point) for point in points]},
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

    def _filter(self, source_type: str | None = None) -> dict[str, Any] | None:
        if not source_type:
            return None
        return {"must": [{"key": "source_type", "match": {"value": source_type}}]}

    def search(self, vector: Any, limit: int = 20, source_type: str | None = None) -> list[dict[str, Any]]:
        if not self.enabled or not vector:
            return []
        dense = self._dense_from_vector(vector)
        if not dense:
            return []
        query_filter = self._filter(source_type)
        if self.hybrid:
            sparse = self._sparse_from_vector(vector)
            if sparse:
                payload: dict[str, Any] = {
                    "prefetch": [
                        {"query": dense, "using": self.dense_vector_name, "limit": max(limit * 4, limit)},
                        {"query": sparse, "using": self.sparse_vector_name, "limit": max(limit * 4, limit)},
                    ],
                    "query": {"fusion": "rrf"},
                    "limit": limit,
                    "with_payload": True,
                }
                if query_filter:
                    payload["filter"] = query_filter
                try:
                    r = requests.post(
                        f"{self.url}/collections/{self.collection}/points/query",
                        json=payload,
                        timeout=self.timeout,
                    )
                    r.raise_for_status()
                    return r.json().get("result", {}).get("points") or r.json().get("result", [])
                except Exception:
                    pass
            payload = {"vector": {"name": self.dense_vector_name, "vector": dense}, "limit": limit, "with_payload": True}
        else:
            payload = {"vector": dense, "limit": limit, "with_payload": True}
        if query_filter:
            payload["filter"] = query_filter
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
