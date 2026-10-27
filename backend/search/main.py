"""Search Agent."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from search.service import answer  # noqa: E402

app = FastAPI(title="Search Agent")


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    dates: str = ""


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "search"}


@app.post("/search")
def search(body: SearchRequest) -> dict:
    return answer(body.query, body.dates)
