"""Noise Agent."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from noise.service import for_hotel  # noqa: E402

app = FastAPI(title="Noise Agent")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "noise"}


@app.post("/facade_noise")
def facade_noise(body: dict) -> dict:
    return for_hotel(body).model_dump()
