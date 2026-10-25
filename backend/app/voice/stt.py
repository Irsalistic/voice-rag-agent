from __future__ import annotations

import asyncio
import importlib.util
import logging
import tempfile
from pathlib import Path

import httpx

from app.config import Settings

log = logging.getLogger(__name__)


class STTProvider:
    name = "none"

    async def transcribe(self, audio: bytes, mime: str) -> str:
        return ""


class OpenAISTT(STTProvider):
    name = "openai"

    def __init__(self, api_key: str, base_url: str, model: str, timeout: float):
        self._api_key = api_key
        self._url = base_url.rstrip("/") + "/audio/transcriptions"
        self._model = model
        self._timeout = timeout

    async def transcribe(self, audio: bytes, mime: str) -> str:
        if not audio:
            return ""
        extension = _extension(mime)
        files = {"file": (f"speech.{extension}", audio, mime or "application/octet-stream")}
        data = {"model": self._model}
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                self._url,
                headers={"Authorization": f"Bearer {self._api_key}"},
                files=files,
                data=data,
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"speech to text failed: {response.status_code} {response.text[:200]}"
            )
        return str(response.json().get("text") or "").strip()


class FasterWhisperSTT(STTProvider):
    name = "faster_whisper"

    def __init__(self, model_name: str):
        from faster_whisper import WhisperModel

        self._model = WhisperModel(model_name, device="cpu", compute_type="int8")

    async def transcribe(self, audio: bytes, mime: str) -> str:
        if not audio:
            return ""
        return await asyncio.to_thread(self._transcribe_file, audio, mime)

    def _transcribe_file(self, audio: bytes, mime: str) -> str:
        suffix = "." + _extension(mime)
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as handle:
            handle.write(audio)
            path = handle.name
        try:
            segments, _info = self._model.transcribe(path)
            return " ".join(segment.text.strip() for segment in segments).strip()
        finally:
            Path(path).unlink(missing_ok=True)


def build_stt(settings: Settings) -> STTProvider:
    choice = settings.stt_provider.lower().strip() or "auto"
    if choice == "auto":
        if settings.openai_api_key.strip():
            choice = "openai"
        elif importlib.util.find_spec("faster_whisper"):
            choice = "faster_whisper"
        else:
            choice = "none"
    try:
        if choice == "openai":
            if not settings.openai_api_key.strip():
                raise RuntimeError("OPENAI_API_KEY is required for openai speech to text")
            return OpenAISTT(
                settings.openai_api_key.strip(),
                settings.openai_base_url,
                settings.openai_stt_model,
                settings.llm_timeout_seconds,
            )
        if choice == "faster_whisper":
            return FasterWhisperSTT(settings.whisper_model)
        if choice != "none":
            log.warning("Unknown speech-to-text provider %s. Using the browser instead.", choice)
    except Exception as exc:
        log.warning(
            "Speech-to-text provider %s failed (%s). Using the browser instead.", choice, exc
        )
    return STTProvider()


def _extension(mime: str) -> str:
    mime = (mime or "").lower()
    if "wav" in mime:
        return "wav"
    if "mpeg" in mime or "mp3" in mime:
        return "mp3"
    if "ogg" in mime:
        return "ogg"
    if "mp4" in mime or "m4a" in mime:
        return "m4a"
    return "webm"
