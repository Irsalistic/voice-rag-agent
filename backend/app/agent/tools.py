from __future__ import annotations

import re
import time
from datetime import date

from app.agent.router import EMAIL_RE
from app.db import Database
from app.llm.base import ToolCall
from app.retrieval.hits import hit_to_passage
from app.retrieval.hybrid import Retriever
from app.textutil import elapsed_ms

TIME_RE = re.compile(r"^\d{2}:\d{2}$")

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge_base",
            "description": (
                "Search uploaded company documents for policies, product facts, and procedures."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "What to look up in the documents"}
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_appointment",
            "description": "Book a support appointment once every field is known.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "email": {"type": "string"},
                    "date": {"type": "string", "description": "YYYY-MM-DD"},
                    "time": {"type": "string", "description": "HH:MM in 24-hour time"},
                    "reason": {"type": "string"},
                },
                "required": ["name", "email", "date", "time", "reason"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": "Look up a demo order by order id (ORD-####) or customer email.",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string"},
                    "email": {"type": "string"},
                },
            },
        },
    },
]


class ToolKit:
    def __init__(self, db: Database, retriever: Retriever):
        self.db = db
        self.retriever = retriever

    def run(self, session_id: str | None, call: ToolCall) -> tuple[dict, dict]:
        started = time.perf_counter()
        if call.name == "search_knowledge_base":
            result = self._search(str(call.arguments.get("query") or ""))
            count = len(result.get("passages") or [])
            summary = f"Found {count} passages" if count else "No matching passages"
        elif call.name == "book_appointment":
            result = self._book(call.arguments)
            if result.get("appointment_id"):
                summary = f"Confirmed {result['appointment_id']}"
            else:
                summary = str(result.get("error") or "Booking failed")
        elif call.name == "lookup_order":
            result = self._lookup(call.arguments)
            summary = _order_summary(result)
        else:
            result = {"error": f"Unknown tool {call.name}"}
            summary = result["error"]
        latency = elapsed_ms(started)
        self.db.add_trace(session_id, f"tool:{call.name}", latency, summary)
        self.db.add_tool_call(session_id, call.name, call.arguments, result, summary, latency)
        public = {
            "name": call.name,
            "arguments": call.arguments,
            "summary": summary,
            "latency_ms": latency,
        }
        return result, public

    def _search(self, query: str) -> dict:
        query = query.strip()
        if not query:
            return {"passages": []}
        hits = self.retriever.search(query)
        return {"passages": [hit_to_passage(hit, index) for index, hit in enumerate(hits, start=1)]}

    def _book(self, arguments: dict) -> dict:
        name = str(arguments.get("name") or "").strip()
        email = str(arguments.get("email") or "").strip()
        day = str(arguments.get("date") or "").strip()
        time_of_day = str(arguments.get("time") or "").strip()
        reason = str(arguments.get("reason") or "").strip()
        missing = [
            label
            for label, value in (
                ("name", name),
                ("email", email),
                ("date", day),
                ("time", time_of_day),
                ("reason", reason),
            )
            if not value
        ]
        if missing:
            return {"error": "Missing " + ", ".join(missing)}
        if not EMAIL_RE.fullmatch(email):
            return {"error": "That email doesn't look valid."}
        try:
            date.fromisoformat(day)
        except ValueError:
            return {"error": "Use a date like 2026-11-03."}
        if not TIME_RE.fullmatch(time_of_day):
            return {"error": "Use a 24-hour time like 14:00."}
        hours, minutes = (int(part) for part in time_of_day.split(":"))
        if hours > 23 or minutes > 59:
            return {"error": "That time isn't valid."}
        row_id = self.db.add_appointment(name, email, day, time_of_day, reason)
        return {
            "appointment_id": f"APT-{row_id:04d}",
            "name": name,
            "email": email,
            "date": day,
            "time": time_of_day,
            "reason": reason,
            "status": "confirmed",
        }

    def _lookup(self, arguments: dict) -> dict:
        order_id = str(arguments.get("order_id") or "").strip()
        email = str(arguments.get("email") or "").strip()
        if order_id:
            order = self.db.get_order(order_id)
            if order is None:
                return {"found": False, "message": f"No order {order_id.upper()}."}
            return {"found": True, "orders": [order]}
        if email:
            orders = self.db.orders_by_email(email)
            if not orders:
                return {"found": False, "message": f"No orders for {email}."}
            return {"found": True, "orders": orders}
        return {"found": False, "message": "Provide an order id or an email."}


def model_payload(name: str, result: dict) -> dict:
    if name == "search_knowledge_base":
        return {
            "passages": [
                {
                    "n": passage["n"],
                    "source": passage["source"],
                    "page": passage["page"],
                    "text": passage["text"],
                }
                for passage in result.get("passages") or []
            ]
        }
    return {key: value for key, value in result.items() if not str(key).startswith("_")}


def _order_summary(result: dict) -> str:
    if not result.get("found"):
        return str(result.get("message") or "Not found")
    orders = result.get("orders") or []
    if len(orders) == 1:
        return f"{orders[0]['id']} is {orders[0]['status']}"
    return f"Found {len(orders)} orders"
