"""Unit tests for the reusable price-action primitives in ``python_bot/analysis``."""
import pandas as pd
import pytest

from tests.conftest import (
    bearish_htf_frame,
    bullish_htf_frame,
    bullish_ltf_frame,
    candle,
    flat_frame,
    make_frame,
    zigzag,
)
from python_bot.analysis import (
    build_zones,
    detect_break_of_structure,
    detect_exhaustion,
    detect_reaction,
    detect_retest,
    detect_trendline_break,
    find_active_zone,
    find_swing_points,
    fit_trendline,
    last_atr,
    next_zone_beyond,
    read_structure,
    structure_stop_level,
    trendline_kind_for,
)
from python_bot.analysis.swings import filter_swings
from python_bot.models import Direction, SwingKind, TrendlineKind, ZoneKind


# --------------------------------------------------------------------- ATR
def test_atr_is_positive_on_real_movement():
    assert last_atr(bullish_ltf_frame(), 14) > 0


def test_atr_never_returns_zero_on_flat_data():
    """A zero ATR would make every ATR-scaled threshold collapse to 0."""
    assert last_atr(flat_frame(), 14) > 0


# ------------------------------------------------------------------ swings
def test_swings_alternate_and_are_confirmed():
    df = make_frame(zigzag([100, 120, 105, 130, 110], bars_per_leg=3, wick=1.0))
    swings = find_swing_points(df, lookback=2)

    assert swings, "expected swing points on a zigzag"
    highs = filter_swings(swings, SwingKind.HIGH)
    lows = filter_swings(swings, SwingKind.LOW)
    assert highs and lows

    # No swing may sit in the unconfirmed tail — it needs `lookback` bars to its right.
    assert max(s.index for s in swings) <= len(df) - 1 - 2


def test_no_swings_on_flat_data():
    assert find_swing_points(flat_frame(), lookback=2) == []


# ------------------------------------------------------------------- zones
def test_support_zone_requires_minimum_touches():
    df = bullish_htf_frame()
    swings = find_swing_points(df, 3)
    tolerance = last_atr(df, 14) * 0.35

    zones = build_zones(df, swings, ZoneKind.SUPPORT, tolerance, "5m", min_touches=3)
    assert zones, "the repeatedly tested support should qualify"
    assert all(z.touches >= 3 for z in zones)
    assert zones[0].rejection_wicks > 0, "rejection wicks should be counted"

    # Raising the bar past what the data supports must yield nothing.
    assert build_zones(df, swings, ZoneKind.SUPPORT, tolerance, "5m", min_touches=99) == []


def test_find_active_zone_respects_max_distance():
    df = bullish_htf_frame()
    swings = find_swing_points(df, 3)
    atr = last_atr(df, 14)
    zones = build_zones(df, swings, ZoneKind.SUPPORT, atr * 0.35, "5m", min_touches=3)
    zone = zones[0]

    assert find_active_zone(zones, zone.mid, atr) is zone
    assert find_active_zone(zones, zone.top + atr * 50, atr) is None


def test_next_zone_beyond_picks_the_nearest_obstacle():
    near = build_zone(ZoneKind.RESISTANCE, 110, 112)
    far = build_zone(ZoneKind.RESISTANCE, 130, 132)
    behind = build_zone(ZoneKind.RESISTANCE, 90, 92)

    chosen = next_zone_beyond([far, near, behind], price=100.0, direction=Direction.LONG)
    assert chosen is near

    chosen_short = next_zone_beyond([far, near, behind], price=100.0, direction=Direction.SHORT)
    assert chosen_short is behind


def test_exhaustion_needs_a_rejection_wick():
    df = bullish_htf_frame()
    swings = find_swing_points(df, 3)
    atr = last_atr(df, 14)
    zone = build_zones(df, swings, ZoneKind.SUPPORT, atr * 0.35, "5m", min_touches=3)[0]

    exhausted, note = detect_exhaustion(df, zone, lookback=6, wick_ratio=0.5)
    assert exhausted, note

    # An impossible wick requirement must fail rather than pass by accident.
    assert detect_exhaustion(df, zone, lookback=6, wick_ratio=0.999)[0] is False


