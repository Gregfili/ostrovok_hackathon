"""Оркестратор читает YAML и вызывает названный инструмент. Ветки по имени характеристики нет."""

from __future__ import annotations

from common.models import Fact
from common.recipes import load_recipes
from events.service import for_hotel as metro_exits
from mobility.service import for_hotel as walk_to
from noise.service import for_hotel as facade_noise
from view.service import for_hotel as building_raycast
from geo.service import list_hotels

TOOLS = {
    "building_raycast": building_raycast,
    "facade_noise": facade_noise,
    "walk_to": walk_to,
    "metro_exits": metro_exits,
}


class _Safe(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


def run_recipe(recipe, ctx: dict) -> list[Fact]:
    if not recipe.tools:
        fact = Fact(
            feature=recipe.id,
            value="не знаем",
            method="recipe",
            confidence=0.0,
            hotelier_status="unknown",
            hotel_id=ctx.get("hotel_id"),
            question=recipe.question,
            ttl_days=recipe.ttl_days,
            detail="В рецепте нет гео-инструмента.",
        )
        return [fact]
    facts: list[Fact] = []
    for name in recipe.tools:
        fact = TOOLS[name](ctx)
        if fact.confidence < recipe.min_confidence and recipe.if_below == "ask_hotelier":
            fact.question = recipe.question.format_map(
                _Safe(side=ctx.get("side") or "эту сторону", anchor=ctx.get("anchor") or "якоря")
            )
            fact.hotelier_status = "unknown"
            if not fact.value:
                fact.value = "не знаем"
        fact.ttl_days = recipe.ttl_days
        facts.append(fact)
    return facts


def build_dossier(anchor: dict | None, dates: str) -> dict:
    recipes = load_recipes()
    hotels = list_hotels()
    anchor = anchor or {}
    if not hotels:
        pets = next((recipe for recipe in recipes if not recipe.tools), None)
        sample = run_recipe(pets, {"anchor": anchor.get("place")}) if pets else []
        return {
            "hotels": [],
            "recipes": [recipe.id for recipe in recipes],
            "sample": [fact.model_dump() for fact in sample],
            "note": "В data/ нет hotels.geojson, сравнивать отели нечего.",
        }
    rows = []
    for hotel in hotels:
        street = next((side for side in hotel.get("sides") or [] if side.get("id") == "street"), None)
        ctx = {
            "hotel_id": hotel["id"],
            "anchor_id": anchor.get("id") or "bad_apartment",
            "anchor": anchor.get("place"),
            "dates": dates,
            "side": "улицу" if street else "эту сторону",
        }
        facts: list[Fact] = []
        for recipe in recipes:
            facts.extend(run_recipe(recipe, ctx))
        rows.append(
            {
                "id": hotel["id"],
                "name": hotel["name"],
                "address": hotel["address"],
                "summary": hotel.get("summary"),
                "image": hotel.get("image"),
                "image_credit": hotel.get("image_credit"),
                "image_source": hotel.get("image_source"),
                "also_known": hotel.get("also_known"),
                "osm_levels": hotel.get("osm_levels"),
                "facts": [fact.model_dump() for fact in facts],
            }
        )
    return {"hotels": rows, "recipes": [recipe.id for recipe in recipes], "note": ""}
