"""
Market-structure reading: higher-highs/higher-lows, lower-highs/lower-lows, and
break-of-structure detection.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd

from python_bot.analysis.swings import last_swings
from python_bot.models import Direction, SwingKind, SwingPoint


@dataclass
class StructureRead:
    """Snapshot of market structure derived from confirmed swings."""
    pattern: str = "NONE"                 # "HH_HL" | "LH_LL" | "MIXED" | "NONE"
    bias: Direction = Direction.NONE
    highs: List[SwingPoint] = field(default_factory=list)
    lows: List[SwingPoint] = field(default_factory=list)
    detail: str = ""

    @property
    def last_high(self) -> Optional[SwingPoint]:
        return self.highs[-1] if self.highs else None

    @property
    def prev_high(self) -> Optional[SwingPoint]:
        return self.highs[-2] if len(self.highs) >= 2 else None

    @property
    def last_low(self) -> Optional[SwingPoint]:
        return self.lows[-1] if self.lows else None

    @property
    def prev_low(self) -> Optional[SwingPoint]:
        return self.lows[-2] if len(self.lows) >= 2 else None

    def to_dict(self) -> Dict[str, object]:
        return {
            "pattern": self.pattern,
            "bias": self.bias.value,
            "detail": self.detail,
            "last_high": self.last_high.to_dict() if self.last_high else None,
            "last_low": self.last_low.to_dict() if self.last_low else None,
            "prev_high": self.prev_high.to_dict() if self.prev_high else None,
            "prev_low": self.prev_low.to_dict() if self.prev_low else None,
        }


def read_structure(swings: List[SwingPoint], min_swings: int = 2) -> StructureRead:
    """
    Classify the recent swing sequence.

    ``min_swings`` is how many highs AND lows must be rising (or falling) in a
    row. 2 means "one higher high and one higher low" — the minimum sequence the
    strategy spec describes.
    """
    count = max(2, min_swings)
    highs = last_swings(swings, SwingKind.HIGH, count)
    lows = last_swings(swings, SwingKind.LOW, count)

    read = StructureRead(highs=highs, lows=lows)

    if len(highs) < count or len(lows) < count:
        read.pattern = "NONE"
        read.detail = f"need {count} confirmed highs and lows, have {len(highs)}H/{len(lows)}L"
        return read

    rising_highs = all(highs[i].price > highs[i - 1].price for i in range(1, len(highs)))
    rising_lows = all(lows[i].price > lows[i - 1].price for i in range(1, len(lows)))
    falling_highs = all(highs[i].price < highs[i - 1].price for i in range(1, len(highs)))
    falling_lows = all(lows[i].price < lows[i - 1].price for i in range(1, len(lows)))

    if rising_highs and rising_lows:
        read.pattern = "HH_HL"
        read.bias = Direction.LONG
        read.detail = "higher highs + higher lows"
    elif falling_highs and falling_lows:
        read.pattern = "LH_LL"
        read.bias = Direction.SHORT
        read.detail = "lower highs + lower lows"
    else:
        read.pattern = "MIXED"
        read.detail = (
            f"highs {'up' if rising_highs else 'down' if falling_highs else 'mixed'}, "
            f"lows {'up' if rising_lows else 'down' if falling_lows else 'mixed'}"
        )
    return read


def detect_break_of_structure(
    df: pd.DataFrame,
    structure: StructureRead,
    direction: Direction,
    buffer: float = 0.0,
) -> Tuple[Optional[Dict[str, object]], str]:
    """
    "Wait for a new candle to take out the previous high (longs) or low (shorts)."

    The break must be a *close* beyond the most recent confirmed swing extreme,
    on the latest completed candle. Returns (break_info, reason).
    """
    if df is None or len(df) == 0:
        return None, "no data"

    close_now = float(df["close"].iloc[-1])

    if direction is Direction.LONG:
        pivot = structure.last_high
        if pivot is None:
            return None, "no confirmed swing high to break"
        level = pivot.price
        if close_now > level + buffer:
            return (
                {"level": level, "pivot_index": pivot.index, "pivot_time": pivot.time,
                 "close": close_now, "side": "ABOVE"},
                f"1m close {close_now:.5f} broke swing high {level:.5f}",
            )
        return None, f"1m close {close_now:.5f} has not broken swing high {level:.5f}"

    if direction is Direction.SHORT:
        pivot = structure.last_low
        if pivot is None:
            return None, "no confirmed swing low to break"
        level = pivot.price
        if close_now < level - buffer:
            return (
                {"level": level, "pivot_index": pivot.index, "pivot_time": pivot.time,
                 "close": close_now, "side": "BELOW"},
                f"1m close {close_now:.5f} broke swing low {level:.5f}",
            )
        return None, f"1m close {close_now:.5f} has not broken swing low {level:.5f}"

    return None, "no direction"


def structure_stop_level(structure: StructureRead, direction: Direction) -> Optional[float]:
    """
    The "immediate 1m structure" the stop loss hides behind: the most recent
    confirmed higher-low for longs, lower-high for shorts.
    """
    if direction is Direction.LONG:
        return structure.last_low.price if structure.last_low else None
    if direction is Direction.SHORT:
        return structure.last_high.price if structure.last_high else None
    return None


def detect_retest(
    df: pd.DataFrame,
    broken_level: float,
    direction: Direction,
    lookback: int = 10,
    tolerance: float = 0.0,
) -> Tuple[bool, str]:
    """
    Optional extra confirmation: after breaking ``broken_level``, price came back
    to it and held, then continued. Checks the last ``lookback`` completed bars
    for a bar that traded back into the level while still closing beyond it.
    """
    if df is None or len(df) < 2:
        return False, "no data"

    window = df.iloc[-lookback:] if lookback > 0 else df
    for i in range(len(window)):
        high = float(window["high"].iloc[i])
        low = float(window["low"].iloc[i])
        close_v = float(window["close"].iloc[i])
        if direction is Direction.LONG:
            if low <= broken_level + tolerance and close_v > broken_level:
                return True, f"retested broken level {broken_level:.5f} and held above"
        elif direction is Direction.SHORT:
            if high >= broken_level - tolerance and close_v < broken_level:
                return True, f"retested broken level {broken_level:.5f} and held below"
    return False, f"no retest of {broken_level:.5f} in last {lookback} bars"
