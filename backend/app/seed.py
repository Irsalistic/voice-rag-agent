from __future__ import annotations

from app.db import Database

DEMO_ORDERS = [
    {
        "id": "ORD-1001",
        "email": "jane@example.com",
        "customer_name": "Jane Adler",
        "status": "shipped",
        "total_cents": 24800,
        "items": ["Oakline sofa, sand linen"],
        "carrier": "Northline Freight",
        "tracking": "NL482193",
    },
    {
        "id": "ORD-1002",
        "email": "marcus@example.com",
        "customer_name": "Marcus Hale",
        "status": "processing",
        "total_cents": 8600,
        "items": ["Halden lamp"],
        "carrier": None,
        "tracking": None,
    },
    {
        "id": "ORD-1003",
        "email": "jane@example.com",
        "customer_name": "Jane Adler",
        "status": "delivered",
        "total_cents": 4200,
        "items": ["Wool throw, moss"],
        "carrier": "Northline Freight",
        "tracking": "NL100288",
    },
    {
        "id": "ORD-1004",
        "email": "sam@example.com",
        "customer_name": "Sam Okonkwo",
        "status": "cancelled",
        "total_cents": 12800,
        "items": ["Dining chair x2"],
        "carrier": None,
        "tracking": None,
    },
]


def seed_orders(db: Database) -> None:
    if db.get_meta("orders_seeded") == "1":
        return
    for order in DEMO_ORDERS:
        db.insert_order(order)
    db.set_meta("orders_seeded", "1")
