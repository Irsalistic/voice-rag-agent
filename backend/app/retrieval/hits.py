from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Hit:
    id: str
    text: str
    score: float
    source: str
    document_id: str
    page: int | None
    ordinal: int


def hit_to_passage(hit: Hit, number: int) -> dict:
    return {
        "n": number,
        "id": hit.id,
        "source": hit.source,
        "page": hit.page,
        "text": hit.text,
        "score": round(hit.score, 4),
        "document_id": hit.document_id,
        "ordinal": hit.ordinal,
    }
