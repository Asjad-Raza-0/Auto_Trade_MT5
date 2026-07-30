"""
Broker abstraction — the only place that knows how orders reach a trading venue.

Swapping MetaTrader 5 for another venue means writing one subclass of
``BaseBroker`` and registering it in ``python_bot/brokers/__init__.py``. No
strategy, engine or notifier code changes.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional

import pandas as pd

from python_bot.models import (
    AccountInfo,
    BrokerPosition,
    ClosedDeal,
    Direction,
    OrderResult,
    SymbolInfo,
)


class BaseBroker(ABC):
    """
    A broker is both an execution venue and (usually) a price source, because the
    prices used for decisions must come from the venue that fills the orders.
    """

    # -------------------------------------------------------------- lifecycle
    @property
    @abstractmethod
    def name(self) -> str:
        """Registry key, e.g. "mt5"."""

    @abstractmethod
    def connect(self) -> bool:
        """Establish the connection. Returns True on success."""

    @abstractmethod
    def disconnect(self) -> None:
        """Tear the connection down."""

    @property
    @abstractmethod
    def is_connected(self) -> bool: ...

    # ------------------------------------------------------------ account info
    @abstractmethod
    def get_account(self) -> Optional[AccountInfo]: ...

    @abstractmethod
    def list_symbols(self) -> List[str]:
        """Every symbol name the account can see (used for fuzzy resolution)."""

    @abstractmethod
    def get_symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        """Contract specs for one broker symbol name."""

    # -------------------------------------------------------------- price data
    @abstractmethod
    def get_candles(self, symbol: str, timeframe: str, count: int) -> Optional[pd.DataFrame]:
        """
        COMPLETED candles only, oldest first, columns
        ``time, open, high, low, close, volume``.
        """

    @abstractmethod
    def get_current_price(self, symbol: str, direction: Direction = Direction.NONE) -> float:
        """Ask for a LONG entry, bid for a SHORT entry, mid for NONE."""

    # ---------------------------------------------------------------- trading
    @abstractmethod
    def get_open_positions(
        self, symbol: Optional[str] = None, magic: Optional[int] = None
    ) -> List[BrokerPosition]: ...

    @abstractmethod
    def place_market_order(
        self,
        symbol: str,
        direction: Direction,
        lots: float,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        comment: str = "",
        magic: int = 0,
    ) -> OrderResult: ...

    @abstractmethod
    def modify_position(
        self, ticket: int, stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> OrderResult: ...

    @abstractmethod
    def close_position(self, ticket: int, volume: Optional[float] = None) -> OrderResult:
        """Close ``volume`` lots (all of it when volume is None)."""

    @abstractmethod
    def get_closed_deals(self, since: datetime) -> List[ClosedDeal]:
        """Closing deals since ``since`` — used to classify exits as TP / SL / other."""

    # ---------------------------------------------------------------- helpers
    def normalize_volume(self, symbol: str, lots: float) -> float:
        """Round ``lots`` DOWN to the broker's volume step and clamp to min/max."""
        info = self.get_symbol_info(symbol)
        if info is None:
            return round(lots, 2)
        step = info.volume_step if info.volume_step > 0 else 0.01
        steps = int((lots + 1e-9) / step)
        normalized = round(steps * step, 8)
        if normalized < info.volume_min:
            return 0.0
        return round(min(normalized, info.volume_max), 8)

    def __enter__(self) -> "BaseBroker":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.disconnect()
