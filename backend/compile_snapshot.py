"""Снимок OSM для трёх отелей. Запуск из backend: python compile_snapshot.py

Берёт уже скачанные backend/data/_map_*.osm и полигоны Nominatim.
Минуты — длина пешего графа при 5 км/ч, не замер шагомером.
Луч и шум по этим файлам считают view и noise в момент запроса.
"""

from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data"
AS_OF = "2026-10-26"
OSM_COPYRIGHT = "https://www.openstreetmap.org/copyright"
SPEED_M_PER_MIN = 5000 / 60

MAPS = [
    "_map_pekin.osm",
    "_map_marriott.osm",
    "_map_lotte.osm",
    "_map_mid_s.osm",
    "_map_mid_n.osm",
]
BUILDING_MAPS = {"_map_pekin.osm", "_map_marriott.osm", "_map_lotte.osm"}

WALK = {
    "footway",
    "pedestrian",
    "path",
    "steps",
    "living_street",
    "residential",
    "unclassified",
    "service",
    "track",
}
MAIN = {"motorway", "trunk", "primary", "motorway_link", "trunk_link", "primary_link"}
ROAD = MAIN | {"secondary", "tertiary", "residential", "living_street", "unclassified", "pedestrian"}
NIGHT = {"bar", "nightclub", "pub", "biergarten", "stripclub"}

ANCHOR = (37.5931706, 55.7670820)
ANCHOR_OSM = "relation/7164364"

HOTELS = {
    "pekin": {
        "name": "Пекин",
        "address": "Большая Садовая улица, 5/1",
        "street": "Большая Садовая улица",
        "osm": "relation/2142863",
        "levels": 7,
        "wikidata": "Q1631004",
        "summary": "В OSM: Большая Садовая улица, 5/1, 7 этажей, relation/2142863, Wikidata Q1631004.",
        "polygon": "nominatim",
        "nominatim_id": 2142863,
    },
    "marriott-tverskaya": {
        "name": "Safmar Grand Moscow",
        "also_known": "Marriott Grand",
        "address": "Тверская улица, 26/1",
        "street": "Тверская улица",
        "osm": "relation/1421095",
        "levels": 9,
        "summary": (
            "В OSM здание называется Safmar Grand Moscow, Тверская улица, 26/1, "
            "9 этажей, relation/1421095. Подпись фото — Marriott, Тверская 25."
        ),
        "polygon": "nominatim",
        "nominatim_id": 1421095,
    },
    "lotte": {
        "name": "Lotte Hotel Moscow",
        "address": "Новинский бульвар, 8",
        "street": "Новинский бульвар",
        "osm": "way/37447149",
        "levels": 21,
        "summary": (
            "Точка отеля в OSM — node/2463731635 на здании Lotte Plaza, "
            "Новинский бульвар, 8, 21 этаж, way/37447149."
        ),
        "polygon": "way",
        "way_id": "37447149",
    },
}


def to_xy(lon: float, lat: float, lon0: float, lat0: float) -> tuple[float, float]:
    x = (lon - lon0) * 111_320 * math.cos(math.radians(lat0))
    y = (lat - lat0) * 110_540
    return x, y


def offset(lon: float, lat: float, east_m: float, north_m: float) -> list[float]:
    return [
        lon + east_m / (111_320 * math.cos(math.radians(lat))),
        lat + north_m / 110_540,
    ]


def meters(a: tuple[float, float], b: tuple[float, float]) -> float:
    x, y = to_xy(b[0], b[1], a[0], a[1])
    return math.hypot(x, y)


def norm_name(value: str) -> str:
    text = value.lower().replace("ё", "е")
    for word in ("улица", "переулок", "бульвар", "проспект", "площадь", "проезд"):
        text = text.replace(word, "")
    return " ".join(text.split())


