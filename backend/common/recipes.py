"""Реестр характеристик. Оркестратор читает инструменты отсюда, без ветки по имени факта."""

from __future__ import annotations

from pathlib import Path

import yaml

from common.models import Recipe

RECIPES = Path(__file__).resolve().parents[1] / "recipes"


def load_recipes() -> list[Recipe]:
    recipes: list[Recipe] = []
    for path in sorted(RECIPES.glob("*.yaml")):
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        raw.setdefault("id", path.stem)
        recipes.append(Recipe.model_validate(raw))
    return recipes
