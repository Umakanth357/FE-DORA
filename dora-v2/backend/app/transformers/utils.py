"""
Shared transformer utilities.
to_utc_mysql() handles every real-world timestamp format seen in the wild.
"""
import re
from datetime import datetime, timezone
from typing import Optional


def to_utc_mysql(raw: Optional[str | int]) -> Optional[str]:
    """
    Convert any timestamp to MySQL DATETIME(3) UTC string.
    Handles: ISO 8601, space-separated, Unix epoch (sec or ms), Z suffix.
    Returns None if input is None.
    """
    if raw is None:
        return None
    try:
        if isinstance(raw, int):
            ts = raw / 1000 if raw > 9_999_999_999 else raw
            return _fmt(datetime.fromtimestamp(ts, tz=timezone.utc))

        s = str(raw).strip()

        # Unix epoch string
        if re.match(r"^\d{10,13}$", s):
            ts = int(s)
            ts = ts / 1000 if ts > 9_999_999_999 else ts
            return _fmt(datetime.fromtimestamp(ts, tz=timezone.utc))

        s = s.replace(" ", "T")
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        if not re.search(r"[+-]\d{2}:\d{2}$", s):
            s += "+00:00"
        return _fmt(datetime.fromisoformat(s).astimezone(timezone.utc))

    except Exception as e:
        raise ValueError(f"Cannot parse timestamp {raw!r}: {e}") from e


def _fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{dt.microsecond // 1000:03d}"


def calc_duration(started: Optional[str], finished: Optional[str]) -> Optional[int]:
    """Return duration in seconds between two timestamps, or None."""
    if not started or not finished:
        return None
    try:
        s = datetime.fromisoformat(to_utc_mysql(started).replace(" ", "T").replace(".000",""))
        f = datetime.fromisoformat(to_utc_mysql(finished).replace(" ", "T").replace(".000",""))
        return max(0, int((f - s).total_seconds()))
    except Exception:
        return None


def calc_mttr_minutes(created: Optional[str], resolved: Optional[str]) -> Optional[int]:
    """Return MTTR in minutes between incident created and resolved."""
    if not created or not resolved:
        return None
    try:
        c = to_utc_mysql(created)
        r = to_utc_mysql(resolved)
        if not c or not r:
            return None
        c_dt = datetime.fromisoformat(c.replace(" ", "T")[:19])
        r_dt = datetime.fromisoformat(r.replace(" ", "T")[:19])
        mins = int((r_dt - c_dt).total_seconds() / 60)
        return max(0, mins)
    except Exception:
        return None


def trunc(s: Optional[str], n: int = 255) -> str:
    if not s:
        return ""
    return str(s)[:n]
