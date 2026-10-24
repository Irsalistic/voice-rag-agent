from app.retrieval.embeddings import HashingEmbedder
from app.retrieval.hits import Hit
from app.retrieval.hybrid import reciprocal_rank_fusion
from app.retrieval.rerank import rerank
from app.textutil import content_tokens


def _hit(hit_id: str, text: str, score: float) -> Hit:
    return Hit(
        id=hit_id,
        text=text,
        score=score,
        source=f"{hit_id}.md",
        document_id=hit_id,
        page=None,
        ordinal=0,
    )


def test_hashing_embedder_prefers_shared_words():
    embedder = HashingEmbedder()
    query = embedder.embed_query("Oakline sofa hardwood")
    sofa = embedder.embed_query("The Oakline sofa is kiln-dried hardwood and linen.")
    other = embedder.embed_query("Refunds are issued within 5 business days.")
    assert _cosine(query, sofa) > _cosine(query, other)


def test_reciprocal_rank_fusion_rewards_agreement():
    left = [_hit("a", "alpha", 0.2), _hit("b", "beta", 0.1)]
    right = [_hit("b", "beta", 9), _hit("c", "gamma", 1)]
    fused = reciprocal_rank_fusion([left, right])
    assert fused[0].id == "b"
    assert len({hit.id for hit in fused}) == 3


def test_rerank_prefers_term_overlap():
    hits = [
        _hit("noise", "Saturday support is open in the afternoon.", 0.9),
        _hit("lamp", "Wipe the frosted glass lamp shade with a dry cloth.", 0.1),
    ]
    ranked = rerank("wipe the lamp shade", hits, top_n=1)
    assert ranked[0].id == "lamp"


def test_content_tokens_drop_question_words():
    assert "what" not in content_tokens("What does expedited shipping cost?")
    assert "expedited" in content_tokens("What does expedited shipping cost?")


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))
