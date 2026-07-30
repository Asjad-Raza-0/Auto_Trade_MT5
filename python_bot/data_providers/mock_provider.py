"""
Mock provider for tests and offline development.

Either inject exact frames with ``set_candles`` (what the tests do) or let it
generate a deterministic random walk. The generator is seeded, so a failing test
fails the same way every run.
"""
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd

from python_bot.data_providers.base_provider import BaseDataProvider

TIMEFRAME_MINUTES: Dict[str, int] = {
    "1m": 1, "2m": 2, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "4h": 240, "1d": 1440,
}


class MockDataProvider(BaseDataProvider):
    def __init__(self, seed: int = 42, base_prices: Optional[Dict[str, float]] = None):
        self.preset: Dict[Tuple[str, str], pd.DataFrame] = {}
        self.seed = seed
        self.base_prices = base_prices or {"US30": 39000.0, "XAUUSD": 2350.0}

    @property
    def name(self) -> str:
        return "mock"

    def set_candles(self, symbol: str, timeframe: str, df: pd.DataFrame) -> None:
        self.preset[(symbol.upper(), timeframe.lower())] = df.reset_index(drop=True)

    def get_candles(self, symbol: str, timeframe: str, count: int = 300) -> Optional[pd.DataFrame]:
        key = (symbol.upper(), timeframe.lower())
        if key in self.preset:
            return self.validate(self.preset[key].tail(count).reset_index(drop=True))
        return self.validate(self._generate(symbol, timeframe, count))

    def _generate(self, symbol: str, timeframe: str, count: int) -> pd.DataFrame:
        rng = np.random.default_rng(self.seed + len(symbol) + count)
        minutes = TIMEFRAME_MINUTES.get(timeframe.lower(), 1)
        base = self.base_prices.get(symbol.upper(), 1.1000)
        step = base * 0.0004

        # Anchored to a fixed timestamp so generated data is reproducible.
        end = datetime(2026, 7, 30, 12, 0, 0)
        times = [end - timedelta(minutes=minutes * (count - i)) for i in range(count)]

        closes = base + np.cumsum(rng.normal(0.0, step, count))
        opens = np.concatenate([[base], closes[:-1]])
        wick = np.abs(rng.normal(step * 0.6, step * 0.3, count))
        highs = np.maximum(opens, closes) + wick
        lows = np.minimum(opens, closes) - wick

        return pd.DataFrame({
            "time": times,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.full(count, 100.0),
        })
