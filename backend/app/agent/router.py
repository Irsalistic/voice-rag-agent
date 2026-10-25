from __future__ import annotations

import re
from datetime import date, timedelta

from app.agent.prompts import GREETING
from app.db import Database
from app.llm.base import ToolCall
from app.textutil import content_tokens

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ORDER_ID_RE = re.compile(r"\b(ORD-\d+)\b", re.IGNORECASE)
ORDER_WORD_RE = re.compile(r"\borders?\b", re.IGNORECASE)
BOOKING_RE = re.compile(r"\b(book|schedule|appointment|reserve)\b", re.IGNORECASE)
BOOKING_REQUEST_RE = re.compile(r"\b(book|schedule|reserve)\b", re.IGNORECASE)
POLICY_QUESTION_RE = re.compile(r"\b(how long|what time|when are|hours|policy)\b", re.IGNORECASE)
GREETING_RE = re.compile(
    r"^(hi|hello|hey|good morning|good afternoon|good evening|thanks|thank you)"
    r"( there| you)?[.!\s]*$",
    re.IGNORECASE,
)
NAME_STOP_RE = re.compile(r"\b(on|at|about|regarding|tomorrow|today|email)\b|,", re.IGNORECASE)

MONTHS = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}

REQUIRED_BOOKING_FIELDS = ("name", "email", "date", "time", "reason")
FIELD_LABELS = {
    "name": "your name",
    "email": "your email",
    "date": "a date like 2026-11-03",
    "time": "a time like 14:00",
    "reason": "what the call is about",
}


def is_greeting(text: str) -> bool:
    if "?" in text:
        return False
    return bool(GREETING_RE.match(text.strip()))


def is_order(text: str) -> bool:
    return bool(ORDER_ID_RE.search(text) or ORDER_WORD_RE.search(text))


def is_booking(text: str) -> bool:
    if not BOOKING_RE.search(text):
        return False
    if POLICY_QUESTION_RE.search(text) and not BOOKING_REQUEST_RE.search(text):
        return False
    if text.strip().endswith("?") and not BOOKING_REQUEST_RE.search(text):
        return False
    return True


def ask_for(missing: list[str]) -> str:
    labels = [FIELD_LABELS[item] for item in missing]
    if len(labels) == 1:
        needed = labels[0]
    else:
        needed = ", ".join(labels[:-1]) + " and " + labels[-1]
    return f"I can book that appointment. I still need {needed}."


def parse_appointment(text: str, today: date | None = None) -> dict:
    return {
        "name": _parse_name(text),
        "email": _parse_email(text),
        "date": _parse_date(text, today or date.today()),
        "time": _parse_time(text),
        "reason": _parse_reason(text),
    }


def parse_order(text: str) -> dict:
    arguments: dict[str, str] = {}
    order_match = ORDER_ID_RE.search(text)
    if order_match:
        arguments["order_id"] = order_match.group(1).upper()
    email = _parse_email(text)
    if email:
        arguments["email"] = email
    return arguments


class IntentRouter:
    def __init__(self, db: Database):
        self.db = db

    def should_force_search(self, text: str, session_id: str) -> bool:
        if (
            self._pending(session_id) is not None
            or is_greeting(text)
            or is_booking(text)
            or is_order(text)
        ):
            return False
        return len(content_tokens(text)) >= 2

    def plan(self, session_id: str, text: str) -> tuple[list[ToolCall], str | None]:
        pending = self._pending(session_id)
        in_booking = pending is not None
        if in_booking and not is_booking(text):
            parsed = parse_appointment(text)
            if not any(parsed.values()) and ("?" in text or is_order(text) or is_greeting(text)):
                self.db.update_session_meta(session_id, {"pending_appointment": None})
                pending = None
                in_booking = False
        if in_booking or is_booking(text):
            return self._plan_booking(session_id, text, pending or {})
        if is_order(text):
            return self._plan_order(text)
        if is_greeting(text):
            return [], GREETING
        return [ToolCall.create("search_knowledge_base", {"query": text})], None

    def _plan_booking(
        self, session_id: str, text: str, pending: dict
    ) -> tuple[list[ToolCall], str | None]:
        fields = {key: value for key, value in pending.items() if value}
        for key, value in parse_appointment(text).items():
            if value:
                fields[key] = value
        missing = [key for key in REQUIRED_BOOKING_FIELDS if not fields.get(key)]
        if missing:
            self.db.update_session_meta(session_id, {"pending_appointment": fields})
            return [], ask_for(missing)
        self.db.update_session_meta(session_id, {"pending_appointment": None})
        arguments = {key: fields[key] for key in REQUIRED_BOOKING_FIELDS}
        return [ToolCall.create("book_appointment", arguments)], None

    def _plan_order(self, text: str) -> tuple[list[ToolCall], str | None]:
        arguments = parse_order(text)
        if not arguments.get("order_id") and not arguments.get("email"):
            return [], "Share an order id like ORD-1001, or the email on the order."
        return [ToolCall.create("lookup_order", arguments)], None

    def _pending(self, session_id: str) -> dict | None:
        raw = self.db.session_meta(session_id).get("pending_appointment")
        if isinstance(raw, dict):
            return raw
        return None


