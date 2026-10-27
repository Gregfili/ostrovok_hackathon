"""Счета гостя и отельера. Пароля нет: хакатон не проверяет личность.

Оплата записывает бронь как оплаченную. Карта не читается, деньги не списываются.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import case, func, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from common.database import session_scope
from common.db import init_db
from common.tables import Account, Booking, HotelRegistration, Message
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


def _account_row(row: Account) -> dict:
    return {
        "id": row.id,
        "role": row.role,
        "name": row.name,
        "hotel_id": row.hotel_id,
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


def _registrations(session) -> list[dict]:
    rows = session.scalars(select(HotelRegistration).order_by(HotelRegistration.id)).all()
    return [
        {
            "account_id": row.account_id,
            "name": row.name,
            "address": row.address or "",
            "hotel_id": row.hotel_id,
        }
        for row in rows
    ]


def _resolve_hotel(hotel_id: str) -> dict | None:
    found = get_hotel(hotel_id)
    if found:
        return found
    init_db()
    with session_scope() as session:
        row = session.scalar(select(HotelRegistration).where(HotelRegistration.hotel_id == hotel_id))
    if row is None:
        return None
    return {"id": row.hotel_id, "name": row.name, "address": row.address or ""}


def list_accounts() -> dict:
    init_db()
    with session_scope() as session:
        guest_first = case((Account.role == "guest", 0), else_=1)
        rows = session.scalars(select(Account).order_by(guest_first, Account.name)).all()
        registrations = _registrations(session)
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
    with session_scope() as session:
        if matched:
            hotel_id = matched
            account_id = f"hotelier-{hotel_id}"
        else:
            seq = session.scalar(select(func.count()).select_from(HotelRegistration)) + 1
            hotel_id = f"registered-{seq}"
            while session.scalar(select(HotelRegistration.id).where(HotelRegistration.hotel_id == hotel_id)):
                seq += 1
                hotel_id = f"registered-{seq}"
            account_id = f"hotelier-{hotel_id}"
        existing = session.scalar(select(HotelRegistration).where(HotelRegistration.hotel_id == hotel_id))
        if existing is None:
            stmt = sqlite_insert(Account).values(
                id=account_id,
                role="hotelier",
                name=f"Отельер · {clean}",
                hotel_id=hotel_id,
            )
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=[Account.id],
                    set_={"name": stmt.excluded.name, "hotel_id": stmt.excluded.hotel_id},
                )
            )
            session.add(
                HotelRegistration(
                    account_id=account_id,
                    name=clean,
                    address=place,
                    hotel_id=hotel_id,
                    created_at=_now(),
                )
            )
        else:
            account_id = existing.account_id
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
    with session_scope() as session:
        seq = session.scalar(select(func.count()).select_from(Account).where(Account.role == "guest")) + 1
        account_id = f"guest-{seq}"
        while session.get(Account, account_id) is not None:
            seq += 1
            account_id = f"guest-{seq}"
        session.add(Account(id=account_id, role="guest", name=clean, hotel_id=None))
    return {"id": account_id, "role": "guest", "name": clean, "hotel_id": None}


def _require(account_id: str) -> dict:
    init_db()
    with session_scope() as session:
        row = session.get(Account, account_id)
    if row is None:
        raise ValueError("Такого счёта нет")
    return _account_row(row)


def _messages(hotel_id: str, viewer: str = "") -> list[dict]:
    with session_scope() as session:
        query = (
            select(Message, Account.name)
            .outerjoin(Account, Account.id == Message.author_id)
            .where(Message.hotel_id == hotel_id)
            .order_by(Message.id)
        )
        if viewer in ("guest", "hotelier"):
            query = query.where(Message.author_role != "system")
        if viewer == "guest":
            query = query.where(Message.hidden_for_guest == 0)
        elif viewer == "hotelier":
            query = query.where(Message.hidden_for_hotelier == 0)
        rows = session.execute(query).all()
    return [
        {
            "id": message.id,
            "hotel_id": message.hotel_id,
            "guest_id": message.guest_id,
            "author_role": message.author_role,
            "author_id": message.author_id,
            "author_name": author_name or "Hotel Fact Agent",
            "body": message.body,
            "created_at": message.created_at,
        }
        for message, author_name in rows
    ]


def _bookings(guest_id: str | None = None, hotel_id: str | None = None) -> list[dict]:
    with session_scope() as session:
        query = select(Booking).order_by(Booking.id.desc())
        if guest_id:
            query = query.where(Booking.guest_id == guest_id)
        if hotel_id:
            query = query.where(Booking.hotel_id == hotel_id)
        rows = session.scalars(query).all()
        registrations = _registrations(session)
    hotels = {hotel["id"]: hotel for hotel in list_hotels()}
    for item in registrations:
        hotels.setdefault(item["hotel_id"], {"name": item["name"]})
    items = []
    for row in rows:
        hotel = hotels.get(row.hotel_id) or {}
        items.append(
            {
                "id": row.id,
                "guest_id": row.guest_id,
                "hotel_id": row.hotel_id,
                "hotel_name": hotel.get("name") or row.hotel_id,
                "check_in": row.check_in,
                "check_out": row.check_out,
                "nights": row.nights,
                "amount_rub": row.amount_rub,
                "status": row.status,
                "created_at": row.created_at,
            }
        )
    return items


def desk(account_id: str) -> dict:
    account = _require(account_id)
    hotel_id = account.get("hotel_id")
    if account["role"] == "guest":
        hotel_ids = [hotel["id"] for hotel in list_accounts()["hotels"]]
        threads = {hotel_id: _messages(hotel_id, viewer="guest") for hotel_id in hotel_ids}
        bookings = _bookings(guest_id=account_id)
    else:
        threads = {hotel_id: _messages(hotel_id, viewer="hotelier")} if hotel_id else {}
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
    with session_scope() as session:
        last = session.scalar(select(Message).where(Message.hotel_id == hotel_id).order_by(Message.id.desc()).limit(1))
        if last and last.author_role == "agent" and last.body == text:
            return
        session.add(
            Message(
                hotel_id=hotel_id,
                guest_id=None,
                author_role="system",
                author_id="hotel-fact-agent",
                body=text,
                created_at=_now(),
            )
        )


def _insert_message(
    session,
    *,
    hotel_id: str,
    guest_id: str | None,
    author_role: str,
    author_id: str,
    body: str,
) -> None:
    session.add(
        Message(
            hotel_id=hotel_id,
            guest_id=guest_id,
            author_role=author_role,
            author_id=author_id,
            body=body,
            created_at=_now(),
        )
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

    if is_quiet_side_question(body):
        fact_text, known = quiet_side_reply(hotel_id)
        payload = {
            "header": header,
            "reply": fact_text,
            "route": "fact_agent" if known else "agent",
            "question": body,
            "hotel_id": hotel_id,
            "booking": paid,
        }
        if not known:
            payload["suggest_hotelier_chat"] = True
        return payload

    faq_result = faq_answer(hotel_id, body)
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

    fact = None
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

    if is_hotel_kb_question(body) and faq_result.get("mode") == "answer":
        return {
            "header": header,
            "reply": faq_result.get("message") or "",
            "route": "hotelier",
            "question": body,
            "hotel_id": hotel_id,
            "booking": paid,
        }

    if fact is None:
        fact = post_booking_fact_answer(hotel_id, body, dates)
    reply = (fact.get("reply") or "").strip()
    if _usable_guest_reply(reply):
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


def _usable_guest_reply(reply: str) -> bool:
    text = (reply or "").strip()
    if len(text) < 8:
        return False
    low = text.lower()
    return low not in {"отель.", "отель"} and not low.endswith(". отель.")


def _chat_pair(guest_id: str, hotel_id: str, question: str, reply: str, author_id: str) -> dict:
    with session_scope() as session:
        _insert_message(
            session,
            hotel_id=hotel_id,
            guest_id=guest_id,
            author_role="guest",
            author_id=guest_id,
            body=question,
        )
        _insert_message(
            session,
            hotel_id=hotel_id,
            guest_id=guest_id,
            author_role="hotelier",
            author_id=author_id,
            body=reply,
        )
    return {"threads": {hotel_id: _messages(hotel_id, viewer="guest")}, "faq": {"mode": author_id}}


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
    if is_quiet_side_question(body):
        fact_text, _known = quiet_side_reply(hotel_id)
        return _chat_pair(guest_id, hotel_id, body, fact_text, "fact-snapshot")
    from common.post_booking_routing import is_fact_agent_question, is_hotel_kb_question
    from search.service import post_booking_fact_answer

    if is_fact_agent_question(body) and not is_hotel_kb_question(body):
        paid = _latest_paid_booking(guest_id, hotel_id)
        dates = ""
        if paid:
            dates = paid["check_in"]
            if paid.get("check_out") and paid["check_out"] != paid["check_in"]:
                dates = f"{paid['check_in']}/{paid['check_out']}"
        fact = post_booking_fact_answer(hotel_id, body, dates)
        reply = (fact.get("reply") or "").strip()
        if not _usable_guest_reply(reply):
            reply = "Этого в снимке нет."
        return _chat_pair(guest_id, hotel_id, body, reply, "fact-snapshot")
    faq_result = faq_answer(hotel_id, body)
    mode = faq_result.get("mode")
    if mode == "answer":
        reply = faq_result.get("message") or "В базе знаний нет ответа."
        author = "hotel-kb"
    elif mode in {"escalate", "human"}:
        reply = faq_result.get("message") or "Передал живому отельеру."
        author = "hotelier-live"
    else:
        reply = "Этого нет ни в снимке, ни в базе знаний. Вопрос передан живому отельеру."
        author = "hotelier-live"
    return _chat_pair(guest_id, hotel_id, body, reply, author)


def send_reply(account_id: str, text: str) -> dict:
    account = _require(account_id)
    if account["role"] != "hotelier" or not account.get("hotel_id"):
        raise ValueError("Отвечает счёт отельера")
    body = text.strip()
    if not body:
        raise ValueError("Пустой ответ")
    hotel_id = account["hotel_id"]
    with session_scope() as session:
        guest_id = session.scalar(
            select(Message.guest_id)
            .where(
                Message.hotel_id == hotel_id,
                Message.author_role == "guest",
                Message.guest_id.is_not(None),
            )
            .order_by(Message.id.desc())
            .limit(1)
        )
        _insert_message(
            session,
            hotel_id=hotel_id,
            guest_id=guest_id,
            author_role="hotelier",
            author_id=account_id,
            body=body,
        )
    return {"threads": {hotel_id: _messages(hotel_id, viewer="hotelier")}}


def hide_message(account_id: str, message_id: int, scope: str) -> dict:
    account = _require(account_id)
    if scope not in ("me", "both"):
        raise ValueError("Нужно выбрать, у кого скрыть сообщение")
    with session_scope() as session:
        row = session.get(Message, message_id)
        if row is None:
            raise ValueError("Этого сообщения нет")
        if account["role"] == "guest":
            if row.guest_id != account_id:
                raise ValueError("Этого сообщения в вашем чате нет")
            row.hidden_for_guest = 1
            if scope == "both":
                row.hidden_for_hotelier = 1
        elif account["role"] == "hotelier" and row.hotel_id == account.get("hotel_id"):
            row.hidden_for_hotelier = 1
            if scope == "both":
                row.hidden_for_guest = 1
        else:
            raise ValueError("Этого сообщения в вашем чате нет")
    return desk(account_id)


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
    with session_scope() as session:
        booking_row = Booking(
            guest_id=guest_id,
            hotel_id=hotel_id,
            check_in=check_in,
            check_out=check_out,
            nights=nights,
            amount_rub=amount,
            status="paid",
            created_at=_now(),
        )
        session.add(booking_row)
        session.flush()
        booking_id = booking_row.id
    booking = next(item for item in _bookings(guest_id=guest_id) if item["id"] == booking_id)
    return {"booking": booking, "payment_note": PAYMENT_NOTE}
