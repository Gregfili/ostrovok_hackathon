"""View Agent."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from view.service import for_hotel  # noqa: E402

app = FastAPI(title="View Agent")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "view"}


@app.post("/raycast")
def raycast_hotel(body: dict) -> dict:
    return for_hotel(body).model_dump()
