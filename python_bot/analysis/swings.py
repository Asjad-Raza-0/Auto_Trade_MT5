"""
Fractal swing (pivot) detection.

A bar is a swing high when its high is above the ``lookback`` highs to its left
and at/above the ``lookback`` highs to its right. Requiring bars on the right is
what makes a swing *confirmed* — the last ``lookback`` bars of the frame can
therefore never be swings, which is correct: they are not confirmed yet.
"""
from datetime import datetime
from typing import List, Optional

import pandas as pd

from python_bot.models import SwingKind, SwingPoint


def _bar_time(df: pd.DataFrame, index: int) -> Optional[datetime]:
    if "time" in df.columns:
        value = df["time"].iloc[index]
    else:
        value = df.index[index]
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, datetime):
        return value
    return None


def find_swing_points(df: pd.DataFrame, lookback: int = 2) -> List[SwingPoint]:
    """
    Returns every confirmed swing high and low, ordered by bar index.

    ``lookback`` is the number of bars required on each side. 2 is a good default
    for 1-minute noise; 3 or more gives coarser, higher-timeframe style pivots.
    """
    if df is None or len(df) < (2 * lookback + 1):
        return []

    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    n = len(df)
    swings: List[SwingPoint] = []

    for i in range(lookback, n - lookback):
        left = slice(i - lookback, i)
        right = slice(i + 1, i + 1 + lookback)

        if highs[i] > highs[left].max() and highs[i] >= highs[right].max():
            swings.append(SwingPoint(index=i, time=_bar_time(df, i), price=float(highs[i]),
                                     kind=SwingKind.HIGH))

        if lows[i] < lows[left].min() and lows[i] <= lows[right].min():
            swings.append(SwingPoint(index=i, time=_bar_time(df, i), price=float(lows[i]),
                                     kind=SwingKind.LOW))

    swings.sort(key=lambda s: s.index)
    return swings


def filter_swings(swings: List[SwingPoint], kind: SwingKind) -> List[SwingPoint]:
    return [s for s in swings if s.kind is kind]


def last_swings(swings: List[SwingPoint], kind: SwingKind, count: int) -> List[SwingPoint]:
    """The ``count`` most recent swings of one kind, still in chronological order."""
    selected = filter_swings(swings, kind)
    return selected[-count:] if count > 0 else selected
