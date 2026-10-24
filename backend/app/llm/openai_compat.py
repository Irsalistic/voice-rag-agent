from __future__ import annotations

import json

import httpx

from app.llm.base import LLMClient, LLMError, LLMResult, ToolCall


class OpenAICompatibleLLM(LLMClient):
    """Chat completions client for OpenAI, Groq, and Ollama's OpenAI-compatible API."""

    supports_tools = True

    def __init__(
        self,
        name: str,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float,
        timeout: float,
    ):
        self.name = name
        self.model = model
        self._api_key = api_key
        self._base = base_url.rstrip("/")
        self._temperature = temperature
        self._timeout = timeout

    def complete(self, messages: list[dict], tools: list[dict] | None = None) -> LLMResult:
        payload: dict = {
            "model": self.model,
            "messages": messages,
            "temperature": self._temperature,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        data = self._post("/chat/completions", payload)
        message = data["choices"][0]["message"]
        tool_calls = [_parse_tool_call(raw) for raw in message.get("tool_calls") or []]
        assistant_message: dict = {"role": "assistant", "content": message.get("content") or ""}
        if message.get("tool_calls"):
            assistant_message["tool_calls"] = message["tool_calls"]
        return LLMResult(
            content=message.get("content") or "",
            tool_calls=[call for call in tool_calls if call.name],
            assistant_message=assistant_message,
        )

    def stream(self, messages: list[dict]):
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self._temperature,
            "stream": True,
        }
        headers = self._headers()
        try:
            with httpx.Client(timeout=self._timeout) as client:
                with client.stream(
                    "POST",
                    f"{self._base}/chat/completions",
                    headers=headers,
                    json=payload,
                ) as response:
                    if response.status_code >= 400:
                        body = response.read().decode("utf-8", errors="replace")
                        raise LLMError(f"{self.name} error {response.status_code}: {body[:300]}")
                    for line in response.iter_lines():
                        token = _stream_token(line)
                        if token is None:
                            continue
                        if token == "":
                            break
                        yield token
        except LLMError:
            raise
        except httpx.HTTPError as exc:
            raise LLMError(f"{self.name} connection failed: {exc}") from exc

    def _post(self, path: str, payload: dict) -> dict:
        try:
            response = httpx.post(
                f"{self._base}{path}",
                headers=self._headers(),
                json=payload,
                timeout=self._timeout,
            )
        except httpx.HTTPError as exc:
            raise LLMError(f"{self.name} connection failed: {exc}") from exc
        if response.status_code >= 400:
            raise LLMError(f"{self.name} error {response.status_code}: {response.text[:300]}")
        return response.json()

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }


def _parse_tool_call(raw: dict) -> ToolCall:
    function = raw.get("function") or {}
    arguments = function.get("arguments") or {}
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments) if arguments else {}
        except json.JSONDecodeError:
            arguments = {}
    if not isinstance(arguments, dict):
        arguments = {}
    return ToolCall(
        id=raw.get("id") or f"call_{function.get('name') or 'tool'}",
        name=function.get("name") or "",
        arguments=arguments,
    )


def _stream_token(line: str) -> str | None:
    if not line or not line.startswith("data:"):
        return None
    data = line[5:].strip()
    if data == "[DONE]":
        return ""
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return None
    choices = payload.get("choices") or [{}]
    delta = choices[0].get("delta") or {}
    return delta.get("content") or None
