from __future__ import annotations

import logging
import re
from collections.abc import Awaitable, Callable

log = logging.getLogger(__name__)

SENTENCE_RE = re.compile(r"\s*(.+?[.!?])(?:\s+|$)")


def take_sentences(buffer: str) -> tuple[list[str], str]:
    sentences: list[str] = []
    while buffer:
        match = SENTENCE_RE.match(buffer)
        if not match:
            break
        sentence = match.group(1).strip()
        if sentence:
            sentences.append(sentence)
        buffer = buffer[match.end() :]
    return sentences, buffer


def clamp_pieces(sentences: list[str], limit: int = 400) -> list[str]:
    pieces: list[str] = []
    for sentence in sentences:
        text = sentence.strip()
        while len(text) > limit:
            cut = text.rfind(" ", 0, limit)
            if cut < limit // 2:
                cut = limit
            pieces.append(text[:cut].strip())
            text = text[cut:].strip()
        if text:
            pieces.append(text)
    return pieces


async def speak_sentences(sentences, tts, cancel, send_audio: Callable[[bytes], Awaitable[None]]) -> str:
    for sentence in clamp_pieces(sentences):
        if cancel.is_set():
            return "interrupted"
        try:
            audio = await tts.synthesize(sentence)
        except Exception:
            log.warning("text to speech failed", exc_info=True)
            return "error"
        if cancel.is_set():
            return "interrupted"
        if audio:
            await send_audio(audio)
    return "done"