def point_segment(point: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    ax, ay = to_xy(a[0], a[1], point[0], point[1])
    bx, by = to_xy(b[0], b[1], point[0], point[1])
    dx, dy = bx - ax, by - ay
    if dx == 0 and dy == 0:
        return math.hypot(ax, ay)
    t = max(0.0, min(1.0, (-ax * dx + -ay * dy) / (dx * dx + dy * dy)))
    return math.hypot(ax + t * dx, ay + t * dy)


def parse_maps() -> tuple[dict, list[dict], dict[str, str]]:
    nodes: dict[str, tuple[float, float, dict]] = {}
    ways: list[dict] = []
    station_by_node: dict[str, str] = {}
    for name in MAPS:
        path = DATA / name
        if not path.exists():
            raise SystemExit(f"Нет {path.name}. Снимок OSM не скачан.")
        building_map = name in BUILDING_MAPS
        for _event, el in ET.iterparse(path, events=("end",)):
            if el.tag == "node":
                tags = {tag.get("k"): tag.get("v") for tag in el.findall("tag")}
                nodes[el.get("id")] = (float(el.get("lon")), float(el.get("lat")), tags)
                el.clear()
            elif el.tag == "way":
                tags = {tag.get("k"): tag.get("v") for tag in el.findall("tag")}
                refs = [nd.get("ref") for nd in el.findall("nd")]
                ways.append({"id": el.get("id"), "refs": refs, "tags": tags, "buildings": building_map})
                el.clear()
            elif el.tag == "relation":
                tags = {tag.get("k"): tag.get("v") for tag in el.findall("tag")}
                station = tags.get("name")
                if station and tags.get("public_transport") == "stop_area":
                    for member in el.findall("member"):
                        if member.get("type") == "node" and member.get("ref"):
                            station_by_node[member.get("ref")] = station
                el.clear()
    return nodes, ways, station_by_node


def way_coords(way: dict, nodes: dict) -> list[tuple[float, float]]:
    coords = []
    for ref in way["refs"]:
        node = nodes.get(ref)
        if node:
            coords.append((node[0], node[1]))
    return coords


def load_hotel_rings(nodes: dict, ways: list[dict]) -> dict[str, list[list[float]]]:
    nominatim = json.loads((DATA / "_nominatim_hotels.json").read_text(encoding="utf-8"))
    by_id = {item["osm_id"]: item for item in nominatim}
    rings = {}
    for hotel_id, spec in HOTELS.items():
        if spec["polygon"] == "nominatim":
            geometry = by_id[spec["nominatim_id"]]["geojson"]
            ring = geometry["coordinates"][0]
        else:
            way = next(item for item in ways if item["id"] == spec["way_id"])
            ring = [[lon, lat] for lon, lat in way_coords(way, nodes)]
            if ring and ring[0] != ring[-1]:
                ring.append(ring[0])
        rings[hotel_id] = ring
    return rings


def centroid(ring: list[list[float]]) -> tuple[float, float]:
    pts = ring[:-1] if ring and ring[0] == ring[-1] else ring
    lon = sum(point[0] for point in pts) / len(pts)
    lat = sum(point[1] for point in pts) / len(pts)
    return lon, lat


def outward_edges(ring: list[list[float]]) -> list[dict]:
    pts = ring[:-1] if ring[0] == ring[-1] else ring
    area = 0.0
    for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]):
        area += x1 * y2 - x2 * y1
    sign = 1.0 if area > 0 else -1.0
    edges = []
    for a, b in zip(pts, pts[1:] + pts[:1]):
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        east, north = to_xy(b[0], b[1], a[0], a[1])
        length = math.hypot(east, north) or 1.0
        # CCW ring: interior is left, street side is the right-hand normal.
        out_e = sign * north / length
        out_n = sign * -east / length
        edges.append({"mid": mid, "out_e": out_e, "out_n": out_n, "length": length})
    return edges


def collect_roads(ways: list[dict], nodes: dict) -> list[dict]:
    roads = []
    seen = set()
    for way in ways:
        highway = way["tags"].get("highway")
        if highway not in ROAD:
            continue
        if way["id"] in seen:
            continue
        coords = way_coords(way, nodes)
        if len(coords) < 2:
            continue
        seen.add(way["id"])
        roads.append(
            {
                "id": f"way/{way['id']}",
                "name": way["tags"].get("name") or highway,
                "named": bool(way["tags"].get("name")),
                "highway": highway,
                "segs": list(zip(coords, coords[1:])),
                "refs": way["refs"],
            }
        )
    return roads


def nearest(
    point: tuple[float, float],
    roads: list[dict],
    street: str | None = None,
    named_only: bool = False,
) -> tuple[float, dict] | None:
    wanted = norm_name(street) if street else None
    best: tuple[float, dict] | None = None
    for road in roads:
        if named_only and not road.get("named"):
            continue
        if wanted is not None and norm_name(road["name"]) != wanted:
            continue
        for a, b in road["segs"]:
            dist = point_segment(point, a, b)
            if best is None or dist < best[0]:
                best = (dist, road)
    return best


