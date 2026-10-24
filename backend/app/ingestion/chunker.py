from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Chunk:
    text: str
    page: int | None
    ordinal: int


def chunk_spans(text: str, chunk_size: int = 700, overlap: int = 120) -> list[tuple[int, int]]:
    """Split text into overlapping character spans.

    The window prefers to end on a newline or space so chunks stay readable.
    Overlap is clamped below the chunk size, and the start index always moves
    forward so a short tail cannot loop.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not cleaned:
        return []
    if overlap < 0:
        overlap = 0
    if overlap >= chunk_size:
        overlap = chunk_size // 5

    spans: list[tuple[int, int]] = []
    start = 0
    length = len(cleaned)
    while start < length:
        end = min(start + chunk_size, length)
        if end < length:
            break_at = cleaned.rfind("\n", start + chunk_size // 2, end)
            if break_at == -1:
                break_at = cleaned.rfind(" ", start + chunk_size // 2, end)
            if break_at != -1:
                end = break_at
        if end <= start:
            end = min(start + chunk_size, length)
        spans.append((start, end))
        if end >= length:
            break
        next_start = end - overlap
        if next_start <= start:
            next_start = start + 1
        start = next_start
    return spans


def chunk_text(text: str, chunk_size: int = 700, overlap: int = 120) -> list[str]:
    cleaned = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    chunks = []
    for start, end in chunk_spans(cleaned, chunk_size, overlap):
        piece = cleaned[start:end].strip()
        if piece:
            chunks.append(piece)
    return chunks


def chunk_pages(
    pages: list[tuple[int | None, str]],
    chunk_size: int = 700,
    overlap: int = 120,
) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page, text in pages:
        for piece in chunk_text(text, chunk_size, overlap):
            chunks.append(Chunk(text=piece, page=page, ordinal=len(chunks)))
    return chunks
