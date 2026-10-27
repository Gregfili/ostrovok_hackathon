"""Контур и якорь. Адрес берётся только из anchors.json и hotels.geojson."""

from __future__ import annotations

from common.snapshots import load_json


def ping() -> dict:
    return {"status": "ok", "service": "geo"}


def resolve_anchor(text: str) -> dict:
    catalog = load_json("anchors.json", {"items": []})
    low = text.lower()
    for item in catalog.get("items", []):
        if any(phrase in low for phrase in item.get("phrases", [])):
            return {
                "id": item["id"],
                "place": item["place"],
                "address": item["address"],
                "wikidata": item["wikidata"],
                "status": "found",
                "source": catalog.get("source"),
                "note": item.get("note", ""),
            }
    return {
        "id": None,
        "place": None,
        "address": None,
        "wikidata": None,
        "status": "ask",
        "source": catalog.get("source"),
        "note": "В справочнике нет такого якоря. Напишите адрес или известное место.",
    }


def list_hotels() -> list[dict]:
    raw = load_json("hotels.geojson", {"features": []})
    hotels: list[dict] = []
    for feature in raw.get("features", []):
        props = feature.get("properties") or {}
        hotels.append(
            {
                "id": str(props.get("id") or feature.get("id") or ""),
                "name": props.get("name"),
                "address": props.get("address"),
                "summary": props.get("summary"),
                "image": props.get("image"),
                "image_credit": " ".join(
                    part
                    for part in (props.get("image_author"), props.get("image_license"))
                    if part
                )
                or None,
                "image_source": props.get("image_source"),
                "also_known": props.get("also_known"),
                "osm_levels": props.get("osm_levels"),
                "geometry": feature.get("geometry"),
                "sides": props.get("sides") or [],
            }
        )
    return [hotel for hotel in hotels if hotel["id"]]


def get_hotel(hotel_id: str) -> dict | None:
    for hotel in list_hotels():
        if hotel["id"] == hotel_id:
            return hotel
    return None
