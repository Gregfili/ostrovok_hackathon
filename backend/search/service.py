"""Слоты фразы и сборка ответа. Магазины и клубы не идут в Noise Agent."""

from __future__ import annotations

import re

from dialogue.voice import guest_reply
from gateway.orchestrator import build_dossier
from hotel_fact_agent.decompose import base_card, named_hotel, nightclub, resolve, shopping
from view.sun import _GENITIVE, stay_text


def ping() -> dict:
    return {"status": "ok", "service": "search"}


def _minutes(text: str) -> int | None:
    match = re.search(r"(\d+)\s*минут", text.lower())
    return int(match.group(1)) if match else None


_CARD_WORDS = (
    ("base", ("базов",)),
    ("ecology", ("эколог",)),
    ("health", ("здоров", "аптек", "клиник", "больниц", "дежур")),
    ("shopping", ("шоп", "покуп", "подар")),
    ("entertainment", ("развлеч", "клуб")),
)
_CARD_ORDER = ("base", "ecology", "health", "shopping", "entertainment")


def _last_line(query: str) -> str:
    lines = [line.strip() for line in query.splitlines() if line.strip()]
    return lines[-1] if lines else query.strip()


def _ordered_cards(text: str) -> list[str]:
    low = text.lower()
    found = {card for card, words in _CARD_WORDS if any(word in low for word in words)}
    if "base" not in found and "информац" in low and "отел" in low:
        found.add("base")
    return [card for card in _CARD_ORDER if card in found]


def _place_search(text: str) -> bool:
    low = text.lower()
    if _minutes(text) is not None:
        return True
    return any(word in low for word in ("тих", "quiet", "булгак", "нехорош", "квартир"))


def _hotel_name(hotel_id: str) -> str:
    from geo.service import get_hotel

    hotel = get_hotel(hotel_id)
    return (hotel or {}).get("name") or hotel_id


def answer(query: str, dates: str = "", hotel_id: str = "", guest_id: str = "") -> dict:
    dates = _resolve_dates(query, dates)
    guest_id = guest_id.strip()
    hotel_id = hotel_id.strip()
    if guest_id and hotel_id and _guest_has_paid(guest_id, hotel_id):
        return _paid_guest_answer(query, dates, guest_id, hotel_id)
    last = _last_line(query)
    cards = _ordered_cards(last)
    if cards and not _place_search(last) and not _chosen_anywhere(query):
        return _menu(query, dates, cards, hotel_id)
    question = _pending_question(query, dates)
    if question and not _chosen_on_last(last):
        return _questions_first(query, dates, question)
    result = resolve(query)
    result["dates"] = dates
    if result["dates"]:
        result["dates_note"] = (
            "Даты приняты. Снимок магазинов и клубов по датам ещё не фильтруется."
        )
    anchor = result.get("answers", {}).get("hotel")
    if not isinstance(anchor, dict):
        anchor = None
    result["slots"] = {
        "anchor_id": anchor.get("id") if anchor else None,
        "max_minutes": _minutes(query),
        "quiet": any(word in query.lower() for word in ("тих", "quiet")),
        "dates": result["dates"],
    }
    result["dossier"] = build_dossier(anchor, result["dates"])
    kept, dropped = _rank(result["dossier"].get("hotels") or [], result["slots"])
    result["dossier"]["hotels"] = kept
    result["dropped"] = dropped
    locked = _chosen_anywhere(query) or ""
    if locked:
        result["dialogue"] = _funnel(result, locked, guest_id.strip())
        return result
    chosen = _chosen_on_last(last)
    if _offer_now(query, last, dates):
        result["dialogue"] = _dialogue(result)
    else:
        result["dialogue"] = _about_turn(result, hotel_id or chosen)
    lead_cards = [card for card in cards if card in ("base", "ecology", "health")]
    lead = _lead_lines(query, lead_cards, hotel_id)
    if lead:
        result["dialogue"]["reply"] = " ".join(lead + [result["dialogue"]["reply"]]).strip()
        result["dialogue"]["cards"] = cards
    if "base" in cards:
        result["dialogue"]["sheet"] = _base_sheet(
            base_card(query, named_hotel(query) or hotel_id.strip() or "pekin")
        )
    _attach_pick_hotel_cta(result.get("dialogue"), query)
    return result


def _attach_pick_hotel_cta(dialogue: dict | None, query: str) -> None:
    if not dialogue or dialogue.get("waiting"):
        return
    if _chosen_on_last(_last_line(query)):
        return
    hotels = dialogue.get("hotels") or []
    if not hotels or dialogue.get("follow_up"):
        return
    dialogue["follow_up"] = "Выберите отель справа."


