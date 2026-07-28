from abc import ABC, abstractmethod
from typing import Optional
import pandas as pd

class BaseDataProvider(ABC):
    """
    Abstract Interface for Market Data Providers.
    Supports pluggable data feeds (TwelveData, YFinance, MetaTrader 5, Mock, Broker REST APIs).
    """
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def get_candles(self, symbol: str, interval: str, outputsize: int = 250) -> Optional[pd.DataFrame]:
        """
        Fetches historical candles for a symbol and interval.
        Intervals: '1d', '30m', etc.
        Returns a DataFrame with columns: ['time', 'open', 'high', 'low', 'close', 'volume'].
        """
        pass
