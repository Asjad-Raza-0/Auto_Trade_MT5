import logging
from typing import Optional, Dict
import pandas as pd
import yfinance as yf
from python_bot.data_providers.base_provider import BaseDataProvider

logger = logging.getLogger(__name__)

DEFAULT_MAPPING = {
    "XAUUSD": "GC=F",
    "EURUSD": "EURUSD=X",
    "USDJPY": "JPY=X",
    "GBPUSD": "GBPUSD=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "CAD=X",
    "USDCHF": "CHF=X",
    "EURGBP": "EURGBP=X"
}

class YFinanceProvider(BaseDataProvider):
    """
    Zero-cost yfinance data adapter fallback.
    Does not require an API key.
    """
    def __init__(self, symbol_mapping: Optional[Dict[str, str]] = None):
        self.mapping = symbol_mapping or DEFAULT_MAPPING

    @property
    def name(self) -> str:
        return "yfinance"

    def get_candles(self, symbol: str, interval: str, outputsize: int = 250) -> Optional[pd.DataFrame]:
        yf_symbol = self.mapping.get(symbol.upper(), f"{symbol.upper()}=X")
        yf_interval = "1d" if interval.lower() in ["1d", "daily"] else "30m"
        period = "60d" if yf_interval == "30m" else "1y"

        try:
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(period=period, interval=yf_interval)

            if df.empty:
                logger.error(f"[YFinance] Empty response for {symbol} ({yf_symbol})")
                return None

            df = df.reset_index()
            # Map columns
            time_col = "Date" if "Date" in df.columns else "Datetime"
            df = df.rename(columns={
                time_col: "time",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume"
            })

            df["time"] = pd.to_datetime(df["time"]).dt.tz_localize(None)
            df = df.sort_values("time").reset_index(drop=True)
            return df[["time", "open", "high", "low", "close", "volume"]].tail(outputsize)

        except Exception as e:
            logger.error(f"[YFinance] Error fetching {symbol}: {e}")
            return None