def _wants_stay(query: str) -> bool:
    low = query.lower()
    return _place_search(query) or "отел" in low or "hotel" in low


def _resolve_dates(query: str, dates: str) -> str:
    clean = (dates or "").strip()
    if clean:
        return clean
    return stay_text(query) or stay_text(_last_line(query)) or ""


def _purpose(query: str) -> str | None:
    low = query.lower()
    last = _last_line(query).lower()
    if any(word in last for word in ("командир", "деловая", "бизнес", "работ")):
        return "командировка"
    if any(word in last for word in ("отдых", "отпуск", "отдохн")):
        return "отдых"
    if any(word in low for word in ("командир", "деловая", "бизнес")):
        return "командировка"
    if any(word in low for word in ("отдых", "отпуск", "отдохн")):
        return "отдых"
    return None


_CHOICE = ("выбира", "беру", "возьму", "оставлю", "подход", "останавлива")


def _chosen_on_last(last: str) -> str | None:
    hotel = named_hotel(last)
    if not hotel:
        return None
    low = last.lower()
    if any(word in low for word in _CHOICE):
        return hotel
    words = re.findall(r"[a-zа-яё0-9]+", low)
    skip = {"хорошо", "да", "ок", "окей", "давайте", "тогда", "этот", "отель", "мне", "я"}
    left = [word for word in words if word not in skip]
    return hotel if len(left) <= 2 else None


def _chosen_anywhere(query: str) -> str | None:
    found = None
    for line in query.splitlines():
        chosen = _chosen_on_last(line.strip())
        if chosen:
            found = chosen
    return found


def _closing_intake(last: str) -> bool:
    if _chosen_on_last(last) or not _purpose(last):
        return False
    low = last.lower()
    if any(word in low for word in ("тих", "булгак", "шоп", "клуб", "отел", "минут", "выбира")):
        return False
    return len(last) < 40


def _offer_now(query: str, last: str, dates: str = "") -> bool:
    if _chosen_on_last(last) or _pending_question(query, dates):
        return False
    if _closing_intake(last):
        return True
    return len([line for line in query.splitlines() if line.strip()]) == 1


def _pending_question(query: str, dates: str = "") -> str | None:
    if not _wants_stay(query):
        return None
    dates = _resolve_dates(query, dates)
    if not dates:
        return "На какие даты заезд и выезд?"
    if not _purpose(query):
        return "Это отдых или командировка?"
    return None


def _stay_phrase(dates: str) -> str:
    if not dates:
        return ""

    def one(iso: str) -> tuple[int, int]:
        _year, month, day = iso.split("-")
        return int(day), int(month)

    parts = dates.split("/")
    start_day, start_month = one(parts[0])
    if len(parts) == 1:
        return f"{start_day} {_GENITIVE[start_month]}"
    end_day, end_month = one(parts[-1])
    if start_month == end_month:
        return f"{start_day}–{end_day} {_GENITIVE[start_month]}"
    return f"{start_day} {_GENITIVE[start_month]} – {end_day} {_GENITIVE[end_month]}"


def _heard(query: str) -> str:
    low = query.lower()
    words = ["тихий"] if any(word in low for word in ("тих", "quiet")) else []
    words.append("отель")
    if "булгак" in low or "нехорош" in low:
        words.append("у булгаковских мест")
    extras = []
    if any(word in low for word in ("шоп", "покуп", "подар")):
        extras.append("днём магазины")
    if any(word in low for word in ("клуб", "развлеч", "вечер")):
        extras.append("вечером клуб")
    text = " ".join(words)
    if extras:
        text += ", " + " и ".join(extras)
    return text[:1].upper() + text[1:] + "."


def _questions_first(query: str, dates: str, question: str) -> dict:
    dates = _resolve_dates(query, dates)
    if dates:
        reply = f"{_stay_phrase(dates)} принял. {_heard(query)}"
    else:
        reply = _heard(query)
    return {
        "query": query,
        "dates": dates,
        "parts": [],
        "answers": {},
        "slots": {
            "anchor_id": None,
            "max_minutes": _minutes(query),
            "quiet": any(word in query.lower() for word in ("тих", "quiet")),
            "dates": dates,
            "cards": [],
            "hotel_id": None,
        },
        "dossier": {"hotels": [], "recipes": [], "note": "Сначала вопросы, отели после ответов."},
        "dropped": [],
        "dialogue": {
            "reply": reply,
            "asks_user": [question],
            "hotels": [],
            "hotelier_question": None,
            "cards": [],
            "sheet": None,
            "waiting": True,
        },
    }


