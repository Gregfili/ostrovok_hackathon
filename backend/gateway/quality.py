"""Метрики по ручной разметке labels.json."""

from __future__ import annotations

from common.snapshots import DATA, load_json


def quality_report() -> dict:
    if not (DATA / "labels.json").exists():
        return {
            "hotels": 0,
            "walk_within_2min": None,
            "occlusion_match": None,
            "coverage": None,
            "hotelier_questions": None,
            "note": "Нет data/labels.json, метрики не посчитаны.",
        }
    items = load_json("labels.json", {"items": []}).get("items", [])
    walk_known = [item for item in items if item.get("walk_error_min") is not None]
    occlusion_known = [item for item in items if item.get("occlusion_match") is not None]
    filled = sum(item.get("features_filled") or 0 for item in items)
    total = sum(item.get("features_total") or 0 for item in items)
    asked = sum(1 for item in items if item.get("asked_hotelier"))
    return {
        "hotels": len(items),
        "walk_within_2min": (
            sum(1 for item in walk_known if abs(item["walk_error_min"]) <= 2) / len(walk_known)
            if walk_known
            else None
        ),
        "occlusion_match": (
            sum(1 for item in occlusion_known if item["occlusion_match"]) / len(occlusion_known)
            if occlusion_known
            else None
        ),
        "coverage": (filled / total) if total else None,
        "hotelier_questions": (asked / len(items)) if items else None,
        "note": "",
    }
