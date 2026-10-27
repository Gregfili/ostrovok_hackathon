"""Азимут и часы солнца на стену. Это сектор фасада, не свет в номере."""

from __future__ import annotations

import math
import re
from datetime import date, timedelta

_MONTHS = (
    ("январ", 1),
    ("феврал", 2),
    ("март", 3),
    ("апрел", 4),
    ("мая", 5),
    ("май", 5),
    ("июн", 6),
    ("июл", 7),
    ("август", 8),
    ("сентябр", 9),
    ("октябр", 10),
    ("ноябр", 11),
    ("декабр", 12),
)

_GENITIVE = {
    1: "января",
    2: "февраля",
    3: "марта",
    4: "апреля",
    5: "мая",
    6: "июня",
    7: "июля",
    8: "августа",
    9: "сентября",
    10: "октября",
    11: "ноября",
    12: "декабря",
}


def parse_day(text: str, year: int = 2026) -> date | None:
    stay = parse_stay(text, year)
    return stay[0] if stay else None


def parse_stay(text: str, year: int = 2026) -> tuple[date, date] | None:
    low = text.lower()
    iso = re.findall(r"(20\d{2})-(\d{2})-(\d{2})", low)
    if iso:
        days = []
        for found_year, month, day in iso[:2]:
            try:
                days.append(date(int(found_year), int(month), int(day)))
            except ValueError:
                return None
        if len(days) == 1:
            return days[0], days[0]
        return (days[0], days[1]) if days[0] <= days[1] else (days[1], days[0])
    for stem, month in _MONTHS:
        at = low.find(stem)
        if at < 0:
            continue
        window = low[max(0, at - 24) : at + len(stem) + 12]
        numbers = [int(item) for item in re.findall(r"\d{1,2}", window)]
        days = [item for item in numbers if 1 <= item <= 31]
        if not days:
            continue
        try:
            start = date(year, month, days[0])
            end = date(year, month, days[1]) if len(days) > 1 else start
        except ValueError:
            continue
        return (start, end) if start <= end else (end, start)
    dotted = re.findall(r"\b(\d{1,2})\.(\d{1,2})(?:\.(20\d{2}))?\b", low)
    if dotted:
        days = []
        for day, month, found_year in dotted[:2]:
            try:
                days.append(date(int(found_year or year), int(month), int(day)))
            except ValueError:
                return None
        if len(days) == 1:
            return days[0], days[0]
        return (days[0], days[1]) if days[0] <= days[1] else (days[1], days[0])
    return None


def stay_text(text: str) -> str:
    stay = parse_stay(text)
    if not stay:
        return ""
    start, end = stay
    if start == end:
        return start.isoformat()
    return f"{start.isoformat()}/{end.isoformat()}"


def stay_days(dates: str) -> list[date]:
    stay = parse_stay(dates)
    if not stay:
        return []
    start, end = stay
    days: list[date] = []
    current = start
    while current <= end and len(days) < 16:
        days.append(current)
        current += timedelta(days=1)
    return days


def sunrise_azimuth(day: date, latitude: float = 55.76) -> float | None:
    decl = math.radians(23.44 * math.sin(math.radians(360 / 365 * (day.timetuple().tm_yday - 81))))
    lat = math.radians(latitude)
    cos_h = -math.tan(lat) * math.tan(decl)
    if cos_h > 1 or cos_h < -1:
        return None
    cos_az = math.sin(decl) / math.cos(lat)
    cos_az = max(-1.0, min(1.0, cos_az))
    return math.degrees(math.acos(cos_az))


def sun_hits_facade(facade_azimuth: float, sunrise: float) -> bool:
    diff = abs((sunrise - facade_azimuth + 180) % 360 - 180)
    return diff <= 90


def wall_sun_label(azimuth: float, dates: str, longitude: float = 37.62) -> str | None:
    days = stay_days(dates)
    if not days:
        return None
    first = _day_label(azimuth, days[0], longitude)
    last = _day_label(azimuth, days[-1], longitude)
    if first == last or len(days) == 1:
        return first
    tail = last[0].lower() + last[1:]
    return f"{first}, к {days[-1].day} {_GENITIVE[days[-1].month]} {tail}"


def _day_label(azimuth: float, day: date, longitude: float) -> str:
    spans = _lit_spans(azimuth, day, longitude)
    if not spans:
        return "Солнца на стену нет"
    body = " и ".join(f"{_hour(start)}–{_hour(end)}" for start, end in spans)
    return f"Солнце на стену {body}"


def _lit_spans(azimuth: float, day: date, longitude: float) -> list[tuple[float, float]]:
    decl = math.radians(23.44 * math.sin(math.radians(360 / 365 * (day.timetuple().tm_yday - 81))))
    lat = math.radians(55.76)
    offset = (45.0 - longitude) * 4 / 60
    clocks: list[float] = []
    for step in range(24 * 4):
        solar = step / 4
        hour_angle = math.radians(15 * (solar - 12))
        sin_alt = math.sin(lat) * math.sin(decl) + math.cos(lat) * math.cos(decl) * math.cos(hour_angle)
        if sin_alt <= 0.02:
            continue
        altitude = math.asin(max(-1.0, min(1.0, sin_alt)))
        east = math.sin(hour_angle)
        north = math.cos(hour_angle) * math.sin(lat) - math.tan(decl) * math.cos(lat)
        sun_azimuth = (math.degrees(math.atan2(east, north)) + 180) % 360
        gap = abs((sun_azimuth - azimuth + 180) % 360 - 180)
        if gap <= 90 and altitude > 0:
            clocks.append((solar + offset) % 24)
    if not clocks:
        return []
    spans: list[tuple[float, float]] = []
    start = previous = clocks[0]
    for clock in clocks[1:]:
        if clock - previous > 0.4:
            spans.append((start, previous + 0.25))
            start = clock
        previous = clock
    spans.append((start, previous + 0.25))
    return spans


def _hour(value: float) -> str:
    hour = int(round(value)) % 24
    return f"{hour}:00"
