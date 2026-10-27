"""Geo Agent."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from geo.service import list_hotels, resolve_anchor  # noqa: E402

app = FastAPI(title="Geo Agent")


class AnchorRequest(BaseModel):
    text: str


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "geo"}


@app.post("/resolve_anchor")
def anchor(body: AnchorRequest) -> dict:
    return resolve_anchor(body.text)


@app.get("/hotels")
def hotels() -> dict:
    return {"hotels": list_hotels()}
