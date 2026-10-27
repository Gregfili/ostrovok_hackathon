"""Чтение JSON-снимков из backend/data. Сеть здесь не вызывается."""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"


def load_json(name: str, default: dict | None = None) -> dict:
    path = DATA / name
    if not path.exists():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))
