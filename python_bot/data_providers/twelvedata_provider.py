import time
import logging
import requests
from typing import Optional
import pandas as pd
from datetime import datetime
from python_bot.data_providers.base_provider import BaseDataProvider

logger = logging.getLogger(__name__)

from python_bot.data_providers.yfinance_provider import YFinanceProvider

class TwelveDataProvider(BaseDataProvider):
    """
    TwelveData API adapter for Forex & Precious Metals with automatic retry and YFinance fallback.
    """
    def __init__(self, api_key: str, rate_limit_pause: float = 8.0):
        self.api_key = api_key
        self.rate_limit_pause = rate_limit_pause
        self.base_url = "https://api.twelvedata.com/time_series"
        self.last_call_time = 0.0
        self.fallback_provider = YFinanceProvider()

    @property
    def name(self) -> str:
        return "twelvedata"

    def format_symbol(self, symbol: str) -> str:
        s = symbol.upper()
        if "/" not in s:
            if s == "XAUUSD":
                return "XAU/USD"
            elif len(s) == 6:
                return f"{s[:3]}/{s[3:]}"
        return s

    def map_interval(self, interval: str) -> str:
        inv = interval.lower()
        if inv in ["1d", "daily", "day"]:
            return "1day"
        elif inv in ["30m", "30min"]:
            return "30min"
        return interval

    def get_candles(self, symbol: str, interval: str, outputsize: int = 250) -> Optional[pd.DataFrame]:
        formatted_sym = self.format_symbol(symbol)
        formatted_interval = self.map_interval(interval)

        params = {
            "symbol": formatted_sym,
            "interval": formatted_interval,
            "outputsize": outputsize,
            "apikey": self.api_key,
            "timezone": "UTC"
        }

        # Try TwelveData API up to 3 times
        max_retries = 3
        for attempt in range(1, max_retries + 1):
            now = time.time()
            elapsed = now - self.last_call_time
            if elapsed < self.rate_limit_pause:
                time.sleep(self.rate_limit_pause - elapsed)

            try:
                self.last_call_time = time.time()
                res = requests.get(self.base_url, params=params, timeout=20)
                data = res.json()

                if "values" in data:
                    values = data["values"]
                    df = pd.DataFrame(values)

                    df["datetime"] = pd.to_datetime(df["datetime"])
                    for col in ["open", "high", "low", "close"]:
                        df[col] = df[col].astype(float)
                    if "volume" in df.columns:
                        df["volume"] = df["volume"].astype(float)
                    else:
                        df["volume"] = 0.0

                    df = df.sort_values("datetime").reset_index(drop=True)
                    df = df.rename(columns={"datetime": "time"})
                    return df[["time", "open", "high", "low", "close", "volume"]]
                else:
                    err_msg = data.get("message", "Unknown error")
                    logger.warning(f"[TwelveData] Attempt {attempt}/{max_retries} failed for {symbol}: {err_msg}")

            except Exception as e:
                logger.warning(f"[TwelveData] Attempt {attempt}/{max_retries} timeout/exception for {symbol}: {e}")

            time.sleep(2.0)

        # Fallback to YFinance if TwelveData fails or times out
        logger.info(f"[TwelveData] Falling back to YFinance for {symbol} ({interval})")
        return self.fallback_provider.get_candles(symbol, interval, outputsize)
