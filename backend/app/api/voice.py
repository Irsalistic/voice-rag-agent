from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.async_iter import iterate_in_thread
from app.textutil import elapsed_ms
from app.voice.pipeline import speak_sentences, take_sentences

log = logging.getLogger(__name__)
router = APIRouter(tags=["voice"])
MAX_AUDIO_BYTES = 8 * 1024 * 1024


@router.websocket("/voice/ws")
async def voice_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    services = websocket.app.state.services
    state = {"session_id": None}
    audio = bytearray()
    mime = "audio/webm"
    cancel = asyncio.Event()
    turn_task: asyncio.Task | None = None

    def ensure_session() -> str:
        if state["session_id"] is None:
            state["session_id"] = services.db.create_session()["id"]
        return state["session_id"]

    async def start_turn(text: str) -> None:
        nonlocal turn_task
        if turn_task is not None and not turn_task.done():
            cancel.set()
            with contextlib.suppress(Exception):
                await turn_task
        cancel.clear()
        session_id = ensure_session()

        async def wrapped() -> None:
            try:
                await run_voice_turn(websocket, services, session_id, text, cancel)
            except Exception:
                log.exception("voice turn failed")
                with contextlib.suppress(Exception):
                    await websocket.send_json({"type": "error", "text": "The voice turn failed."})

        turn_task = asyncio.create_task(wrapped())

    try:
        while True:
            incoming = await websocket.receive()
            if incoming["type"] == "websocket.disconnect":
                break
            blob = incoming.get("bytes")
            if blob is not None:
                if len(audio) + len(blob) > MAX_AUDIO_BYTES:
                    audio.clear()
                    await websocket.send_json(
                        {"type": "error", "text": "That recording is too long."}
                    )
                    continue
                audio.extend(blob)
                continue
            raw = incoming.get("text")
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json(
                    {"type": "error", "text": "That message was not valid JSON."}
                )
                continue
            kind = payload.get("type")
            if kind == "start":
                requested = payload.get("session_id")
                if requested and services.db.get_session(requested):
                    state["session_id"] = requested
                elif requested:
                    await websocket.send_json({"type": "error", "text": "Unknown session."})
                    continue
                else:
                    state["session_id"] = services.db.create_session()["id"]
                await websocket.send_json(
                    {
                        "type": "ready",
                        "session_id": state["session_id"],
                        "stt_provider": services.stt.name,
                        "tts_provider": services.tts.name,
                        "tts_media_type": services.tts.media_type,
                    }
                )
            elif kind == "barge_in":
                cancel.set()
                await websocket.send_json({"type": "interrupted"})
            elif kind == "utterance_end":
                mime = payload.get("mime") or mime
                captured = bytes(audio)
                audio.clear()
                session_id = ensure_session()
                started = time.perf_counter()
                try:
                    transcript = await services.stt.transcribe(captured, mime)
                except Exception:
                    log.exception("speech to text failed")
                    await websocket.send_json(
                        {"type": "error", "text": "I couldn't transcribe that audio."}
                    )
                    continue
                services.db.add_trace(session_id, "stt", elapsed_ms(started), services.stt.name)
                if not transcript.strip():
                    await websocket.send_json(
                        {"type": "error", "text": "I didn't catch any speech."}
                    )
                    continue
                await start_turn(transcript)
            elif kind == "text":
                text = str(payload.get("text") or "").strip()
                if text:
                    await start_turn(text)
            elif kind == "stop":
                cancel.set()
                break
    except WebSocketDisconnect:
        cancel.set()
    finally:
        cancel.set()


async def run_voice_turn(
    websocket, services, session_id: str, text: str, cancel: asyncio.Event
) -> None:
    await websocket.send_json({"type": "transcript", "text": text, "final": True})
    buffer = ""
    pending_done = None
    tts_error = False
    tts_ms = 0

    async def send_audio(audio: bytes) -> None:
        await websocket.send_bytes(audio)

    async for event in iterate_in_thread(
        lambda: services.agent.iter_turn(session_id, text),
        should_stop=cancel.is_set,
    ):
        if cancel.is_set():
            await websocket.send_json({"type": "interrupted"})
            return
        if event.get("type") == "done":
            pending_done = event
            continue
        if event.get("type") == "token":
            await websocket.send_json(event)
            buffer += event.get("text") or ""
            sentences, buffer = take_sentences(buffer)
            if sentences:
                status, spent = await _speak(sentences, services, cancel, send_audio)
                tts_ms += spent
                if status == "interrupted":
                    await websocket.send_json({"type": "interrupted"})
                    return
                if status == "error":
                    tts_error = True
            continue
        await websocket.send_json(event)

    tail = buffer.strip()
    if tail and not cancel.is_set():
        status, spent = await _speak([tail], services, cancel, send_audio)
        tts_ms += spent
        if status == "interrupted":
            await websocket.send_json({"type": "interrupted"})
            return
        if status == "error":
            tts_error = True
    if tts_ms:
        services.db.add_trace(session_id, "tts", tts_ms, services.tts.name)
    if tts_error:
        await websocket.send_json(
            {
                "type": "notice",
                "text": "Voice playback is unavailable right now. The text answer is still here.",
            }
        )
    if cancel.is_set():
        await websocket.send_json({"type": "interrupted"})
        return
    if pending_done:
        await websocket.send_json(pending_done)


async def _speak(sentences, services, cancel, send_audio) -> tuple[str, int]:
    started = time.perf_counter()
    status = await speak_sentences(sentences, services.tts, cancel, send_audio)
    return status, elapsed_ms(started)
