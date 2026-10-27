"""Переранжирование и выбор фрагмента ответа по запросу."""

from __future__ import annotations

import re

from hotel_faq.rag import tokenize

_STOP = frozenset(
    "и в на с по для от до из к у о что как какие какой какая какое где когда кто это не ли же бы".split()
)


def _query_terms(query: str) -> set[str]:
    terms: set[str] = set()
    for token in tokenize(query):
        if len(token) < 3 or token in _STOP:
            continue
        terms.add(token)
        if len(token) > 5:
            terms.add(token[:5])
        if len(token) > 7:
            terms.add(token[:7])
    return terms


def keyword_overlap(query: str, text: str) -> float:
    terms = _query_terms(query)
    if not terms:
        return 0.0
    chunk = set(tokenize(text))
    chunk_stems = {t[:5] for t in chunk if len(t) >= 5}
    hits = 0
    for term in terms:
        if term in chunk or term in chunk_stems:
            hits += 1
        elif any(c.startswith(term[:4]) or term.startswith(c[:4]) for c in chunk if len(term) >= 4):
            hits += 0.5
    return hits / len(terms)


def is_offers_query(query: str) -> bool:
    low = query.lower()
    if "предлож" in low:
        return True
    if "эксклюзив" in low and any(x in low for x in ("отел", "гостин", "пекин", "услов")):
        return True
    return "свад" in low or ("семей" in low and "пар" in low)


def rerank_hits(query: str, hits: list[dict]) -> list[dict]:
    ranked: list[dict] = []
    offers_q = is_offers_query(query)
    for hit in hits:
        text = str(hit.get("text", ""))
        vec = float(hit.get("score", 0))
        kw = keyword_overlap(query, text)
        low_q = query.lower()
        low_t = text.lower()
        extra = 0.0
        if "предлож" in low_q and ("предлож" in low_t or "тариф" in low_t or "фотосесс" in low_t):
            extra += 0.12
        if "эксклюзив" in low_q and "эксклюзив" in low_t:
            extra += 0.1
        if offers_q:
            if low_t.startswith("предлож") or "эксклюзивный тариф" in low_t:
                extra += 0.2
            if "фотосесс" in low_t:
                extra += 0.18
            if "каждой пар" in low_t or ("индивидуальный подход" in low_t and "пар" in low_t):
                extra += 0.15
        combined = vec + 0.22 * kw + extra
        ranked.append({**hit, "keyword_overlap": round(kw, 3), "rerank_score": round(combined, 4)})
    ranked.sort(key=lambda item: -item["rerank_score"])
    for i, hit in enumerate(ranked, start=1):
        hit["rank"] = i
    return ranked


_SENTENCE = re.compile(r"(?<=[.!?…])\s+")


def snippet_for_query(query: str, text: str, *, max_len: int = 520) -> str:
    text = text.strip()
    if not text:
        return ""
    terms = _query_terms(query)
    sentences = _SENTENCE.split(text)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return text[:max_len]

    def score_sent(sent: str) -> float:
        st = set(tokenize(sent))
        base = len(terms & st)
        low = sent.lower()
        if "предлож" in query.lower() and ("предлож" in low or "тариф" in low or "фотосесс" in low):
            base += 2
        if "эксклюзив" in query.lower() and "эксклюзив" in low:
            base += 1.5
        return base

    scored = [(score_sent(s), i, s) for i, s in enumerate(sentences)]
    best_score = max(s for s, _, _ in scored)
    if best_score <= 0:
        # начинаем с первого предложения, которое не обрывается на полуслове
        start = 0
        if re.match(r"^[a-zа-яё]{1,3},", sentences[0], re.I):
            start = 1 if len(sentences) > 1 else 0
    else:
        start = max(scored, key=lambda row: row[0])[1]

    out: list[str] = []
    length = 0
    for i in range(start, len(sentences)):
        sent = sentences[i]
        add = len(sent) + (1 if out else 0)
        if out and length + add > max_len:
            break
        out.append(sent)
        length += add
    return " ".join(out).strip() if out else text[:max_len]


