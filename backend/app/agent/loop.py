from __future__ import annotations

import json
import logging
import time
from collections.abc import Iterator

from app.agent.compose import compose_answer, public_sources
from app.agent.prompts import GREETING, SYSTEM_PROMPT
from app.agent.router import IntentRouter
from app.agent.tools import TOOL_SCHEMAS, ToolKit, model_payload
from app.config import Settings
from app.db import Database
from app.llm.base import LLMClient, LLMError, ToolCall
from app.textutil import elapsed_ms

log = logging.getLogger(__name__)

FALLBACK_NOTICE = (
    "The language model was unavailable, so this answer uses the local document tools."
)


class Agent:
    def __init__(self, settings: Settings, db: Database, llm: LLMClient, tools: ToolKit):
        self.settings = settings
        self.db = db
        self.llm = llm
        self.tools = tools
        self.router = IntentRouter(db)

    def iter_turn(self, session_id: str, user_text: str) -> Iterator[dict]:
        user_text = user_text.strip()
        self.db.maybe_title(session_id, user_text)
        self.db.add_message(session_id, "user", user_text)
        started = time.perf_counter()
        bag: dict = {"parts": [], "sources": [], "tools": []}
        saved = False
        try:
            if self.llm.supports_tools:
                try:
                    yield from self._llm_turn(session_id, user_text, bag)
                except LLMError as exc:
                    log.warning("language model failed: %s", exc)
                    yield {"type": "notice", "text": FALLBACK_NOTICE}
                    self._fill_direct(session_id, user_text, bag)
                    yield from self._emit_direct(bag)
            else:
                self._fill_direct(session_id, user_text, bag)
                yield from self._emit_direct(bag)

            sources = public_sources(bag["sources"])
            if sources:
                yield {"type": "sources", "sources": sources}
            text = "".join(bag["parts"]).strip()
            self._save(session_id, text, sources, bag["tools"])
            saved = True
            latency = elapsed_ms(started)
            self.db.add_trace(session_id, "turn", latency, self.llm.name)
            yield {"type": "done", "latency_ms": latency}
        finally:
            if not saved:
                partial = "".join(bag["parts"]).strip()
                if partial:
                    self._save(
                        session_id,
                        partial + " …",
                        public_sources(bag["sources"]),
                        bag["tools"],
                    )

    def _emit_direct(self, bag: dict) -> Iterator[dict]:
        for event in bag["tools"]:
            yield {"type": "tool", **event}
        text = "".join(bag["parts"]).strip()
        if text:
            yield {"type": "token", "text": text}

    def _fill_direct(self, session_id: str, user_text: str, bag: dict) -> None:
        calls, ask = self.router.plan(session_id, user_text)
        executed: list[tuple[ToolCall, dict]] = []
        if ask and not calls:
            bag["parts"].append(ask)
            return
        for call in calls:
            self._execute(session_id, call, bag, executed)
        text = compose_answer(executed) if executed else (ask or GREETING)
        if text:
            bag["parts"].append(text)

    def _llm_turn(self, session_id: str, user_text: str, bag: dict) -> Iterator[dict]:
        messages = self._messages(session_id)
        executed: list[tuple[ToolCall, dict]] = []
        direct = yield from self._resolve_tools(session_id, messages, bag, executed)
        if not bag["tools"]:
            calls, ask = self.router.plan(session_id, user_text)
            if calls:
                for call in calls:
                    output, _public = self._execute(session_id, call, bag, executed)
                    messages.append(
                        {
                            "role": "user",
                            "content": "Tool result:\n"
                            + json.dumps(model_payload(call.name, output)),
                        }
                    )
                    yield {"type": "tool", **bag["tools"][-1]}
                direct = None
            elif not direct:
                direct = ask
        if direct:
            bag["parts"].append(direct)
            yield {"type": "token", "text": direct}
            return
        yield from self._stream_answer(session_id, messages, bag, executed)

    def _resolve_tools(self, session_id, messages, bag, executed) -> Iterator[dict]:
        direct = None
        for round_index in range(3):
            try:
                started = time.perf_counter()
                result = self.llm.complete(messages, tools=TOOL_SCHEMAS)
                self.db.add_trace(session_id, "llm", elapsed_ms(started), "decision")
            except LLMError:
                if round_index == 0 and not executed:
                    raise
                break
            if not result.tool_calls:
                direct = result.content
                break
            if result.assistant_message:
                messages.append(result.assistant_message)
            for call in result.tool_calls:
                output, public = self._execute(session_id, call, bag, executed)
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(model_payload(call.name, output)),
                    }
                )
                yield {"type": "tool", **public}
            direct = None
        return direct

    def _stream_answer(self, session_id, messages, bag, executed) -> Iterator[dict]:
        started = time.perf_counter()
        try:
            for token in self.llm.stream(messages):
                bag["parts"].append(token)
                yield {"type": "token", "text": token}
            self.db.add_trace(session_id, "llm", elapsed_ms(started), "answer")
        except LLMError as exc:
            log.warning("answer stream failed: %s", exc)
        if not "".join(bag["parts"]).strip():
            text = compose_answer(executed) or "I couldn't complete that answer."
            bag["parts"].append(text)
            yield {"type": "token", "text": text}

    def _execute(self, session_id, call: ToolCall, bag: dict, executed: list) -> tuple[dict, dict]:
        output, public = self.tools.run(session_id, call)
        executed.append((call, output))
        bag["tools"].append(public)
        if call.name == "search_knowledge_base":
            bag["sources"] = output.get("passages") or []
        return output, public

    def _messages(self, session_id: str) -> list[dict]:
        history = self.db.recent_messages(session_id, self.settings.memory_turns * 2)
        return [{"role": "system", "content": SYSTEM_PROMPT}, *history]

    def _save(self, session_id: str, text: str, sources: list, tools: list) -> None:
        if not text:
            return
        self.db.add_message(session_id, "assistant", text, sources=sources, tools=tools)
