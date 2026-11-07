"""С какого этажа стены видна цель, с рельефом под лучом.

Высота глаз на этаже N: (N − 1) × 3 м + 1,6 м над землёй у стены.
Крыша соседа: рельеф в точке пересечения плюс высота здания.
Цель: рельеф у неё плюс её высота. Дома без высоты луч не закрывают
и не дают назвать этаж.
"""

from __future__ import annotations

import math

from common.snapshots import load_json
from view.raycast import to_xy

FLOOR_M = 3.0
EYE_M = 1.6
SKIP_M = 18.0


def _elevation(lon: float, lat: float, points: list[dict]) -> float:
    lon0, lat0 = points[0]["lon"], points[0]["lat"]
    ox, oy = to_xy(lon, lat, lon0, lat0)
    ranked = []
    for point in points:
        x, y = to_xy(point["lon"], point["lat"], lon0, lat0)
        ranked.append(((x - ox) ** 2 + (y - oy) ** 2, float(point["elevation_m"])))
    ranked.sort()
    if ranked[0][0] < 1.0:
        return ranked[0][1]
    weights = 0.0
    total = 0.0
    for dist2, elevation in ranked[:4]:
        weight = 1.0 / dist2
        weights += weight
        total += weight * elevation
    return total / weights


def _cross_distance(
    origin: tuple[float, float],
    toward: tuple[float, float],
    ring: list,
) -> float | None:
    best = None
    points = [(float(p[0]), float(p[1])) for p in ring]
    if len(points) < 2:
        return None
    rx, ry = toward[0] - origin[0], toward[1] - origin[1]
    for start, end in zip(points, points[1:] + points[:1]):
        sx, sy = end[0] - start[0], end[1] - start[1]
        denom = rx * sy - ry * sx
        if abs(denom) < 1e-8:
            continue
        qx, qy = start[0] - origin[0], start[1] - origin[1]
        t = (qx * sy - qy * sx) / denom
        u = (qx * ry - qy * rx) / denom
        if t <= 0 or t >= 1 or u < 0 or u > 1:
            continue
        dist = t * math.hypot(rx, ry)
        if best is None or dist < best:
            best = dist
    return best


def _along(origin_ll: list, target_ll: list, distance: float, total: float) -> tuple[float, float]:
    if total <= 0:
        return float(origin_ll[0]), float(origin_ll[1])
    share = distance / total
    lon = float(origin_ll[0]) + (float(target_ll[0]) - float(origin_ll[0])) * share
    lat = float(origin_ll[1]) + (float(target_ll[1]) - float(origin_ll[1])) * share
    return lon, lat


def _ordinal(floor: int) -> str:
    return f"{floor}-го"


def _prepare(buildings: list, lon0: float, lat0: float) -> list[dict]:
    prepared = []
    for feature in buildings:
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        rings = geometry.get("coordinates") or []
        if not rings or not isinstance(rings[0], list):
            continue
        ring = rings[0]
        if ring and isinstance(ring[0], list) and ring[0] and isinstance(ring[0][0], list):
            ring = ring[0]
        height = props.get("height")
        if height is None and props.get("building:levels") not in (None, ""):
            height = float(props["building:levels"]) * FLOOR_M
        prepared.append(
            {
                "id": props.get("id") or feature.get("id"),
                "ring": [(to_xy(float(p[0]), float(p[1]), lon0, lat0)) for p in ring if len(p) >= 2],
                "height_m": None if height is None else float(height),
            }
        )
    return prepared


def _wall_phrase(side: dict) -> str:
    if side.get("id") == "street":
        return "со стороны улицы"
    if side.get("id") == "opposite":
        return "с противоположной стороны"
    return "с этой стены"