def _menu(query: str, dates: str, cards: list[str], hotel_id: str) -> dict:
    subject = named_hotel(query) or hotel_id or None
    lines: list[str] = []
    answers: dict = {}
    open_cards = list(cards)
    if any(card in open_cards for card in ("ecology", "health")) and not subject:
        lines.append("По какому отелю открыть карту?")
        open_cards = [card for card in open_cards if card not in ("ecology", "health")]
    for card in open_cards:
        if card == "base":
            payload = base_card(query, subject or "pekin")
            answers["base"] = payload
            lines.extend(_base_lines(payload))
        elif card == "ecology":
            lines.extend(_ecology_lines(subject or ""))
            answers["ecology"] = {"hotel_id": subject}
        elif card == "health":
            lines.extend(_health_lines(subject or ""))
            answers["health"] = {"hotel_id": subject, "value": "не знаем"}
        elif card == "shopping":
            payload = shopping()
            answers["shopping"] = payload
            names = _and_list([item["name"] for item in payload.get("results") or []])
            lines.append(f"Днём можно зайти в {names}." if names else "Дневных магазинов в снимке нет.")
        elif card == "entertainment":
            payload = nightclub()
            answers["entertainment"] = payload
            lines.extend(_evening_lines(payload))
    return {
        "query": query,
        "dates": dates,
        "parts": cards,
        "answers": answers,
        "slots": {
            "anchor_id": None,
            "max_minutes": None,
            "quiet": False,
            "dates": dates,
            "card": cards[0],
            "cards": cards,
            "hotel_id": subject,
        },
        "dossier": {
            "hotels": [],
            "recipes": [],
            "note": "Открыты запрошенные карты. Остальной поиск не запускался.",
        },
        "dropped": [],
        "dialogue": {
            "reply": " ".join(lines),
            "asks_user": [],
            "hotels": [],
            "hotelier_question": None,
            "cards": cards,
            "sheet": _base_sheet(answers.get("base")),
        },
    }


def _lead_lines(query: str, cards: list[str], hotel_id: str) -> list[str]:
    if not cards:
        return []
    subject = named_hotel(query) or hotel_id or None
    lines: list[str] = []
    if "base" in cards:
        lines.extend(_base_lines(base_card(query, subject or "pekin")))
    if "ecology" in cards:
        if subject:
            lines.extend(_ecology_lines(subject))
        else:
            lines.append("По какому отелю открыть экологию?")
    if "health" in cards:
        if subject:
            lines.extend(_health_lines(subject))
        else:
            lines.append("По какому отелю открыть карту здоровья?")
    return lines


def _ecology_lines(hotel_id: str) -> list[str]:
    reply, _known = quiet_side_reply(hotel_id)
    return [reply]


def quiet_side_reply(hotel_id: str) -> tuple[str, bool]:
    """Ответ про тишину сторон. known=True — есть вывод по снимку."""
    from noise.service import for_hotel

    fact = for_hotel({"hotel_id": hotel_id})
    label = (fact.data or {}).get("quieter_label")
    if label:
        side = _guest_side(label)
        text = f"По снимку окружения тише {side or label.lower()}. Это не замер шума в номере."
        return text, True
    return (
        "Какая сторона тише, по открытым данным пока не ясно. "
        "Но вы можете спросить об этом у отельера — сначала ответит база знаний отеля, "
        "если там нет точного ответа, подключится живой человек.",
        False,
    )


def _health_lines(hotel_id: str) -> list[str]:
    name = _hotel_name(hotel_id)
    return [f"Здоровье, {name}. Аптеку и клинику рядом пока не нашли."]


def _base_lines(card: dict) -> list[str]:
    if not card or card.get("status") != "snapshot":
        return ["По этому отелю базовой карточки нет."]
    metro = card.get("metro") or {}
    review = card.get("review") or {}
    guru = ", GURU" if card.get("guru") else ""
    label = str(card.get("rating_label") or "").lower()
    return [
        (
            f"{card.get('name')}, {card.get('stars')} звезды{guru}. "
            f"{card.get('district')}, {card.get('address')}. "
            f"От центра {card.get('center')}, метро {metro.get('name')} {metro.get('distance')}. "
            f"От {card.get('price_from')}."
        ),
        (
            f"Оценка {card.get('rating')}, {label}, {card.get('reviews')} отзывов. "
            f"{card.get('badge')}. "
            f"{review.get('author')}: «{review.get('text')}»."
        ),
        "Удобства: " + ", ".join(card.get("amenities") or []) + ".",
    ]