def _side_record(side_id: str, title: str, edge: dict, roads: list[dict], street: str) -> dict:
    faced = nearest(edge["mid"], roads, named_only=True) or nearest(edge["mid"], roads)
    named = nearest(edge["mid"], roads, street)
    if faced is None or named is None:
        raise RuntimeError(f"Нет дороги у стороны {side_id}")
    origin = offset(edge["mid"][0], edge["mid"][1], edge["out_e"] * 2, edge["out_n"] * 2)
    target = offset(edge["mid"][0], edge["mid"][1], edge["out_e"] * 70, edge["out_n"] * 70)
    azimuth = (math.degrees(math.atan2(edge["out_e"], edge["out_n"])) + 360) % 360
    return {
        "id": side_id,
        "title": title,
        "origin": [round(origin[0], 7), round(origin[1], 7)],
        "target": [round(target[0], 7), round(target[1], 7)],
        "azimuth": round(azimuth, 1),
        "faces_distance_m": round(faced[0], 1),
        "faces_class": faced[1]["highway"],
        "faces_name": faced[1]["name"],
        "faces_osm": faced[1]["id"],
        "address_street": street,
        "address_distance_m": round(named[0], 1),
        "address_class": named[1]["highway"],
        "address_osm": named[1]["id"],
    }


def pick_sides(ring: list[list[float]], roads: list[dict], street: str) -> list[dict]:
    ranked = []
    for edge in outward_edges(ring):
        named = nearest(edge["mid"], roads, street)
        if named is None:
            continue
        ranked.append((named[0], edge))
    if not ranked:
        return []
    _near, street_edge = min(ranked, key=lambda item: item[0])
    _far, opposite_edge = max(ranked, key=lambda item: item[0])
    return [
        _side_record("street", "Улица", street_edge, roads, street),
        _side_record("opposite", "Противоположная сторона", opposite_edge, roads, street),
    ]


def buildings_near(ways: list[dict], nodes: dict, centers: list[tuple[float, float]]) -> list[dict]:
    features = []
    seen = set()
    for way in ways:
        if not way["buildings"] or "building" not in way["tags"]:
            continue
        if way["id"] in seen:
            continue
        coords = way_coords(way, nodes)
        if len(coords) < 4:
            continue
        center = centroid([[lon, lat] for lon, lat in coords])
        if all(meters(center, hotel) > 220 for hotel in centers):
            continue
        seen.add(way["id"])
        tags = way["tags"]
        ring = [[lon, lat] for lon, lat in coords]
        if ring[0] != ring[-1]:
            ring.append(ring[0])
        levels = tags.get("building:levels")
        height = tags.get("height")
        props = {"id": f"way/{way['id']}", "name": tags.get("name")}
        if height:
            props["height"] = height.replace("m", "").strip()
        if levels:
            props["building:levels"] = levels
        features.append(
            {
                "type": "Feature",
                "id": f"way/{way['id']}",
                "properties": props,
                "geometry": {"type": "Polygon", "coordinates": [ring]},
            }
        )
    return features


def night_pois(nodes: dict, centers: list[tuple[float, float]]) -> list[dict]:
    items = []
    seen = set()
    for node_id, (lon, lat, tags) in nodes.items():
        amenity = tags.get("amenity")
        if amenity not in NIGHT or node_id in seen:
            continue
        if all(meters((lon, lat), hotel) > 400 for hotel in centers):
            continue
        seen.add(node_id)
        items.append(
            {
                "id": f"node/{node_id}",
                "name": tags.get("name") or amenity,
                "amenity": amenity,
                "lon": lon,
                "lat": lat,
            }
        )
    return items


def metro_entrances(nodes: dict) -> list[dict]:
    items = []
    for node_id, (lon, lat, tags) in nodes.items():
        if tags.get("railway") != "subway_entrance":
            continue
        items.append(
            {
                "id": f"node/{node_id}",
                "name": tags.get("name") or tags.get("ref") or "вход без имени",
                "lon": lon,
                "lat": lat,
            }
        )
    return items


def build_graph(ways: list[dict], nodes: dict) -> tuple[dict, dict, dict]:
    adj: dict[str, list[tuple[str, float, str]]] = defaultdict(list)
    way_tags = {}
    main_nodes: dict[str, set[str]] = defaultdict(set)
    seen = set()
    for way in ways:
        tags = way["tags"]
        highway = tags.get("highway")
        if not highway or way["id"] in seen:
            continue
        seen.add(way["id"])
        way_tags[way["id"]] = tags
        refs = [ref for ref in way["refs"] if ref in nodes]
        if highway in MAIN:
            name = tags.get("name") or highway
            for ref in refs:
                main_nodes[ref].add(name)
        if highway not in WALK:
            continue
        if tags.get("access") in {"private", "no"} or tags.get("foot") in {"no", "private"}:
            continue
        for left, right in zip(refs, refs[1:]):
            dist = meters(nodes[left][:2], nodes[right][:2])
            if dist <= 0 or dist > 400:
                continue
            adj[left].append((right, dist, way["id"]))
            adj[right].append((left, dist, way["id"]))
    return adj, way_tags, main_nodes


