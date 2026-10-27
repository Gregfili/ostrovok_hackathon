"""Свободная реплика гостю. Факты приходят снаружи, модель их не выдумывает."""

from __future__ import annotations

import json
import urllib.request

_URL = "https://text.pollinations.ai/openai"
_SYSTEM = (
    "Ты говоришь с гостем по-русски, коротко, как живой человек, две-четыре фразы. "
    "Отвечай на последнюю реплику, не повторяй предыдущее предложение отелей. "
    "Опирайся только на факты в сообщении. Чего нет в фактах — так и скажи: этого в снимке нет. "
    "Не используй слова: якорь, OSM, уверенность, досье."
)


def guest_reply(transcript: str, facts: str, fallback: str) -> str:
    payload = {
        "model": "openai",
        "messages": [
            {"role": "system", "content": _SYSTEM},
            {
                "role": "user",
                "content": f"Факты:\n{facts}\n\nРеплики гостя:\n{transcript}",
            },
        ],
    }
    request = urllib.request.Request(
        _URL,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=25) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except Exception:
        return fallback
    text = _content(raw).strip()
    if not text or len(text) > 700:
        return fallback
    return text


def _content(raw: str) -> str:
    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    choices = body.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "")