def _base_sheet(card: dict | None) -> dict | None:
    if not card or card.get("status") != "snapshot":
        return None
    sections = [
        ("Рядом", card.get("nearby") or []),
        ("Вокруг", card.get("around") or []),
        ("Достопримечательности", card.get("sights") or []),
        ("Аэропорты", card.get("airports") or []),
        ("Вокзалы", card.get("stations") or []),
    ]
    return {
        "title": card.get("name"),
        "address": card.get("address"),
        "image": _hotel_photo(card.get("hotel_id")),
        "sections": [{"title": title, "items": items} for title, items in sections if items],
    }


def _hotel_photo(hotel_id: str | None) -> dict | None:
    if not hotel_id:
        return None
    from geo.service import get_hotel

    hotel = get_hotel(hotel_id) or {}
    if not hotel.get("image"):
        return None
    return {
        "src": hotel.get("image"),
        "credit": hotel.get("image_credit"),
        "source": hotel.get("image_source"),
    }


def _dialogue(result: dict) -> dict:
    answers = result.get("answers") or {}
    parts = result.get("parts") or []
    lines: list[str] = []
    asks: list[str] = []

    hotel = answers.get("hotel")
    if (
        isinstance(hotel, dict)
        and hotel.get("status") == "ask"
        and not named_hotel(result.get("query") or "")
        and _place_search(result.get("query") or "")
    ):
        asks.append("Напишите адрес или известное место.")

    if "excursion" in parts:
        lines.append("Экскурсию не составляю.")

    hotels = ((result.get("dossier") or {}).get("hotels") or [])[:3]
    if hotels:
        lines.append(_hotel_offer(result.get("query") or "", hotels, result.get("dates") or ""))
    elif "hotel" in parts:
        lines.append("Подходящих отелей нет.")
    for item in result.get("dropped") or []:
        lines.append(
            f"{item['name']} не берём: {int(item['minutes'])} {_minute_word(int(item['minutes']))} пешком, вы просили до {item['limit']}."
        )

    shops = (answers.get("shopping") or {}).get("results") or []
    if shops:
        lines.append("Днём можно зайти в " + _and_list([item["name"] for item in shops]) + ".")

    if answers.get("nightclub"):
        lines.append(" ".join(_evening_lines(answers["nightclub"])))

    if "hotel" in parts and not result.get("dates") and not _has_date(result.get("query") or ""):
        asks.append("На какие даты заезд и выезд?")

    question = _hotelier_question(result, hotels)
    if not lines and not asks:
        lines.append("Напишите, какой отель посмотреть или какую карту открыть.")

    return {
        "reply": "\n\n".join(lines),
        "asks_user": asks,
        "hotels": hotels,
        "hotelier_question": question,
    }


def _has_date(text: str) -> bool:
    months = ("январ", "феврал", "март", "апрел", "мая", "май", "июн", "июл", "август", "сентябр", "октябр", "ноябр", "декабр")
    low = text.lower()
    return any(month in low for month in months)


def _fact(hotel: dict, feature: str) -> dict | None:
    for fact in hotel.get("facts") or []:
        if fact.get("feature") == feature:
            return fact
    return None


def _minute_word(count: int) -> str:
    number = abs(int(count))
    if number % 10 == 1 and number % 100 != 11:
        return "минута"
    if number % 10 in (2, 3, 4) and number % 100 not in (12, 13, 14):
        return "минуты"
    return "минут"


def _and_list(names: list[str]) -> str:
    if len(names) <= 1:
        return names[0] if names else ""
    return ", ".join(names[:-1]) + " и " + names[-1]


def _evening_lines(payload: dict) -> list[str]:
    names = [item["name"] for item in payload.get("results") or []]
    lines = []
    if len(names) == 1:
        lines.append(f"Вечером открыт {names[0]}.")
    elif names:
        lines.append("Вечером открыты " + _and_list(names) + ".")
    for closed in payload.get("not_recommended") or []:
        lines.append(f"{closed['name']} сейчас закрыт.")
    if not lines:
        lines.append("Вечерних клубов в снимке нет.")
    return lines


def _guest_side(label: str | None) -> str | None:
    if label == "Противоположная сторона":
        return "не со стороны улицы"
    if label == "Улица":
        return "со стороны улицы"
    return None


def _walk_minutes(hotel: dict) -> int | None:
    minutes = ((_fact(hotel, "walk_to") or {}).get("data") or {}).get("minutes")
    if isinstance(minutes, (int, float)):
        return int(minutes)
    return None


