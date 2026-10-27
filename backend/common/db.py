"""SQLite для фактов отельера. Строка OSM отсюда не удаляется."""

from __future__ import annotations

import json
import sqlite3

from common.models import Fact
from common.snapshots import DATA

DB_PATH = DATA / "app.db"


def connect() -> sqlite3.Connection:
    DATA.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hotel_id TEXT NOT NULL,
                feature TEXT NOT NULL,
                method TEXT NOT NULL,
                payload TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id TEXT PRIMARY KEY,
                role TEXT NOT NULL,
                name TEXT NOT NULL,
                hotel_id TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hotel_id TEXT NOT NULL,
                guest_id TEXT,
                author_role TEXT NOT NULL,
                author_id TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS hotel_registrations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_id TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                address TEXT,
                hotel_id TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guest_id TEXT NOT NULL,
                hotel_id TEXT NOT NULL,
                check_in TEXT NOT NULL,
                check_out TEXT NOT NULL,
                nights INTEGER NOT NULL,
                amount_rub INTEGER NOT NULL,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        _seed_accounts(conn)
        count = conn.execute("SELECT COUNT(*) AS n FROM facts").fetchone()["n"]
        if count:
            return
        snapshot = DATA / "facts.json"
        if not snapshot.exists():
            return
        raw = json.loads(snapshot.read_text(encoding="utf-8"))
        for item in raw.get("items", []):
            fact = Fact.model_validate(item)
            _insert(conn, fact)


def _seed_accounts(conn: sqlite3.Connection) -> None:
    from geo.service import list_hotels

    guests = conn.execute("SELECT COUNT(*) AS n FROM accounts WHERE role = 'guest'").fetchone()["n"]
    if not guests:
        conn.execute(
            "INSERT INTO accounts (id, role, name, hotel_id) VALUES ('guest', 'guest', 'Гость', NULL)"
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
