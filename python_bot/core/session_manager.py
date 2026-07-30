"""
Optional trading-session filter.

The 1-minute scalper ships with the filter DISABLED (``session.enabled: false``),
so the bot scans whenever the market is open. Turn it on in ``config.json`` to
restrict trading to one window — e.g. the 30-minute NY-open burst the strategy
spec describes:

    "session": {
      "enabled": true,
      "start": "09:30",
      "end": "10:00",
      "timezone": "America/New_York",
      "trade_days": [0, 1, 2, 3, 4]
    }

Windows that wrap past midnight (e.g. 22:00 -> 02:00) are handled.
"""
from datetime import datetime, time
from typing import List, Optional, Tuple

import pytz

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


class SessionManager:
    def __init__(
        self,
        enabled: bool = False,
        start: str = "09:30",
        end: str = "10:00",
        timezone: str = "America/New_York",
        trade_days: Optional[List[int]] = None,
    ):
        self.enabled = bool(enabled)
        self.tz = pytz.timezone(timezone)
        self.timezone_name = timezone
        self.start_time = self._parse(start)
        self.end_time = self._parse(end)
        # Monday = 0 ... Sunday = 6
        self.trade_days = list(trade_days) if trade_days is not None else [0, 1, 2, 3, 4]

    @staticmethod
    def _parse(value: str) -> time:
        hour, minute = (int(part) for part in value.split(":")[:2])
        return time(hour, minute)

    def now(self, dt: Optional[datetime] = None) -> datetime:
        """``dt`` (or now) converted to the session timezone."""
        if dt is None:
            dt = datetime.now(pytz.utc)
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        return dt.astimezone(self.tz)

    def is_open(self, dt: Optional[datetime] = None) -> Tuple[bool, str]:
        """Returns (open, reason). Always open when the filter is disabled."""
        if not self.enabled:
            return True, "session filter disabled (24/5 scanning)"

        local = self.now(dt)
        if local.weekday() not in self.trade_days:
            allowed = ", ".join(WEEKDAY_NAMES[d] for d in self.trade_days)
            return False, f"{WEEKDAY_NAMES[local.weekday()]} is not a trading day (allowed: {allowed})"

        current = local.time()
        wraps_midnight = self.start_time > self.end_time
        inside = (
            (self.start_time <= current <= self.end_time)
            if not wraps_midnight
            else (current >= self.start_time or current <= self.end_time)
        )

        window = (
            f"{self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')} "
            f"{self.timezone_name}"
        )
        if inside:
            return True, f"inside session {window}"
        return False, f"{current.strftime('%H:%M')} is outside session {window}"

    def is_dst_active(self, dt: Optional[datetime] = None) -> bool:
        return bool(self.now(dt).dst())

    def describe(self) -> str:
        if not self.enabled:
            return "disabled (trading 24/5)"
        return (
            f"{self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')} "
            f"{self.timezone_name} on {', '.join(WEEKDAY_NAMES[d] for d in self.trade_days)}"
        )