def _hotel_offer(query: str, hotels: list[dict], dates: str = "") -> str:
    low = query.lower()
    if ("булгак" in low or "нехорош" in low) and any(word in low for word in ("тих", "quiet")):
        head = "Тихие отели у булгаковских мест."
    elif "булгак" in low or "нехорош" in low:
        head = "Отели у булгаковских мест."
    elif any(word in low for word in ("тих", "quiet")):
        head = "Тихие отели."
    else:
        head = "Подходят такие отели."
    when = _stay_phrase(dates)
    purpose = _purpose(query)
    if when and purpose:
        head = f"На {when}, {purpose}. {head}"
    elif when:
        head = f"На {when}. {head}"
    ordered = sorted(hotels, key=lambda hotel: _walk_minutes(hotel) if _walk_minutes(hotel) is not None else 10**9)
    sentences = [head]
    for hotel in ordered:
        sentences.append(_brief(hotel))
    return " ".join(sentences)


def _brief(hotel: dict) -> str:
    name = hotel.get("name") or hotel.get("id")
    minutes = _walk_minutes(hotel)
    side = _guest_side(((_fact(hotel, "facade_noise") or {}).get("data") or {}).get("quieter_label"))
    if minutes is None:
        walk = name
    else:
        walk = f"{name} — {minutes} {_minute_word(minutes)} пешком"
    if side:
        return f"{walk}, тише {side}."
    return f"{walk}."


def _sun_hours(hotel: dict) -> dict:
    data = (_fact(hotel, "facade_visibility") or {}).get("data") or {}
    hours = data.get("sun_hours") or {}
    return hours if isinstance(hours, dict) else {}


def _clock_span(label: str) -> float:
    if "нет" in label.lower():
        return 0
    total = 0.0
    for start, end in re.findall(r"(\d{1,2}):00[–-](\d{1,2}):00", label):
        begin, finish = int(start), int(end)
        if finish < begin:
            finish += 24
        total += finish - begin
    return total


def _sunnier(hotel: dict) -> str:
    sun = _sun_hours(hotel)
    if not sun:
        return ""
    title, label = max(sun.items(), key=lambda item: _clock_span(item[1]))
    if _clock_span(label) <= 0:
        return "Солнца на стены в эти даты нет."
    side = _guest_side(title)
    where = f"на стене {side}" if side else f"на {str(title).lower()}"
    clock = label.split(", к ")[0].replace("Солнце на стену ", "")
    return f"Больше солнца {where}: {clock}."


def _one_facts(hotel: dict, query: str) -> str:
    name = hotel.get("name") or hotel.get("id")
    bits = [f"{name}."]
    minutes = _walk_minutes(hotel)
    if minutes is not None:
        place = " до булгаковских мест" if any(word in query.lower() for word in ("булгак", "нехорош")) else ""
        bits.append(f"{minutes} {_minute_word(minutes)} пешком{place}.")
    side = _guest_side(((_fact(hotel, "facade_noise") or {}).get("data") or {}).get("quieter_label"))
    if side:
        bits.append(f"Тише {side}.")
    elif _fact(hotel, "facade_noise"):
        bits.append("Какая сторона тише, пока не ясно.")
    sun = _sunnier(hotel)
    if sun:
        bits.append(sun)
    return " ".join(bits)


def _spoken(result: dict, hotels: list[dict], fallback: str) -> dict:
    query = result.get("query") or ""
    when = _stay_phrase(result.get("dates") or "")
    facts = "\n".join(_one_facts(hotel, query) for hotel in hotels)
    if when:
        facts = f"Даты: {when}.\n{facts}"
    shops = ((result.get("answers") or {}).get("shopping") or {}).get("results") or []
    if shops:
        facts += "\nДнём: " + _and_list([item["name"] for item in shops]) + "."
    night = (result.get("answers") or {}).get("nightclub") or {}
    if night:
        facts += "\n" + " ".join(_evening_lines(night))
    return {
        "reply": guest_reply(query, facts, fallback),
        "asks_user": [],
        "hotels": hotels,
        "hotelier_question": _hotelier_question(result, hotels),
        "cards": [],
        "sheet": None,
    }


def _pay_intent(text: str) -> bool:
    low = text.lower()
    return any(word in low for word in ("оплат", "оплачи", "брон", "плачу", "зафиксир"))


def _register_line(hotel_name: str) -> str:
    return (
        f"Чтобы закрепить {hotel_name}, нажмите «Регистрация» в правом верхнем углу. "
        "Если аккаунт уже есть — войдите в него."
    )


def _entered(name: str) -> str:
    return (
        f"{name}, счёт открыт. До оплаты по этому отелю могу открыть экологию, "
        "шопинг, развлечения или здоровье. Базовую карточку Островка — после оплаты. "
        "Ночь в прототипе 10 000 ₽. Напишите карту или «оплатить»."
    )


