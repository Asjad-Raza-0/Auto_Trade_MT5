"""
Market-data abstraction.

CONTRACT — every provider must honour all four points, because strategies rely
on them and a violation silently corrupts every signal:

  1. Return a DataFrame with columns exactly ``time, open, high, low, close, volume``.
  2. Rows ordered OLDEST FIRST.
  3. **COMPLETED CANDLES ONLY.** Never include the bar currently forming.
  4. Return ``None`` (never an empty frame, never a partial frame) on failure.

Timeframe strings are the canonical set: ``1m 2m 3m 5m 15m 30m 1h 4h 1d 1w``.
"""
from abc import ABC, abstractmethod
from typing import Optional

import pandas as pd

REQUIRED_COLUMNS = ["time", "open", "high", "low", "close", "volume"]


class BaseDataProvider(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def get_candles(self, symbol: str, timeframe: str, count: int = 300) -> Optional[pd.DataFrame]:
        """Fetch the last ``count`` COMPLETED candles for ``symbol`` at ``timeframe``."""

    # ------------------------------------------------------------------ helper
    @staticmethod
    def validate(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
        """Return ``df`` if it satisfies the contract, else None."""
        if df is None or len(df) == 0:
            return None
        if any(column not in df.columns for column in REQUIRED_COLUMNS):
            return None
        return df[REQUIRED_COLUMNS]
