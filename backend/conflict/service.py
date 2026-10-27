"""Два значения одного поля. Ответ отельера строку OSM не удаляет."""

from __future__ import annotations

from common.models import Fact


def ping() -> dict:
    return {"status": "ok", "service": "conflict"}


def _hotelier_beats(osm: Fact, hotelier: Fact) -> bool:
    if not osm.as_of:
        return True
    if not hotelier.as_of:
        return False
    return osm.as_of < hotelier.as_of


def judge(osm: Fact | None, hotelier: Fact | None, min_confidence: float = 0.6) -> dict:
    if hotelier is None and osm is None:
        return {"status": "unknown", "accepted": None, "rows": []}
    if hotelier is None:
        assert osm is not None
        if osm.confidence < min_confidence or osm.value in (None, "не знаем"):
            return {"status": "unknown", "accepted": None, "rows": [osm]}
        return {"status": "computed", "accepted": osm, "rows": [osm]}
    if osm is None:
        if hotelier.confidence < min_confidence:
            return {"status": "unknown", "accepted": None, "rows": [hotelier]}
        accepted = hotelier.model_copy(update={"hotelier_status": "confirmed"})
        return {"status": "confirmed", "accepted": accepted, "rows": [accepted]}
    if osm.value != hotelier.value:
        if _hotelier_beats(osm, hotelier):
            marked = osm.model_copy(update={"conflicts": [*osm.conflicts, "hotelier"]})
            accepted = hotelier.model_copy(
                update={"hotelier_status": "confirmed", "conflicts": [*hotelier.conflicts, "osm"]}
            )
            return {"status": "conflict", "accepted": accepted, "rows": [marked, accepted]}
        return {
            "status": "unresolved",
            "accepted": None,
            "rows": [
                osm.model_copy(update={"conflicts": [*osm.conflicts, "hotelier"]}),
                hotelier.model_copy(
                    update={"hotelier_status": "unresolved", "conflicts": [*hotelier.conflicts, "osm"]}
                ),
            ],
        }
    accepted = hotelier.model_copy(update={"hotelier_status": "confirmed"})
    return {"status": "confirmed", "accepted": accepted, "rows": [osm, accepted]}