def _guest_account(guest_id: str) -> dict | None:
    if not guest_id:
        return None
    from admin.service import _require

    try:
        account = _require(guest_id)
    except ValueError:
        return None
    if account.get("role") != "guest":
        return None
    return account


def _guest_has_paid(guest_id: str, hotel_id: str) -> bool:
    if not guest_id:
        return False
    from admin.service import _bookings
    from common.db import init_db

    init_db()
    rows = _bookings(guest_id=guest_id, hotel_id=hotel_id)
    return any(row.get("status") == "paid" for row in rows)


def _paid_guest_answer(query: str, dates: str, guest_id: str, hotel_id: str) -> dict:
    """Дополнительные вопросы на главной после оплаты — без воронки дат."""
    from admin.service import post_booking_ask

    last = _last_line(query)
    payload = post_booking_ask(guest_id, hotel_id, last)
    result = resolve(f"Отель {_hotel_name(hotel_id)}. {last}")
    result["dates"] = dates
    anchor = result.get("answers", {}).get("hotel")
    if not isinstance(anchor, dict):
        anchor = None
    result["slots"] = {
        "anchor_id": anchor.get("id") if anchor else None,
        "max_minutes": _minutes(query),
        "quiet": any(word in query.lower() for word in ("тих", "quiet")),
        "dates": dates,
        "hotel_id": hotel_id,
    }
    result["dossier"] = build_dossier(anchor, dates)
    hotels = [
        hotel
        for hotel in (result["dossier"].get("hotels") or [])
        if hotel.get("id") == hotel_id
    ]
    result["dossier"]["hotels"] = hotels[:1]
    result["dropped"] = []
    route = payload.get("route") or "agent"
    result["dialogue"] = {
        "reply": payload.get("reply") or "",
        "route": route,
        "asks_user": [],
        "hotels": hotels[:1],
        "hotelier_question": None,
        "cards": [],
        "sheet": None,
        "paid": True,
        "guest_id": guest_id,
        "waiting": False,
        "suggest_hotelier_chat": bool(payload.get("suggest_hotelier_chat")),
        "hotelier_chat_question": payload.get("question") if payload.get("suggest_hotelier_chat") else "",
    }
    return result


def _stay_bounds(dates: str) -> tuple[str, str]:
    from datetime import date, timedelta

    start, _, end = dates.partition("/")
    if not end or end == start:
        end = (date.fromisoformat(start) + timedelta(days=1)).isoformat()
    return start, end


def _card_text(hotel_id: str, card: str) -> str:
    if card == "ecology":
        return " ".join(_ecology_lines(hotel_id))
    if card == "health":
        return " ".join(_health_lines(hotel_id))
    if card == "shopping":
        names = _and_list([item["name"] for item in (shopping().get("results") or [])])
        return f"Шопинг рядом. Днём можно зайти в {names}." if names else "Дневных магазинов в снимке нет."
    if card == "entertainment":
        return " ".join(_evening_lines(nightclub()))
    return ""


def _hold(result: dict, hotel_id: str, reply: str, guest_id: str = "", paid: bool = False, sheet: dict | None = None) -> dict:
    found = [
        hotel
        for hotel in ((result.get("dossier") or {}).get("hotels") or [])
        if hotel.get("id") == hotel_id
    ][:1]
    return {
        "reply": reply,
        "asks_user": [],
        "hotels": found,
        "hotelier_question": _hotelier_question(result, found),
        "cards": [],
        "sheet": sheet,
        "guest_id": guest_id,
        "paid": paid,
    }


def _choice_facts(result: dict, hotel_id: str, hotel_name: str) -> str:
    query = result.get("query") or ""
    when = _stay_phrase(result.get("dates") or "")
    found = [
        hotel
        for hotel in ((result.get("dossier") or {}).get("hotels") or [])
        if hotel.get("id") == hotel_id
    ][:1]
    fact = _one_facts(found[0], query) if found else hotel_name
    prefix = f"На {when}. " if when else ""
    return f"{prefix}{fact}"


