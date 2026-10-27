"""Hotel FAQ Agent — отдельный процесс (uvicorn hotel_faq.main:app --port 8092)."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from hotel_faq.service import (  # noqa: E402
    answer_question,
    delete_document,
    get_config,
    init_faq_db,
    ping,
    save_config,
    upload_document,
    vector_retrieve,
)

app = FastAPI(title="Hotel FAQ Agent")


@app.on_event("startup")
def startup() -> None:
    init_faq_db()


@app.get("/health")
def health() -> dict:
    return ping()


@app.get("/hotels/{hotel_id}")
def config(hotel_id: str) -> dict:
    return get_config(hotel_id)


class ConfigBody(BaseModel):
    enabled: bool | None = None
    sections: dict[str, str] | None = None


@app.put("/hotels/{hotel_id}")
def put_config(hotel_id: str, body: ConfigBody) -> dict:
    return save_config(hotel_id, body.enabled, body.sections)


@app.post("/hotels/{hotel_id}/upload")
async def upload(hotel_id: str, file: UploadFile = File(...)) -> dict:
    raw = await file.read()
    try:
        return upload_document(hotel_id, file.filename or "upload.txt", raw)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.delete("/hotels/{hotel_id}/documents/{document_id}")
def remove_document(hotel_id: str, document_id: int) -> dict:
    try:
        return delete_document(hotel_id, document_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


class AskBody(BaseModel):
    question: str = Field(min_length=1)


@app.post("/hotels/{hotel_id}/ask")
def ask(hotel_id: str, body: AskBody) -> dict:
    return answer_question(hotel_id, body.question)


class VectorBody(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=4, ge=1, le=10)


@app.post("/hotels/{hotel_id}/vector-retrieve")
def vector_route(hotel_id: str, body: VectorBody) -> dict:
    return vector_retrieve(hotel_id, body.question, top_k=body.top_k)
