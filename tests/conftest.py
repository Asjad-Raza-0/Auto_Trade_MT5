"""
Shared synthetic-candle builders.

Every helper produces DETERMINISTIC data — no randomness — so a failure always
reproduces. Frames follow the provider contract: completed candles only, oldest
first, columns ``time, open, high, low, close, volume``.
"""
from datetime import datetime, timedelta
from typing import List, Sequence

import pandas as pd
import pytest

BASE_TIME = datetime(2026, 7, 30, 9, 0, 0)


def candle(open_: float, high: float, low: float, close: float) -> dict:
    return {"open": open_, "high": high, "low": low, "close": close}


def make_frame(bars: Sequence[dict], start: datetime = BASE_TIME,
               minutes: int = 1) -> pd.DataFrame:
    """Build a frame from open/high/low/close dicts, timestamping them in order."""
    rows = [
        {
            "time": start + timedelta(minutes=minutes * i),
            "open": float(bar["open"]),
            "high": float(bar["high"]),
            "low": float(bar["low"]),
            "close": float(bar["close"]),
            "volume": float(bar.get("volume", 100.0)),
        }
        for i, bar in enumerate(bars)
    ]
    return pd.DataFrame(rows)


def zigzag(points: Sequence[float], bars_per_leg: int = 3, wick: float = 2.0) -> List[dict]:
    """
    Walk linearly between turning points, ``bars_per_leg`` candles per leg.

    Each turning point lands on a bar boundary and becomes a clean local extreme,
    which is exactly what the fractal swing detector is designed to find.
    """
    bars: List[dict] = []
    for i in range(len(points) - 1):
        start, end = float(points[i]), float(points[i + 1])
        for j in range(bars_per_leg):
            open_ = start + (end - start) * j / bars_per_leg
            close = start + (end - start) * (j + 1) / bars_per_leg
            bars.append(candle(open_, max(open_, close) + wick,
                               min(open_, close) - wick, close))
    return bars


def ramp(start_price: float, count: int, step: float, wick: float = 1.0) -> List[dict]:
    """A clean directional run of ``count`` candles moving ``step`` per bar."""
    bars = []
    price = start_price
    for _ in range(count):
        close = price + step
        bars.append(candle(price, max(price, close) + wick, min(price, close) - wick, close))
        price = close
    return bars


def support_test(level: float, wick_depth: float, close_above: float,
                 body: float = 4.0) -> dict:
    """A candle that pierces ``level`` with a long lower wick and closes above it."""
    return candle(close_above - body, close_above + 2.0, level - wick_depth, close_above)


def resistance_test(level: float, wick_height: float, close_below: float,
                    body: float = 4.0) -> dict:
    """A candle that pierces ``level`` with a long upper wick and closes below it."""
    return candle(close_below + body, level + wick_height, close_below - 2.0, close_below)


# ---------------------------------------------------------------------------
# Full multi-timeframe scenarios
# ---------------------------------------------------------------------------

def bullish_htf_frame() -> pd.DataFrame:
    """
    5m frame: price has tested a support band near 39000 five times, each time
    rejected with a long lower wick, and has just begun pushing up off it.
    Expected read: LONG bias.
    """
    bars: List[dict] = []
    bars += zigzag([39180, 39120, 39160, 39100], bars_per_leg=3, wick=6.0)

    # Four visits to support, each rejected.
    for _ in range(4):
        bars.append(support_test(39000.0, wick_depth=18.0, close_above=39040.0))
        bars += ramp(39040.0, 3, step=9.0, wick=5.0)     # bounce away
        bars += ramp(39067.0, 3, step=-9.0, wick=5.0)    # drift back down

    # Final exhaustion at the zone, then the reaction — kept short so price is
    # still near the zone when the bias is read.
    bars.append(support_test(39000.0, wick_depth=22.0, close_above=39050.0))
    bars += ramp(39050.0, 3, step=8.0, wick=4.0)

    return make_frame(bars, minutes=5)


def bearish_htf_frame() -> pd.DataFrame:
    """5m frame rejecting a resistance band near 2400 repeatedly — SHORT bias."""
    bars: List[dict] = []
    bars += zigzag([2360, 2372, 2364, 2376], bars_per_leg=3, wick=1.2)

    for _ in range(4):
        bars.append(resistance_test(2400.0, wick_height=3.6, close_below=2392.0))
        bars += ramp(2392.0, 3, step=-1.8, wick=1.0)
        bars += ramp(2386.6, 3, step=1.8, wick=1.0)

    bars.append(resistance_test(2400.0, wick_height=4.4, close_below=2390.0))
    bars += ramp(2390.0, 3, step=-1.6, wick=0.8)

    return make_frame(bars, minutes=5)


def bullish_ltf_frame() -> pd.DataFrame:
    """
    1m frame containing all three LONG confirmations:
      * descending trendline across falling swing highs (39172 -> 39140)
      * HH/HL base (low 39050 -> higher low 39056 -> higher low 39070)
      * a final candle closing above the last swing high AND the trendline
    """
    points = [
        39200, 39120,   # opening decline
        39172, 39090,   # swing high #1 (trendline anchor)
        39140, 39050,   # swing high #2 (lower) -> descending trendline; then the base low
        39066, 39056,   # first bounce, then a HIGHER low
        39084, 39070,   # HIGHER high, then another HIGHER low
    ]
    bars = zigzag(points, bars_per_leg=3, wick=2.0)
    # The trigger: close decisively above the 39084 swing high.
    bars.append(candle(39070.0, 39098.0, 39068.0, 39096.0))
    return make_frame(bars, minutes=1)


def bearish_ltf_frame() -> pd.DataFrame:
    """Mirror image of ``bullish_ltf_frame`` for SHORT setups."""
    points = [
        2360, 2392,
        2366, 2400,
        2374, 2420,
        2410, 2416,
        2396, 2404,
    ]
    bars = zigzag(points, bars_per_leg=3, wick=0.6)
    bars.append(candle(2404.0, 2405.0, 2392.0, 2393.0))
    return make_frame(bars, minutes=1)


def flat_frame(bars: int = 120, price: float = 100.0) -> pd.DataFrame:
    """Featureless data — no zones, no structure. Nothing may trigger on this."""
    return make_frame([candle(price, price + 0.5, price - 0.5, price)] * bars, minutes=1)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def bullish_data():
    return {"htf": bullish_htf_frame(), "ltf": bullish_ltf_frame()}


@pytest.fixture
def bearish_data():
    return {"htf": bearish_htf_frame(), "ltf": bearish_ltf_frame()}


@pytest.fixture
def flat_data():
    return {"htf": flat_frame(), "ltf": flat_frame()}
