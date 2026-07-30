"""
YFinance provider — zero-cost fallback / offline research source.

LIMITS YOU MUST KNOW BEFORE USING THIS FOR 1-MINUTE DATA:
  * 1m history is capped at ~7 days and is delayed.
  * Index and metal quotes are futures proxies (``^DJI``, ``GC=F``), so their
    prices differ from your broker's CFD by a non-trivial offset.
Use it for research and smoke tests; use the broker feed for live trading.
"""
import logging
from typing import Dict, Optional

import pandas as pd

from python_bot.data_providers.base_provider import BaseDataProvider

logger = logging.getLogger(__name__)

DEFAULT_MAPPING = {
    "US30": "^DJI",
    "NAS100": "^NDX",
    "SPX500": "^GSPC",
    "GER40": "^GDAXI",
    "UK100": "^FTSE",
    "JP225": "^N225",
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
    "USOIL": "CL=F",
    "BTCUSD": "BTC-USD",
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "JPY=X",
    "AUDUSD": "AUDUSD=X",
    "USDCAD": "CAD=X",
    "USDCHF": "CHF=X",
    "EURGBP": "EURGBP=X",
}

# timeframe -> (yfinance interval, max period yfinance allows for it)
INTERVAL_MAP: Dict[str, tuple] = {
    "1m": ("1m", "7d"),
    "2m": ("2m", "60d"),
    "5m": ("5m", "60d"),
    "15m": ("15m", "60d"),
    "30m": ("30m", "60d"),
    "1h": ("1h", "730d"),
    "1d": ("1d", "5y"),
    "1w": ("1wk", "10y"),
}


class YFinanceProvider(BaseDataProvider):
    def __init__(self, symbol_mapping: Optional[Dict[str, str]] = None):
        self.mapping = {**DEFAULT_MAPPING, **(symbol_mapping or {})}

    @property
    def name(self) -> str:
        return "yfinance"

    def get_candles(self, symbol: str, timeframe: str, count: int = 300) -> Optional[pd.DataFrame]:
        mapped = self.mapping.get(symbol.upper())
        if mapped is None:
            logger.error(
                f"[YFinance] No ticker mapping for '{symbol}'. "
                f"Add one under config.json -> yfinance.symbol_mapping."
            )
            return None

        entry = INTERVAL_MAP.get(timeframe.lower())
        if entry is None:
            logger.error(
                f"[YFinance] Unsupported timeframe '{timeframe}'. "
                f"Supported: {', '.join(sorted(INTERVAL_MAP))}"
            )
            return None
        interval, period = entry

        try:
            import yfinance as yf
        except ImportError:
            logger.error("[YFinance] yfinance is not installed (`pip install yfinance`).")
            return None

        try:
            df = yf.Ticker(mapped).history(period=period, interval=interval)
            if df is None or df.empty:
                logger.error(f"[YFinance] Empty response for {symbol} ({mapped} {interval})")
                return None

            df = df.reset_index()
            time_col = "Datetime" if "Datetime" in df.columns else "Date"
            df = df.rename(columns={
                time_col: "time", "Open": "open", "High": "high",
                "Low": "low", "Close": "close", "Volume": "volume",
            })
            df["time"] = pd.to_datetime(df["time"], utc=True).dt.tz_localize(None)
            df = df.sort_values("time").reset_index(drop=True)

            # Drop the still-forming bar: yfinance includes it for intraday intervals.
            if interval != "1d" and len(df) > 1:
                df = df.iloc[:-1]

            return self.validate(df.tail(count).reset_index(drop=True))
        except Exception as exc:
            logger.error(f"[YFinance] Error fetching {symbol} ({mapped}): {exc}")
            return None
