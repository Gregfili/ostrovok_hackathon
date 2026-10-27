"""Conflict Agent."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from common.models import Fact  # noqa: E402
from conflict.service import judge  # noqa: E402

app = FastAPI(title="Conflict Agent")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "conflict"}


@app.post("/judge")
def judge_facts(body: dict) -> dict:
    osm = Fact.model_validate(body["osm"]) if body.get("osm") else None
    hotelier = Fact.model_validate(body["hotelier"]) if body.get("hotelier") else None
    result = judge(osm, hotelier, float(body.get("min_confidence", 0.6)))
    return {
        "status": result["status"],
        "accepted": result["accepted"].model_dump() if result["accepted"] else None,
        "rows": [row.model_dump() for row in result["rows"]],
    }
