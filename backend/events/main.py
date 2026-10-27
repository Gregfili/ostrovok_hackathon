"""City Events Agent."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from events.service import closed_exits, for_hotel  # noqa: E402

app = FastAPI(title="City Events Agent")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "events"}


@app.get("/metro_repairs")
def metro_repairs() -> dict:
    return {"closed": closed_exits()}


@app.post("/metro_exits")
def metro_exits(body: dict) -> dict:
    return for_hotel(body).model_dump()
