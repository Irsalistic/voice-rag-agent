from __future__ import annotations

import re
import time
from pathlib import Path

TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "of",
        "to",
        "and",
        "or",
        "for",
        "how",
        "what",
        "when",
        "where",
        "why",
        "who",
        "does",
        "do",
        "did",
        "i",
        "my",
        "me",
        "we",
        "our",
        "you",
        "your",
        "it",
        "this",
        "that",
        "with",
        "on",
        "in",
        "at",
        "from",
        "be",
        "can",
        "could",
        "would",
        "should",
        "please",
        "about",
        "into",
        "than",
        "then",
        "there",
    }
)


def elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def normalize_token(token: str) -> str:
    if len(token) > 4 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def tokenize(text: str) -> list[str]:
    return [normalize_token(token) for token in TOKEN_RE.findall(text.lower())]


def content_tokens(text: str) -> list[str]:
    return [token for token in tokenize(text) if token not in STOPWORDS]


def squash(text: str, limit: int) -> str:
    flat = re.sub(r"\s+", " ", text).strip()
    if len(flat) <= limit:
        return flat
    cut = flat[:limit].rsplit(" ", 1)[0]
    return (cut or flat[:limit]).rstrip() + "…"


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(name).name).strip("._")
    return (cleaned or "upload.txt")[:120]


def decode_text(data: bytes) -> str:
    text = data.decode("utf-8-sig", errors="replace")
    return text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
