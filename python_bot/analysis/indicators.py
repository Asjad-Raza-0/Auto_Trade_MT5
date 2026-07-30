"""Plain numeric indicators. No strategy knowledge lives here."""
from typing import Optional

import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average (same convention as MT5 / TradingView)."""
    return series.ewm(span=period, adjust=False).mean()


def sma(series: pd.Series, period: int) -> pd.Series:
    return series.rolling(window=period, min_periods=1).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    ranges = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    )
    return ranges.max(axis=1)


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Wilder's Average True Range."""
    tr = true_range(df)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=1).mean()


def last_atr(df: pd.DataFrame, period: int = 14, fallback: Optional[float] = None) -> float:
    """
    ATR of the most recent completed bar, with a safe fallback so callers never
    divide by zero on thin or malformed data.
    """
    if df is None or len(df) == 0:
        return fallback if fallback is not None else 0.0
    value = float(atr(df, period).iloc[-1])
    if value > 0:
        return value
    # Degenerate data (flat bars): fall back to mean bar range, then to a tick.
    mean_range = float((df["high"] - df["low"]).mean())
    if mean_range > 0:
        return mean_range
    return fallback if fallback is not None else max(float(df["close"].iloc[-1]) * 1e-5, 1e-8)
