import json
from pathlib import Path

from app.config import ROOT


def test_retrieval_gold_set(client):
    gold_path = Path(ROOT) / "evals" / "retrieval_gold.json"
    cases = json.loads(gold_path.read_text())
    retriever = client.app.state.services.retriever
    misses = []
    for case in cases:
        hits = retriever.search(case["question"])
        top = hits[0].source if hits else None
        if top != case["expect_source"]:
            misses.append(f"{case['question']} -> {top}, expected {case['expect_source']}")
    assert not misses, "\n".join(misses)
