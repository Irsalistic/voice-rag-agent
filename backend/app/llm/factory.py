from __future__ import annotations

import logging

import httpx

from app.config import Settings
from app.llm.base import ExtractiveLLM, LLMClient
from app.llm.openai_compat import OpenAICompatibleLLM

log = logging.getLogger(__name__)


def probe_ollama(base_url: str) -> bool:
    try:
        response = httpx.get(base_url.rstrip("/") + "/api/tags", timeout=0.4)
    except httpx.HTTPError:
        return False
    return response.status_code == 200


def build_llm(settings: Settings) -> LLMClient:
    choice = _resolve(settings)
    if choice == "openai":
        return _remote(
            "openai",
            settings.openai_api_key.strip(),
            settings.openai_base_url,
            settings.openai_model,
            settings,
        )
    if choice == "groq":
        return _remote(
            "groq",
            settings.groq_api_key.strip(),
            settings.groq_base_url,
            settings.groq_model,
            settings,
        )
    if choice == "ollama":
        return OpenAICompatibleLLM(
            name="ollama",
            api_key="ollama",
            base_url=settings.ollama_base_url.rstrip("/") + "/v1",
            model=settings.ollama_model,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_seconds,
        )
    if choice != "extractive":
        log.warning("Unknown LLM provider %s. Using extractive answers.", choice)
    return ExtractiveLLM()


def _resolve(settings: Settings) -> str:
    choice = settings.llm_provider.lower().strip() or "auto"
    if choice != "auto":
        return choice
    if settings.openai_api_key.strip():
        return "openai"
    if settings.groq_api_key.strip():
        return "groq"
    if probe_ollama(settings.ollama_base_url):
        return "ollama"
    return "extractive"


def _remote(name: str, api_key: str, base_url: str, model: str, settings: Settings) -> LLMClient:
    if not api_key:
        log.warning("%s API key is missing. Using extractive answers.", name)
        return ExtractiveLLM()
    return OpenAICompatibleLLM(
        name=name,
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
    )
