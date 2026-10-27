"""Луч по контурам зданий. Высота соседа — метры или этажи × 3. DEM не используется."""

from __future__ import annotations

import math


def to_xy(lon: float, lat: float, lon0: float, lat0: float) -> tuple[float, float]:
    x = (lon - lon0) * 111_320 * math.cos(math.radians(lat0))
    y = (lat - lat0) * 110_540
    return x, y


def _orient(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _crosses(
    p1: tuple[float, float],
    p2: tuple[float, float],
    q1: tuple[float, float],
    q2: tuple[float, float],
) -> bool:
    o1 = _orient(p1, p2, q1)
    o2 = _orient(p1, p2, q2)
    o3 = _orient(q1, q2, p1)
    o4 = _orient(q1, q2, p2)
    return o1 * o2 < 0 and o3 * o4 < 0


def _hit_distance(origin: tuple[float, float], toward: tuple[float, float], ring: list) -> float | None:
    best: float | None = None
    points = [(float(p[0]), float(p[1])) for p in ring]
    if len(points) < 2:
        return None
    edges = list(zip(points, points[1:] + points[:1]))
    for a, b in edges:
        if not _crosses(origin, toward, a, b):
            continue
        dist = math.hypot((a[0] + b[0]) / 2 - origin[0], (a[1] + b[1]) / 2 - origin[1])
        if best is None or dist < best:
            best = dist
    return best


def raycast(
    origin: tuple[float, float],
    target: tuple[float, float],
    eye_height_m: float,
    buildings: list[dict],
) -> dict:
    """buildings: id, ring как пары метров, height_m или levels."""
    nearest_id = None
    nearest_dist = None
    missing_height = False
    for building in buildings:
        ring = building.get("ring") or []
        dist = _hit_distance(origin, target, ring)
        if dist is None:
            continue
        height = building.get("height_m")
        if height is None and building.get("levels") is not None:
            height = float(building["levels"]) * 3
        if height is None:
            missing_height = True
            continue
        if float(height) < eye_height_m:
            continue
        if nearest_dist is None or dist < nearest_dist:
            nearest_dist = dist
            nearest_id = building.get("id")
    if missing_height and nearest_id is None:
        return {
            "verdict": "unknown",
            "text": "не знаем",
            "blocker_id": None,
            "confidence": 0.3,
            "detail": "У соседнего здания нет высоты, луч в вердикт не берём.",
        }
    if nearest_id is None:
        return {
            "verdict": "open",
            "text": "проём до точки",
            "blocker_id": None,
            "confidence": 0.75,
            "detail": "Луч по контурам не встретил здание выше точки обзора.",
        }
    return {
        "verdict": "blocked",
        "text": f"перекрыто зданием OSM {nearest_id}",
        "blocker_id": nearest_id,
        "confidence": 0.75,
        "detail": "Оценка по полигону и высоте, не по фото из номера.",
    }
