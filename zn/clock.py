"""Zegar z możliwością przesunięcia (testy)."""
import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

TZ = ZoneInfo(os.environ.get("ZNAJOMY_TZ", "Europe/Warsaw"))
_offset = 0.0


def now_ts() -> float:
    return time.time() + _offset


def now() -> datetime:
    return datetime.fromtimestamp(now_ts(), TZ)


def at(ts: float) -> datetime:
    return datetime.fromtimestamp(ts, TZ)


def advance(seconds: float) -> None:
    global _offset
    _offset += seconds


def set_offset(seconds: float) -> None:
    global _offset
    _offset = seconds


def day_ts(d, hour: float) -> float:
    """Timestamp godziny `hour` (może być >24) w dniu d (date)."""
    base = datetime(d.year, d.month, d.day, tzinfo=TZ)
    return base.timestamp() + hour * 3600.0


def fmt_last_seen(ts: float) -> str:
    n = now()
    t = at(ts)
    if t.date() == n.date():
        return "dziś " + t.strftime("%H:%M")
    if (n.date() - t.date()).days == 1:
        return "wczoraj " + t.strftime("%H:%M")
    return t.strftime("%d.%m %H:%M")
