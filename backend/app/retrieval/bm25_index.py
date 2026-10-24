from __future__ import annotations

from rank_bm25 import BM25Okapi

from app.retrieval.hits import Hit
from app.textutil import content_tokens


class BM25Index:
    def __init__(self):
        self._rows: list[dict] = []
        self._bm25: BM25Okapi | None = None

    def rebuild(self, chunks: list[dict]) -> None:
        self._rows = list(chunks)
        if not self._rows:
            self._bm25 = None
            return
        tokenized = [content_tokens(row["text"]) or ["empty"] for row in self._rows]
        self._bm25 = BM25Okapi(tokenized)

    def search(self, query: str, k: int) -> list[Hit]:
        if self._bm25 is None or k <= 0:
            return []
        tokens = content_tokens(query)
        if not tokens:
            return []
        scores = self._bm25.get_scores(tokens)
        order = sorted(range(len(scores)), key=lambda index: scores[index], reverse=True)
        hits: list[Hit] = []
        for index in order:
            score = float(scores[index])
            if score <= 0 or len(hits) >= k:
                break
            row = self._rows[index]
            page = row.get("page")
            hits.append(
                Hit(
                    id=row["id"],
                    text=row["text"],
                    score=score,
                    source=row["source"],
                    document_id=row["document_id"],
                    page=None if page is None else int(page),
                    ordinal=int(row["ordinal"]),
                )
            )
        return hits
