import pytest
from datetime import datetime
import pytz
from python_bot.core.session_manager import SessionManager

def test_session_manager_in_session():
    sm = SessionManager(start_str="03:00", end_str="06:30", tz_name="America/New_York")
    
    # 04:15 NY time (within 03:00 - 06:30)
    ny_tz = pytz.timezone("America/New_York")
    dt_in = ny_tz.localize(datetime(2026, 7, 28, 4, 15, 0))
    assert sm.is_in_session(dt_in) is True
    assert sm.is_session_expired(dt_in) is False

def test_session_manager_outside_session():
    sm = SessionManager(start_str="03:00", end_str="06:30", tz_name="America/New_York")
    ny_tz = pytz.timezone("America/New_York")
    
    # 02:30 NY time (before session)
    dt_before = ny_tz.localize(datetime(2026, 7, 28, 2, 30, 0))
    assert sm.is_in_session(dt_before) is False
    assert sm.is_session_expired(dt_before) is False

    # 07:00 NY time (after session)
    dt_after = ny_tz.localize(datetime(2026, 7, 28, 7, 0, 0))
    assert sm.is_in_session(dt_after) is False
    assert sm.is_session_expired(dt_after) is True

def test_session_manager_dst_detection():
    sm = SessionManager()
    ny_tz = pytz.timezone("America/New_York")
    
    # Summer (EDT - UTC-4)
    summer_dt = ny_tz.localize(datetime(2026, 7, 1, 4, 0, 0))
    assert sm.is_dst_active(summer_dt) is True

    # Winter (EST - UTC-5)
    winter_dt = ny_tz.localize(datetime(2026, 1, 15, 4, 0, 0))
    assert sm.is_dst_active(winter_dt) is False
