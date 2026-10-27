"""Разбор свободного текста отельера в поля категории, стороны и этажа."""

from __future__ import annotations

import re
from datetime import date

from common.db import facts_for, replace_hotelier
from common.models import Fact
from conflict.service import judge
from geo.service import get_hotel

STOP = {"с", "со", "на", "от", "в", "и", "у", "до", "этажа", "этаж", "этажей"}


def ping() -> dict:
    return {"status": "ok", "service": "hotelier"}


def parse_text(text: str) -> dict:
    rooms: list[dict] = []
    floors: int | None = None
    for chunk in re.split(r"[,;]", text):
        piece = chunk.strip(" .")
        if not piece:
            continue
        floor_match = re.search(r"(\d+)\s*этаж", piece, flags=re.IGNORECASE)
        floor = int(floor_match.group(1)) if floor_match else None
        low = piece.lower()
        side = None
        if "двор" in low:
            side = "courtyard"
        elif "садов" in low:
            side = "street"
        if floor is not None and side is None and re.search(r"этажност|этажей", low):
            floors = floor
            continue
        word = re.match(r"([a-zа-яё\-]+)", low)
        category = word.group(1) if word else None
        if category in STOP:
            category = None
        if category is None and side is None:
            if floor is not None and floors is None:
                floors = floor
            continue
        rooms.append({"room_category": category, "side": side, "floor_from": floor if side else None})
    return {
        "source": "hotelier",
        "confidence": 0.95,
        "rooms": rooms,
        "floors": floors,
    }


def _fact(hotel_id: str, feature: str, value: str, data: dict) -> Fact:
    return Fact(
        feature=feature,
        value=value,
        method="parse_hotelier",
        sources=["hotelier"],
        confidence=0.95,
        as_of=date.today().isoformat(),
        hotelier_status="confirmed",
        hotel_id=hotel_id,
        data=data,
    )


def submit(hotel_id: str, text: str) -> dict:
    parsed = parse_text(text)
    hotel = get_hotel(hotel_id)
    if hotel is None:
        return {
            "hotel_id": hotel_id,
            "saved": False,
            "parsed": parsed,
            "conflicts": [],
            "order": [],
            "note": "Этого отеля нет в снимке hotels.geojson, ответ не записан.",
        }
    existing = {fact.feature: fact for fact in facts_for(hotel_id) if fact.method != "parse_hotelier"}
    conflicts = []
    saved: list[Fact] = []
    if parsed["rooms"]:
        lines = []
        for room in parsed["rooms"]:
            line = f"{room['room_category'] or 'категория'} → {room['side'] or 'сторона не названа'}"
            if room["floor_from"]:
                line += f", с {room['floor_from']} этажа"
            lines.append(line)
        fact = _fact(hotel_id, "room_category", "; ".join(lines), {"rooms": parsed["rooms"]})
        conflicts.append(_dump(judge(existing.get("room_category"), fact)))
        replace_hotelier(hotel_id, "room_category", fact)
        saved.append(fact)
    if parsed["floors"] is not None:
        fact = _fact(hotel_id, "floors", str(parsed["floors"]), {"floors": parsed["floors"]})
        verdict = judge(existing.get("floors"), fact)
        conflicts.append(_dump(verdict))
        replace_hotelier(hotel_id, "floors", fact)
        saved.append(fact)
    return {
        "hotel_id": hotel_id,
        "saved": True,
        "parsed": parsed,
        "conflicts": conflicts,
        "facts": [fact.model_dump() for fact in saved],
        "order": [],
        "note": "Ответ записан рядом с расчётом. Строка OSM не удалена.",
    }


def _dump(verdict: dict) -> dict:
    return {
        "status": verdict["status"],
        "accepted": verdict["accepted"].model_dump() if verdict["accepted"] else None,
        "rows": [row.model_dump() for row in verdict["rows"]],
    }
