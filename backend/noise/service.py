"""Noise Agent. Ночной POI здесь — источник шума у стены, не клуб для гостя.

Рекомендация, куда пойти вечером, лежит в search и data/nightclubs.json.
Этот модуль тот файл не открывает.
"""

from __future__ import annotations

import math

from common.models import Fact, unknown
from common.snapshots import load_json

ROAD_RANK = {
    "motorway": 6,
    "trunk": 5,
    "motorway_link": 5,
    "trunk_link": 5,
    "primary": 4,
    "primary_link": 4,
    "secondary": 3,
    "tertiary": 2,
    "unclassified": 1,
    "residential": 1,
    "living_street": 1,
    "pedestrian": 1,
}


def ping() -> dict:
    return {"status": "ok", "service": "noise"}


def _meters(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    x = (lon2 - lon1) * 111_320 * math.cos(math.radians((lat1 + lat2) / 2))
    y = (lat2 - lat1) * 110_540
    return math.hypot(x, y)


def _hotel(hotel_id: str) -> dict | None:
    raw = load_json("hotels.geojson", {"features": []})
    for feature in raw.get("features", []):
        props = feature.get("properties") or {}
        if str(props.get("id") or feature.get("id")) == str(hotel_id):
            return props
    return None


def for_hotel(ctx: dict) -> Fact:
    hotel_id = str(ctx.get("hotel_id") or "")
    props = _hotel(hotel_id)
    sides = (props or {}).get("sides") or []
    if not sides:
        return unknown(
            "facade_noise",
            "facade_noise",
            "Нет сторон фасада в снимке отеля.",
            hotel_id,
        )
    pois = load_json("night_poi.geojson", {"items": []})
    rows = []
    for side in sides:
        origin = side.get("origin") or [0, 0]
        nearest = None
        for poi in pois.get("items", []):
            dist = _meters(float(origin[0]), float(origin[1]), float(poi["lon"]), float(poi["lat"]))
            if nearest is None or dist < nearest[0]:
                nearest = (dist, poi)
        faces_dist = float(side.get("faces_distance_m") or 0)
        rank = ROAD_RANK.get(side.get("faces_class"), 1)
        penalty = rank * 100 / max(faces_dist, 5)
        night_m = None
        night_name = None
        night_kind = None
        if nearest and nearest[0] <= 250:
            night_m = nearest[0]
            night_name = nearest[1].get("name")
            night_kind = nearest[1].get("amenity")
            penalty += max(0.0, 150 - night_m) / 3
        rows.append(
            {
                "id": side.get("id"),
                "title": side.get("title") or side.get("id"),
                "faces_class": side.get("faces_class"),
                "faces_name": side.get("faces_name"),
                "faces_distance_m": faces_dist,
                "address_distance_m": side.get("address_distance_m"),
                "night_m": None if night_m is None else round(night_m),
                "night_name": night_name,
                "night_kind": night_kind,
                "penalty": round(penalty, 2),
            }
        )
    quieter = min(rows, key=lambda row: row["penalty"])
    louder = max(rows, key=lambda row: row["penalty"])
    kind_name = {
        "nightclub": "ночной клуб",
        "bar": "бар",
        "pub": "паб",
        "biergarten": "бирхаус",
        "stripclub": "стриптиз-клуб",
    }
    phrases = []
    for row in rows:
        if row["night_m"] is None:
            night = "ночного POI ближе 250 м нет"
        else:
            kind = kind_name.get(row["night_kind"], row["night_kind"] or "POI")
            night = f"{kind} «{row['night_name']}» в {row['night_m']} м"
        phrases.append(
            f"{row['title']}: {row['faces_class']} «{row['faces_name']}» в {round(row['faces_distance_m'])} м, {night}"
        )
    both_night = all(row["night_m"] is not None and row["night_m"] <= 80 for row in rows)
    close = both_night or louder["penalty"] <= quieter["penalty"] * 1.15
    if close:
        tail = "Какая сторона тише, по этому снимку не утверждаем."
        confidence = 0.5
    else:
        tail = f"Тише по этой оценке: {quieter['title']}."
        confidence = 0.72
    return Fact(
        feature="facade_noise",
        value=". ".join(phrases) + ". " + tail,
        method="facade_noise",
        sources=["hotels.geojson", "night_poi.geojson", pois.get("source") or "https://www.openstreetmap.org/copyright"],
        confidence=confidence,
        as_of=pois.get("as_of"),
        hotel_id=hotel_id,
        detail="Оценка окружения по классу дороги и ночному POI, не замер в номере.",
        data={
            "sides": rows,
            "quieter_side": None if close else quieter["id"],
            "quieter_label": None if close else quieter["title"],
            "penalty": quieter["penalty"],
        },
    )
