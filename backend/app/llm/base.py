from __future__ import annotations

import uuid
from dataclasses import dataclass, field


class LLMError(RuntimeError):
    pass


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict

    @classmethod
    def create(cls, name: str, arguments: dict, call_id: str | None = None) -> ToolCall:
        return cls(id=call_id or f"call_{uuid.uuid4().hex[:12]}", name=name, arguments=arguments)


@dataclass
class LLMResult:
    content: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    assistant_message: dict | None = None


class LLMClient:
    name = "base"
    model = ""
    supports_tools = False

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResult:
        raise NotImplementedError

    def stream(self, messages: list[dict]):
        raise NotImplementedError
        yield ""


class ExtractiveLLM(LLMClient):
    """Answers are composed from tool output. No remote model is called."""

    name = "extractive"
    model = "local-extractive"
    supports_tools = False

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResult:
        raise LLMError("extractive provider answers from local tools")

    def stream(self, messages: list[dict]):
        raise LLMError("extractive provider answers from local tools")
        yield ""
