from __future__ import annotations

from app.llm.base import ToolCall
from app.textutil import squash


def compose_answer(executed: list[tuple[ToolCall, dict]]) -> str:
    parts = []
    for call, result in executed:
        if call.name == "search_knowledge_base":
            parts.append(compose_search(result.get("passages") or []))
        elif call.name == "book_appointment":
            parts.append(compose_booking(result))
        elif call.name == "lookup_order":
            parts.append(compose_orders(result))
        elif result.get("error"):
            parts.append(str(result["error"]))
    return "\n\n".join(part for part in parts if part)


def compose_search(passages: list[dict]) -> str:
    if not passages:
        return "I couldn't find that in the uploaded documents."
    lines = ["Here's what the documents say."]
    for passage in passages:
        page = f", page {passage['page']}" if passage.get("page") else ""
        snippet = squash(passage.get("text") or "", 500)
        lines.append(f"[{passage['n']}] {snippet} ({passage['source']}{page})")
    return "\n\n".join(lines)


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
