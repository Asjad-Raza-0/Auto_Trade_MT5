"""Tests for the optional trading-session filter."""
from datetime import datetime

import pytz

from python_bot.core.session_manager import SessionManager

NY = pytz.timezone("America/New_York")


def test_disabled_filter_is_always_open():
    sm = SessionManager(enabled=False)
    is_open, reason = sm.is_open(NY.localize(datetime(2026, 7, 26, 3, 0)))  # a Sunday
    assert is_open is True
    assert "disabled" in reason


def test_inside_the_window():
    sm = SessionManager(enabled=True, start="09:30", end="10:00",
                        timezone="America/New_York")
    is_open, reason = sm.is_open(NY.localize(datetime(2026, 7, 28, 9, 45)))  # Tuesday
    assert is_open is True
    assert "inside session" in reason


def test_outside_the_window():
    sm = SessionManager(enabled=True, start="09:30", end="10:00",
                        timezone="America/New_York")
    assert sm.is_open(NY.localize(datetime(2026, 7, 28, 8, 0)))[0] is False
    assert sm.is_open(NY.localize(datetime(2026, 7, 28, 10, 1)))[0] is False


def test_non_trading_day_is_rejected():
    sm = SessionManager(enabled=True, start="09:30", end="10:00",
                        timezone="America/New_York", trade_days=[0, 1, 2, 3, 4])
    saturday = NY.localize(datetime(2026, 7, 25, 9, 45))
    is_open, reason = sm.is_open(saturday)
    assert is_open is False
    assert "not a trading day" in reason


def test_window_wrapping_past_midnight():
    sm = SessionManager(enabled=True, start="22:00", end="02:00",
                        timezone="America/New_York",
                        trade_days=[0, 1, 2, 3, 4])
    assert sm.is_open(NY.localize(datetime(2026, 7, 28, 23, 0)))[0] is True
    assert sm.is_open(NY.localize(datetime(2026, 7, 28, 1, 0)))[0] is True
    assert sm.is_open(NY.localize(datetime(2026, 7, 28, 12, 0)))[0] is False


def test_utc_input_is_converted_to_session_timezone():
    sm = SessionManager(enabled=True, start="09:30", end="10:00",
                        timezone="America/New_York")
    # 13:45 UTC == 09:45 New York in July (EDT, UTC-4).
    utc_dt = pytz.utc.localize(datetime(2026, 7, 28, 13, 45))
    assert sm.is_open(utc_dt)[0] is True


def test_dst_detection():
    sm = SessionManager()
    assert sm.is_dst_active(NY.localize(datetime(2026, 7, 1, 4, 0))) is True    # EDT
    assert sm.is_dst_active(NY.localize(datetime(2026, 1, 15, 4, 0))) is False  # EST
