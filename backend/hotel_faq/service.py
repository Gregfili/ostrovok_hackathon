"""FAQ-агент отельера: KB в SQLite, RAG по TF-IDF."""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone

from common.db import connect, init_db
from hotel_faq.chunking import split_chunks_overlap
from hotel_faq.rag import Chunk, TfidfIndex, split_chunks

MIN_SCORE = 0.28
VECTOR_MIN_SCORE = 0.45
SECTION_LABELS = {
    "checkin": "Заезд / выезд",
    "breakfast": "Завтрак",
    "parking": "Парковка",
    "pets": "С питомцами",
    "other": "Прочее",
}

GEO_BLOCK = (
    "тишин",
    "шум",
    "вид",
    "сторон",
    "фасад",
    "этаж",
    "минут",
    "метро",
    "пеш",
    "закат",
    "солнц",
    "окружен",
    "карт",
    "эколог",
)

HUMAN_ESCALATE = (
    "живой человек",
    "живого человека",
    "оператор",
    "менеджер",
    "отельер лично",
    "человек на линии",
)

DEFAULT_SECTIONS = {
    "checkin": "Заезд с 15:00, выезд до 12:00. Ранний заезд и поздний выезд — по запросу.",
    "breakfast": "Завтрак «шведский стол» 07:00–11:00. В тариф не входит.",
    "parking": "Охраняемой парковки у здания нет. Ближайшие платные места — на ресепшене.",
    "pets": "",
    "other": "Wi‑Fi в лобби и номерах. Багаж можно оставить до заезда при наличии места.",
}

_INDEX: dict[str, TfidfIndex] = {}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ping() -> dict:
    return {"status": "ok", "service": "hotel_faq", "engine": "tfidf-rag"}


