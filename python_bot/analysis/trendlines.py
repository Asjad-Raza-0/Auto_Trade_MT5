"""
Trendline fitting and break detection.

A trendline here is always anchored on two confirmed swing points and validated
against every bar between them, so "a clear trendline" means: the line was never
meaningfully violated while it was being respected.

For a LONG setup we care about a DESCENDING line across swing highs (falling
resistance being broken upward). For a SHORT setup, an ASCENDING line across
swing lows.
"""
from typing import Dict, List, Optional, Tuple

import pandas as pd

from python_bot.analysis.swings import filter_swings
from python_bot.models import Direction, SwingKind, SwingPoint, Trendline, TrendlineKind


def _line_from_points(a: SwingPoint, b: SwingPoint, kind: TrendlineKind,
                      touches: int = 2) -> Optional[Trendline]:
    span = b.index - a.index
    if span <= 0:
        return None
    slope = (b.price - a.price) / span
    intercept = a.price - slope * a.index
    return Trendline(
        kind=kind,
        slope=slope,
        intercept=intercept,
        start_index=a.index,
        end_index=b.index,
        start_time=a.time,
        end_time=b.time,
        touches=touches,
    )


def fit_trendline(
    df: pd.DataFrame,
    swings: List[SwingPoint],
    kind: TrendlineKind,
    lookback_bars: int = 40,
    tolerance: float = 0.0,
    min_touches: int = 2,
) -> Tuple[Optional[Trendline], str]:
    """
    Fit the most recent valid trendline of ``kind``.

    Walks the newest swing point backwards against older ones and returns the
    first pair that (a) slopes the right way and (b) is not violated by any
    intervening PIVOT (allowing ``tolerance``, normally a small ATR fraction).
    """
    if df is None or len(df) == 0:
        return None, "no data"

    min_index = max(0, len(df) - lookback_bars)
    swing_kind = SwingKind.HIGH if kind is TrendlineKind.DESCENDING else SwingKind.LOW
    points = [s for s in filter_swings(swings, swing_kind) if s.index >= min_index]

    if len(points) < 2:
        return None, f"need 2 confirmed swing {swing_kind.value.lower()}s within {lookback_bars} bars, have {len(points)}"

    newest = points[-1]

    for older in reversed(points[:-1]):
        line = _line_from_points(older, newest, kind)
        if line is None:
            continue

        # Direction check: descending resistance must fall, ascending support must rise.
        if kind is TrendlineKind.DESCENDING and line.slope >= 0:
            continue
        if kind is TrendlineKind.ASCENDING and line.slope <= 0:
            continue

        if not _line_respected(points, line, kind, tolerance):
            continue

        line.touches = _count_touches(points, line, tolerance)
        if line.touches < min_touches:
            continue
        return line, (
            f"{kind.value.lower()} trendline from bar {line.start_index} to {line.end_index} "
            f"({line.touches} touches, slope {line.slope:+.6f}/bar)"
        )

    return None, f"no valid {kind.value.lower()} trendline in last {lookback_bars} bars"


def _line_respected(points: List[SwingPoint], line: Trendline, kind: TrendlineKind,
                    tolerance: float) -> bool:
    """
    No PIVOT strictly between the anchors may pierce the line by more than
    ``tolerance``.

    Validating against pivots rather than every raw bar is deliberate: a
    trendline anchored on a wick extreme is nearly always clipped by the wick of
    the very next candle, which no trader would call a broken line. Pivots are
    what the line is drawn across, so pivots are what must respect it.
    """
    for point in points:
        if not (line.start_index < point.index < line.end_index):
            continue
        expected = line.value_at(point.index)
        if kind is TrendlineKind.DESCENDING and point.price > expected + tolerance:
            return False
        if kind is TrendlineKind.ASCENDING and point.price < expected - tolerance:
            return False
    return True


def _count_touches(points: List[SwingPoint], line: Trendline, tolerance: float) -> int:
    """How many swing points of the relevant kind sit on the line."""
    band = tolerance if tolerance > 0 else abs(line.slope) * 1.0
    return sum(
        1 for p in points
        if line.start_index <= p.index <= line.end_index
        and abs(p.price - line.value_at(p.index)) <= band
    )


def detect_trendline_break(
    df: pd.DataFrame,
    line: Trendline,
    direction: Direction,
    buffer: float = 0.0,
) -> Tuple[Optional[Dict[str, object]], str]:
    """
    A break is a CLOSE of the latest completed candle beyond the projected line.
    Returns (break_info, reason).
    """
    if df is None or len(df) == 0 or line is None:
        return None, "no trendline"

    last_index = len(df) - 1
    projected = line.value_at(last_index)
    close_now = float(df["close"].iloc[-1])

    if direction is Direction.LONG:
        if close_now > projected + buffer:
            return (
                {"projected": projected, "close": close_now, "bar_index": last_index,
                 "trendline": line.to_dict()},
                f"1m close {close_now:.5f} broke descending trendline at {projected:.5f}",
            )
        return None, f"1m close {close_now:.5f} still under descending trendline {projected:.5f}"

    if direction is Direction.SHORT:
        if close_now < projected - buffer:
            return (
                {"projected": projected, "close": close_now, "bar_index": last_index,
                 "trendline": line.to_dict()},
                f"1m close {close_now:.5f} broke ascending trendline at {projected:.5f}",
            )
        return None, f"1m close {close_now:.5f} still above ascending trendline {projected:.5f}"

    return None, "no direction"


def trendline_kind_for(direction: Direction) -> Optional[TrendlineKind]:
    """A long breaks falling resistance; a short breaks rising support."""
    if direction is Direction.LONG:
        return TrendlineKind.DESCENDING
    if direction is Direction.SHORT:
        return TrendlineKind.ASCENDING
    return None
