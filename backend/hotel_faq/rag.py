"""TF-IDF retrieval + extractive ответ без галлюцинаций вне чанков."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

TOKEN = re.compile(r"[a-z0-9а-яё]+", re.IGNORECASE)
CHUNK_SIZE = 480


@dataclass
class Chunk:
    chunk_id: int
    source: str
    text: str


@dataclass
class Hit:
    chunk: Chunk
    score: float


def tokenize(text: str) -> list[str]:
    return TOKEN.findall(text.lower())


def split_chunks(text: str, source: str, start_id: int) -> tuple[list[Chunk], int]:
    clean = text.strip()
    if not clean:
        return [], start_id
    parts: list[str] = []
    for block in re.split(r"\n\s*\n", clean):
        block = " ".join(block.split())
        if not block:
            continue
        while len(block) > CHUNK_SIZE:
            cut = block.rfind(" ", 0, CHUNK_SIZE)
            if cut < CHUNK_SIZE // 2:
                cut = CHUNK_SIZE
            parts.append(block[:cut].strip())
            block = block[cut:].strip()
        if block:
            parts.append(block)
    chunks: list[Chunk] = []
    cid = start_id
    for piece in parts:
        chunks.append(Chunk(chunk_id=cid, source=source, text=piece))
        cid += 1
    return chunks, cid


class TfidfIndex:
    def __init__(self) -> None:
        self.chunks: list[Chunk] = []
        self._vectors: list[dict[str, float]] = []
        self._idf: dict[str, float] = {}

    def build(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        if not chunks:
            self._vectors = []
            self._idf = {}
            return
        doc_tokens = [tokenize(chunk.text) for chunk in chunks]
        df: dict[str, int] = {}
        for tokens in doc_tokens:
            for term in set(tokens):
                df[term] = df.get(term, 0) + 1
        n = len(chunks)
        self._idf = {term: math.log((1 + n) / (1 + count)) + 1.0 for term, count in df.items()}
        self._vectors = []
        for tokens in doc_tokens:
            tf: dict[str, int] = {}
            for term in tokens:
                tf[term] = tf.get(term, 0) + 1
            length = float(len(tokens)) or 1.0
            vec = {term: (count / length) * self._idf.get(term, 0.0) for term, count in tf.items()}
            self._vectors.append(vec)

    @staticmethod
    def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
        if not a or not b:
            return 0.0
        dot = sum(value * b.get(key, 0.0) for key, value in a.items())
        na = math.sqrt(sum(value * value for value in a.values()))
        nb = math.sqrt(sum(value * value for value in b.values()))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    def search(self, query: str, top_k: int = 3) -> list[Hit]:
        if not self.chunks:
            return []
        tokens = tokenize(query)
        if not tokens:
            return []
        length = float(len(tokens))
        tf: dict[str, int] = {}
        for term in tokens:
            tf[term] = tf.get(term, 0) + 1
        qvec = {term: (count / length) * self._idf.get(term, 0.0) for term, count in tf.items()}
        scored: list[Hit] = []
        for chunk, vec in zip(self.chunks, self._vectors, strict=True):
            scored.append(Hit(chunk=chunk, score=self._cosine(qvec, vec)))
        scored.sort(key=lambda item: item.score, reverse=True)
        return scored[:top_k]


def compose_answer(
    hits: list[Hit],
    min_score: float,
    *,
    guest_facing: bool = False,
) -> tuple[str | None, list[str]]:
    strong = [hit for hit in hits if hit.score >= min_score]
    if not strong:
        return None, []
    lines = [hit.chunk.text for hit in strong[:2]]
    body = " ".join(lines)
    sources = []
    seen: set[str] = set()
    for hit in strong[:2]:
        label = hit.chunk.source
        if label not in seen:
            sources.append(label)
            seen.add(label)
    if guest_facing:
        answer = body
    else:
        answer = f"По базе знаний отеля: {body}"
        if sources:
            answer += f" (источник: {', '.join(sources)})"
    return answer, sources