def route(
    adj: dict,
    nodes: dict,
    origin: tuple[float, float],
    goal: tuple[float, float],
) -> dict | None:
    start_ids = [
        node_id
        for node_id in adj
        if meters(nodes[node_id][:2], origin) <= 80
    ]
    goal_ids = [
        node_id
        for node_id in adj
        if meters(nodes[node_id][:2], goal) <= 80
    ]
    if not start_ids or not goal_ids:
        return None
    start = "snap-start"
    end = "snap-end"
    graph = defaultdict(list)
    for node_id, edges in adj.items():
        graph[node_id].extend(edges)
    for node_id in start_ids:
        dist = meters(nodes[node_id][:2], origin)
        graph[start].append((node_id, dist, ""))
    for node_id in goal_ids:
        dist = meters(nodes[node_id][:2], goal)
        graph[node_id].append((end, dist, ""))

    dist = {start: 0.0}
    prev: dict[str, tuple[str, str]] = {}
    heap: list[tuple[float, str]] = [(0.0, start)]
    import heapq

    while heap:
        current, node_id = heapq.heappop(heap)
        if current != dist.get(node_id):
            continue
        if node_id == end:
            break
        for nxt, weight, way_id in graph[node_id]:
            nxt_dist = current + weight
            if nxt_dist < dist.get(nxt, 1e18):
                dist[nxt] = nxt_dist
                prev[nxt] = (node_id, way_id)
                heapq.heappush(heap, (nxt_dist, nxt))
    if end not in dist:
        return None

    path_nodes = []
    cursor = end
    while cursor != start:
        parent, _way_id = prev[cursor]
        if cursor in nodes:
            path_nodes.append(cursor)
        cursor = parent
    path_nodes.reverse()
    return {
        "distance_m": round(dist[end]),
        "minutes": max(1, round(dist[end] / SPEED_M_PER_MIN)),
        "path_nodes": path_nodes,
    }


def _orient(a: tuple[float, float], b: tuple[float, float], c: tuple[float, float]) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _proper_cross(p1: tuple[float, float], p2: tuple[float, float], q1: tuple[float, float], q2: tuple[float, float]) -> bool:
    o1 = _orient(p1, p2, q1)
    o2 = _orient(p1, p2, q2)
    o3 = _orient(q1, q2, p1)
    o4 = _orient(q1, q2, p2)
    return o1 * o2 < 0 and o3 * o4 < 0


def crossing_names(path_nodes: list[str], nodes: dict, main_nodes: dict, roads: list[dict]) -> list[str]:
    names: list[str] = []
    for node_id in path_nodes:
        for name in sorted(main_nodes.get(node_id, ())):
            if name not in names:
                names.append(name)
    primary = [road for road in roads if road["highway"] in MAIN]
    coords = [nodes[node_id][:2] for node_id in path_nodes]
    for a, b in zip(coords, coords[1:]):
        ab = (to_xy(a[0], a[1], ANCHOR[0], ANCHOR[1]), to_xy(b[0], b[1], ANCHOR[0], ANCHOR[1]))
        for road in primary:
            hit = False
            for left, right in road["segs"]:
                cd = (
                    to_xy(left[0], left[1], ANCHOR[0], ANCHOR[1]),
                    to_xy(right[0], right[1], ANCHOR[0], ANCHOR[1]),
                )
                if _proper_cross(ab[0], ab[1], cd[0], cd[1]):
                    hit = True
                    break
            if hit and road["name"] not in names:
                names.append(road["name"])
    return names


def write(name: str, payload: dict) -> None:
    path = DATA / name
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {name}")


