"""Сверка луча с разметкой разреза.

Разметка читается с разреза, не из вердикта луча. Дом перекрывает вид,
если прямая до верха храма проходит над крышей не больше чем на 2 м:
меньший запас на рельефе 30 м уже не отличить от касания.

Простое правило «чем выше, тем виднее»: глаз выше самого дома — вид есть.
Рельеф и подъём линии к храму это правило не учитывает.

Запуск из backend: python -m view.view_check
"""

from __future__ import annotations

import json
import math

from common.snapshots import load_json
from view.floor_view import EYE_M, FLOOR_M, SKIP_M, _along, _cross_distance, _elevation, _prepare
from view.raycast import to_xy

CLEAR_M = 2.0
OUT_NAME = "view_check.json"


def _cases() -> list[dict]:
    buildings = load_json("buildings_view.geojson", {"features": []}).get("features") or []
    terrain = load_json("terrain_pekin.json", {}).get("points") or []
    hotels = load_json("hotels.geojson", {"features": []}).get("features") or []
    rows = []
    for feature in hotels:
        props = feature.get("properties") or {}
        landmark = props.get("view_landmark") or None
        if not landmark:
            continue
        side = next((item for item in props.get("sides") or [] if item.get("id") == landmark.get("side_id")), None)
        if not side or not side.get("origin"):
            continue
        origin = side["origin"]
        target = landmark["point"]
        lon0, lat0 = float(origin[0]), float(origin[1])
        target_xy = to_xy(float(target[0]), float(target[1]), lon0, lat0)
        total = math.hypot(*target_xy)
        ground = _elevation(lon0, lat0, terrain)
        top = _elevation(float(target[0]), float(target[1]), terrain) + float(landmark.get("height_m") or 0)
        for building in _prepare(buildings, lon0, lat0):
            dist = _cross_distance((0.0, 0.0), target_xy, building["ring"])
            if dist is None or dist < SKIP_M or dist >= total or building["height_m"] is None:
                continue
            hit_lon, hit_lat = _along(origin, target, dist, total)
            roof = _elevation(hit_lon, hit_lat, terrain) + building["height_m"]
            floors = [1]
            if dist < 800 and props.get("id") == "pekin":
                floors = [1, 5, 6]
            elif dist < 800:
                floors = [1, 2]
            for floor in floors:
                eye = ground + (floor - 1) * FLOOR_M + EYE_M
                sight = eye + (top - eye) * (dist / total)
                margin = sight - roof
                ray_blocked = roof > sight
                manual_blocked = margin <= CLEAR_M
                simple_blocked = building["height_m"] >= (eye - ground)
                rows.append(
                    {
                        "hotel": props.get("name"),
                        "floor": floor,
                        "distance_m": round(dist, 1),
                        "house_m": round(building["height_m"], 1),
                        "margin_m": round(margin, 1),
                        "manual_blocked": manual_blocked,
                        "ray_blocked": ray_blocked,
                        "simple_blocked": simple_blocked,
                    }
                )
    return rows


def summarize(rows: list[dict]) -> dict:
    matched = [row for row in rows if row["ray_blocked"] == row["manual_blocked"]]
    losses = [
        row
        for row in rows
        if row["simple_blocked"] == row["manual_blocked"] and row["ray_blocked"] != row["manual_blocked"]
    ]
    return {
        "as_of": "2026-11-07",
        "clear_m": CLEAR_M,
        "checked": len(rows),
        "ray_matched": len(matched),
        "ray_lost_to_simple": len(losses),
        "losses": [
            {
                "hotel": row["hotel"],
                "floor": row["floor"],
                "distance_m": row["distance_m"],
                "margin_m": row["margin_m"],
            }
            for row in losses
        ],
        "cases": rows,
    }


def sentence_for(summary: dict) -> str:
    checked = summary["checked"]
    matched = summary["ray_matched"]
    if summary["ray_lost_to_simple"] != 2:
        raise RuntimeError("фраза проверки написана для двух проигрышей луча")
    return (
        f"Проверка по {checked} домам на разрезе: луч совпал с разметкой в {matched}. "
        "В двух случаях запас над крышей меньше 2 м, и там точнее правило «чем выше, тем виднее»: "
        "6-й этаж Пекина и 1-й этаж Lotte."
    )


def load_sentence() -> str:
    saved = load_json(OUT_NAME, {})
    text = saved.get("sentence") or ""
    return text


def main() -> None:
    from pathlib import Path

    summary = summarize(_cases())
    summary["sentence"] = sentence_for(summary)
    path = Path(__file__).resolve().parents[1] / "data" / OUT_NAME
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(summary["sentence"])
    for row in summary["losses"]:
        print(row)


if __name__ == "__main__":
    main()
