"""
Support / resistance zone construction and reaction analysis.

Zones are built by clustering confirmed swing points that sit within a price
tolerance of each other, then counting how many bars in the whole frame actually
touched the resulting band. That gives the "price has touched this level 3-4
times" requirement a concrete, testable definition.
"""
from typing import List, Optional, Tuple

import pandas as pd

from python_bot.analysis.swings import filter_swings
from python_bot.models import Direction, SwingKind, SwingPoint, Zone, ZoneKind


def build_zones(
    df: pd.DataFrame,
    swings: List[SwingPoint],
    kind: ZoneKind,
    tolerance: float,
    timeframe: str = "",
    min_touches: int = 3,
    wick_ratio: float = 0.5,
) -> List[Zone]:
    """
    Cluster swing points of one kind into zones and count touches.

    Args:
        tolerance: max price distance for two swings to belong to the same zone
                   (callers normally pass ``atr * zone_cluster_atr_mult``).
        min_touches: zones with fewer touches are discarded.
        wick_ratio: a touching bar counts as a *rejection wick* when the wick
                    pointing into the zone is at least this fraction of its range.

    Returns zones sorted by touch count (strongest first).
    """
    if df is None or len(df) == 0 or tolerance <= 0:
        return []

    swing_kind = SwingKind.HIGH if kind is ZoneKind.RESISTANCE else SwingKind.LOW
    points = filter_swings(swings, swing_kind)
    if not points:
        return []

    # Greedy clustering over price-sorted swings.
    ordered = sorted(points, key=lambda s: s.price)
    clusters: List[List[SwingPoint]] = [[ordered[0]]]
    for point in ordered[1:]:
        if abs(point.price - clusters[-1][-1].price) <= tolerance:
            clusters[-1].append(point)
        else:
            clusters.append([point])

    zones: List[Zone] = []
    for cluster in clusters:
        prices = [p.price for p in cluster]
        zone = Zone(
            kind=kind,
            timeframe=timeframe,
            top=max(prices),
            bottom=min(prices),
        )
        # A zone built from a single swing still needs width to be testable.
        if zone.height <= 0:
            half = tolerance / 2.0
            zone.top += half
            zone.bottom -= half

        _count_touches(df, zone, wick_ratio=wick_ratio)
        if zone.touches >= min_touches:
            zones.append(zone)

    zones.sort(key=lambda z: (z.touches, z.rejection_wicks), reverse=True)
    return zones


def _count_touches(df: pd.DataFrame, zone: Zone, wick_ratio: float = 0.5) -> None:
    """Fills ``touches``, ``rejection_wicks`` and the touch timestamps on ``zone``."""
    is_support = zone.kind is ZoneKind.SUPPORT
    touches = 0
    rejections = 0
    first_time = None
    last_time = None
    in_touch = False   # collapse consecutive bars inside the zone into one touch

    times = df["time"] if "time" in df.columns else pd.Series(df.index, index=df.index)

    for i in range(len(df)):
        high = float(df["high"].iloc[i])
        low = float(df["low"].iloc[i])
        touching = (low <= zone.top) if is_support else (high >= zone.bottom)
        # Require the bar to actually reach into the band, not merely be beyond it.
        touching = touching and (high >= zone.bottom if is_support else low <= zone.top)

        if not touching:
            in_touch = False
            continue

        if not in_touch:
            touches += 1
            in_touch = True
            bar_time = times.iloc[i]
            if first_time is None:
                first_time = bar_time
            last_time = bar_time

        open_v = float(df["open"].iloc[i])
        close_v = float(df["close"].iloc[i])
        bar_range = high - low
        if bar_range <= 0:
            continue
        wick = (min(open_v, close_v) - low) if is_support else (high - max(open_v, close_v))
        closed_away = (close_v > zone.mid) if is_support else (close_v < zone.mid)
        if (wick / bar_range) >= wick_ratio and closed_away:
            rejections += 1

    zone.touches = touches
    zone.rejection_wicks = rejections
    zone.first_touch_time = _to_datetime(first_time)
    zone.last_touch_time = _to_datetime(last_time)


def _to_datetime(value):
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    return value


