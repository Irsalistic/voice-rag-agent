from __future__ import annotations

import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(raw: str | None, fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return fallback


SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    content_type TEXT,
    byte_size INTEGER NOT NULL DEFAULT 0,
    chunk_count INTEGER NOT NULL DEFAULT 0,
    stored_name TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    ordinal INTEGER NOT NULL,
    text TEXT NOT NULL,
    source TEXT NOT NULL,
    page INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    meta_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    sources_json TEXT,
    tools_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    name TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    result_json TEXT NOT NULL,
    summary TEXT NOT NULL,
    latency_ms INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS traces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,
    stage TEXT NOT NULL,
    latency_ms INTEGER NOT NULL,
    detail TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL,
    date TEXT NOT NULL,
    time TEXT NOT NULL,
    reason TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    status TEXT NOT NULL,
    total_cents INTEGER NOT NULL,
    items_json TEXT NOT NULL,
    carrier TEXT,
    tracking TEXT,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);
CREATE INDEX IF NOT EXISTS idx_traces_stage ON traces(stage);
CREATE INDEX IF NOT EXISTS idx_orders_email ON orders(email);
"""


class Database:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")
        self.migrate()

    def migrate(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self._lock:
            cursor = self._conn.execute(sql, params)
            self._conn.commit()
            return cursor

    def query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return list(self._conn.execute(sql, params).fetchall())

    def query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def set_meta(self, key: str, value: str) -> None:
        self.execute(
            "INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    def get_meta(self, key: str) -> str | None:
        row = self.query_one("SELECT value FROM meta WHERE key = ?", (key,))
        if row is None:
            return None
        return str(row["value"])

    def counts(self) -> dict[str, int]:
        tables = {
            "documents": "documents",
            "chunks": "chunks",
            "sessions": "sessions",
            "messages": "messages",
            "tool_calls": "tool_calls",
            "appointments": "appointments",
            "orders": "orders",
        }
        return {name: int(self.query_one(f"SELECT COUNT(*) AS n FROM {table}")["n"]) for name, table in tables.items()}

    def create_session(self, title: str = "New conversation") -> dict:
        session_id = uuid.uuid4().hex[:16]
        now = utcnow()
        self.execute(
            "INSERT INTO sessions (id, title, meta_json, created_at, updated_at) VALUES (?, ?, '{}', ?, ?)",
            (session_id, title, now, now),
        )
        session = self.get_session(session_id)
        assert session is not None
        return session

    def get_session(self, session_id: str) -> dict | None:
        row = self.query_one("SELECT * FROM sessions WHERE id = ?", (session_id,))
        return dict(row) if row else None

    def list_sessions(self, limit: int = 40) -> list[dict]:
        rows = self.query(
            """
            SELECT s.id, s.title, s.created_at, s.updated_at,
                   (SELECT COUNT(*) FROM messages m WHERE m.session_id = s.id) AS message_count
            FROM sessions s
            ORDER BY s.updated_at DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in rows]

    def delete_session(self, session_id: str) -> bool:
        cursor = self.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        return cursor.rowcount > 0

    def touch_session(self, session_id: str, title: str | None = None) -> None:
        if title is None:
            self.execute(
                "UPDATE sessions SET updated_at = ? WHERE id = ?",
                (utcnow(), session_id),
            )
            return
        self.execute(
            "UPDATE sessions SET title = ?, updated_at = ? WHERE id = ?",
            (title, utcnow(), session_id),
        )

    def maybe_title(self, session_id: str, user_text: str) -> None:
        session = self.get_session(session_id)
        if session is None or session["title"] != "New conversation":
            return
        title = " ".join(user_text.split())
        if len(title) > 48:
            shortened = title[:48].rsplit(" ", 1)[0]
            title = (shortened or title[:48]).rstrip() + "…"
        self.touch_session(session_id, title)

    def session_meta(self, session_id: str) -> dict:
        row = self.query_one("SELECT meta_json FROM sessions WHERE id = ?", (session_id,))
        if row is None:
            return {}
        value = _load_json(row["meta_json"], {})
        return value if isinstance(value, dict) else {}

    def update_session_meta(self, session_id: str, patch: dict) -> None:
        meta = self.session_meta(session_id)
        for key, value in patch.items():
            if value is None:
                meta.pop(key, None)
            else:
                meta[key] = value
        self.execute(
            "UPDATE sessions SET meta_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(meta), utcnow(), session_id),
        )

    def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        sources: list | None = None,
        tools: list | None = None,
    ) -> int:
        now = utcnow()
        cursor = self.execute(
            """
            INSERT INTO messages (session_id, role, content, sources_json, tools_json, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                session_id,
                role,
                content,
                json.dumps(sources or []),
                json.dumps(tools or []),
                now,
            ),
        )
        self.touch_session(session_id)
        return int(cursor.lastrowid)

    def list_messages(self, session_id: str) -> list[dict]:
        rows = self.query(
            """
            SELECT id, role, content, sources_json, tools_json, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY id
            """,
            (session_id,),
        )
        messages = []
        for row in rows:
            item = dict(row)
            item["sources"] = _load_json(item.pop("sources_json"), [])
            item["tools"] = _load_json(item.pop("tools_json"), [])
            messages.append(item)
        return messages

    def recent_messages(self, session_id: str, limit: int) -> list[dict]:
        rows = self.query(
            """
            SELECT role, content FROM messages
            WHERE session_id = ? AND role IN ('user', 'assistant')
            ORDER BY id DESC
            LIMIT ?
            """,
            (session_id, limit),
        )
        return [dict(row) for row in reversed(rows)]

    def add_document(
        self,
        document_id: str,
        filename: str,
        content_type: str | None,
        byte_size: int,
        chunk_count: int,
        stored_name: str,
    ) -> None:
        self.execute(
            """
            INSERT INTO documents (id, filename, content_type, byte_size, chunk_count, stored_name, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (document_id, filename, content_type, byte_size, chunk_count, stored_name, utcnow()),
        )

    def list_documents(self) -> list[dict]:
        rows = self.query(
            """
            SELECT id, filename, content_type, byte_size, chunk_count, created_at
            FROM documents
            ORDER BY created_at DESC
            """
        )
        return [dict(row) for row in rows]

    def get_document(self, document_id: str) -> dict | None:
        row = self.query_one("SELECT * FROM documents WHERE id = ?", (document_id,))
        return dict(row) if row else None

    def delete_document(self, document_id: str) -> bool:
        cursor = self.execute("DELETE FROM documents WHERE id = ?", (document_id,))
        return cursor.rowcount > 0

    def add_chunks(self, rows: list[dict]) -> None:
        if not rows:
            return
        payload = [
            (
                row["id"],
                row["document_id"],
                row["ordinal"],
                row["text"],
                row["source"],
                row.get("page"),
                utcnow(),
            )
            for row in rows
        ]
        with self._lock:
            self._conn.executemany(
                """
                INSERT INTO chunks (id, document_id, ordinal, text, source, page, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                payload,
            )
            self._conn.commit()

    def list_chunks(self) -> list[dict]:
        rows = self.query(
            """
            SELECT id, document_id, ordinal, text, source, page
            FROM chunks
            ORDER BY document_id, ordinal
            """
        )
        return [dict(row) for row in rows]

    def chunks_for_document(self, document_id: str) -> list[dict]:
        rows = self.query(
            """
            SELECT id, document_id, ordinal, text, source, page
            FROM chunks
            WHERE document_id = ?
            ORDER BY ordinal
            """,
            (document_id,),
        )
        return [dict(row) for row in rows]

    def add_tool_call(
        self,
        session_id: str | None,
        name: str,
        arguments: dict,
        result: dict,
        summary: str,
        latency_ms: int,
    ) -> None:
        raw = json.dumps(result)
        if len(raw) > 20000:
            raw = raw[:20000]
        self.execute(
            """
            INSERT INTO tool_calls (session_id, name, arguments_json, result_json, summary, latency_ms, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (session_id, name, json.dumps(arguments), raw, summary[:300], latency_ms, utcnow()),
        )

    def list_tool_calls(self, limit: int = 40) -> list[dict]:
        rows = self.query(
            """
            SELECT id, session_id, name, arguments_json, summary, latency_ms, created_at
            FROM tool_calls
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        items = []
        for row in rows:
            item = dict(row)
            item["arguments"] = _load_json(item.pop("arguments_json"), {})
            items.append(item)
        return items

    def add_trace(self, session_id: str | None, stage: str, latency_ms: int, detail: str = "") -> None:
        self.execute(
            "INSERT INTO traces (session_id, stage, latency_ms, detail, created_at) VALUES (?, ?, ?, ?, ?)",
            (session_id, stage, latency_ms, detail[:300], utcnow()),
        )

    def latency_summary(self, limit: int = 1000) -> list[dict]:
        rows = self.query(
            "SELECT stage, latency_ms FROM traces ORDER BY id DESC LIMIT ?",
            (limit,),
        )
        grouped: dict[str, list[int]] = {}
        for row in rows:
            grouped.setdefault(str(row["stage"]), []).append(int(row["latency_ms"]))
        summary = []
        for stage, values in grouped.items():
            ordered = sorted(values)
            summary.append(
                {
                    "stage": stage,
                    "count": len(values),
                    "avg_ms": round(sum(values) / len(values), 1),
                    "p50_ms": ordered[len(ordered) // 2],
                    "max_ms": max(values),
                }
            )
        summary.sort(key=lambda item: item["stage"])
        return summary

    def add_appointment(self, name: str, email: str, day: str, time_of_day: str, reason: str) -> int:
        cursor = self.execute(
            """
            INSERT INTO appointments (name, email, date, time, reason, status, created_at)
            VALUES (?, ?, ?, ?, ?, 'confirmed', ?)
            """,
            (name, email, day, time_of_day, reason, utcnow()),
        )
        return int(cursor.lastrowid)

    def list_appointments(self, limit: int = 20) -> list[dict]:
        rows = self.query(
            """
            SELECT id, name, email, date, time, reason, status, created_at
            FROM appointments
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        items = []
        for row in rows:
            item = dict(row)
            item["appointment_id"] = f"APT-{item['id']:04d}"
            items.append(item)
        return items

    def insert_order(self, order: dict) -> None:
        self.execute(
            """
            INSERT OR IGNORE INTO orders
                (id, email, customer_name, status, total_cents, items_json, carrier, tracking, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order["id"],
                order["email"],
                order["customer_name"],
                order["status"],
                order["total_cents"],
                json.dumps(order["items"]),
                order.get("carrier"),
                order.get("tracking"),
                utcnow(),
            ),
        )

    def get_order(self, order_id: str) -> dict | None:
        row = self.query_one("SELECT * FROM orders WHERE id = ?", (order_id.upper(),))
        return _order_out(row) if row else None

    def orders_by_email(self, email: str) -> list[dict]:
        rows = self.query(
            "SELECT * FROM orders WHERE lower(email) = lower(?) ORDER BY id",
            (email.strip(),),
        )
        return [_order_out(row) for row in rows]


def _order_out(row: sqlite3.Row) -> dict:
    item = dict(row)
    item["items"] = _load_json(item.pop("items_json"), [])
    return item