def main() -> None:
    nodes, ways, station_by_node = parse_maps()
    rings = load_hotel_rings(nodes, ways)
    centers = {hotel_id: centroid(ring) for hotel_id, ring in rings.items()}
    roads = collect_roads(ways, nodes)
    hotels_doc = json.loads((DATA / "hotels.geojson").read_text(encoding="utf-8"))
    by_feature = {feature.get("id"): feature for feature in hotels_doc["features"]}

    for hotel_id, spec in HOTELS.items():
        ring = rings[hotel_id]
        sides = pick_sides(ring, roads, spec["street"])
        feature = by_feature[hotel_id]
        props = feature["properties"]
        props["name"] = spec["name"]
        props["address"] = spec["address"]
        props["summary"] = spec["summary"]
        props["osm"] = spec["osm"]
        props["osm_levels"] = spec["levels"]
        props["eye_height_m"] = 2
        props["sides"] = sides
        if spec.get("also_known"):
            props["also_known"] = spec["also_known"]
        if sides:
            props["side_origin"] = sides[0]["origin"]
            props["view_target"] = sides[0]["target"]
            props["side_azimuth"] = sides[0]["azimuth"]
        if spec.get("anchor_ray"):
            props["anchor_target"] = [ANCHOR[0], ANCHOR[1]]
        else:
            props.pop("anchor_target", None)
        feature["geometry"] = {"type": "Polygon", "coordinates": [ring]}
        print(hotel_id, "center", [round(v, 5) for v in centers[hotel_id]])
        for side in sides:
            print(
                " ",
                side["id"],
                "faces",
                side["faces_class"],
                side["faces_name"],
                side["faces_distance_m"],
                "m; to",
                side["address_street"],
                side["address_distance_m"],
                "m",
            )

    building_features = buildings_near(ways, nodes, list(centers.values()) + [ANCHOR])
    print("buildings", len(building_features))
    pois = night_pois(nodes, list(centers.values()))
    print("night poi", len(pois), [item["name"] for item in pois])
    entrances = metro_entrances(nodes)
    print("metro entrances", len(entrances))

    adj, way_tags, main_nodes = build_graph(ways, nodes)
    print("graph nodes", len(adj))
    walks = []
    for hotel_id, center in centers.items():
        found = route(adj, nodes, ANCHOR, center)
        if not found:
            print(hotel_id, "NO ROUTE")
            continue
        names = crossing_names(found.pop("path_nodes"), nodes, main_nodes, roads)
        found["hotel_id"] = hotel_id
        found["anchor_id"] = "bad_apartment"
        found["crosses_trunk"] = bool(names)
        found["crossing_names"] = names
        found["confidence"] = 0.75
        found["detail"] = (
            "Длина пеших линий OSM до Садовой, 10, скорость 5 км/ч. "
            "Это не замер шагомером и не время с багажом."
        )
        walks.append(found)
        print(hotel_id, found["minutes"], "min", found["distance_m"], "m", "cross", names)

    nearest_metro = []
    for hotel_id, center in centers.items():
        best = None
        for entrance in entrances:
            dist = meters(center, (entrance["lon"], entrance["lat"]))
            if dist > 900:
                continue
            if best is None or dist < best[0]:
                best = (dist, entrance)
        if best:
            node_id = best[1]["id"].split("/", 1)[1]
            station = station_by_node.get(node_id)
            nearest_metro.append(
                {
                    "hotel_id": hotel_id,
                    "station": station,
                    "entrance": best[1]["name"],
                    "distance_m": round(best[0]),
                    "osm": best[1]["id"],
                }
            )
            print("metro", hotel_id, station, "вход", best[1]["name"], round(best[0]))

    write("hotels.geojson", hotels_doc)
    write(
        "buildings.geojson",
        {
            "type": "FeatureCollection",
            "as_of": AS_OF,
            "source": OSM_COPYRIGHT,
            "features": building_features,
        },
    )
    write(
        "night_poi.geojson",
        {"as_of": AS_OF, "source": OSM_COPYRIGHT, "items": pois},
    )
    write(
        "walk_cache.json",
        {
            "as_of": AS_OF,
            "source": OSM_COPYRIGHT,
            "anchor_osm": ANCHOR_OSM,
            "speed_m_per_min": round(SPEED_M_PER_MIN, 3),
            "items": walks,
        },
    )
    write(
        "metro_entrances.json",
        {
            "as_of": AS_OF,
            "source": OSM_COPYRIGHT,
            "repairs": "not_collected",
            "items": nearest_metro,
        },
    )
    anchors = json.loads((DATA / "anchors.json").read_text(encoding="utf-8"))
    for item in anchors.get("items", []):
        if item.get("id") != "bad_apartment":
            continue
        item["lat"] = ANCHOR[1]
        item["lon"] = ANCHOR[0]
        item["osm"] = ANCHOR_OSM
        item["note"] = (
            "Координаты — «Булгаковский дом», OSM relation/7164364, Wikidata Q4098878. "
            "В каталоге якорь по-прежнему квартира Wikidata Q4146884."
        )
    anchors["as_of"] = AS_OF
    write("anchors.json", anchors)


if __name__ == "__main__":
    main()
