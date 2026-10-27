"""Запросы к SQLite. Схема живёт в common.tables и миграциях Alembic.

Новый код берёт Session через common.database.get_db. Строка OSM отсюда не удаляется.
"""

from __future__ import annotations

import json
import sqlite3
import threading

from common.database import DB_PATH, apply_migrations
from common.models import Fact
from common.snapshots import DATA

_ready = False
_lock = threading.Lock()


def connect() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Схема и стартовые счета готовятся один раз на процесс.

    Повторный вызов на каждом открытии кабинета снова писал в SQLite и при двух
    одновременных запросах страницы отвечал 500.
    """
    global _ready
    if _ready:
        return
    with _lock:
        if _ready:
            return
        apply_migrations()
        with connect() as conn:
            _seed_accounts(conn)
            count = conn.execute("SELECT COUNT(*) AS n FROM facts").fetchone()["n"]
            if not count:
                snapshot = DATA / "facts.json"
                if snapshot.exists():
                    raw = json.loads(snapshot.read_text(encoding="utf-8"))
                    for item in raw.get("items", []):
                        fact = Fact.model_validate(item)
                        _insert(conn, fact)
        _ready = True


def _seed_accounts(conn: sqlite3.Connection) -> None:
    from geo.service import list_hotels

    guests = conn.execute("SELECT COUNT(*) AS n FROM accounts WHERE role = 'guest'").fetchone()["n"]
    if not guests:
        conn.execute(
            "INSERT INTO accounts (id, role, name, hotel_id) VALUES ('ostrovok-admin', 'guest', 'Админ Островка', NULL)"
        )
    for hotel in list_hotels():
        account_id = f"hotelier-{hotel['id']}"
        name = hotel.get("name") or hotel["id"]
        conn.execute(
            """
            INSERT INTO accounts (id, role, name, hotel_id) VALUES (?, 'hotelier', ?, ?)
            ON CONFLICT(id) DO UPDATE SET name = excluded.name, hotel_id = excluded.hotel_id
            """,
            (account_id, f"Отельер · {name}", hotel["id"]),
        )


def _insert(conn: sqlite3.Connection, fact: Fact) -> None:
    conn.execute(
        "INSERT INTO facts (hotel_id, feature, method, payload) VALUES (?, ?, ?, ?)",
        (fact.hotel_id or "", fact.feature, fact.method, fact.model_dump_json()),
    )


def facts_for(hotel_id: str) -> list[Fact]:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT payload FROM facts WHERE hotel_id = ? ORDER BY id",
            (hotel_id,),
        ).fetchall()
    return [Fact.model_validate_json(row["payload"]) for row in rows]


def replace_hotelier(hotel_id: str, feature: str, fact: Fact) -> None:
    """Новый ответ отельера сменяет его прежний ответ по этому полю. Расчёт OSM остаётся."""
    init_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, method FROM facts WHERE hotel_id = ? AND feature = ?",
            (hotel_id, feature),
        ).fetchall()
        for row in rows:
            if row["method"] == "parse_hotelier":
                conn.execute("DELETE FROM facts WHERE id = ?", (row["id"],))
        _insert(conn, fact)
