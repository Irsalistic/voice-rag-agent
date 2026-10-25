from __future__ import annotations

import logging
from dataclasses import replace

from app.config import Settings
from app.retrieval.bm25_index import BM25Index
from app.retrieval.embeddings import Embedder
from app.retrieval.hits import Hit
from app.retrieval.rerank import rerank
from app.retrieval.store import ChromaStore

log = logging.getLogger(__name__)


def reciprocal_rank_fusion(rankings: list[list[Hit]], k: int = 60) -> list[Hit]:
    scores: dict[str, float] = {}
    best: dict[str, Hit] = {}
    for ranking in rankings:
        for rank, hit in enumerate(ranking):
            scores[hit.id] = scores.get(hit.id, 0.0) + 1.0 / (k + rank + 1)
            best.setdefault(hit.id, hit)
    fused = [replace(best[hit_id], score=score) for hit_id, score in scores.items()]
    fused.sort(key=lambda hit: hit.score, reverse=True)
    return fused


class Retriever:
    def __init__(self, embedder: Embedder, store: ChromaStore, bm25: BM25Index, settings: Settings):
        self.embedder = embedder
        self.store = store
        self.bm25 = bm25
        self.settings = settings

    def search(self, query: str, k: int | None = None) -> list[Hit]:
        query = query.strip()
        if not query:
            return []
        top_k = k or self.settings.retrieval_k
        try:
            vector_hits = self.store.query(self.embedder.embed_query(query), top_k)
        except Exception:
            log.exception("vector search failed")
            vector_hits = []
        lexical_hits = self.bm25.search(query, top_k)
        fused = reciprocal_rank_fusion([vector_hits, lexical_hits])
        return rerank(query, fused, self.settings.rerank_k)