def find_active_zone(zones: List[Zone], price: float, max_distance: float) -> Optional[Zone]:
    """
    The zone price is currently interacting with: nearest zone within
    ``max_distance``, strongest (most touches) breaking ties.
    """
    candidates = [z for z in zones if z.distance_to(price) <= max_distance]
    if not candidates:
        return None
    candidates.sort(key=lambda z: (z.distance_to(price), -z.touches, -z.rejection_wicks))
    return candidates[0]


def next_zone_beyond(
    zones: List[Zone],
    price: float,
    direction: Direction,
    min_distance: float = 0.0,
) -> Optional[Zone]:
    """
    The first zone standing in the way of a trade: above ``price`` for LONG,
    below for SHORT, at least ``min_distance`` away. Used for zone-based targets.
    """
    if direction is Direction.LONG:
        ahead = [z for z in zones if z.bottom > price + min_distance]
        ahead.sort(key=lambda z: z.bottom)
    elif direction is Direction.SHORT:
        ahead = [z for z in zones if z.top < price - min_distance]
        ahead.sort(key=lambda z: -z.top)
    else:
        return None
    return ahead[0] if ahead else None


def detect_exhaustion(
    df: pd.DataFrame,
    zone: Zone,
    lookback: int = 6,
    wick_ratio: float = 0.5,
) -> Tuple[bool, str]:
    """
    "Sellers/buyers are getting tired at the zone."

    Looks at the last ``lookback`` completed bars and requires at least one bar
    that pushed into the zone but was rejected out of it — a long wick into the
    zone with the close back on the safe side of the zone mid.
    """
    if df is None or len(df) == 0:
        return False, "no data"

    is_support = zone.kind is ZoneKind.SUPPORT
    window = df.iloc[-lookback:] if lookback > 0 else df
    rejections = 0
    max_wick_ratio = 0.0

    for i in range(len(window)):
        high = float(window["high"].iloc[i])
        low = float(window["low"].iloc[i])
        open_v = float(window["open"].iloc[i])
        close_v = float(window["close"].iloc[i])
        bar_range = high - low
        if bar_range <= 0:
            continue

        reached = (low <= zone.top) if is_support else (high >= zone.bottom)
        if not reached:
            continue

        wick = (min(open_v, close_v) - low) if is_support else (high - max(open_v, close_v))
        ratio = wick / bar_range
        max_wick_ratio = max(max_wick_ratio, ratio)
        closed_away = (close_v > zone.mid) if is_support else (close_v < zone.mid)
        if ratio >= wick_ratio and closed_away:
            rejections += 1

    if rejections > 0:
        return True, f"{rejections} rejection wick(s) at {zone.kind.value} zone (max wick {max_wick_ratio:.0%} of range)"
    return False, (
        f"no rejection wick >= {wick_ratio:.0%} of range at {zone.kind.value} zone "
        f"in last {lookback} bars (best {max_wick_ratio:.0%})"
    )


def detect_reaction(
    df: pd.DataFrame,
    zone: Zone,
    direction: Direction,
    bars: int = 3,
) -> Tuple[bool, str]:
    """
    "Price has solidified its reaction and begun moving in the opposite direction."

    Requires the latest completed close to be on the correct side of the zone mid
    AND to have progressed away from the zone over the last ``bars`` closes.
    """
    if df is None or len(df) < bars + 1:
        return False, "not enough bars to measure the reaction"

    close_now = float(df["close"].iloc[-1])
    close_then = float(df["close"].iloc[-1 - bars])

    if direction is Direction.LONG:
        if close_now <= zone.mid:
            return False, f"close {close_now:.5f} still at/below support mid {zone.mid:.5f}"
        if close_now <= close_then:
            return False, f"no upward progress over last {bars} bars ({close_then:.5f} -> {close_now:.5f})"
        return True, f"price pushing up off support ({close_then:.5f} -> {close_now:.5f})"

    if direction is Direction.SHORT:
        if close_now >= zone.mid:
            return False, f"close {close_now:.5f} still at/above resistance mid {zone.mid:.5f}"
        if close_now >= close_then:
            return False, f"no downward progress over last {bars} bars ({close_then:.5f} -> {close_now:.5f})"
        return True, f"price pushing down off resistance ({close_then:.5f} -> {close_now:.5f})"

    return False, "no direction"
