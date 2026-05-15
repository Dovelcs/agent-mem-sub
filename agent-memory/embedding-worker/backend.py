from __future__ import annotations

from typing import Any


def _as_float_list(values: Any) -> list[float]:
    if hasattr(values, "tolist"):
        values = values.tolist()
    return [float(value) for value in values]


def _first(values: Any) -> Any:
    if hasattr(values, "tolist"):
        values = values.tolist()
    if isinstance(values, (list, tuple)):
        return values[0] if values else []
    return values


def _sparse_to_qdrant(weights: Any) -> dict[str, list[float] | list[int]] | None:
    weights = _first(weights)
    if not isinstance(weights, dict):
        return None
    merged: dict[int, float] = {}
    for key, value in weights.items():
        try:
            index = int(key)
            score = float(value)
        except (TypeError, ValueError):
            continue
        if score == 0.0:
            continue
        merged[index] = max(score, merged.get(index, 0.0))
    if not merged:
        return None
    indices = sorted(merged)
    return {"indices": indices, "values": [merged[index] for index in indices]}


class EmbeddingBackend:
    def __init__(self, model_name: str, device: str | None = None, sparse: bool = False, max_length: int | None = None):
        self.model_name = model_name
        self.device = device
        self.sparse = sparse
        self.max_length = max_length
        self._model: Any = None
        self._backend = "flagembedding" if sparse else "sentence-transformers"

    def load(self) -> None:
        if self._model is not None:
            return
        if self.sparse:
            from FlagEmbedding import BGEM3FlagModel

            kwargs: dict[str, Any] = {"use_fp16": False}
            if self.device:
                kwargs["device"] = self.device
            self._model = BGEM3FlagModel(self.model_name, **kwargs)
            return

        from sentence_transformers import SentenceTransformer

        self._model = SentenceTransformer(self.model_name, device=self.device)

    @property
    def backend_name(self) -> str:
        return self._backend

    def encode(self, texts: list[str], batch_size: int = 32) -> list[dict[str, Any]]:
        self.load()
        if self.sparse:
            encoded = self._model.encode(
                texts,
                batch_size=batch_size,
                max_length=self.max_length,
                return_dense=True,
                return_sparse=True,
                return_colbert_vecs=False,
            )
            dense_values = encoded.get("dense_vecs")
            sparse_values = encoded.get("lexical_weights")
            if dense_values is None:
                dense_values = []
            if sparse_values is None:
                sparse_values = []
            dense_list = dense_values.tolist() if hasattr(dense_values, "tolist") else dense_values
            return [
                {"vector": _as_float_list(dense), "sparse": _sparse_to_qdrant(sparse)}
                for dense, sparse in zip(dense_list, sparse_values)
            ]

        vectors = self._model.encode(
            texts,
            batch_size=batch_size,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [{"vector": _as_float_list(vector), "sparse": None} for vector in vectors]


class RerankBackend:
    def __init__(
        self,
        model_name: str,
        device: str | None = None,
        batch_size: int = 8,
        max_length: int | None = 512,
    ):
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self.max_length = max_length
        self._model: Any = None

    def load(self) -> None:
        if self._model is not None:
            return
        from FlagEmbedding import FlagReranker

        kwargs: dict[str, Any] = {"use_fp16": False}
        if self.device:
            kwargs["device"] = self.device
        self._model = FlagReranker(self.model_name, **kwargs)

    def compute_score(self, pairs: list[list[str]]) -> list[float]:
        self.load()
        kwargs: dict[str, Any] = {"normalize": True, "batch_size": self.batch_size}
        if self.max_length:
            kwargs["max_length"] = self.max_length
        scores = self._model.compute_score(pairs, **kwargs)
        if isinstance(scores, (int, float)):
            return [float(scores)]
        if hasattr(scores, "tolist"):
            scores = scores.tolist()
        return [float(score) for score in scores]