def describe(hotel_id: str, props: dict, buildings: list) -> dict | None:
    landmark = props.get("view_landmark") or None
    if not landmark:
        return None
    wider = load_json("buildings_view.geojson", {})
    map_as_of = None
    if wider.get("features"):
        buildings = wider["features"]
        map_as_of = wider.get("as_of")
    terrain = load_json("terrain_pekin.json", {})
    points = terrain.get("points") or []
    if len(points) < 4:
        return None
    side = next((item for item in props.get("sides") or [] if item.get("id") == landmark.get("side_id")), None)
    if not side or not side.get("origin"):
        return None
    origin = side["origin"]
    target = landmark.get("point") or []
    if len(target) < 2:
        return None
    lon0, lat0 = float(origin[0]), float(origin[1])
    target_xy = to_xy(float(target[0]), float(target[1]), lon0, lat0)
    total = math.hypot(*target_xy)
    if total < 50:
        return None
    ground_here = _elevation(lon0, lat0, points)
    ground_there = _elevation(float(target[0]), float(target[1]), points)
    target_abs = ground_there + float(landmark.get("height_m") or 0)
    prepared = _prepare(buildings, lon0, lat0)
    levels = int(props.get("osm_levels") or 7)
    unknown = False
    blockers = []
    for building in prepared:
        dist = _cross_distance((0.0, 0.0), target_xy, building["ring"])
        if dist is None or dist < SKIP_M or dist >= total:
            continue
        if building["height_m"] is None:
            unknown = True
            continue
        hit_lon, hit_lat = _along(origin, target, dist, total)
        roof = _elevation(hit_lon, hit_lat, points) + building["height_m"]
        blockers.append({"id": building["id"], "distance_m": round(dist, 1), "roof_m": round(roof, 1)})

    def clear(floor: int) -> bool:
        eye = ground_here + (floor - 1) * FLOOR_M + EYE_M
        for step in range(1, int(total // 40)):
            dist = step * 40.0
            if dist >= total:
                break
            lon, lat = _along(origin, target, dist, total)
            sight = eye + (target_abs - eye) * (dist / total)
            if _elevation(lon, lat, points) > sight:
                return False
        for blocker in blockers:
            dist = blocker["distance_m"]
            sight = eye + (target_abs - eye) * (dist / total)
            if blocker["roof_m"] > sight:
                return False
        return True

    name = str(landmark.get("name") or "цель")
    where = _wall_phrase(side)
    opened = next((floor for floor in range(1, levels + 1) if not unknown and clear(floor)), None)
    if unknown:
        sentence = f"С какого этажа {where} виден {name}, по этим домам не скажем."
        opened = None
    elif opened is None:
        sentence = f"{where[:1].upper()}{where[1:]} {name} с {levels}-го этажа этого корпуса не открывается."
    else:
        sentence = (
            f"{name} {where} открывается с {_ordinal(opened)} этажа. "
            "Дома, которых нет в снимке окрестностей, в расчёт не входили."
        )
    scene = _scene(
        prepared,
        blockers,
        target_xy,
        ground_here,
        ground_there,
        float(landmark.get("height_m") or 0),
        points,
        origin,
        levels,
        opened,
        str(props.get("name") or "отель"),
    )
    return {
        "sentence": sentence,
        "floor": opened,
        "scene": scene,
        "levels": levels,
        "side_id": side.get("id"),
        "side_title": side.get("title"),
        "landmark": name,
        "ground_m": round(ground_here, 1),
        "target_ground_m": round(ground_there, 1),
        "target_top_m": round(target_abs, 1),
        "terrain_source": terrain.get("source"),
        "terrain_as_of": terrain.get("as_of"),
        "map_as_of": map_as_of,
        "blockers": blockers[:8],
    }


def _segment_distance(px: float, py: float, ax: float, ay: float, bx: float, by: float) -> float:
    abx, aby = bx - ax, by - ay
    length2 = abx * abx + aby * aby
    if length2 <= 1:
        return math.hypot(px - ax, py - ay)
    t = max(0.0, min(1.0, ((px - ax) * abx + (py - ay) * aby) / length2))
    return math.hypot(px - (ax + abx * t), py - (ay + aby * t))


def _ll(origin: list, x: float, y: float) -> tuple[float, float]:
    lon0, lat0 = float(origin[0]), float(origin[1])
    lon = lon0 + x / (111_320 * math.cos(math.radians(lat0)))
    lat = lat0 + y / 110_540
    return lon, lat


def _scene(
    prepared: list[dict],
    blockers: list[dict],
    target_xy: tuple[float, float],
    ground_here: float,
    ground_there: float,
    target_height: float,
    terrain_points: list[dict],
    origin: list,
    levels: int,
    opened: int | None,
    hotel_name: str,
) -> dict:
    blocker_ids = {item["id"] for item in blockers}
    shapes = []
    for building in prepared:
        ring = building["ring"]
        if building["height_m"] is None or len(ring) < 3:
            continue
        cx = sum(point[0] for point in ring) / len(ring)
        cy = sum(point[1] for point in ring) / len(ring)
        near_ray = _segment_distance(cx, cy, 0, 0, target_xy[0], target_xy[1]) < 200
        near_hotel = math.hypot(cx, cy) < 180
        if not near_ray and not near_hotel and building["id"] not in blocker_ids:
            continue
        if len(ring) > 36:
            step = math.ceil(len(ring) / 36)
            ring = ring[::step]
        lon, lat = _ll(origin, cx, cy)
        shapes.append(
            {
                "ring": [[round(point[0], 1), round(-point[1], 1)] for point in ring],
                "base": round(_elevation(lon, lat, terrain_points) - ground_here, 1),
                "height": round(building["height_m"], 1),
                "blocks": building["id"] in blocker_ids,
            }
        )
    margin = 280
    min_x = min(0.0, target_xy[0]) - margin
    max_x = max(0.0, target_xy[0]) + margin
    min_y = min(0.0, target_xy[1]) - margin
    max_y = max(0.0, target_xy[1]) + margin
    cols, rows = 24, 28
    step_x = (max_x - min_x) / (cols - 1)
    step_y = (max_y - min_y) / (rows - 1)
    heights = []
    for row in range(rows):
        north = min_y + row * step_y
        for col in range(cols):
            east = min_x + col * step_x
            lon, lat = _ll(origin, east, north)
            heights.append(round(_elevation(lon, lat, terrain_points) - ground_here, 1))
    length = math.hypot(*target_xy) or 1.0
    ray_blockers = []
    for blocker in sorted(blockers, key=lambda item: item["distance_m"]):
        share = blocker["distance_m"] / length
        ray_blockers.append(
            {
                "x": round(target_xy[0] * share, 1),
                "z": round(-target_xy[1] * share, 1),
                "distance": blocker["distance_m"],
                "roof": round(blocker["roof_m"] - ground_here, 1),
            }
        )
    return {
        "hotel": hotel_name,
        "levels": levels,
        "open_floor": opened or levels,
        "floor_m": FLOOR_M,
        "eye_m": EYE_M,
        "target": [
            round(target_xy[0], 1),
            round(ground_there - ground_here, 1),
            round(-target_xy[1], 1),
            target_height,
        ],
        "buildings": shapes,
        "blockers": ray_blockers,
        "terrain": {
            "cols": cols,
            "rows": rows,
            "origin": [round(min_x, 1), round(-min_y, 1)],
            "step": [round(step_x, 1), round(-step_y, 1)],
            "heights": heights,
        },
    }
