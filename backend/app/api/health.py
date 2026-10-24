from __future__ import annotations

from fastapi import APIRouter, Request

from app.state import public_status

router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health")
@router.get("/config")
def health(request: Request) -> dict:
    return {"status": "ok", **public_status(request.app.state.services)}
