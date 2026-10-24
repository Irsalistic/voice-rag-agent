from __future__ import annotations

import logging
import uuid
from pathlib import Path

from app.config import Settings
from app.db import Database
from app.ingestion.chunker import chunk_pages
from app.ingestion.loaders import SUPPORTED_EXTENSIONS, load_document
from app.retrieval.bm25_index import BM25Index
from app.retrieval.embeddings import Embedder
from app.retrieval.store import ChromaStore
from app.textutil import safe_filename

log = logging.getLogger(__name__)


class IngestError(ValueError):
    pass


def ingest_bytes(
    *,
    filename: str,
    data: bytes,
    content_type: str | None,
    settings: Settings,
    db: Database,
    embedder: Embedder,
    store: ChromaStore,
    bm25: BM25Index,
) -> dict:
    display_name = Path(filename).name
    try:
        pages = load_document(display_name, data)
    except Exception as exc:
        raise IngestError(str(exc)) from exc
    pieces = chunk_pages(pages, settings.chunk_size, settings.chunk_overlap)
    if not pieces:
        raise IngestError("No text found in that file")

    document_id = uuid.uuid4().hex
    stored_name = f"{document_id}_{safe_filename(display_name)}"
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    (settings.upload_path / stored_name).write_bytes(data)
    rows = [
        {
            "id": f"{document_id}_{piece.ordinal}",
            "document_id": document_id,
            "ordinal": piece.ordinal,
            "text": piece.text,
            "source": display_name,
            "page": piece.page,
        }
        for piece in pieces
    ]
    db.add_document(document_id, display_name, content_type, len(data), len(rows), stored_name)
    db.add_chunks(rows)
    try:
        store.upsert(rows, embedder.embed_documents([row["text"] for row in rows]))
    except Exception:
        db.delete_document(document_id)
        upload = settings.upload_path / stored_name
        if upload.is_file():
            upload.unlink()
        raise
    bm25.rebuild(db.list_chunks())
    return {
        "id": document_id,
        "filename": display_name,
        "chunks": len(rows),
        "bytes": len(data),
    }


def delete_document(
    *,
    document_id: str,
    settings: Settings,
    db: Database,
    store: ChromaStore,
    bm25: BM25Index,
) -> bool:
    document = db.get_document(document_id)
    if document is None:
        return False
    chunk_ids = [chunk["id"] for chunk in db.chunks_for_document(document_id)]
    store.delete(chunk_ids)
    db.delete_document(document_id)
    bm25.rebuild(db.list_chunks())
    stored_name = document.get("stored_name")
    if stored_name:
        upload = settings.upload_path / stored_name
        if upload.is_file():
            upload.unlink()
    return True


def ingest_examples(
    settings: Settings,
    db: Database,
    embedder: Embedder,
    store: ChromaStore,
    bm25: BM25Index,
) -> int:
    folder = Path(settings.examples_dir)
    if not folder.is_dir():
        return 0
    existing = {document["filename"] for document in db.list_documents()}
    added = 0
    for path in sorted(folder.iterdir()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue
        if path.name in existing:
            continue
        try:
            ingest_bytes(
                filename=path.name,
                data=path.read_bytes(),
                content_type=None,
                settings=settings,
                db=db,
                embedder=embedder,
                store=store,
                bm25=bm25,
            )
            added += 1
        except IngestError as exc:
            log.warning("skipped example %s: %s", path.name, exc)
    if added:
        log.info("ingested %s sample document(s)", added)
    return added


def ensure_vector_index(db: Database, embedder: Embedder, store: ChromaStore) -> None:
    chunks = db.list_chunks()
    if store.count() == len(chunks):
        return
    log.info("rebuilding vector index (%s chunks)", len(chunks))
    store.reset()
    if chunks:
        store.upsert(chunks, embedder.embed_documents([chunk["text"] for chunk in chunks]))
