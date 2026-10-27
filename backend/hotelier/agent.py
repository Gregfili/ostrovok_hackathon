"""Ответ счёта отеля. Текст собирается из уже посчитанных фактов, без новой цены и без замера."""

from __future__ import annotations

from geo.service import get_hotel
from noise.service import for_hotel as facade_noise


def draft_reply(hotel_id: str) -> str:
    hotel = get_hotel(hotel_id)
    if hotel is None:
        return "Этого отеля нет в снимке, ответить нечем."
    noise = facade_noise({"hotel_id": hotel_id})
    name = hotel.get("name") or hotel_id
    levels = hotel.get("osm_levels")
    levels_text = f" В OSM {levels} этажей." if levels else ""
    heard = noise.value if noise.value and noise.value != "не знаем" else "По шуму у стены снимка недостаточно."
    return (
        f"Счёт отеля {name}. {heard}{levels_text} "
        "Категорию номера и этаж гостя этот ответ не назначает: плана этажа в снимке нет."
    )
