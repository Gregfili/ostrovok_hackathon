"""Mobility Agent. Минуты берутся из walk_cache.json, живой граф — если он уже лежит в data."""

from __future__ import annotations

from common.models import Fact, unknown
from common.snapshots import DATA, load_json
from events.service import closed_exits


def ping() -> dict:
    return {"status": "ok", "service": "mobility"}


def _minute_phrase(minutes) -> str:
    if not isinstance(minutes, (int, float)):
        return "минуты не посчитаны"
    count = int(minutes)
    tail = count % 100
    if 11 <= tail <= 14:
        word = "минут"
    elif tail % 10 == 1:
        word = "минута"
    elif tail % 10 in {2, 3, 4}:
        word = "минуты"
    else:
        word = "минут"
    return f"{count} {word}"


def walk_to(hotel_id: str, anchor_id: str = "bad_apartment") -> Fact:
    cache = load_json("walk_cache.json", {"items": []})
    for item in cache.get("items", []):
        if str(item.get("hotel_id")) != str(hotel_id):
            continue
        if anchor_id and str(item.get("anchor_id")) != str(anchor_id):
            continue
        minutes = item.get("minutes")
        crosses = bool(item.get("crosses_trunk"))
        names = [str(name) for name in item.get("crossing_names") or []]
        if crosses and names:
            trunk = "пересекает " + ", ".join(names)
        elif crosses:
            trunk = "пересекает primary/trunk"
        else:
            trunk = "ось primary/trunk не пересекает"
        distance = item.get("distance_m")
        distance_text = f", {distance} м" if distance is not None else ""
        closed = closed_exits()
        extra = f" Закрытые выходы: {len(closed)}." if closed else ""
        return Fact(
            feature="walk_to",
            value=f"{_minute_phrase(minutes)}{distance_text}, {trunk}.{extra}".strip(),
            method="walk_to",
            sources=[cache.get("source") or "walk_cache.json"],
            confidence=float(item.get("confidence") or 0.75),
            as_of=cache.get("as_of"),
            hotel_id=hotel_id,
            detail=item.get("detail"),
            data={
                "minutes": minutes,
                "distance_m": distance,
                "crosses_trunk": crosses,
                "crossing_names": names,
                "anchor_id": anchor_id,
                "closed_exits": closed,
            },
        )
    graph = DATA / "walk_graph"
    detail = "Нет walk_cache.json для этой пары отель–якорь."
    if not graph.exists():
        detail += " Пеший граф для живого пересчёта тоже не собран."
    return unknown("walk_to", "walk_to", detail, hotel_id)


def for_hotel(ctx: dict) -> Fact:
    return walk_to(str(ctx.get("hotel_id") or ""), str(ctx.get("anchor_id") or "bad_apartment"))