def _ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hotel_faq_config (
            hotel_id TEXT PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 0,
            sections_json TEXT NOT NULL DEFAULT '{}',
            updated_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hotel_faq_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hotel_id TEXT NOT NULL,
            filename TEXT NOT NULL,
            body TEXT NOT NULL,
            uploaded_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS hotel_faq_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            hotel_id TEXT NOT NULL,
            source TEXT NOT NULL,
            text TEXT NOT NULL
        )
        """
    )


def init_faq_db() -> None:
    init_db()
    with connect() as conn:
        _ensure_schema(conn)
        _seed_pekin(conn)


def _seed_pekin(conn) -> None:
    row = conn.execute(
        "SELECT 1 FROM hotel_faq_config WHERE hotel_id = ?",
        ("pekin",),
    ).fetchone()
    if row:
        return
    conn.execute(
        """
        INSERT INTO hotel_faq_config (hotel_id, enabled, sections_json, updated_at)
        VALUES (?, 1, ?, ?)
        """,
        ("pekin", json.dumps(DEFAULT_SECTIONS, ensure_ascii=False), _now()),
    )
    _rebuild_section_chunks(conn, "pekin", DEFAULT_SECTIONS)


def _load_sections(raw: str | None) -> dict[str, str]:
    if not raw:
        return dict(DEFAULT_SECTIONS)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return dict(DEFAULT_SECTIONS)
    merged = dict(DEFAULT_SECTIONS)
    for key, value in data.items():
        if key in SECTION_LABELS and isinstance(value, str):
            merged[key] = value
    return merged


def _rebuild_section_chunks(conn, hotel_id: str, sections: dict[str, str]) -> None:
    conn.execute(
        "DELETE FROM hotel_faq_chunks WHERE hotel_id = ? AND source LIKE 'section:%'",
        (hotel_id,),
    )
    cid = 1
    for section_id, body in sections.items():
        text = (body or "").strip()
        if not text:
            continue
        source = f"section:{section_id}"
        chunks, cid = split_chunks(text, source, cid)
        for chunk in chunks:
            conn.execute(
                "INSERT INTO hotel_faq_chunks (hotel_id, source, text) VALUES (?, ?, ?)",
                (hotel_id, chunk.source, chunk.text),
            )


def _chunk_upload(conn, hotel_id: str, doc_id: int, filename: str, body: str) -> None:
    prefix = f"upload:{doc_id}:"
    conn.execute(
        "DELETE FROM hotel_faq_chunks WHERE hotel_id = ? AND source LIKE ?",
        (hotel_id, f"{prefix}%"),
    )
    source = f"upload:{doc_id}:{filename}"
    chunks, _ = split_chunks_overlap(body, source, 1)
    for chunk in chunks:
        conn.execute(
            "INSERT INTO hotel_faq_chunks (hotel_id, source, text) VALUES (?, ?, ?)",
            (hotel_id, chunk.source, chunk.text),
        )


def _chunks_for_hotel(hotel_id: str) -> list[Chunk]:
    init_faq_db()
    with connect() as conn:
        rows = conn.execute(
            "SELECT id, source, text FROM hotel_faq_chunks WHERE hotel_id = ? ORDER BY id",
            (hotel_id,),
        ).fetchall()
    return [Chunk(chunk_id=row["id"], source=row["source"], text=row["text"]) for row in rows]


def _reindex(hotel_id: str) -> None:
    chunks = _chunks_for_hotel(hotel_id)
    index = TfidfIndex()
    index.build(chunks)
    _INDEX[hotel_id] = index
    try:
        from hotel_faq.vector_store import rebuild_vector_index

        upload_chunks = [chunk for chunk in chunks if chunk.source.startswith("upload:")]
        rebuild_vector_index(hotel_id, upload_chunks or chunks)
    except ImportError:
        pass


def vector_retrieve(hotel_id: str, question: str, *, top_k: int = 4) -> dict:
    from hotel_faq.vector_store import vector_search

    if hotel_id not in _INDEX:
        _reindex(hotel_id)
    try:
        return vector_search(hotel_id, question, top_k=top_k)
    except FileNotFoundError:
        chunks = _chunks_for_hotel(hotel_id)
        from hotel_faq.vector_store import rebuild_vector_index, vector_search

        rebuild_vector_index(hotel_id, chunks)
        return vector_search(hotel_id, question, top_k=top_k)


def _config_row(conn, hotel_id: str):
    row = conn.execute(
        "SELECT hotel_id, enabled, sections_json, updated_at FROM hotel_faq_config WHERE hotel_id = ?",
        (hotel_id,),
    ).fetchone()
    if row:
        return row
    conn.execute(
        """
        INSERT INTO hotel_faq_config (hotel_id, enabled, sections_json, updated_at)
        VALUES (?, 0, ?, ?)
        """,
        (hotel_id, json.dumps(DEFAULT_SECTIONS, ensure_ascii=False), _now()),
    )
    _rebuild_section_chunks(conn, hotel_id, DEFAULT_SECTIONS)
    return conn.execute(
        "SELECT hotel_id, enabled, sections_json, updated_at FROM hotel_faq_config WHERE hotel_id = ?",
        (hotel_id,),
    ).fetchone()


def get_config(hotel_id: str) -> dict:
    init_faq_db()
    with connect() as conn:
        row = _config_row(conn, hotel_id)
        docs = conn.execute(
            """
            SELECT id, filename, LENGTH(body) AS chars, uploaded_at
            FROM hotel_faq_documents WHERE hotel_id = ? ORDER BY id DESC
            """,
            (hotel_id,),
        ).fetchall()
        chunk_count = conn.execute(
            "SELECT COUNT(*) AS n FROM hotel_faq_chunks WHERE hotel_id = ?",
            (hotel_id,),
        ).fetchone()["n"]
    sections = _load_sections(row["sections_json"])
    return {
        "hotel_id": hotel_id,
        "enabled": bool(row["enabled"]),
        "sections": sections,
        "section_labels": SECTION_LABELS,
        "documents": [
            {
                "id": doc["id"],
                "filename": doc["filename"],
                "chars": doc["chars"],
                "uploaded_at": doc["uploaded_at"],
            }
            for doc in docs
        ],
        "chunk_count": chunk_count,
        "updated_at": row["updated_at"],
        "min_score": MIN_SCORE,
    }


def save_config(hotel_id: str, enabled: bool | None, sections: dict[str, str] | None) -> dict:
    init_faq_db()
    with connect() as conn:
        row = _config_row(conn, hotel_id)
        current = _load_sections(row["sections_json"])
        if sections is not None:
            for key, value in sections.items():
                if key in SECTION_LABELS and isinstance(value, str):
                    current[key] = value
        flag = bool(row["enabled"]) if enabled is None else bool(enabled)
        updated = _now()
        conn.execute(
            """
            UPDATE hotel_faq_config
            SET enabled = ?, sections_json = ?, updated_at = ?
            WHERE hotel_id = ?
            """,
            (1 if flag else 0, json.dumps(current, ensure_ascii=False), updated, hotel_id),
        )
        _rebuild_section_chunks(conn, hotel_id, current)
    _reindex(hotel_id)
    return get_config(hotel_id)


def upload_document(hotel_id: str, filename: str, raw: bytes) -> dict:
    clean_name = re.sub(r"[^\w.\- ()а-яА-ЯёЁ]", "_", filename.strip()) or "upload.txt"
    if not raw:
        raise ValueError("Пустой файл")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ValueError("Пока принимаем только UTF-8 (.txt, .md, .json)") from error
    if not text.strip():
        raise ValueError("В файле нет текста")
    init_faq_db()
    with connect() as conn:
        _config_row(conn, hotel_id)
        cursor = conn.execute(
            """
            INSERT INTO hotel_faq_documents (hotel_id, filename, body, uploaded_at)
            VALUES (?, ?, ?, ?)
            """,
            (hotel_id, clean_name, text, _now()),
        )
        doc_id = int(cursor.lastrowid)
        _chunk_upload(conn, hotel_id, doc_id, clean_name, text)
        conn.execute(
            "UPDATE hotel_faq_config SET updated_at = ? WHERE hotel_id = ?",
            (_now(), hotel_id),
        )
    _reindex(hotel_id)
    return get_config(hotel_id)


def delete_document(hotel_id: str, document_id: int) -> dict:
    init_faq_db()
    with connect() as conn:
        row = conn.execute(
            """
            SELECT id FROM hotel_faq_documents
            WHERE hotel_id = ? AND id = ?
            """,
            (hotel_id, document_id),
        ).fetchone()
        if not row:
            raise ValueError("Документ не найден")
        prefix = f"upload:{document_id}:"
        conn.execute(
            "DELETE FROM hotel_faq_chunks WHERE hotel_id = ? AND source LIKE ?",
            (hotel_id, f"{prefix}%"),
        )
        conn.execute(
            "DELETE FROM hotel_faq_documents WHERE hotel_id = ? AND id = ?",
            (hotel_id, document_id),
        )
        conn.execute(
            "UPDATE hotel_faq_config SET updated_at = ? WHERE hotel_id = ?",
            (_now(), hotel_id),
        )
    _reindex(hotel_id)
    return get_config(hotel_id)


def _maybe_llm_polish(question: str, draft: str) -> str:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        return draft
    try:
        import urllib.request

        payload = json.dumps(
            {
                "model": os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "Сожми ответ отельера для гостя. Используй только факты из черновика. "
                            "Не добавляй про вид, тишину, этаж и расположение номера."
                        ),
                    },
                    {"role": "user", "content": f"Вопрос: {question}\nЧерновик: {draft}"},
                ],
                "temperature": 0.2,
            },
            ensure_ascii=False,
        ).encode("utf-8")
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=payload,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"].strip() or draft
    except Exception:
        return draft


def _answer_from_vector(hotel_id: str, text: str) -> dict | None:
    from common.post_booking_routing import rag_hit_relevant
    from hotel_faq.retrieval import compose_guest_answer, is_offers_query, keyword_overlap

    try:
        from hotel_faq.vector_store import vector_search

        payload = vector_search(hotel_id, text, top_k=8 if is_offers_query(text) else 5)
    except (ImportError, FileNotFoundError, OSError):
        return None
    hits = payload.get("hits") or []
    if not hits:
        return None
    if is_offers_query(text):
        from hotel_faq.retrieval import _is_offers_chunk, rerank_hits

        extra = [
            {"text": c.text, "score": 0.55, "source": c.source}
            for c in _chunks_for_hotel(hotel_id)
            if _is_offers_chunk(c.text)
        ]
        seen = {str(h.get("text", ""))[:80] for h in hits}
        for row in extra:
            if row["text"][:80] not in seen:
                hits.append(row)
                seen.add(row["text"][:80])
        hits = rerank_hits(text, hits)[:10]
    upload = [hit for hit in hits if str(hit.get("source", "")).startswith("upload:")]
    best = upload[0] if upload else hits[0]
    score = float(best.get("rerank_score", best.get("score", 0)))
    chunk = str(best.get("text", ""))
    if not chunk:
        return None
    kw = keyword_overlap(text, chunk)
    if score < 0.38 and kw < 0.25:
        return None
    if not rag_hit_relevant(text, chunk, max(float(best.get("score", 0)), 0.35)):
        if kw < 0.34:
            return None
    draft = compose_guest_answer(text, hits)
    sources = list(dict.fromkeys(str(h.get("source", "")) for h in hits[:3] if h.get("source")))
    return {
        "draft": draft,
        "sources": sources or [str(best.get("source", ""))],
        "scores": [round(score, 3)],
        "method": "rag_vector",
    }


def answer_question(hotel_id: str, question: str) -> dict:
    from hotel_faq.rag import compose_answer

    text = question.strip()
    low = text.lower()
    if not text:
        return {"mode": "escalate", "reason": "empty", "message": "Пустой вопрос."}
    if any(word in low for word in HUMAN_ESCALATE):
        return {
            "mode": "human",
            "reason": "guest_requested_human",
            "message": "Передаю живому отельеру.",
        }
    from common.post_booking_routing import FACT_AGENT_CARDS, is_fact_agent_question, is_quiet_side_question

    if is_fact_agent_question(text) and not is_quiet_side_question(text):
        return {
            "mode": "geo_redirect",
            "reason": "fact_agent_topic",
            "message": f"Это тема карт Fact Agent: {FACT_AGENT_CARDS}.",
        }

    init_faq_db()
    with connect() as conn:
        row = _config_row(conn, hotel_id)
    if not row["enabled"]:
        return {
            "mode": "escalate",
            "reason": "disabled",
            "message": "FAQ-агент выключен. Вопрос увидит отельер.",
        }

    if hotel_id not in _INDEX:
        _reindex(hotel_id)
    index = _INDEX.get(hotel_id) or TfidfIndex()
    from common.post_booking_routing import rag_hit_relevant

    hits = index.search(text, top_k=3)
    draft, sources = compose_answer(hits, MIN_SCORE, guest_facing=True)
    if not draft and hits and rag_hit_relevant(text, hits[0].chunk.text, hits[0].score):
        draft = hits[0].chunk.text
        sources = [hits[0].chunk.source]
    tfidf_ok = bool(draft) and hits and rag_hit_relevant(text, hits[0].chunk.text, hits[0].score)
    section_tfidf = tfidf_ok and str(hits[0].chunk.source).startswith("section:")

    if section_tfidf:
        answer = _maybe_llm_polish(text, draft)
        return {
            "mode": "answer",
            "message": answer,
            "sources": sources,
            "scores": [round(hit.score, 3) for hit in hits[:2]],
            "method": "rag_tfidf",
        }

    vector = _answer_from_vector(hotel_id, text)
    if vector:
        answer = _maybe_llm_polish(text, vector["draft"])
        return {
            "mode": "answer",
            "message": answer,
            "sources": vector["sources"],
            "scores": vector["scores"],
            "method": vector["method"],
        }

    if tfidf_ok:
        answer = _maybe_llm_polish(text, draft)
        return {
            "mode": "answer",
            "message": answer,
            "sources": sources,
            "scores": [round(hit.score, 3) for hit in hits[:2]],
            "method": "rag_tfidf",
        }

    return {
        "mode": "escalate",
        "reason": "no_match" if not draft else "weak_match",
        "message": "В базе знаний нет ответа. Передаю отельеру.",
        "scores": [round(hit.score, 3) for hit in hits],
    }
