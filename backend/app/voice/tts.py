from __future__ import annotations

import asyncio
import importlib.util
import logging
import shutil
import tempfile
from pathlib import Path

import httpx

from app.config import Settings

log = logging.getLogger(__name__)


class TTSProvider:
    name = "none"
    media_type = "audio/mpeg"

    async def synthesize(self, text: str) -> bytes:
        return b""


class EdgeTTS(TTSProvider):
    name = "edge"
    media_type = "audio/mpeg"

    def __init__(self, voice: str):
        self._voice = voice

    async def synthesize(self, text: str) -> bytes:
        text = text.strip()
        if not text:
            return b""
        import edge_tts

        communicate = edge_tts.Communicate(text, self._voice)
        buffer = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio" and chunk.get("data"):
                buffer.extend(chunk["data"])
        return bytes(buffer)


class OpenAITTS(TTSProvider):
    name = "openai"
    media_type = "audio/mpeg"

    def __init__(self, api_key: str, base_url: str, model: str, voice: str, timeout: float):
        self._api_key = api_key
        self._url = base_url.rstrip("/") + "/audio/speech"
        self._model = model
        self._voice = voice
        self._timeout = timeout

    async def synthesize(self, text: str) -> bytes:
        text = text.strip()
        if not text:
            return b""
        payload = {
            "model": self._model,
            "voice": self._voice,
            "input": text,
            "response_format": "mp3",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                self._url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"text to speech failed: {response.status_code} {response.text[:200]}"
            )
        return response.content


class PiperTTS(TTSProvider):
    name = "piper"
    media_type = "audio/wav"

    def __init__(self, binary: str, model: str):
        self._binary = binary
        self._model = model

    async def synthesize(self, text: str) -> bytes:
        text = text.strip()
        if not text:
            return b""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            path = handle.name
        process = await asyncio.create_subprocess_exec(
            self._binary,
            "--model",
            self._model,
            "--output_file",
            path,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _stdout, stderr = await process.communicate(text.encode())
        try:
            if process.returncode != 0:
                detail = stderr.decode("utf-8", errors="replace")[:200]
                raise RuntimeError(f"piper failed: {detail}")
            return Path(path).read_bytes()
        finally:
            Path(path).unlink(missing_ok=True)


def build_tts(settings: Settings) -> TTSProvider:
    choice = settings.tts_provider.lower().strip() or "auto"
    if choice == "auto":
        if settings.openai_api_key.strip():
            choice = "openai"
        elif importlib.util.find_spec("edge_tts"):
            choice = "edge"
        elif shutil.which(settings.piper_bin) and settings.piper_model:
            choice = "piper"
        else:
            choice = "none"
    try:
        if choice == "openai":
            if not settings.openai_api_key.strip():
                raise RuntimeError("OPENAI_API_KEY is required for openai text to speech")
            return OpenAITTS(
                settings.openai_api_key.strip(),
                settings.openai_base_url,
                settings.openai_tts_model,
                settings.openai_tts_voice,
                settings.llm_timeout_seconds,
            )
        if choice == "edge":
            return EdgeTTS(settings.edge_tts_voice)
        if choice == "piper":
            if not shutil.which(settings.piper_bin) or not settings.piper_model:
                raise RuntimeError("piper binary or PIPER_MODEL is missing")
            return PiperTTS(settings.piper_bin, settings.piper_model)
        if choice != "none":
            log.warning("Unknown text-to-speech provider %s.", choice)
    except Exception as exc:
        log.warning("Text-to-speech provider %s failed (%s).", choice, exc)
        if choice != "edge" and importlib.util.find_spec("edge_tts"):
            return EdgeTTS(settings.edge_tts_voice)
    return TTSProvider()
