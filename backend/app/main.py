from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.chat import router as chat_router
from app.api.documents import router as documents_router
from app.api.health import router as health_router
from app.api.voice import router as voice_router
from app.config import ROOT, Settings
from app.state import build_services

log = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = Settings()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        services = build_services(Settings())
        app.state.services = services
        try:
            yield
        finally:
            services.db.close()

    app = FastAPI(
        title="Vesper",
        summary="Voice AI agent with RAG and tool calling",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list(),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(health_router)
    app.include_router(documents_router, prefix="/api")
    app.include_router(chat_router, prefix="/api")
    app.include_router(voice_router, prefix="/api")
    app.include_router(admin_router, prefix="/api")

    dist = ROOT / "frontend" / "dist"
    if settings.serve_frontend and dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="ui")
    else:

        @app.get("/")
        def root() -> dict:
            return {"name": settings.app_name, "health": "/api/health", "docs": "/docs"}

    return app