def _funnel(result: dict, hotel_id: str, guest_id: str) -> dict:
    from admin.service import NIGHT_RUB, pay

    query = result.get("query") or ""
    last = _last_line(query)
    paid = _guest_has_paid(guest_id, hotel_id)
    hotel_name = _hotel_name(hotel_id)
    account = _guest_account(guest_id)
    if account is None:
        if _chosen_on_last(last):
            return _hold(
                result,
                hotel_id,
                f"{_choice_facts(result, hotel_id, hotel_name)} Далее вам нужно зарегистрироваться. {_register_line(hotel_name)}",
            )
        return _hold(result, hotel_id, f"Сначала регистрация. {_register_line(hotel_name)}")
    guest_id = account["id"]
    if not paid and _chosen_on_last(last):
        return _hold(
            result,
            hotel_id,
            f"{_choice_facts(result, hotel_id, hotel_name)} {_entered(account['name'])}",
            guest_id,
        )
    if not paid:
        if _pay_intent(last):
            dates = result.get("dates") or ""
            if not dates:
                return _hold(
                    result,
                    hotel_id,
                    "Для оплаты нужны даты заезда и выезда.",
                    guest_id,
                )
            try:
                check_in, check_out = _stay_bounds(dates)
                booking = pay(guest_id, hotel_id, check_in, check_out)["booking"]
            except ValueError as error:
                return _hold(result, hotel_id, str(error), guest_id)
            nights = int(booking.get("nights") or 1)
            amount = int(booking.get("amount_rub") or nights * NIGHT_RUB)
            tail = "ночь" if nights % 10 == 1 and nights % 100 != 11 else "ночи" if nights % 10 in (2, 3, 4) and nights % 100 not in (12, 13, 14) else "ночей"
            money = f"{amount:,}".replace(",", " ")
            return _hold(
                result,
                hotel_id,
                (
                    f"Бронь {hotel_name} оплачена: {nights} {tail}, {money} ₽. "
                    "Номер карты не нужен, деньги не списываются. Теперь можно спрашивать что угодно по этому отелю."
                ),
                guest_id,
                True,
            )
        extra = [card for card in _ordered_cards(last) if card != "base"]
        if extra:
            text = _card_text(hotel_id, extra[0])
            return _hold(
                result,
                hotel_id,
                f"{text} Это до оплаты. Ночь — {NIGHT_RUB:,} ₽. Напишите «оплатить», когда решите.".replace(",", " "),
                guest_id,
            )
        if "base" in _ordered_cards(last):
            return _hold(
                result,
                hotel_id,
                "Базовую карточку открою после оплаты. Сейчас могу экологию, шопинг, развлечения или здоровье.",
                guest_id,
            )
        return _hold(
            result,
            hotel_id,
            "До оплаты другие вопросы закрыты. Напишите: экология, шопинг, развлечения, здоровье — или «оплатить».",
            guest_id,
        )
    cards = _ordered_cards(last)
    if cards and not _place_search(last):
        if "base" in cards:
            payload = base_card(query, hotel_id)
            reply = " ".join(_base_lines(payload))
            return _hold(result, hotel_id, reply, guest_id, True, _base_sheet(payload))
        extra = [card for card in cards if card != "base"]
        if extra:
            return _hold(result, hotel_id, _card_text(hotel_id, extra[0]), guest_id, True)
    spoken = _about_turn(result, hotel_id)
    spoken["guest_id"] = guest_id
    spoken["paid"] = True
    return spoken


def _about_one(result: dict, hotel_id: str) -> dict:
    found = [
        hotel
        for hotel in ((result.get("dossier") or {}).get("hotels") or [])
        if hotel.get("id") == hotel_id
    ][:1]
    if not found:
        return {
            "reply": "Этого отеля нет в снимке.",
            "asks_user": [],
            "hotels": [],
            "hotelier_question": None,
            "cards": [],
            "sheet": None,
        }
    when = _stay_phrase(result.get("dates") or "")
    facts = _one_facts(found[0], result.get("query") or "")
    if when:
        facts = f"На {when}. {facts}"
    return {
        "reply": facts,
        "asks_user": [],
        "hotels": found,
        "hotelier_question": _hotelier_question(result, found),
        "cards": [],
        "sheet": None,
    }


def _about_turn(result: dict, hotel_id: str) -> dict:
    hotels = ((result.get("dossier") or {}).get("hotels") or [])[:3]
    if hotel_id:
        picked = [hotel for hotel in hotels if hotel.get("id") == hotel_id]
        if picked:
            hotels = picked
    fallback = "Этого в снимке нет. Могу сказать про дорогу, тихую сторону и солнце на стену."
    return _spoken(result, hotels, fallback)


