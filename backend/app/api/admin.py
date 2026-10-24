from __future__ import annotations

from fastapi import APIRouter, Query, Request

from app.api.deps import get_services
from app.state import public_status

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview")
def overview(request: Request) -> dict:
    services = get_services(request)
    return {
        "providers": public_status(services),
        "counts": services.db.counts(),
        "latency": services.db.latency_summary(),
        "tool_calls": services.db.list_tool_calls(30),
        "appointments": services.db.list_appointments(12),
        "sessions": services.db.list_sessions(30),
    }


@router.get("/tool-calls")
def tool_calls(request: Request, limit: int = Query(default=40, ge=1, le=200)) -> dict:
    return {"tool_calls": get_services(request).db.list_tool_calls(limit)}


@router.get("/latency")
def latency(request: Request) -> dict:
    return {"latency": get_services(request).db.latency_summary()}
