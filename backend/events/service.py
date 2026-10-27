"""City Events Agent. Сейчас это снимок закрытых выходов метро."""

from __future__ import annotations

from common.models import Fact, unknown
from common.snapshots import load_json


def ping() -> dict:
    return {"status": "ok", "service": "events"}


def closed_exits() -> list[dict]:
    raw = load_json("metro_repairs.json", {"items": []})
    return [item for item in raw.get("items", []) if item.get("closed", True)]


def for_hotel(ctx: dict) -> Fact:
    hotel_id = ctx.get("hotel_id")
    from common.snapshots import DATA

    entrances = load_json("metro_entrances.json", {"items": []})
    match = next(
        (item for item in entrances.get("items", []) if str(item.get("hotel_id")) == str(hotel_id)),
        None,
    )
    if match:
        station = match.get("station") or "станция без имени в снимке"
        entrance = match.get("entrance") or "без номера"
        return Fact(
            feature="metro_exit",
            value=(
                f"{station}, вход {entrance}, {match.get('distance_m')} м по прямой. "
                "Открыт ли вход сегодня, снимок ремонтов не говорит."
            ),
            method="metro_entrance",
            sources=[entrances.get("source") or "metro_entrances.json"],
            confidence=0.55,
            as_of=entrances.get("as_of"),
            hotel_id=hotel_id,
            detail="Расстояние по прямой до узла subway_entrance, не минуты пешком.",
            data=match,
        )
    if not (DATA / "metro_repairs.json").exists():
        return unknown(
            "metro_exit",
            "metro_repairs",
            "Нет снимка входа метро и нет снимка закрытых выходов.",
            hotel_id,
        )
    path_items = closed_exits()
    if not path_items:
        return Fact(
            feature="metro_exit",
            value="закрытых выходов в снимке нет",
            method="metro_repairs",
            sources=["metro_repairs.json"],
            confidence=0.8,
            hotel_id=hotel_id,
            data={"closed": []},
        )
    names = ", ".join(str(item.get("exit_id") or item.get("station")) for item in path_items)
    return Fact(
        feature="metro_exit",
        value=f"закрыты: {names}",
        method="metro_repairs",
        sources=["metro_repairs.json"],
        confidence=0.8,
        hotel_id=hotel_id,
        detail="Обход этих выходов увеличивает пеший путь.",
        data={"closed": path_items},
    )
