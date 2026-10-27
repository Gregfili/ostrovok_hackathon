"""Hotel Fact Agent: публичный шлюз на порту 8080.

Агенты подключены как модули этого процесса. У каждого есть свой main.py,
его можно поднять отдельно, когда появится Compose.
"""

from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

BACKEND = Path(__file__).resolve().parents[1]
FRONTEND_DIST = BACKEND.parent / "frontend" / "dist"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from admin.service import (  # noqa: E402
    ask,
    create_guest,
    desk,
    list_accounts,
    pay,
    post_booking_ask,
    register_hotel,
    remember_question,
    send_reply,
)
from common.db import facts_for, init_db  # noqa: E402
from conflict.service import ping as conflict_ping  # noqa: E402
from events.service import ping as events_ping  # noqa: E402
from gateway.quality import quality_report  # noqa: E402
from geo.service import get_hotel, ping as geo_ping  # noqa: E402
from hotel_faq.service import (  # noqa: E402
    answer_question as faq_answer,
    delete_document as faq_delete_document,
    get_config as faq_get_config,
    init_faq_db,
    ping as faq_ping,
    save_config as faq_save_config,
    upload_document as faq_upload,
    vector_retrieve as faq_vector_retrieve,
)
from hotelier.service import ping as hotelier_ping, submit  # noqa: E402
from mobility.service import ping as mobility_ping, walk_to  # noqa: E402
from noise.service import ping as noise_ping  # noqa: E402
from search.service import answer, ping as search_ping  # noqa: E402
from view.service import ping as view_ping  # noqa: E402

AGENTS = {
    "geo": geo_ping,
    "view": view_ping,
    "noise": noise_ping,
    "mobility": mobility_ping,
    "events": events_ping,
    "hotelier": hotelier_ping,
    "conflict": conflict_ping,
    "search": search_ping,
    "hotel_faq": faq_ping,
}


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    init_faq_db()
    yield


app = FastAPI(title="Hotel Fact Agent", lifespan=lifespan)


class SearchRequest(BaseModel):
    query: str = Field(min_length=1)
    dates: str = ""
    hotel_id: str = ""
    guest_id: str = ""


class HotelierRequest(BaseModel):
    text: str = Field(min_length=1)


class WalkRequest(BaseModel):
    hotel_id: str
    anchor_id: str = "bad_apartment"


class GuestAccountRequest(BaseModel):
    name: str = Field(min_length=1)


class AskRequest(BaseModel):
    guest_id: str
    hotel_id: str
    text: str = Field(min_length=1)


class PostBookingAskRequest(BaseModel):
    guest_id: str
    hotel_id: str
    text: str = Field(min_length=1)


class ReplyRequest(BaseModel):
    account_id: str
    text: str = Field(min_length=1)


class RegisterHotelRequest(BaseModel):
    name: str = Field(min_length=1)
    address: str = ""


class PayRequest(BaseModel):
    guest_id: str
    hotel_id: str
    check_in: str
    check_out: str


class FaqConfigRequest(BaseModel):
    enabled: bool | None = None
    sections: dict[str, str] | None = None


class FaqAskRequest(BaseModel):
    question: str = Field(min_length=1)


class FaqVectorRequest(BaseModel):
    question: str = Field(min_length=1)
    top_k: int = Field(default=4, ge=1, le=10)


@app.get("/health")
def health() -> dict:
    agents = {name: fn()["status"] for name, fn in AGENTS.items()}
    status = "ok" if all(value == "ok" for value in agents.values()) else "degraded"
    return {"status": status, "agents": agents}


@app.post("/api/search")
def search(body: SearchRequest) -> dict:
    text = body.query.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Нужна фраза гостя")
    result = answer(text, body.dates, body.hotel_id, body.guest_id)
    question = (result.get("dialogue") or {}).get("hotelier_question") or ""
    for hotel in (result.get("dialogue") or {}).get("hotels") or []:
        remember_question(str(hotel.get("id") or ""), question)
    return result


@app.get("/api/hotels/{hotel_id}")
def hotel(hotel_id: str) -> dict:
    found = get_hotel(hotel_id)
    if found is None:
        raise HTTPException(status_code=404, detail="Этого отеля нет в снимке")
    public = {key: value for key, value in found.items() if key != "geometry"}
    public["facts"] = [fact.model_dump() for fact in facts_for(hotel_id)]
    return public


