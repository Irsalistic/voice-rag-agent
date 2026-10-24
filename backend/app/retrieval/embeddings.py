from __future__ import annotations

import hashlib
import importlib.util
import logging
import math
import os
from pathlib import Path

import httpx

from app.config import Settings
from app.textutil import tokenize

log = logging.getLogger(__name__)


class Embedder:
    name = "base"
    model_name = "base"
    dim = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError

    def embed_query(self, text: str) -> list[float]:
        raise NotImplementedError


class HashingEmbedder(Embedder):
    """Bag-of-words feature hashing. Stable offline baseline, no model download."""

    name = "hashing"
    model_name = "feature-hashing"

    def __init__(self, dim: int = 384):
        self.dim = dim

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        tokens = tokenize(text)
        vector = [0.0] * self.dim
        features = list(tokens)
        features.extend(f"{left}_{right}" for left, right in zip(tokens, tokens[1:], strict=False))
        for feature in features:
            digest = hashlib.blake2b(feature.encode(), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "little") % self.dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class FastEmbedder(Embedder):
    name = "fastembed"

    def __init__(self, model_name: str, cache_dir: str):
        from fastembed import TextEmbedding

        self.model_name = model_name
        self.model = TextEmbedding(model_name=model_name, cache_dir=cache_dir, threads=2)
        self.dim = int(self.model.embedding_size)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return [_as_list(vector) for vector in self.model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        vector = next(iter(self.model.query_embed([text])))
        return _as_list(vector)


class OpenAIEmbedder(Embedder):
    name = "openai"

    def __init__(self, api_key: str, base_url: str, model: str, dim: int, timeout: float):
        self.model_name = model
        self.dim = dim
        self._api_key = api_key
        self._url = base_url.rstrip("/") + "/embeddings"
        self._timeout = timeout

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        vectors: list[list[float]] = []
        for start in range(0, len(texts), 64):
            vectors.extend(self._embed(texts[start : start + 64]))
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]

    def _embed(self, texts: list[str]) -> list[list[float]]:
        response = httpx.post(
            self._url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self.model_name, "input": texts},
            timeout=self._timeout,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"openai embeddings failed: {response.status_code} {response.text[:200]}"
            )
        data = response.json()["data"]
        data.sort(key=lambda item: item["index"])
        return [item["embedding"] for item in data]


def _as_list(vector) -> list[float]:
    return [float(value) for value in vector]


def _fastembed_available() -> bool:
    return importlib.util.find_spec("fastembed") is not None


def build_embedder(settings: Settings) -> Embedder:
    choice = settings.embedding_provider.lower().strip()
    if choice == "auto":
        if _fastembed_available():
            choice = "fastembed"
        elif settings.openai_api_key.strip():
            choice = "openai"
        else:
            choice = "hashing"
    try:
        if choice == "hashing":
            return HashingEmbedder()
        if choice == "fastembed":
            cache_dir = os.environ.get("FASTEMBED_CACHE_PATH") or str(settings.model_cache_path)
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            return FastEmbedder(settings.embedding_model, cache_dir)
        if choice == "openai":
            if not settings.openai_api_key.strip():
                raise RuntimeError("OPENAI_API_KEY is required for openai embeddings")
            return OpenAIEmbedder(
                settings.openai_api_key.strip(),
                settings.openai_base_url,
                settings.openai_embedding_model,
                settings.openai_embedding_dim,
                settings.llm_timeout_seconds,
            )
        raise RuntimeError(f"Unknown embedding provider: {choice}")
    except Exception as exc:
        if choice == "hashing":
            raise
        log.warning("Embedding provider %s failed (%s). Using hashing embeddings.", choice, exc)
        return HashingEmbedder()
