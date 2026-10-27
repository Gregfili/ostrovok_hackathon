"""Mobility Agent."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from mobility.service import walk_to  # noqa: E402

app = FastAPI(title="Mobility Agent")


class WalkRequest(BaseModel):
    hotel_id: str
    anchor_id: str = "bad_apartment"


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "mobility"}


@app.post("/walk_to")
def walk(body: WalkRequest) -> dict:
    return walk_to(body.hotel_id, body.anchor_id).model_dump()
