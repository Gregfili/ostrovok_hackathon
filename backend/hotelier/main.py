"""Hotelier Agent."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from hotelier.service import parse_text, submit  # noqa: E402

app = FastAPI(title="Hotelier Agent")


class TextBody(BaseModel):
    text: str = Field(min_length=1)
    hotel_id: str | None = None


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "hotelier"}


@app.post("/parse")
def parse(body: TextBody) -> dict:
    if body.hotel_id:
        return submit(body.hotel_id, body.text)
    return parse_text(body.text)