def test_reaction_direction_is_directional():
    df = bullish_htf_frame()
    swings = find_swing_points(df, 3)
    atr = last_atr(df, 14)
    zone = build_zones(df, swings, ZoneKind.SUPPORT, atr * 0.35, "5m", min_touches=3)[0]

    assert detect_reaction(df, zone, Direction.LONG, bars=3)[0] is True
    assert detect_reaction(df, zone, Direction.SHORT, bars=3)[0] is False


def build_zone(kind: ZoneKind, bottom: float, top: float):
    from python_bot.models import Zone
    return Zone(kind=kind, timeframe="1m", top=top, bottom=bottom, touches=3)


# --------------------------------------------------------------- structure
def test_structure_reads_hh_hl():
    df = make_frame(zigzag([100, 110, 104, 118, 112, 126, 120], bars_per_leg=3, wick=1.0))
    structure = read_structure(find_swing_points(df, 2), min_swings=2)
    assert structure.pattern == "HH_HL"
    assert structure.bias is Direction.LONG


def test_structure_reads_lh_ll():
    df = make_frame(zigzag([126, 116, 122, 108, 114, 100, 106], bars_per_leg=3, wick=1.0))
    structure = read_structure(find_swing_points(df, 2), min_swings=2)
    assert structure.pattern == "LH_LL"
    assert structure.bias is Direction.SHORT


def test_structure_is_none_without_enough_swings():
    assert read_structure([], min_swings=2).pattern == "NONE"


def test_break_of_structure_requires_a_close_beyond_the_pivot():
    df = bullish_ltf_frame()
    structure = read_structure(find_swing_points(df, 2), 2)

    breakout, reason = detect_break_of_structure(df, structure, Direction.LONG)
    assert breakout is not None, reason
    assert breakout["close"] > breakout["level"]

    # The same data must NOT read as a short break.
    assert detect_break_of_structure(df, structure, Direction.SHORT)[0] is None


def test_break_of_structure_rejects_a_wick_only_poke():
    """A candle that pokes above the pivot but closes back under is not a break."""
    df = bullish_ltf_frame()
    structure = read_structure(find_swing_points(df, 2), 2)
    level = structure.last_high.price

    poked = df.copy()
    poked.loc[poked.index[-1], "high"] = level + 20.0
    poked.loc[poked.index[-1], "close"] = level - 5.0

    assert detect_break_of_structure(poked, structure, Direction.LONG)[0] is None


def test_structure_stop_level_uses_the_opposite_extreme():
    df = bullish_ltf_frame()
    structure = read_structure(find_swing_points(df, 2), 2)
    assert structure_stop_level(structure, Direction.LONG) == structure.last_low.price
    assert structure_stop_level(structure, Direction.SHORT) == structure.last_high.price


def test_retest_detection():
    df = make_frame([
        candle(100, 101, 99, 100),
        candle(100, 106, 100, 105),    # break above 102
        candle(105, 106, 101, 104),    # comes back to 101, closes above 102
    ])
    assert detect_retest(df, 102.0, Direction.LONG, lookback=5)[0] is True
    assert detect_retest(df, 200.0, Direction.LONG, lookback=5)[0] is False


# --------------------------------------------------------------- trendlines
def test_descending_trendline_is_found_and_broken():
    df = bullish_ltf_frame()
    atr = last_atr(df, 14)
    swings = find_swing_points(df, 2)

    line, reason = fit_trendline(df, swings, TrendlineKind.DESCENDING,
                                 lookback_bars=40, tolerance=atr * 0.1, min_touches=2)
    assert line is not None, reason
    assert line.slope < 0, "a descending line must fall"
    assert line.touches >= 2

    breakout, note = detect_trendline_break(df, line, Direction.LONG)
    assert breakout is not None, note
    assert breakout["close"] > breakout["projected"]


def test_trendline_kind_matches_trade_direction():
    assert trendline_kind_for(Direction.LONG) is TrendlineKind.DESCENDING
    assert trendline_kind_for(Direction.SHORT) is TrendlineKind.ASCENDING
    assert trendline_kind_for(Direction.NONE) is None


def test_no_trendline_without_two_pivots():
    df = flat_frame()
    line, reason = fit_trendline(df, find_swing_points(df, 2), TrendlineKind.DESCENDING)
    assert line is None
    assert "need 2" in reason
