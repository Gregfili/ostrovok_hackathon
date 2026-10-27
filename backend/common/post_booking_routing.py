"""Маршрутизация вопросов после оплаты: Fact Agent vs база отельера."""

from __future__ import annotations

from hotel_faq.rag import tokenize

FACT_AGENT_CARDS = (
    "базовая карточка Островка, экология, здоровье («Дежурство»), шопинг, развлечения; "
    "гео-карты: корпус, вид, солнце, путь и метро, город (события), шум стороны"
)

FACT_AGENT_KEYWORDS = (
    "тишин",
    "шум",
    "вид",
    "сторон",
    "фасад",
    "этаж",
    "минут",
    "метро",
    "пеш",
    "закат",
    "солнц",
    "светл",
    "светла",
    "светлую",
    "эколог",
    "здоров",
    "аптек",
    "клиник",
    "больниц",
    "дежур",
    "шоп",
    "покуп",
    "подар",
    "развлеч",
    "клуб",
    "бег",
    "пробеж",
    "пробег",
    "парк",
    "стадион",
    "спорт",
    "фитнес",
    "маршрут",
    "дорог",
    "булгак",
    "якор",
    "карт",
    "корпус",
    "окружен",
    "базов",
    "выход",
    "ремонт",
)

HOTEL_KB_KEYWORDS = (
    "заезд",
    "выезд",
    "check-in",
    "checkin",
    "завтрак",
    "breakfast",
    "парков",
    "пarking",
    "wifi",
    "wi-fi",
    "интернет",
    "питом",
    "животн",
    "собак",
    "кошк",
    "багаж",
    "ресепшен",
    "полотен",
    "халат",
    "консьерж",
)

_RAG_STOP = frozenset(
    {
        "есть",
        "ли",
        "или",
        "как",
        "что",
        "где",
        "когда",
        "можно",
        "нужно",
        "этот",
        "этом",
        "отель",
        "отеле",
        "номер",
        "рядом",
        "утром",
        "вечером",
        "очень",
        "пожалуйста",
    }
)


def is_fact_agent_question(text: str) -> bool:
    low = text.lower()
    return any(word in low for word in FACT_AGENT_KEYWORDS)


def is_quiet_side_question(text: str) -> bool:
    low = text.lower()
    if not any(word in low for word in ("тиш", "шум", "quiet")):
        return False
    return any(word in low for word in ("сторон", "улиц", "двор", "окн", "ночью", "номер"))


def is_hotel_kb_question(text: str) -> bool:
    low = text.lower()
    return any(word in low for word in HOTEL_KB_KEYWORDS)


def rag_hit_relevant(query: str, chunk_text: str, score: float) -> bool:
    if score < 0.28:
        return False
    q = {t for t in tokenize(query) if t not in _RAG_STOP and len(t) > 2}
    c = set(tokenize(chunk_text))
    if q & c:
        return True
    if score >= 0.42 and is_hotel_kb_question(query):
        return True
    return False
