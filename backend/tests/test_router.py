from pathlib import Path

from app.agent.router import IntentRouter, parse_appointment
from app.db import Database


def test_booking_fills_slots_across_turns(tmp_path: Path):
    db = Database(tmp_path / "slots.db")
    session_id = db.create_session()["id"]
    router = IntentRouter(db)

    calls, ask = router.plan(session_id, "Please book an appointment")
    assert calls == []
    assert ask is not None
    assert "email" in ask.lower()

    calls, ask = router.plan(
        session_id,
        "Priya Shah, priya@example.com, 2026-11-03 at 14:00 about a damaged lamp",
    )
    assert ask is None
    assert calls[0].name == "book_appointment"
    assert calls[0].arguments == {
        "name": "Priya Shah",
        "email": "priya@example.com",
        "date": "2026-11-03",
        "time": "14:00",
        "reason": "a damaged lamp",
    }


def test_order_question_without_an_id_asks_for_one(tmp_path: Path):
    db = Database(tmp_path / "orders.db")
    session_id = db.create_session()["id"]
    calls, ask = IntentRouter(db).plan(session_id, "Where is my order?")
    assert calls == []
    assert "ORD-1001" in ask


def test_parse_relative_date_and_ampm():
    from datetime import date

    parsed = parse_appointment("Book tomorrow at 2pm about a scuffed leg", today=date(2026, 10, 24))
    assert parsed["date"] == "2026-10-25"
    assert parsed["time"] == "14:00"
    assert parsed["reason"] == "a scuffed leg"
