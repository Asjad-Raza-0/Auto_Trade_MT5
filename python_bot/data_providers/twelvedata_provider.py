"""
TwelveData REST provider — optional secondary feed.

Free tier is 8 requests/minute, which a 1-minute strategy scanning two symbols
across two timeframes will exhaust quickly. Keep it as a fallback, not a primary.
"""
import logging
import time
from typing import Dict, Optional

import pandas as pd
import requests

from python_bot.data_providers.base_provider import BaseDataProvider

logger = logging.getLogger(__name__)

INTERVAL_MAP: Dict[str, str] = {
    "1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
    "45m": "45min", "1h": "1h", "2h": "2h", "4h": "4h",
    "1d": "1day", "1w": "1week",
}

SYMBOL_MAP: Dict[str, str] = {
    "US30": "DJI",
    "NAS100": "IXIC",
    "SPX500": "SPX",
    "XAUUSD": "XAU/USD",
    "XAGUSD": "XAG/USD",
}


class TwelveDataProvider(BaseDataProvider):
    def __init__(self, api_key: str, rate_limit_pause: float = 8.0, fallback=None):
        self.api_key = api_key
        self.rate_limit_pause = float(rate_limit_pause)
        self.base_url = "https://api.twelvedata.com/time_series"
        self.fallback = fallback
        self._last_call = 0.0

    @property
    def name(self) -> str:
        return "twelvedata"

    def format_symbol(self, symbol: str) -> str:
        upper = symbol.upper()
        if upper in SYMBOL_MAP:
            return SYMBOL_MAP[upper]
        if "/" not in upper and len(upper) == 6:
            return f"{upper[:3]}/{upper[3:]}"
        return upper

    def get_candles(self, symbol: str, timeframe: str, count: int = 300) -> Optional[pd.DataFrame]:
        interval = INTERVAL_MAP.get(timeframe.lower())
        if interval is None:
            logger.error(
                f"[TwelveData] Unsupported timeframe '{timeframe}'. "
                f"Supported: {', '.join(sorted(INTERVAL_MAP))}"
            )
            return None

        params = {
            "symbol": self.format_symbol(symbol),
            "interval": interval,
            # +1 so the still-forming bar can be dropped without losing history.
            "outputsize": int(count) + 1,
            "apikey": self.api_key,
            "timezone": "UTC",
        }

        for attempt in range(1, 4):
            elapsed = time.time() - self._last_call
            if elapsed < self.rate_limit_pause:
                time.sleep(self.rate_limit_pause - elapsed)
            self._last_call = time.time()

            try:
                data = requests.get(self.base_url, params=params, timeout=20).json()
                if "values" in data:
                    return self._to_frame(data["values"], count, timeframe)
                logger.warning(
                    f"[TwelveData] Attempt {attempt}/3 for {symbol}: {data.get('message', 'unknown error')}"
                )
            except Exception as exc:
                logger.warning(f"[TwelveData] Attempt {attempt}/3 for {symbol} raised: {exc}")
            time.sleep(2.0)

        if self.fallback is not None:
            logger.info(f"[TwelveData] Falling back to {self.fallback.name} for {symbol} {timeframe}")
            return self.fallback.get_candles(symbol, timeframe, count)
        return None

    def _to_frame(self, values, count: int, timeframe: str) -> Optional[pd.DataFrame]:
        df = pd.DataFrame(values)
        if df.empty:
            return None
        df["time"] = pd.to_datetime(df["datetime"])
        for column in ("open", "high", "low", "close"):
            df[column] = df[column].astype(float)
        df["volume"] = df["volume"].astype(float) if "volume" in df.columns else 0.0
        df = df.sort_values("time").reset_index(drop=True)

        # TwelveData's newest intraday row is the bar in progress.
        if timeframe.lower() not in ("1d", "1w") and len(df) > 1:
            df = df.iloc[:-1]

        return self.validate(df.tail(count).reset_index(drop=True))
