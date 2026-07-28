from typing import Optional, Dict
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from python_bot.data_providers.base_provider import BaseDataProvider

class MockDataProvider(BaseDataProvider):
    """
    Mock Data Provider for testing and strategy verification.
    Can inject custom synthetic DataFrames.
    """
    def __init__(self):
        self.preset_data: Dict[str, pd.DataFrame] = {}

    @property
    def name(self) -> str:
        return "mock"

    def set_preset_data(self, symbol: str, interval: str, df: pd.DataFrame):
        key = f"{symbol.upper()}_{interval.lower()}"
        self.preset_data[key] = df

    def get_candles(self, symbol: str, interval: str, outputsize: int = 250) -> Optional[pd.DataFrame]:
        key = f"{symbol.upper()}_{interval.lower()}"
        if key in self.preset_data:
            return self.preset_data[key]

        # Generate default synthetic bullish candles if no preset
        now = datetime.utcnow()
        times = [now - timedelta(minutes=30 * (outputsize - i)) for i in range(outputsize)]
        base_price = 2000.0 if "XAU" in symbol.upper() else 1.1000
        
        opens, highs, lows, closes = [], [], [], []
        curr = base_price
        for _ in range(outputsize):
            o = curr
            c = o + np.random.uniform(-0.002, 0.003) * o
            h = max(o, c) + np.random.uniform(0.0001, 0.001) * o
            l = min(o, c) - np.random.uniform(0.0001, 0.001) * o
            opens.append(o)
            highs.append(h)
            lows.append(l)
            closes.append(c)
            curr = c

        df = pd.DataFrame({
            "time": times,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": [100.0] * outputsize
        })
        return df
