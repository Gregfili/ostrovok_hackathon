"""View Agent: луч и сектор утреннего солнца на том же фасаде."""

from __future__ import annotations

import math

from common.models import Fact, unknown
from common.snapshots import load_json
from view.raycast import raycast, to_xy
from view.sun import wall_sun_label


def ping() -> dict:
    return {"status": "ok", "service": "view"}


def _ring_meters(ring: list, lon0: float, lat0: float) -> list[tuple[float, float]]:
    points = []
    for pair in ring:
        if len(pair) < 2:
            continue
        points.append(to_xy(float(pair[0]), float(pair[1]), lon0, lat0))
    return points


def _prepare(buildings: list, lon0: float, lat0: float) -> list[dict]:
    prepared = []
    for feature in buildings:
        bprops = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        rings = geometry.get("coordinates") or []
        if not rings or not isinstance(rings[0], list):
            continue
        ring = rings[0]
        if ring and isinstance(ring[0], list) and ring[0] and isinstance(ring[0][0], list):
            ring = ring[0]
        prepared.append(
            {
                "id": bprops.get("id") or feature.get("id"),
                "ring": _ring_meters(ring, lon0, lat0),
                "height_m": bprops.get("height"),
                "levels": bprops.get("building:levels"),
            }
        )
    return prepared


def _cast(origin: list, target: list, eye: float, buildings: list) -> dict:
    lon0, lat0 = float(origin[0]), float(origin[1])
    return raycast(
        (0.0, 0.0),
        to_xy(float(target[0]), float(target[1]), lon0, lat0),
        eye,
        _prepare(buildings, lon0, lat0),
    )


def for_hotel(ctx: dict) -> Fact:
    hotel_id = ctx.get("hotel_id")
    snapshot = load_json("buildings.geojson", {"features": []})
    buildings = snapshot.get("features", [])
    hotels = load_json("hotels.geojson", {"features": []}).get("features", [])
    hotel = next(
        (
            feature
            for feature in hotels
            if str((feature.get("properties") or {}).get("id") or feature.get("id")) == str(hotel_id)
        ),
        None,
    )
    if not hotel or not buildings:
        return unknown(
            "facade_visibility",
            "building_raycast",
            "Нет контура отеля или соседних зданий в снимке.",
            hotel_id,
        )
    props = hotel.get("properties") or {}
    sides = list(props.get("sides") or [])
    if not sides and props.get("side_origin") and props.get("view_target"):
        sides = [{"title": "Сторона", "origin": props["side_origin"], "target": props["view_target"]}]
    if not sides:
        return unknown(
            "facade_visibility",
            "building_raycast",
            "У стороны нет точки старта луча.",
            hotel_id,
        )
    eye = float(props.get("eye_height_m") or 2)
    shots = []
    for side in sides:
        if not side.get("origin") or not side.get("target"):
            continue
        shots.append((side.get("title") or side.get("id") or "Сторона", _cast(side["origin"], side["target"], eye, buildings)))
    anchor_target = props.get("anchor_target")
    if anchor_target and sides and sides[0].get("origin"):
        origin = sides[0]["origin"]
        dx = (float(anchor_target[0]) - float(origin[0])) * 111_320 * math.cos(math.radians(float(origin[1])))
        dy = (float(anchor_target[1]) - float(origin[1])) * 110_540
        if math.hypot(dx, dy) <= 250:
            shots.append(("Луч к дому 10", _cast(origin, anchor_target, eye, buildings)))
    if not shots:
        return unknown(
            "facade_visibility",
            "building_raycast",
            "У стороны нет точки старта луча.",
            hotel_id,
        )
    fact = Fact(
        feature="facade_visibility",
        value="; ".join(
            f"{title}: {'по контурам OSM проём на 70 м' if hit['verdict'] == 'open' else hit['text']}"
            for title, hit in shots
        ),
        method="building_raycast",
        sources=["buildings.geojson", snapshot.get("source") or "https://www.openstreetmap.org/copyright"],
        confidence=min(hit["confidence"] for _title, hit in shots),
        as_of=snapshot.get("as_of"),
        hotel_id=hotel_id,
        detail=(
            f"Луч с {eye:g} м над землёй у стены, этаж номера не задан. "
            + shots[0][1]["detail"]
        ),
        data={"shots": [{"title": title, **hit} for title, hit in shots]},
    )
    _attach_sun(fact, props, ctx.get("dates") or "")
    return fact


def _attach_sun(fact: Fact, props: dict, dates: str) -> None:
    sides = props.get("sides") or []
    origin = (sides[0].get("origin") if sides else None) or []
    longitude = float(origin[0]) if len(origin) >= 1 else 37.62
    labels: dict[str, str] = {}
    for side in sides:
        azimuth = side.get("azimuth")
        title = side.get("title") or side.get("id")
        if azimuth is None or not title:
            continue
        label = wall_sun_label(float(azimuth), dates, longitude)
        if label:
            labels[str(title)] = label
    if not labels:
        return
    fact.data["sun_hours"] = labels
    for shot in fact.data.get("shots") or []:
        label = labels.get(shot.get("title") or "")
        if label:
            shot["sun_label"] = label