def _parse_email(text: str) -> str | None:
    match = EMAIL_RE.search(text)
    return match.group(0) if match else None


def _parse_name(text: str) -> str | None:
    patterns = [
        re.compile(
            r"\b(?:my name is|name is|i am|i'm)\s+"
            r"([A-Za-z][A-Za-z.'-]+(?:\s+[A-Za-z][A-Za-z.'-]+){0,3})",
            re.IGNORECASE,
        ),
        re.compile(r"\bfor\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})"),
        re.compile(r"^\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3})\s*,"),
    ]
    for pattern in patterns:
        match = pattern.search(text)
        if not match:
            continue
        name = _trim_name(match.group(1))
        if name and name.lower() not in {"an", "a", "the", "appointment", "me"}:
            return name
    return None


def _trim_name(value: str) -> str:
    value = NAME_STOP_RE.split(value, maxsplit=1)[0].strip()
    parts = [part for part in value.split() if part][:4]
    tidy = []
    for part in parts:
        tidy.append(part.capitalize() if part.islower() else part)
    return " ".join(tidy)


def _parse_date(text: str, today: date) -> str | None:
    iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if iso:
        try:
            return date.fromisoformat(iso.group(1)).isoformat()
        except ValueError:
            return None
    if re.search(r"\btomorrow\b", text, re.IGNORECASE):
        return (today + timedelta(days=1)).isoformat()
    if re.search(r"\btoday\b", text, re.IGNORECASE):
        return today.isoformat()
    match = re.search(
        r"\b(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|"
        r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
        r"\s+(\d{1,2})(?:st|nd|rd|th)?(?:,?\s+(\d{4}))?\b",
        text,
        re.IGNORECASE,
    )
    if not match:
        return None
    month = MONTHS[match.group(1).lower()]
    day = int(match.group(2))
    year = int(match.group(3) or today.year)
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return None


def _parse_time(text: str) -> str | None:
    clock = re.search(r"\b(\d{1,2}):(\d{2})\s*(am|pm)?\b", text, re.IGNORECASE)
    if clock:
        return _normalize_clock(int(clock.group(1)), int(clock.group(2)), clock.group(3))
    ampm = re.search(r"\b(\d{1,2})\s*(am|pm)\b", text, re.IGNORECASE)
    if ampm:
        return _normalize_clock(int(ampm.group(1)), 0, ampm.group(2))
    return None


def _normalize_clock(hour: int, minute: int, suffix: str | None) -> str | None:
    if minute > 59:
        return None
    suffix = (suffix or "").lower()
    if suffix == "pm" and hour < 12:
        hour += 12
    elif suffix == "am" and hour == 12:
        hour = 0
    elif suffix == "am" and hour > 12:
        return None
    elif suffix == "pm" and hour > 12:
        return None
    if hour > 23:
        return None
    return f"{hour:02d}:{minute:02d}"


def _parse_reason(text: str) -> str | None:
    match = re.search(r"\b(?:about|regarding|because|reason(?: is)?)\s+(.+)$", text, re.IGNORECASE)
    if not match:
        return None
    reason = EMAIL_RE.sub("", match.group(1))
    reason = re.sub(r"\s+", " ", reason).strip(" .")
    return reason[:400] or None
