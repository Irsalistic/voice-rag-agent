from __future__ import annotations

import logging
from dataclasses import dataclass

from app.agent.loop import Agent
from app.agent.tools import ToolKit
from app.config import Settings
from app.db import Database
from app.ingestion.pipeline import ensure_vector_index, ingest_examples
from app.llm.base import LLMClient
from app.llm.factory import build_llm
from app.retrieval.bm25_index import BM25Index
from app.retrieval.embeddings import Embedder, build_embedder
from app.retrieval.hybrid import Retriever
from app.retrieval.store import ChromaStore
from app.seed import seed_orders
from app.voice.stt import STTProvider, build_stt
from app.voice.tts import TTSProvider, build_tts

log = logging.getLogger(__name__)


@dataclass
class Services:
    settings: Settings
    db: Database
    embedder: Embedder
    store: ChromaStore
    bm25: BM25Index
    retriever: Retriever
    llm: LLMClient
    stt: STTProvider
    tts: TTSProvider
    agent: Agent


def build_services(settings: Settings) -> Services:
    settings.data_path.mkdir(parents=True, exist_ok=True)
    settings.upload_path.mkdir(parents=True, exist_ok=True)
    db = Database(settings.db_path)
    seed_orders(db)
    embedder = build_embedder(settings)
    store = ChromaStore(str(settings.chroma_path), f"vesper_{embedder.name}_{embedder.dim}")
    bm25 = BM25Index()
    bm25.rebuild(db.list_chunks())
    ensure_vector_index(db, embedder, store)
    if settings.auto_ingest_examples:
        ingest_examples(settings, db, embedder, store, bm25)
    retriever = Retriever(embedder, store, bm25, settings)
    llm = build_llm(settings)
    stt = build_stt(settings)
    tts = build_tts(settings)
    agent = Agent(settings, db, llm, ToolKit(db, retriever))
    log.info(
        "services ready llm=%s embeddings=%s stt=%s tts=%s",
        llm.name,
        embedder.name,
        stt.name,
        tts.name,
    )
    return Services(
        settings=settings,
        db=db,
        embedder=embedder,
        store=store,
        bm25=bm25,
        retriever=retriever,
        llm=llm,
        stt=stt,
        tts=tts,
        agent=agent,
    )


def public_status(services: Services) -> dict:
    return {
        "app": services.settings.app_name,
        "llm_provider": services.llm.name,
        "llm_model": services.llm.model,
        "embedding_provider": services.embedder.name,
        "embedding_model": services.embedder.model_name,
        "stt_provider": services.stt.name,
        "tts_provider": services.tts.name,
        "tts_media_type": services.tts.media_type,
        "browser_stt_fallback": services.stt.name == "none",
    }
