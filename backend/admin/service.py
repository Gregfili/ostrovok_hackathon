"""Счета гостя и отельера. Пароля нет: хакатон не проверяет личность.

Оплата записывает бронь как оплаченную. Карта не читается, деньги не списываются.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from common.db import connect, init_db
from geo.service import get_hotel, list_hotels
from hotel_faq.service import answer_question as faq_answer
from hotel_faq.service import get_config as faq_get_config
from hotelier.agent import draft_reply

NIGHT_RUB = 10_000
PAYMENT_NOTE = (
    "10 000 ₽ за ночь — сумма прототипа, не тариф Островка. "
    "Номер карты не нужен, деньги не списываются."
)


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _account_row(row) -> dict:
    return {
        "id": row["id"],
        "role": row["role"],
        "name": row["name"],
        "hotel_id": row["hotel_id"],
    }


def _norm(value: str) -> str:
    return " ".join(value.lower().replace("ё", "е").split())


def _match_snapshot(name: str) -> str | None:
    needle = _norm(name)
    if len(needle) < 3 or needle in {"отель", "hotel", "гостиница"}:
        return None
    for hotel in list_hotels():
        for label in (hotel.get("name") or "", hotel.get("also_known") or ""):
            text = _norm(label)
            if text and (needle == text or needle in text or text in needle):
                return hotel["id"]
    return None


def _registrations(conn) -> list[dict]:
    rows = conn.execute(
        """
        SELECT account_id, name, address, hotel_id
        FROM hotel_registrations ORDER BY id
        """
    ).fetchall()
    return [
        {
            "account_id": row["account_id"],
            "name": row["name"],
            "address": row["address"] or "",
            "hotel_id": row["hotel_id"],
        }
        for row in rows
    ]


def _resolve_hotel(hotel_id: str) -> dict | None:
    found = get_hotel(hotel_id)
    if found:
        return found
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT name, address, hotel_id FROM hotel_registrations WHERE hotel_id = ?",
            (hotel_id,),
        ).fetchone()
    if row is None:
        return None
    return {"id": row["hotel_id"], "name": row["name"], "address": row["address"] or ""}


def list_accounts() -> dict:
    init_db()
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT id, role, name, hotel_id FROM accounts
            ORDER BY CASE role WHEN 'guest' THEN 0 ELSE 1 END, name
            """
        ).fetchall()
        registrations = _registrations(conn)
    hotels = [
        {"id": hotel["id"], "name": hotel["name"], "address": hotel["address"]}
        for hotel in list_hotels()
    ]
    known = {hotel["id"] for hotel in hotels}
    for item in registrations:
        if item["hotel_id"] not in known:
            hotels.append({"id": item["hotel_id"], "name": item["name"], "address": item["address"]})
            known.add(item["hotel_id"])
    return {
        "accounts": [_account_row(row) for row in rows],
        "registrations": registrations,
        "night_rub": NIGHT_RUB,
        "payment_note": PAYMENT_NOTE,
        "hotels": hotels,
    }


