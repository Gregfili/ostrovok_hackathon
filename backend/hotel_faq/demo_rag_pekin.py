"""Демо vector RAG для отеля «Пекин»: ingest → FAISS → вопрос.

Запуск из каталога backend:

  pip install -r requirements.txt
  python -m hotel_faq.demo_rag_pekin --ingest --rebuild --ask "Где музей и когда он работает?"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

HOTEL_ID = "pekin"
KB_FILENAME = "База знаний гостинницы Пекин.txt"
KB_PATH = ROOT / "doc" / KB_FILENAME


def rechunk_upload_documents(hotel_id: str) -> int:
    from common.db import connect
    from hotel_faq.service import _chunk_upload, _reindex, init_faq_db

    init_faq_db()
    with connect() as conn:
        docs = conn.execute(
            """
            SELECT id, filename, body FROM hotel_faq_documents
            WHERE hotel_id = ? ORDER BY id
            """,
            (hotel_id,),
        ).fetchall()
        for doc in docs:
            _chunk_upload(conn, hotel_id, int(doc["id"]), doc["filename"], doc["body"])
        conn.commit()
    _reindex(hotel_id)
    return len(docs)


def ingest_kb(hotel_id: str, path: Path) -> None:
    from hotel_faq.service import get_config, init_faq_db, upload_document

    if not path.is_file():
        raise SystemExit(f"Файл базы знаний не найден: {path}")
    init_faq_db()
    cfg = get_config(hotel_id)
    names = {doc["filename"] for doc in cfg.get("documents") or []}
    raw = path.read_bytes()
    if path.name in names:
        print(f"Документ «{path.name}» уже в FAQ — пересобираю чанки с overlap.")
        rechunk_upload_documents(hotel_id)
        return
    upload_document(hotel_id, path.name, raw)
    print(f"Загружен «{path.name}» → upload:* чанки в SQLite + FAISS.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Vector RAG demo (Пекин)")
    parser.add_argument("--ingest", action="store_true", help="Загрузить doc/База знаний… в FAQ pekin")
    parser.add_argument("--rebuild", action="store_true", help="Пересобрать TF-IDF и FAISS из SQLite")
    parser.add_argument("--ask", type=str, help="Вопрос для retrieval")
    parser.add_argument("--top-k", type=int, default=4)
    args = parser.parse_args()

    if not any([args.ingest, args.rebuild, args.ask]):
        parser.error("Укажите --ingest, --rebuild и/или --ask")

    if args.ingest:
        ingest_kb(HOTEL_ID, KB_PATH)

    if args.rebuild:
        from hotel_faq.service import _chunks_for_hotel, _reindex, init_faq_db
        from hotel_faq.vector_store import _paths

        init_faq_db()
        docs = rechunk_upload_documents(HOTEL_ID)
        _reindex(HOTEL_ID)
        index_path, meta_path = _paths(HOTEL_ID)
        print(
            f"Пересобрано: документов {docs}, чанков {len(_chunks_for_hotel(HOTEL_ID))}, "
            f"FAISS → {index_path}"
        )

    if args.ask:
        from hotel_faq.service import vector_retrieve

        result = vector_retrieve(HOTEL_ID, args.ask, top_k=args.top_k)
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