_OFFER_CLUES = (
    "тариф",
    "пара",
    "пар ",
    "фотосесс",
    "интерьер",
    "завтрак",
    "шведск",
    "выезд",
    "визаж",
    "парикмах",
    "парков",
    "8500",
    "делюкс",
    "люкс",
    "800 250",
    "980 59",
    "sales@",
    "локац",
    "проживан",
    "бронир",
    "эксклюзив",
)


def _normalize_marketing(line: str) -> str:
    low = line.lower()
    if "идеальной сказки" in low or ("сказк" in low and "тариф" in low):
        return (
            "Эксклюзивный тариф для свадебных и семейных пар: проживание в номерах Делюкс и выше, "
            "интерьеры отеля — фон для торжества и фотосъёмки."
        )
    if line.lower().startswith("уникальные интерьеры"):
        return (
            "Интерьеры номера и гостиницы можно использовать как фон для фото; "
            "в тариф входит завтрак — можно не спешить с утра."
        )
    return line


def _is_offers_chunk(text: str) -> bool:
    low = text.lower()
    if "11 этаже" in low and "эксклюзивные номера" in low and "тариф" not in low:
        return False
    if any(x in low for x in ("гулаг", "музей гостиницы «пекин»", "львы-стражник")):
        return False
    markers = (
        "предложения отель",
        "условия тарифа",
        "эксклюзивный тариф",
        "поздний выезд",
        "фотосесс",
        "8500",
        "каждой пар",
        "золотой сад",
        "sales@hotelpeking",
        "800 250",
    )
    return any(m in low for m in markers)


def _compose_offers_compact(hits: list[dict]) -> str:
    pool = [h for h in hits if _is_offers_chunk(str(h.get("text", "")))] or hits[:4]
    blob = re.sub(r"\s+", " ", " ".join(str(h.get("text", "")) for h in pool)).lower()
    if not blob.strip():
        return ""

    lines: list[str] = []

    if "эксклюзив" in blob or "тариф" in blob:
        lines.append(
            "• Пары (свадьба, семейное торжество): тариф на номера Делюкс и выше, "
            "интерьеры отеля — фон для фото и праздника."
        )

    stay_perks: list[str] = []
    if "поздний выезд" in blob and "18-00" in blob:
        stay_perks.append("поздний выезд до 18:00")
    if "шведск" in blob and "13 этаже" in blob:
        stay_perks.append("завтрак «шведский стол» на 13 этаже")
    elif "завтрак" in blob and "тариф" in blob:
        stay_perks.append("завтрак в тарифе")
    if "бесплатно" in blob and "фотосесс" in blob:
        stay_perks.append("фотосессия со своим фотографом бесплатно (холлы, 3–7 этажи)")
    if "визаж" in blob or "парикмах" in blob:
        stay_perks.append("можно пригласить визажиста и парикмахера")
    if "парковоч" in blob and ("комплемент" in blob or "бесплат" in blob):
        stay_perks.append("парковка complimentary при наличии мест")
    if stay_perks:
        lines.append("• При проживании по тарифу: " + "; ".join(stay_perks[:4]) + ".")

    if "8500" in blob:
        book = "8 495 980 59 95 / sales@hotelpeking.ru"
        if "sales@hotelpeking" not in blob and "980 59" in blob:
            book = "8 495 980 59 95"
        lines.append(f"• Фотосессия без проживания: 8500 ₽/час, бронь заранее ({book}).")

    if "800 250" in blob or "каждой пар" in blob:
        lines.append("• Вопросы по тарифу для пар: 8 800 250 05 50.")

    if not lines:
        return ""
    header = "Эксклюзивные предложения «Пекин»:"
    return header + "\n" + "\n".join(lines[:4])


def compose_guest_answer(query: str, hits: list[dict], *, max_len: int = 520) -> str:
    if not hits:
        return ""
    if is_offers_query(query):
        compact = _compose_offers_compact(hits)
        if compact:
            return compact if len(compact) <= max_len else compact[: max_len - 1].rsplit("\n", 1)[0] + "…"
    return snippet_for_query(query, str(hits[0].get("text", "")), max_len=min(max_len, 420))
