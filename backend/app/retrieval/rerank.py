from __future__ import annotations

from dataclasses import replace

from app.retrieval.hits import Hit
from app.textutil import content_tokens


def rerank(query: str, hits: list[Hit], top_n: int) -> list[Hit]:
    if not hits or top_n <= 0:
        return []
    terms = content_tokens(query)
    term_set = set(terms)
    phrase = " ".join(terms)
    raw_scores = [hit.score for hit in hits]
    low = min(raw_scores)
    high = max(raw_scores)
    span = high - low or 1.0
    ranked: list[Hit] = []
    for hit in hits:
        overlap = 0.0
        if term_set:
            overlap = len(term_set & set(content_tokens(hit.text))) / len(term_set)
        lexical = 1.0 if phrase and phrase in " ".join(content_tokens(hit.text)) else 0.0
        blended = 0.35 * ((hit.score - low) / span) + 0.50 * overlap + 0.15 * lexical
        ranked.append(replace(hit, score=blended))
    ranked.sort(key=lambda hit: hit.score, reverse=True)
    return ranked[:top_n]
