"""Свободная реплика гостю.

Без ключа остаётся фраза из снимка. С GIGACHAT_AUTHORIZATION_KEY модель
GigaChat-2 пересказывает только переданные факты. Число, которого в фактах нет,
гостю не показывается. Ключ лежит в .env и в git не входит.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
import urllib.error
import urllib.request
from pathlib import Path

_OAUTH = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
_CHAT = "https://api.giga.chat/v1/chat/completions"
_MODEL = "GigaChat-2"
_KEY_NAME = "GIGACHAT_AUTHORIZATION_KEY"
_ROOT = Path(__file__).resolve().parents[2]
_SYSTEM = (
    "Ты говоришь с гостем по-русски, две-четыре фразы. "
    "Используй только факты из сообщения. Не добавляй числа, адреса и названия, которых в фактах нет. "
    "Если ответа в фактах нет, напиши ровно: этого в снимке нет. "
    "Не используй слова: якорь, OSM, уверенность, досье."
)
_lock = threading.Lock()
_token = ""
_token_until = 0.0


def guest_reply(transcript: str, facts: str, fallback: str) -> str:
    key = _api_key()
    if not key:
        return fallback
    token = _access_token(key)
    if not token:
        return fallback
    payload = {
        "model": _MODEL,
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": f"Факты:\n{facts}\n\nПоследняя реплика гостя:\n{transcript}"},
        ],
        "temperature": 0.2,
    }
    request = urllib.request.Request(
        _CHAT,
        data=json.dumps(payload).encode(),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=40) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError):
        return fallback
    text = _content(raw).strip()
    if not text or len(text) > 700 or not _numbers_allowed(text, facts) or not _plain_gap(text):
        return fallback
    return text


def _api_key() -> str:
    key = os.environ.get(_KEY_NAME, "").strip()
    if key:
        return key
    path = _ROOT / ".env"
    if not path.is_file():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        name, sep, value = line.partition("=")
        if sep and name.strip() == _KEY_NAME:
            return value.strip().strip('"').strip("'")
    return ""


def _access_token(key: str) -> str:
    global _token, _token_until
    now = time.time()
    with _lock:
        if _token and now < _token_until:
            return _token
        request = urllib.request.Request(
            _OAUTH,
            data=b"scope=GIGACHAT_API_PERS",
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "RqUID": str(uuid.uuid4()),
                "Authorization": f"Basic {key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                body = json.loads(response.read().decode("utf-8", errors="replace"))
        except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError):
            return ""
        token = str(body.get("access_token") or "")
        if not token:
            return ""
        expires = float(body.get("expires_at") or 0)
        if expires > 10_000_000_000:
            expires = expires / 1000
        _token = token
        _token_until = (expires - 60) if expires else now + 25 * 60
        return token


def _content(raw: str) -> str:
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    choices = body.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "")


def _numbers_allowed(reply: str, facts: str) -> bool:
    allowed = set(re.findall(r"\d+(?:[.,]\d+)?", facts))
    return set(re.findall(r"\d+(?:[.,]\d+)?", reply)).issubset(allowed)


def _plain_gap(reply: str) -> bool:
    low = reply.lower().strip().rstrip(".")
    if "снимке нет" not in low:
        return True
    return low == "этого в снимке нет"
