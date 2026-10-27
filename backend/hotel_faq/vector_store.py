"""Локальный vector RAG: sentence-transformers + FAISS на диске."""

from __future__ import annotations

import json
import re
from pathlib import Path

from hotel_faq.rag import Chunk
from hotel_faq.retrieval import compose_guest_answer, rerank_hits

BACKEND = Path(__file__).resolve().parents[1]
VECTOR_DIR = BACKEND / "data" / "faq_vectors"
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

_MODEL = None
_INDEX_CACHE: dict[str, tuple[object, list[dict]]] = {}


def _model():
    global _MODEL
    if _MODEL is None:
        from sentence_transformers import SentenceTransformer

        _MODEL = SentenceTransformer(MODEL_NAME)
    return _MODEL


def _paths(hotel_id: str) -> tuple[Path, Path]:
    VECTOR_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^\w\-]", "_", hotel_id)
    base = VECTOR_DIR / safe
    return base.with_suffix(".faiss"), base.with_suffix(".meta.json")


def embed_texts(texts: list[str]):
    import numpy as np

    if not texts:
        return np.zeros((0, 384), dtype="float32")
    vectors = _model().encode(texts, normalize_embeddings=True, show_progress_bar=False)
    return np.asarray(vectors, dtype="float32")


def rebuild_vector_index(hotel_id: str, chunks: list[Chunk]) -> dict:
    import faiss

    index_path, meta_path = _paths(hotel_id)
    meta = [
        {"chunk_id": chunk.chunk_id, "source": chunk.source, "text": chunk.text}
        for chunk in chunks
    ]
    if not meta:
        if index_path.exists():
            index_path.unlink()
        if meta_path.exists():
            meta_path.unlink()
        _INDEX_CACHE.pop(hotel_id, None)
        return {"hotel_id": hotel_id, "chunks": 0, "index_path": str(index_path)}

    vectors = embed_texts([row["text"] for row in meta])
    dim = int(vectors.shape[1])
    index = faiss.IndexFlatIP(dim)
    index.add(vectors)
    faiss.write_index(index, str(index_path))
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    _INDEX_CACHE.pop(hotel_id, None)
    return {
        "hotel_id": hotel_id,
        "chunks": len(meta),
        "dimensions": dim,
        "model": MODEL_NAME,
        "index_path": str(index_path),
        "meta_path": str(meta_path),
    }


def _load_index(hotel_id: str):
    if hotel_id in _INDEX_CACHE:
        return _INDEX_CACHE[hotel_id]
    import faiss

    index_path, meta_path = _paths(hotel_id)
    if not index_path.exists() or not meta_path.exists():
        raise FileNotFoundError(
            f"Vector index for {hotel_id} not found. Run demo_rag_pekin.py --rebuild first."
        )
    index = faiss.read_index(str(index_path))
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    _INDEX_CACHE[hotel_id] = (index, meta)
    return index, meta


def vector_search(hotel_id: str, question: str, *, top_k: int = 4) -> dict:
    query = (question or "").strip()
    if not query:
        return {"query": query, "hits": [], "context": "", "answer": ""}

    index, meta = _load_index(hotel_id)
    qvec = embed_texts([query])
    fetch_k = min(max(top_k * 3, 12), len(meta))
    scores, ids = index.search(qvec, fetch_k)
    hits = []
    for score, idx in zip(scores[0].tolist(), ids[0].tolist(), strict=True):
        if idx < 0:
            continue
        row = meta[idx]
        hits.append(
            {
                "rank": len(hits) + 1,
                "score": round(float(score), 4),
                "source": row["source"],
                "text": row["text"],
            }
        )

    ranked = rerank_hits(query, hits)
    ranked = ranked[:top_k]
    from hotel_faq.retrieval import snippet_for_query

    context_parts = [snippet_for_query(query, hit["text"]) for hit in ranked[:3]]
    context = "\n\n---\n\n".join(context_parts)
    answer = _grounded_answer(query, ranked)
    return {
        "hotel_id": hotel_id,
        "query": query,
        "model": MODEL_NAME,
        "hits": ranked,
        "context": context,
        "answer": answer,
    }


def _grounded_answer(query: str, hits: list[dict]) -> str:
    if not hits:
        return ""
    best = hits[0]
    if float(best.get("rerank_score", best.get("score", 0))) < 0.38:
        return "В базе знаний нет уверенного совпадения по этому вопросу."
    return compose_guest_answer(query, hits)
