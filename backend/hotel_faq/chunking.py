"""Разбиение текста: абзацы и предложения, без обрывов посередине слова."""

from __future__ import annotations

import re

from hotel_faq.rag import Chunk

DEFAULT_CHUNK_SIZE = 480
SECTION_CHUNK_SIZE = 1150
OVERLAP_SENTENCES = 1

_SENTENCE = re.compile(r"(?<=[.!?…])\s+")


def _is_section_header(line: str) -> bool:
    line = line.strip()
    if not line or len(line) > 42:
        return False
    if line.endswith((".", "?", "!", ":", ";")):
        return False
    return bool(re.match(r"^[А-ЯЁA-Z0-9«]", line)) and line.count(" ") <= 5


def _paragraphs(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            if current and current[0].lower().startswith("предлож"):
                continue
            if current and current[0].lower().startswith("фотосесс"):
                continue
            if current:
                blocks.append(re.sub(r"\s+", " ", " ".join(current)).strip())
                current = []
            continue
        if _is_section_header(line) and current:
            blocks.append(re.sub(r"\s+", " ", " ".join(current)).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append(re.sub(r"\s+", " ", " ".join(current)).strip())
    if not blocks:
        for block in re.split(r"\n\s*\n", (text or "").strip()):
            merged = re.sub(r"\s+", " ", block).strip()
            if merged:
                blocks.append(merged)
    return blocks


def _sentences(paragraph: str) -> list[str]:
    parts = _SENTENCE.split(paragraph.strip())
    return [part.strip() for part in parts if part.strip()]


def _pack_sentences(sentences: list[str], chunk_size: int, overlap_sentences: int) -> list[str]:
    chunks: list[str] = []
    i = 0
    n = len(sentences)
    while i < n:
        buf: list[str] = []
        total = 0
        j = i
        while j < n:
            sent = sentences[j]
            add = len(sent) + (1 if buf else 0)
            if buf and total + add > chunk_size:
                break
            buf.append(sent)
            total += add
            j += 1
        if not buf:
            buf = [sentences[i]]
            j = i + 1
        chunks.append(" ".join(buf))
        if j >= n:
            break
        i = max(j - overlap_sentences, i + 1)
    return chunks


def split_chunks_overlap(
    text: str,
    source: str,
    start_id: int,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = OVERLAP_SENTENCES,
) -> tuple[list[Chunk], int]:
    overlap_sentences = max(0, min(3, overlap if overlap < 10 else OVERLAP_SENTENCES))
    pieces: list[str] = []
    for para in _paragraphs(text):
        low = para.lower()
        if low.startswith(("предлож", "фотосесс")) and len(para) <= SECTION_CHUNK_SIZE:
            pieces.append(para)
            continue
        if len(para) <= chunk_size:
            pieces.append(para)
            continue
        sents = _sentences(para)
        if len(sents) <= 1:
            pos = 0
            while pos < len(para):
                end = min(pos + chunk_size, len(para))
                if end < len(para):
                    cut = para.rfind(" ", pos + chunk_size // 3, end)
                    if cut > pos:
                        end = cut
                piece = para[pos:end].strip()
                if piece:
                    pieces.append(piece)
                if end >= len(para):
                    break
                pos = end
            continue
        pieces.extend(_pack_sentences(sents, chunk_size, overlap_sentences))

    chunks: list[Chunk] = []
    cid = start_id
    for piece in pieces:
        if piece.strip():
            chunks.append(Chunk(chunk_id=cid, source=source, text=piece))
            cid += 1
    return chunks, cid
