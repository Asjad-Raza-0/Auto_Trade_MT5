from datetime import datetime, time
import pytz

class SessionManager:
    """
    Manages trading session rules for TG Capital London Session.
    Session: 03:00 to 06:30 America/New_York time.
    Handles DST transitions automatically via pytz.
    """
    def __init__(self, start_str: str = "03:00", end_str: str = "06:30", tz_name: str = "America/New_York"):
        self.tz = pytz.timezone(tz_name)
        start_parts = [int(x) for x in start_str.split(":")]
        end_parts = [int(x) for x in end_str.split(":")]
        self.start_time = time(start_parts[0], start_parts[1])
        self.end_time = time(end_parts[0], end_parts[1])

    def get_ny_now(self, dt: datetime = None) -> datetime:
        """Converts UTC or naïve datetime to America/New_York time."""
        if dt is None:
            dt = datetime.now(pytz.utc)
        if dt.tzinfo is None:
            # Assume UTC if naive
            dt = pytz.utc.localize(dt)
        return dt.astimezone(self.tz)

    def is_in_session(self, dt: datetime = None) -> bool:
        """
        Returns True if the given datetime (or current time) falls within
        03:00 to 06:30 America/New_York.
        """
        ny_dt = self.get_ny_now(dt)
        current_time = ny_dt.time()
        return self.start_time <= current_time <= self.end_time

    def is_session_expired(self, dt: datetime = None) -> bool:
        """
        Returns True if current time is past 06:30 America/New_York.
        """
        ny_dt = self.get_ny_now(dt)
        current_time = ny_dt.time()
        return current_time > self.end_time

    def is_dst_active(self, dt: datetime = None) -> bool:
        """Checks if Daylight Saving Time (EDT) is active in New York."""
        ny_dt = self.get_ny_now(dt)
        return bool(ny_dt.dst())
