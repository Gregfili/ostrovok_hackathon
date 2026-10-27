"""Контракт факта. Гостю уходит эта схема, не свободный текст модели."""

from __future__ import annotations

from pydantic import BaseModel, Field


class Fact(BaseModel):
    feature: str
    value: str | None = None
    method: str
    sources: list[str] = Field(default_factory=list)
    confidence: float
    as_of: str | None = None
    ttl_days: int | None = None
    conflicts: list[str] = Field(default_factory=list)
    hotelier_status: str = "computed"
    hotel_id: str | None = None
    side: str | None = None
    question: str | None = None
    detail: str | None = None
    data: dict = Field(default_factory=dict)


class Recipe(BaseModel):
    id: str
    tools: list[str] = Field(default_factory=list)
    min_confidence: float = 0.6
    if_below: str = "ask_hotelier"
    ttl_days: int = 90
    question: str = ""


def unknown(feature: str, method: str, detail: str, hotel_id: str | None = None) -> Fact:
    return Fact(
        feature=feature,
        value="не знаем",
        method=method,
        confidence=0.0,
        hotelier_status="unknown",
        hotel_id=hotel_id,
        detail=detail,
    )
