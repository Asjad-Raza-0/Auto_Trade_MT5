import time
import logging
import requests
from typing import Optional
import pandas as pd
from datetime import datetime
from python_bot.data_providers.base_provider import BaseDataProvider

logger = logging.getLogger(__name__)

class TwelveDataProvider(BaseDataProvider):
    """
    TwelveData API adapter for Forex & Precious Metals.
    """
    def __init__(self, api_key: str, rate_limit_pause: float = 8.0):
        self.api_key = api_key
        self.rate_limit_pause = rate_limit_pause
        self.base_url = "https://api.twelvedata.com/time_series"
        self.last_call_time = 0.0

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
        # Rate limit control (free tier = 8 calls/min)
        now = time.time()
        elapsed = now - self.last_call_time
        if elapsed < self.rate_limit_pause:
            time.sleep(self.rate_limit_pause - elapsed)

        formatted_sym = self.format_symbol(symbol)
        formatted_interval = self.map_interval(interval)

        params = {
            "symbol": formatted_sym,
            "interval": formatted_interval,
            "outputsize": outputsize,
            "apikey": self.api_key,
            "timezone": "UTC"
        }

        try:
            self.last_call_time = time.time()
            res = requests.get(self.base_url, params=params, timeout=10)
            data = res.json()

            if "values" not in data:
                err_msg = data.get("message", "Unknown error")
                logger.error(f"[TwelveData] Error fetching {symbol} ({interval}): {err_msg}")
                return None

            values = data["values"]
            df = pd.DataFrame(values)

            df["datetime"] = pd.to_datetime(df["datetime"])
            for col in ["open", "high", "low", "close"]:
                df[col] = df[col].astype(float)
            if "volume" in df.columns:
                df["volume"] = df["volume"].astype(float)
            else:
                df["volume"] = 0.0

            # Sort ascending by time
            df = df.sort_values("datetime").reset_index(drop=True)
            df = df.rename(columns={"datetime": "time"})

            return df[["time", "open", "high", "low", "close", "volume"]]

        except Exception as e:
            logger.error(f"[TwelveData] Request exception for {symbol}: {e}")
            return None