def _rank(hotels: list[dict], slots: dict) -> tuple[list[dict], list[dict]]:
    limit = slots.get("max_minutes")
    kept = []
    dropped = []
    for hotel in hotels:
        minutes = (( _fact(hotel, "walk_to") or {}).get("data") or {}).get("minutes")
        if limit is not None and isinstance(minutes, (int, float)) and minutes > limit:
            dropped.append(
                {
                    "id": hotel.get("id"),
                    "name": hotel.get("name") or hotel.get("id"),
                    "minutes": minutes,
                    "limit": limit,
                }
            )
            continue
        kept.append(hotel)
    if slots.get("quiet"):
        kept.sort(key=lambda hotel: ((_fact(hotel, "facade_noise") or {}).get("data") or {}).get("penalty", 10**9))
    else:
        kept.sort(
            key=lambda hotel: ((_fact(hotel, "walk_to") or {}).get("data") or {}).get("minutes")
            if isinstance(((_fact(hotel, "walk_to") or {}).get("data") or {}).get("minutes"), (int, float))
            else 10**9
        )
    return kept, dropped


def _hotelier_question(_result: dict, hotels: list[dict]) -> str | None:
    for hotel in hotels:
        for fact in hotel.get("facts") or []:
            if fact.get("question"):
                return fact["question"]
    return None


def _is_weak_fact_reply(reply: str) -> bool:
    clean = (reply or "").strip()
    if len(clean) < 40:
        return True
    low = clean.lower()
    if low in {"отель.", "отель"} or low.endswith(". отель."):
        return True
    return False


def _running_nearby_lines(hotel_id: str) -> str | None:
    card = base_card("", hotel_id)
    if card.get("status") == "not_in_snapshot":
        return None
    spots: list[str] = []
    for key in ("around", "sights", "nearby"):
        for item in card.get(key) or []:
            name = (item.get("name") or "").strip()
            if not name:
                continue
            low = name.lower()
            if any(word in low for word in ("парк", "пруд", "сад", "стадион", "спорт")):
                dist = item.get("distance") or ""
                spots.append(f"{name} ({dist})" if dist else name)
    if not spots:
        return None
    joined = "; ".join(spots[:5])
    return f"По карте «Базовая» (окрестности из карточки Островка): {joined}."


def post_booking_fact_answer(hotel_id: str, question: str, dates: str) -> dict:
    """Ответ Fact Agent для оплаченной брони по одному отелю."""
    from common.post_booking_routing import is_fact_agent_question

    last = _last_line(question)
    low = last.lower()
    if any(word in low for word in ("светл", "солнц", "сunny", "закат")):
        result = resolve(f"Отель {_hotel_name(hotel_id)}. {last}")
        result["dates"] = dates.strip()
        result["dossier"] = build_dossier(result.get("answers", {}).get("hotel"), dates)
        hotels = [
            hotel
            for hotel in (result["dossier"].get("hotels") or [])
            if hotel.get("id") == hotel_id
        ]
        if hotels:
            sun = _sunnier(hotels[0])
            if sun:
                return {"reply": sun, "weak": False}
    from common.post_booking_routing import is_quiet_side_question

    if is_quiet_side_question(last):
        reply, known = quiet_side_reply(hotel_id)
        return {"reply": reply, "weak": not known}

    cards = _ordered_cards(last)
    if is_fact_agent_question(question) and not cards:
        low = question.lower()
        if any(word in low for word in ("бег", "пробеж", "парк", "стадион", "спорт", "фитнес")):
            run = _running_nearby_lines(hotel_id)
            if run:
                return {"reply": run, "weak": False}

    result = resolve(f"Отель {_hotel_name(hotel_id)}. {question}")
    result["dates"] = dates.strip()
    anchor = result.get("answers", {}).get("hotel")
    if not isinstance(anchor, dict):
        anchor = None
    result["dossier"] = build_dossier(anchor, result["dates"])
    hotels = [
        hotel
        for hotel in (result["dossier"].get("hotels") or [])
        if hotel.get("id") == hotel_id
    ]
    if not hotels:
        from geo.service import get_hotel

        snap = get_hotel(hotel_id)
        if snap:
            hotels = [snap]
    result["dossier"]["hotels"] = hotels[:1]

    if cards:
        card = cards[0]
        if card == "base":
            payload = base_card(question, hotel_id)
            reply = " ".join(_base_lines(payload))
            return {"reply": reply, "weak": _is_weak_fact_reply(reply)}
        text = _card_text(hotel_id, card)
        if text:
            return {"reply": text, "weak": _is_weak_fact_reply(text)}

    spoken = _about_turn(result, hotel_id)
    reply = (spoken.get("reply") or "").strip()
    if is_fact_agent_question(question):
        run = _running_nearby_lines(hotel_id)
        if run and _is_weak_fact_reply(reply):
            reply = run
    return {"reply": reply, "weak": _is_weak_fact_reply(reply)}
