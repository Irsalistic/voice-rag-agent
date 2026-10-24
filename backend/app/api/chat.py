from __future__ import annotations

import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.api.deps import get_services
from app.async_iter import iterate_in_thread

log = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    session_id: str | None = None

    @field_validator("message")
    @classmethod
    def strip_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Message is empty")
        return value


def sse(event: dict) -> str:
    return f"data: {json.dumps(event, ensure_ascii=False)}\n\n"


@router.post("/sessions")
def create_session(request: Request) -> dict:
    return get_services(request).db.create_session()


@router.get("/sessions")
def list_sessions(request: Request) -> dict:
    return {"sessions": get_services(request).db.list_sessions()}


@router.get("/sessions/{session_id}")
def get_session(session_id: str, request: Request) -> dict:
    session = get_services(request).db.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    return session


@router.delete("/sessions/{session_id}")
def remove_session(session_id: str, request: Request) -> dict:
    if not get_services(request).db.delete_session(session_id):
        raise HTTPException(status_code=404, detail="Unknown session")
    return {"deleted": session_id}


@router.get("/sessions/{session_id}/messages")
def list_messages(session_id: str, request: Request) -> dict:
    services = get_services(request)
    if services.db.get_session(session_id) is None:
        raise HTTPException(status_code=404, detail="Unknown session")
    return {"messages": services.db.list_messages(session_id)}


@router.post("/chat")
async def chat(body: ChatRequest, request: Request) -> StreamingResponse:
    services = get_services(request)
    if body.session_id:
        session = services.db.get_session(body.session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="Unknown session")
        session_id = session["id"]
    else:
        session_id = services.db.create_session()["id"]

    async def events():
        yield sse({"type": "session", "session_id": session_id})
        try:
            generator = iterate_in_thread(
                lambda: services.agent.iter_turn(session_id, body.message)
            )
            async for event in generator:
                yield sse(event)
        except Exception:
            log.exception("chat failed")
            yield sse({"type": "error", "text": "The agent failed to answer."})

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
