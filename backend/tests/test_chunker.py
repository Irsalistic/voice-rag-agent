from app.ingestion.chunker import chunk_spans, chunk_text


def test_blank_text_yields_no_chunks():
    assert chunk_text("  \n\t") == []


def test_short_text_is_one_chunk():
    assert chunk_text("Harbor returns", chunk_size=100, overlap=20) == ["Harbor returns"]


def test_overlap_stays_inside_the_previous_chunk():
    text = ("alpha beta " * 40).strip()
    chunks = chunk_text(text, chunk_size=80, overlap=20)
    assert len(chunks) >= 2
    assert any(right[:12] in left for left, right in zip(chunks, chunks[1:], strict=False))


def test_spans_move_forward_and_overlap():
    text = "word " * 80
    spans = chunk_spans(text, chunk_size=50, overlap=15)
    assert len(spans) >= 2
    for (start, end), (nxt, _following) in zip(spans, spans[1:], strict=False):
        assert nxt > start
        assert nxt < end


def test_overlap_larger_than_chunk_does_not_hang():
    text = "a" * 200
    spans = chunk_spans(text, chunk_size=40, overlap=400)
    assert spans[0] == (0, 40)
    assert spans[-1][1] == 200
    assert all(right > left for (left, _), (right, _) in zip(spans, spans[1:], strict=False))
