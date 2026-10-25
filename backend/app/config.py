from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime settings loaded from the environment and an optional .env file."""

    model_config = SettingsConfigDict(
        env_file=str(ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Vesper"
    environment: str = "development"
    data_dir: str = str(ROOT / "data")
    examples_dir: str = str(ROOT / "examples" / "docs")
    auto_ingest_examples: bool = True
    serve_frontend: bool = True
    cors_origins: str = (
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:8080,http://127.0.0.1:8080,"
        "http://localhost:8000,http://127.0.0.1:8000"
    )

    llm_provider: str = "auto"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_model: str = "llama-3.3-70b-versatile"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2"
    llm_temperature: float = 0.2
    llm_timeout_seconds: float = 60.0

    embedding_provider: str = "auto"
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dim: int = 1536

    chunk_size: int = 700
    chunk_overlap: int = 120
    retrieval_k: int = 8
    rerank_k: int = 4

    stt_provider: str = "auto"
    whisper_model: str = "base"
    openai_stt_model: str = "whisper-1"
    tts_provider: str = "auto"
    openai_tts_model: str = "tts-1"
    openai_tts_voice: str = "alloy"
    edge_tts_voice: str = "en-US-AriaNeural"
    piper_bin: str = "piper"
    piper_model: str = ""

    max_upload_bytes: int = 10 * 1024 * 1024
    memory_turns: int = 8

    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def data_path(self) -> Path:
        return Path(self.data_dir)

    @property
    def db_path(self) -> Path:
        return self.data_path / "app.db"

    @property
    def chroma_path(self) -> Path:
        return self.data_path / "chroma"

    @property
    def upload_path(self) -> Path:
        return self.data_path / "uploads"

    @property
    def model_cache_path(self) -> Path:
        return self.data_path / "models"
