from __future__ import annotations

import asyncio

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from app.api.deps import get_services
from app.ingestion.pipeline import IngestError, delete_document, ingest_bytes
from app.textutil import squash

router = APIRouter(prefix="/documents", tags=["documents"])


@router.get("")
def list_documents(request: Request) -> dict:
    return {"documents": get_services(request).db.list_documents()}


@router.get("/{document_id}")
def get_document(document_id: str, request: Request) -> dict:
    services = get_services(request)
    document = services.db.get_document(document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found")
    document.pop("stored_name", None)
    document["chunks"] = [
        {
            "id": chunk["id"],
            "ordinal": chunk["ordinal"],
            "page": chunk["page"],
            "snippet": squash(chunk["text"], 220),
        }
        for chunk in services.db.chunks_for_document(document_id)
    ]
    return document


@router.post("")
async def upload_document(request: Request, file: UploadFile = File(...)) -> dict:
    services = get_services(request)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="That file is empty")
    if len(data) > services.settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail="File is larger than 10 MB")
    try:
        return await asyncio.to_thread(
            lambda: ingest_bytes(
                filename=file.filename or "upload.txt",
                data=data,
                content_type=file.content_type,
                settings=services.settings,
                db=services.db,
                embedder=services.embedder,
                store=services.store,
                bm25=services.bm25,
            )
        )
    except IngestError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{document_id}")
async def remove_document(document_id: str, request: Request) -> dict:
    services = get_services(request)

    def _delete() -> bool:
        return delete_document(
            document_id=document_id,
            settings=services.settings,
            db=services.db,
            store=services.store,
            bm25=services.bm25,
        )

    deleted = await asyncio.to_thread(_delete)
    if not deleted:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"deleted": document_id}