@app.post("/api/hotels/{hotel_id}/hotelier")
def hotelier(hotel_id: str, body: HotelierRequest) -> dict:
    return submit(hotel_id, body.text)


@app.post("/api/walk")
def walk(body: WalkRequest) -> dict:
    return walk_to(body.hotel_id, body.anchor_id).model_dump()


@app.get("/api/quality")
def quality() -> dict:
    return quality_report()


def _admin_call(fn, *args):
    try:
        return fn(*args)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.get("/api/admin/accounts")
def admin_accounts() -> dict:
    return list_accounts()


@app.post("/api/admin/accounts")
def admin_create_guest(body: GuestAccountRequest) -> dict:
    return _admin_call(create_guest, body.name)


@app.post("/api/admin/register-hotel")
def admin_register_hotel(body: RegisterHotelRequest) -> dict:
    return _admin_call(register_hotel, body.name, body.address)


@app.get("/api/admin/accounts/{account_id}")
def admin_desk(account_id: str) -> dict:
    return _admin_call(desk, account_id)


@app.post("/api/admin/ask")
def admin_ask(body: AskRequest) -> dict:
    return _admin_call(ask, body.guest_id, body.hotel_id, body.text)


@app.post("/api/admin/post-booking-ask")
def admin_post_booking_ask(body: PostBookingAskRequest) -> dict:
    return _admin_call(post_booking_ask, body.guest_id, body.hotel_id, body.text)


@app.post("/api/admin/reply")
def admin_reply(body: ReplyRequest) -> dict:
    return _admin_call(send_reply, body.account_id, body.text)


@app.post("/api/admin/pay")
def admin_pay(body: PayRequest) -> dict:
    return _admin_call(pay, body.guest_id, body.hotel_id, body.check_in, body.check_out)


@app.get("/api/faq/hotels/{hotel_id}")
def faq_config(hotel_id: str) -> dict:
    return faq_get_config(hotel_id)


@app.put("/api/faq/hotels/{hotel_id}")
def faq_put_config(hotel_id: str, body: FaqConfigRequest) -> dict:
    return faq_save_config(hotel_id, body.enabled, body.sections)


@app.post("/api/faq/hotels/{hotel_id}/upload")
async def faq_upload_route(hotel_id: str, file: UploadFile = File(...)) -> dict:
    raw = await file.read()
    try:
        return faq_upload(hotel_id, file.filename or "upload.txt", raw)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@app.delete("/api/faq/hotels/{hotel_id}/documents/{document_id}")
def faq_delete_document_route(hotel_id: str, document_id: int) -> dict:
    try:
        return faq_delete_document(hotel_id, document_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@app.post("/api/faq/hotels/{hotel_id}/ask")
def faq_ask_route(hotel_id: str, body: FaqAskRequest) -> dict:
    return faq_answer(hotel_id, body.question)


@app.post("/api/faq/hotels/{hotel_id}/vector-retrieve")
def faq_vector_retrieve_route(hotel_id: str, body: FaqVectorRequest) -> dict:
    return faq_vector_retrieve(hotel_id, body.question, top_k=body.top_k)


def _page(path: str) -> FileResponse:
    root = FRONTEND_DIST.resolve()
    candidate = (FRONTEND_DIST / path).resolve()
    inside = candidate == root or root in candidate.parents
    if inside and candidate.is_file():
        return FileResponse(candidate)
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index)
    raise HTTPException(
        status_code=404,
        detail="Страница не собрана. В каталоге frontend выполните npm run build.",
    )


MEDIA = BACKEND.parent / "media" / "pictures"


@app.get("/media/pictures/{file_path:path}")
def picture(file_path: str) -> FileResponse:
    root = MEDIA.resolve()
    candidate = (MEDIA / file_path).resolve()
    if candidate != root and root not in candidate.parents:
        raise HTTPException(status_code=404, detail="Нет такого файла")
    if not candidate.is_file():
        raise HTTPException(status_code=404, detail="Нет такого файла")
    return FileResponse(candidate)


@app.get("/")
def index() -> FileResponse:
    return _page("index.html")


@app.get("/{file_path:path}")
def frontend(file_path: str) -> FileResponse:
    if file_path == "health" or file_path.startswith("api"):
        raise HTTPException(status_code=404, detail="Нет такого адреса")
    return _page(file_path)
