from abc import ABC, abstractmethod
from typing import Optional, Tuple, Dict, Any, List
import pandas as pd
from python_bot.models import TradeSignal, SymbolContext

class BaseStrategy(ABC):
    """
    Abstract Base Class for all trading strategies.
    Any new strategy (e.g. ICT Silver Bullet, RSI Mean Reversion, Breakout)
    can be implemented by subclassing BaseStrategy and overriding these methods.
    """
    @property
    @abstractmethod
    def name(self) -> str:
        """Strategy unique identifier name."""
        pass

    @abstractmethod
    def evaluate_daily_filter(self, symbol: str, df_daily: pd.DataFrame) -> Tuple[bool, str]:
        """
        Evaluates higher timeframe (Daily) trend filters on completed candles.
        Returns (is_valid, reason).
        """
        pass

    @abstractmethod
    def evaluate_signal(
        self,
        symbol: str,
        df_daily: pd.DataFrame,
        df_m30: pd.DataFrame,
        context: SymbolContext
    ) -> Tuple[Optional[TradeSignal], str]:
        """
        Evaluates execution timeframe (M30) setup pattern.
        Returns (TradeSignal object if setup valid else None, status_reason).
        """
        pass
