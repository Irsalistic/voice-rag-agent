from __future__ import annotations

import chromadb

from app.retrieval.hits import Hit


class ChromaStore:
    def __init__(self, path: str, name: str):
        self.name = name
        self.client = chromadb.PersistentClient(path=path)
        self.col = self._open()

    def _open(self):
        return self.client.get_or_create_collection(
            name=self.name,
            metadata={"hnsw:space": "cosine"},
            embedding_function=None,
        )

    def count(self) -> int:
        return int(self.col.count())

    def reset(self) -> None:
        self.client.delete_collection(self.name)
        self.col = self._open()

    def upsert(self, chunks: list[dict], embeddings: list[list[float]]) -> None:
        if not chunks:
            return
        self.col.upsert(
            ids=[chunk["id"] for chunk in chunks],
            embeddings=embeddings,
            documents=[chunk["text"] for chunk in chunks],
            metadatas=[
                {
                    "source": chunk["source"],
                    "document_id": chunk["document_id"],
                    "page": -1 if chunk.get("page") is None else int(chunk["page"]),
                    "ordinal": int(chunk["ordinal"]),
                }
                for chunk in chunks
            ],
        )

    def delete(self, ids: list[str]) -> None:
        if ids:
            self.col.delete(ids=ids)

    def query(self, embedding: list[float], k: int) -> list[Hit]:
        count = self.count()
        if count == 0 or k <= 0:
            return []
        result = self.col.query(
            query_embeddings=[embedding],
            n_results=min(k, count),
            include=["documents", "metadatas", "distances"],
        )
        hits: list[Hit] = []
        ids = result["ids"][0]
        documents = result["documents"][0]
        metadatas = result["metadatas"][0]
        distances = result["distances"][0]
        for chunk_id, document, meta, distance in zip(
            ids, documents, metadatas, distances, strict=True
        ):
            meta = meta or {}
            page = int(meta.get("page", -1))
            hits.append(
                Hit(
                    id=chunk_id,
                    text=document or "",
                    score=max(0.0, 1.0 - float(distance)),
                    source=str(meta.get("source") or ""),
                    document_id=str(meta.get("document_id") or ""),
                    page=None if page < 0 else page,
                    ordinal=int(meta.get("ordinal") or 0),
                )
            )
        return hits
