from __future__ import annotations

import re

from app.llm.base import ToolCall
from app.textutil import content_tokens, squash

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_ABBREV = re.compile(r"\b(Co|Inc|Ltd|Mr|Mrs|Ms|Dr|St|vs)\.")


def compose_answer(executed: list[tuple[ToolCall, dict]]) -> str:
    parts = []
    for call, result in executed:
        if call.name == "search_knowledge_base":
            query = str(call.arguments.get("query") or "")
            parts.append(compose_search(result.get("passages") or [], query))
        elif call.name == "book_appointment":
            parts.append(compose_booking(result))
        elif call.name == "lookup_order":
            parts.append(compose_orders(result))
        elif result.get("error"):
            parts.append(str(result["error"]))
    return "\n\n".join(part for part in parts if part)


def compose_search(passages: list[dict], query: str = "") -> str:
    if not passages:
        return "I couldn't find that in the uploaded documents."
    lines = ["Here's what the documents say."]
    for passage in _focus(passages):
        page = f", page {passage['page']}" if passage.get("page") else ""
        quote = _best_sentences(passage.get("text") or "", query)
        lines.append(f"[{passage['n']}] {quote} ({passage['source']}{page})")
    return "\n\n".join(lines)


def _focus(passages: list[dict]) -> list[dict]:
    top = float(passages[0].get("score") or 0)
    if top <= 0:
        return passages[:1]
    kept = [item for item in passages if float(item.get("score") or 0) >= top * 0.55]
    return (kept or passages)[:2]


def _best_sentences(text: str, query: str, limit: int = 2) -> str:
    body = "\n".join(line for line in text.splitlines() if not line.strip().startswith("#"))
    flat = re.sub(r"\s+", " ", body).strip()
    protected = _ABBREV.sub(lambda match: match.group(0)[:-1] + "\u0000", flat)
    sentences = [part.strip() for part in _SENTENCE.split(protected) if part.strip()]
    sentences = [part.replace("\u0000", ".") for part in sentences]
    if not sentences:
        return squash(text, 280)
    wanted = set(content_tokens(query))
    if not wanted:
        return " ".join(sentences[:limit])
    ranked = []
    for index, sentence in enumerate(sentences):
        overlap = len(wanted & set(content_tokens(sentence)))
        ranked.append((overlap, -index, sentence))
    ranked.sort(reverse=True)
    picked = [item[2] for item in ranked if item[0] > 0][:limit] or sentences[:1]
    order = {sentence: index for index, sentence in enumerate(sentences)}
    picked.sort(key=lambda sentence: order[sentence])
    return " ".join(picked)


def compose_booking(result: dict) -> str:
    if result.get("error"):
        return str(result["error"])
    return (
        f"Booked {result['appointment_id']} for {result['name']} "
        f"on {result['date']} at {result['time']}. "
        f"Reason: {result['reason']}. It is saved locally and marked confirmed."
    )


def compose_orders(result: dict) -> str:
    if not result.get("found"):
        return str(result.get("message") or "I couldn't find that order.")
    lines = []
    for order in result["orders"]:
        items = ", ".join(order.get("items") or [])
        line = (
            f"Order {order['id']} for {order['customer_name']} is {order['status']}. "
            f"Total ${order['total_cents'] / 100:.2f}. Items: {items}."
        )
        if order.get("tracking"):
            via = f" via {order['carrier']}" if order.get("carrier") else ""
            line += f" Tracking {order['tracking']}{via}."
        lines.append(line)
    return " ".join(lines)


def public_sources(passages: list[dict]) -> list[dict]:
    sources = []
    for passage in passages:
        sources.append(
            {
                "n": passage.get("n"),
                "id": passage.get("id"),
                "source": passage.get("source"),
                "page": passage.get("page"),
                "document_id": passage.get("document_id"),
                "score": passage.get("score"),
                "snippet": squash(passage.get("text") or "", 320),
            }
        )
    return sources
