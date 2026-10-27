"""Разбор фразы гостя по снимкам. Шум отеля сюда не входит."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DATA = ROOT / "data"


def _load(name: str) -> dict:
    return json.loads((DATA / name).read_text(encoding="utf-8"))


def _hit(text: str, words: tuple[str, ...]) -> bool:
    low = text.lower()
    return any(word in low for word in words)


def decompose(text: str) -> list[str]:
    parts: list[str] = []
    if _hit(text, ("базов",)):
        parts.append("base")
    if _hit(text, ("отел", "hotel", "булгак", "нехорош", "квартир")):
        parts.append("hotel")
    if _hit(text, ("экскурс", "excursion")):
        parts.append("excursion")
    if _hit(text, ("шоп", "покуп", "подар", "shopping", "buy")):
        parts.append("shopping")
    if _hit(text, ("клуб", "nightclub", "evening", "вечер")):
        parts.append("nightclub")
    return parts


def shopping() -> dict:
    snap = _load("shops.json")
    return {
        "source": snap["source"],
        "as_of": snap["as_of"],
        "results": snap["items"],
    }


def nightclub() -> dict:
    snap = _load("nightclubs.json")
    open_items = [item for item in snap["items"] if item["status"] == "listed"]
    closed_items = [item for item in snap["items"] if item["status"] == "closed"]
    return {
        "source": snap["source"],
        "as_of": snap["as_of"],
        "separate_from": "Noise Agent",
        "results": open_items,
        "not_recommended": closed_items,
    }


_HOTELS = (
    ("pekin", ("пекин", "pekin", "peking")),
    ("marriott-tverskaya", ("safmar", "сафмар", "marriott", "марриот")),
    ("lotte", ("lotte", "лотте")),
)


def _named_hotel(text: str) -> str | None:
    low = text.lower()
    for hotel_id, words in _HOTELS:
        if any(word in low for word in words):
            return hotel_id
    return None


def named_hotel(text: str) -> str | None:
    return _named_hotel(text)


def base_card(text: str, hotel_id: str | None = None) -> dict:
    snap = _load("base_card.json")
    hotel_id = _named_hotel(text) or hotel_id or "pekin"
    card = (snap.get("hotels") or {}).get(hotel_id)
    head = {
        "id": snap["id"],
        "title": snap["title"],
        "source": snap["source"],
        "as_of": snap["as_of"],
        "note": snap["note"],
        "hotel_id": hotel_id,
    }
    if not card:
        return {
            **head,
            "status": "not_in_snapshot",
            "value": "не знаем",
            "note": "Снимка карточки Островка для этого отеля нет.",
        }
    return {**head, **card, "status": "snapshot"}


def resolve(text: str) -> dict:
    parts = decompose(text)
    out: dict = {"query": text, "parts": parts, "answers": {}}
    for part in parts:
        if part == "base":
            out["answers"]["base"] = base_card(text)
        elif part == "hotel":
            from geo.service import resolve_anchor

            out["answers"]["hotel"] = resolve_anchor(text)
        elif part == "excursion":
            out["answers"]["excursion"] = {
                "status": "not_in_scope",
                "note": "Маршрут экскурсии агент не собирает.",
            }
        elif part == "shopping":
            out["answers"]["shopping"] = shopping()
        elif part == "nightclub":
            out["answers"]["nightclub"] = nightclub()
    return out


if __name__ == "__main__":
    query = (
        "I want to come to a hotel in Moscow near Bulgakov's bad apartment, "
        "go on an excursion, then during the day go shopping to buy things "
        "for my loved ones, and in the evening go to a nightclub."
    )
    print(json.dumps(resolve(query), ensure_ascii=False, indent=2))