def register_hotel(name: str, address: str = "") -> dict:
    clean = " ".join(name.split())
    if not clean:
        raise ValueError("Нужно название отеля")
    place = " ".join((address or "").split())
    matched = _match_snapshot(clean)
    init_db()
    with connect() as conn:
        if matched:
            hotel_id = matched
            account_id = f"hotelier-{hotel_id}"
        else:
            seq = conn.execute("SELECT COUNT(*) AS n FROM hotel_registrations").fetchone()["n"] + 1
            hotel_id = f"registered-{seq}"
            while conn.execute(
                "SELECT 1 FROM hotel_registrations WHERE hotel_id = ?",
                (hotel_id,),
            ).fetchone():
                seq += 1
                hotel_id = f"registered-{seq}"
            account_id = f"hotelier-{hotel_id}"
        existing = conn.execute(
            "SELECT account_id, name, address FROM hotel_registrations WHERE hotel_id = ?",
            (hotel_id,),
        ).fetchone()
        if existing is None:
            conn.execute(
                """
                INSERT INTO accounts (id, role, name, hotel_id) VALUES (?, 'hotelier', ?, ?)
                ON CONFLICT(id) DO UPDATE SET name = excluded.name, hotel_id = excluded.hotel_id
                """,
                (account_id, f"Отельер · {clean}", hotel_id),
            )
            conn.execute(
                """
                INSERT INTO hotel_registrations (account_id, name, address, hotel_id, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (account_id, clean, place, hotel_id, _now()),
            )
        else:
            account_id = existing["account_id"]
    return {
        "account_id": account_id,
        "hotel_id": hotel_id,
        "name": clean,
        "address": place,
        "in_snapshot": matched is not None,
    }


def create_guest(name: str) -> dict:
    clean = " ".join(name.split())
    if not clean:
        raise ValueError("Нужно имя гостя")
    init_db()
    with connect() as conn:
        seq = conn.execute("SELECT COUNT(*) AS n FROM accounts WHERE role = 'guest'").fetchone()["n"] + 1
        account_id = f"guest-{seq}"
        while conn.execute("SELECT 1 FROM accounts WHERE id = ?", (account_id,)).fetchone():
            seq += 1
            account_id = f"guest-{seq}"
        conn.execute(
            "INSERT INTO accounts (id, role, name, hotel_id) VALUES (?, 'guest', ?, NULL)",
            (account_id, clean),
        )
    return {"id": account_id, "role": "guest", "name": clean, "hotel_id": None}


def _require(account_id: str) -> dict:
    init_db()
    with connect() as conn:
        row = conn.execute(
            "SELECT id, role, name, hotel_id FROM accounts WHERE id = ?",
            (account_id,),
        ).fetchone()
    if row is None:
        raise ValueError("Такого счёта нет")
    return _account_row(row)


def _messages(hotel_id: str) -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT m.id, m.hotel_id, m.guest_id, m.author_role, m.author_id, m.body, m.created_at,
                   a.name AS author_name
            FROM messages m
            LEFT JOIN accounts a ON a.id = m.author_id
            WHERE m.hotel_id = ?
            ORDER BY m.id
            """,
            (hotel_id,),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "hotel_id": row["hotel_id"],
            "guest_id": row["guest_id"],
            "author_role": row["author_role"],
            "author_id": row["author_id"],
            "author_name": row["author_name"] or "Hotel Fact Agent",
            "body": row["body"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def _bookings(guest_id: str | None = None, hotel_id: str | None = None) -> list[dict]:
    clauses = []
    params: list[str] = []
    if guest_id:
        clauses.append("guest_id = ?")
        params.append(guest_id)
    if hotel_id:
        clauses.append("hotel_id = ?")
        params.append(hotel_id)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT id, guest_id, hotel_id, check_in, check_out, nights, amount_rub, status, created_at
            FROM bookings {where} ORDER BY id DESC
            """,
            params,
        ).fetchall()
    hotels = {hotel["id"]: hotel for hotel in list_hotels()}
    with connect() as conn:
        for item in _registrations(conn):
            hotels.setdefault(item["hotel_id"], {"name": item["name"]})
    items = []
    for row in rows:
        hotel = hotels.get(row["hotel_id"]) or {}
        items.append(
            {
                "id": row["id"],
                "guest_id": row["guest_id"],
                "hotel_id": row["hotel_id"],
                "hotel_name": hotel.get("name") or row["hotel_id"],
                "check_in": row["check_in"],
                "check_out": row["check_out"],
                "nights": row["nights"],
                "amount_rub": row["amount_rub"],
                "status": row["status"],
                "created_at": row["created_at"],
            }
        )
    return items


def desk(account_id: str) -> dict:
    account = _require(account_id)
    hotel_id = account.get("hotel_id")
    if account["role"] == "guest":
        hotel_ids = [hotel["id"] for hotel in list_accounts()["hotels"]]
        threads = {hotel_id: _messages(hotel_id) for hotel_id in hotel_ids}
        bookings = _bookings(guest_id=account_id)
    else:
        threads = {hotel_id: _messages(hotel_id)} if hotel_id else {}
        bookings = _bookings(hotel_id=hotel_id)
    return {
        "account": account,
        "threads": threads,
        "bookings": bookings,
        "night_rub": NIGHT_RUB,
        "payment_note": PAYMENT_NOTE,
        "draft": draft_reply(hotel_id) if account["role"] == "hotelier" and hotel_id else "",
        "faq": faq_get_config(hotel_id) if account["role"] == "hotelier" and hotel_id else None,
    }


def remember_question(hotel_id: str, question: str) -> None:
    text = (question or "").strip()
    if not text or get_hotel(hotel_id) is None:
        return
    init_db()
    with connect() as conn:
        last = conn.execute(
            """
            SELECT body, author_role FROM messages
            WHERE hotel_id = ? ORDER BY id DESC LIMIT 1
            """,
            (hotel_id,),
        ).fetchone()
        if last and last["author_role"] == "agent" and last["body"] == text:
            return
        conn.execute(
            """
            INSERT INTO messages (hotel_id, guest_id, author_role, author_id, body, created_at)
            VALUES (?, NULL, 'system', 'hotel-fact-agent', ?, ?)
            """,
            (hotel_id, text, _now()),
        )


def _insert_message(
    conn,
    *,
    hotel_id: str,
    guest_id: str | None,
    author_role: str,
    author_id: str,
    body: str,
) -> None:
    conn.execute(
        """
        INSERT INTO messages (hotel_id, guest_id, author_role, author_id, body, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (hotel_id, guest_id, author_role, author_id, body, _now()),
    )


def _latest_paid_booking(guest_id: str, hotel_id: str) -> dict | None:
    rows = _bookings(guest_id=guest_id, hotel_id=hotel_id)
    for row in rows:
        if row.get("status") == "paid":
            return row
    return None


def _live_hotelier_reply(extra: str = "") -> str:
    tail = (
        "Эту информацию лучше уточнить у живого отельера — вопрос уже передан, "
        "ответ появится в кабинете. Можете написать «живой человек»."
    )
    return f"{extra} {tail}".strip() if extra else tail


def post_booking_ask(guest_id: str, hotel_id: str, text: str) -> dict:
    """Вопрос после оплаты: база отельера (RAG), Fact Agent или живой отельер."""
    from common.post_booking_routing import FACT_AGENT_CARDS, is_fact_agent_question, is_hotel_kb_question
    from search.service import post_booking_fact_answer

    account = _require(guest_id)
    if account["role"] != "guest":
        raise ValueError("Вопрос после брони задаёт гость")
    hotel = _resolve_hotel(hotel_id)
    if hotel is None:
        raise ValueError("Этого отеля нет среди зарегистрированных")
    body = text.strip()
    if not body:
        raise ValueError("Пустой вопрос")
    paid = _latest_paid_booking(guest_id, hotel_id)
    if paid is None:
        raise ValueError("Сначала оплатите бронь по этому отелю")

    hotel_name = paid.get("hotel_name") or hotel.get("name") or hotel_id
    header = (
        f"Вы забронировали {hotel_name}, {paid['check_in']} — {paid['check_out']}. "
        f"Отвечаем на ваш вопрос: {body}"
    )
    dates = paid["check_in"]
    if paid["check_out"] and paid["check_out"] != paid["check_in"]:
        dates = f"{paid['check_in']}/{paid['check_out']}"

    from common.post_booking_routing import is_quiet_side_question
    from search.service import quiet_side_reply

    faq_result = faq_answer(hotel_id, body)
    if is_quiet_side_question(body):
        fact_text, known = quiet_side_reply(hotel_id)
        if known:
            return {
                "header": header,
                "reply": fact_text,
                "route": "fact_agent",
                "question": body,
                "hotel_id": hotel_id,
                "booking": paid,
            }
        if faq_result.get("mode") == "answer":
            return {
                "header": header,
                "reply": faq_result.get("message") or "",
                "route": "hotelier",
                "question": body,
                "hotel_id": hotel_id,
                "booking": paid,
            }
        return {
            "header": header,
            "reply": fact_text,
            "route": "agent",
            "suggest_hotelier_chat": True,
            "question": body,
            "hotel_id": hotel_id,
            "booking": paid,
        }

    if faq_result.get("mode") == "human":
        ask(guest_id, hotel_id, body)
        return {
            "header": header,
            "reply": _live_hotelier_reply(),
            "route": "hotelier",
            "question": body,
            "hotel_id": hotel_id,
            "booking": paid,
        }

    fact_first = is_fact_agent_question(body) and not is_hotel_kb_question(body)
    if fact_first:
        fact = post_booking_fact_answer(hotel_id, body, dates)
        reply = (fact.get("reply") or "").strip()
        if reply and not fact.get("weak"):
            return {
                "header": header,
                "reply": reply,
                "route": "fact_agent",
                "question": body,
                "hotel_id": hotel_id,
                "booking": paid,
            }
        if fact.get("weak") and is_quiet_side_question(body):
            if faq_result.get("mode") == "answer":
                return {
                    "header": header,
                    "reply": faq_result.get("message") or "",
                    "route": "hotelier",
                    "question": body,
                    "hotel_id": hotel_id,
                    "booking": paid,
                }
            reply, _ = quiet_side_reply(hotel_id)
            return {
                "header": header,
                "reply": reply,
                "route": "agent",
                "suggest_hotelier_chat": True,
                "question": body,
                "hotel_id": hotel_id,
                "booking": paid,
            }

    if faq_result.get("mode") == "answer":
        return {
            "header": header,
            "reply": faq_result.get("message") or "",
            "route": "hotelier",
            "question": body,
            "hotel_id": hotel_id,
            "booking": paid,
        }

    if not fact_first:
        fact = post_booking_fact_answer(hotel_id, body, dates)
        reply = (fact.get("reply") or "").strip()
        low = reply.lower()
        if reply and not fact.get("weak") and "не знаем" not in low:
            return {
                "header": header,
                "reply": reply,
                "route": "fact_agent",
                "question": body,
                "hotel_id": hotel_id,
                "booking": paid,
            }

    ask(guest_id, hotel_id, body)
    cards_hint = f"Fact Agent отвечает по картам: {FACT_AGENT_CARDS}."
    return {
        "header": header,
        "reply": _live_hotelier_reply(
            f"По открытым данным и базе отеля однозначного ответа нет. {cards_hint}"
        ),
        "route": "hotelier",
        "question": body,
        "hotel_id": hotel_id,
        "booking": paid,
    }


def ask(guest_id: str, hotel_id: str, text: str) -> dict:
    from common.post_booking_routing import is_quiet_side_question
    from search.service import quiet_side_reply

    account = _require(guest_id)
    if account["role"] != "guest":
        raise ValueError("Вопрос отелю пишет гость")
    if _resolve_hotel(hotel_id) is None:
        raise ValueError("Этого отеля нет среди зарегистрированных")
    body = text.strip()
    if not body:
        raise ValueError("Пустой вопрос")
    faq_result = faq_answer(hotel_id, body)
    with connect() as conn:
        _insert_message(
            conn,
            hotel_id=hotel_id,
            guest_id=guest_id,
            author_role="guest",
            author_id=guest_id,
            body=body,
        )
        mode = faq_result.get("mode")
        if is_quiet_side_question(body):
            fact_text, known = quiet_side_reply(hotel_id)
            if known:
                _insert_message(
                    conn,
                    hotel_id=hotel_id,
                    guest_id=guest_id,
                    author_role="hotelier",
                    author_id="hotel-kb",
                    body=fact_text,
                )
            elif mode == "answer":
                _insert_message(
                    conn,
                    hotel_id=hotel_id,
                    guest_id=guest_id,
                    author_role="hotelier",
                    author_id="hotel-kb",
                    body=faq_result.get("message") or "",
                )
            else:
                note = faq_result.get("message") or "Передал живому отельеру."
                _insert_message(
                    conn,
                    hotel_id=hotel_id,
                    guest_id=guest_id,
                    author_role="hotelier",
                    author_id="hotel-kb",
                    body=f"{fact_text} {note}".strip(),
                )
        elif mode == "answer":
            _insert_message(
                conn,
                hotel_id=hotel_id,
                guest_id=guest_id,
                author_role="hotelier",
                author_id="hotel-kb",
                body=faq_result.get("message") or "",
            )
        elif mode in {"escalate", "human"}:
            note = faq_result.get("message") or "Передал живому отельеру."
            _insert_message(
                conn,
                hotel_id=hotel_id,
                guest_id=guest_id,
                author_role="hotelier",
                author_id="hotel-kb",
                body=note,
            )
        elif mode == "geo_redirect":
            _insert_message(
                conn,
                hotel_id=hotel_id,
                guest_id=guest_id,
                author_role="hotelier",
                author_id="hotel-kb",
                body=(
                    "По картам Fact Agent на главной можно уточнить гео и окружение. "
                    "Здесь отвечаю как отельер: напишите «живой человек», если нужен сотрудник."
                ),
            )
    return {"threads": {hotel_id: _messages(hotel_id)}, "faq": faq_result}


def send_reply(account_id: str, text: str) -> dict:
    account = _require(account_id)
    if account["role"] != "hotelier" or not account.get("hotel_id"):
        raise ValueError("Отвечает счёт отельера")
    body = text.strip()
    if not body:
        raise ValueError("Пустой ответ")
    hotel_id = account["hotel_id"]
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO messages (hotel_id, guest_id, author_role, author_id, body, created_at)
            VALUES (?, NULL, 'hotelier', ?, ?, ?)
            """,
            (hotel_id, account_id, body, _now()),
        )
    return {"threads": {hotel_id: _messages(hotel_id)}}


def quote(check_in: str, check_out: str) -> int:
    start = date.fromisoformat(check_in)
    end = date.fromisoformat(check_out)
    nights = (end - start).days
    if nights < 1 or nights > 30:
        raise ValueError("Нужны даты: от 1 до 30 ночей")
    return nights


def pay(guest_id: str, hotel_id: str, check_in: str, check_out: str) -> dict:
    account = _require(guest_id)
    if account["role"] != "guest":
        raise ValueError("Бронь оплачивает гость")
    hotel = _resolve_hotel(hotel_id)
    if hotel is None:
        raise ValueError("Этого отеля нет среди зарегистрированных")
    nights = quote(check_in, check_out)
    amount = nights * NIGHT_RUB
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO bookings (
                guest_id, hotel_id, check_in, check_out, nights, amount_rub, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'paid', ?)
            """,
            (guest_id, hotel_id, check_in, check_out, nights, amount, _now()),
        )
        booking_id = cursor.lastrowid
    booking = next(item for item in _bookings(guest_id=guest_id) if item["id"] == booking_id)
    return {"booking": booking, "payment_note": PAYMENT_NOTE}
