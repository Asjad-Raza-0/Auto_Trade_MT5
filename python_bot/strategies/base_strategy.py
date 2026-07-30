"""
The plug-and-play strategy contract.

A strategy declares WHICH timeframes it needs, then answers two questions:
  1. ``evaluate()``        -> should I open a trade on the latest completed bar?
  2. ``manage_position()`` -> what should I do with the trade I already have?

Everything else (data fetching, symbol resolution, lot sizing, order execution,
persistence, notifications) is the engine's job and is identical for every
strategy. That is the whole point of this interface: swapping the strategy must
never require touching the engine, broker, or notifier layers.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from python_bot.models import ManagementAction, Position, SymbolContext, TradeSignal


class BaseStrategy(ABC):
    """
    Abstract base class for all strategies.

    Timeframe roles
    ---------------
    ``required_timeframes`` maps a *role name* you choose to a timeframe string
    ("1m", "5m", "15m", "30m", "1h", "4h", "1d"). The engine fetches each one and
    hands them to you in ``data``, keyed by role:

        required_timeframes = {"htf": "5m", "ltf": "1m"}
        # -> evaluate(symbol, {"htf": df_5m, "ltf": df_1m}, context)

    Data contract
    -------------
    Every DataFrame contains ONLY COMPLETED candles, oldest first, with columns
    ``time, open, high, low, close, volume``. ``df.iloc[-1]`` is therefore always
    the most recently closed bar — never a partially formed one.

    Call schedule
    -------------
    The engine calls ``evaluate()`` and ``manage_position()`` once per NEW
    completed bar of the *shortest* required timeframe, not once per scan cycle.
    Position closures (TP/SL) are detected every cycle by the engine itself, so
    alerts stay prompt regardless.

    Construction
    -------------
    Every strategy MUST accept a single ``params`` dict so the registry can build
    any strategy uniformly from ``config.json -> strategy_parameters``:

        def __init__(self, params=None):
            super().__init__(params)
            self.my_setting = self.p("my_setting", 1.5)
    """

    def __init__(self, params: Optional[Dict[str, Any]] = None):
        self.params: Dict[str, Any] = dict(params or {})

    def p(self, key: str, default: Any) -> Any:
        """
        Read a parameter with the type of ``default`` enforced. Keeps JSON config
        values (which arrive as str/int) from leaking wrong types into maths.
        """
        value = self.params.get(key, default)
        if value is None:
            return default
        try:
            if isinstance(default, bool):
                if isinstance(value, str):
                    return value.strip().lower() in ("1", "true", "yes", "on")
                return bool(value)
            if isinstance(default, int) and not isinstance(default, bool):
                return int(value)
            if isinstance(default, float):
                return float(value)
        except (TypeError, ValueError):
            return default
        return value

    # ---------------------------------------------------------------- identity
    @property
    @abstractmethod
    def name(self) -> str:
        """Unique registry key, e.g. "scalp_1m_v1"."""

    @property
    def display_name(self) -> str:
        """Human-readable name used in alerts. Override for nicer messages."""
        return self.name

    # -------------------------------------------------------------- data needs
    @property
    @abstractmethod
    def required_timeframes(self) -> Dict[str, str]:
        """Role -> timeframe string, e.g. ``{"htf": "5m", "ltf": "1m"}``."""

    @property
    def warmup_bars(self) -> Dict[str, int]:
        """
        Role -> how many completed bars to fetch. Roles missing from this dict
        default to 300.
        """
        return {}

    def bars_for(self, role: str) -> int:
        return int(self.warmup_bars.get(role, 300))

    # ---------------------------------------------------------------- decision
    @abstractmethod
    def evaluate(
        self,
        symbol: str,
        data: Dict[str, pd.DataFrame],
        context: SymbolContext,
    ) -> Tuple[Optional[TradeSignal], str]:
        """
        Decide whether the latest completed bar produces an entry.

        Return ``(signal, reason)``. ``signal`` is None when there is no trade;
        ``reason`` is always a human-readable explanation and is logged verbatim,
        so make it specific — it is the primary debugging tool for a live bot.

        Leave ``signal.calculated_lots`` at 0: the engine sizes the position via
        the RiskManager using live broker contract specs.
        """

    def manage_position(
        self,
        symbol: str,
        data: Dict[str, pd.DataFrame],
        context: SymbolContext,
        position: Position,
    ) -> List[ManagementAction]:
        """
        Return actions to apply to an open position (move stop, bank a partial,
        close early, scale in). Default: do nothing — the broker's server-side
        SL/TP handles the trade.
        """
        return []

    # ------------------------------------------------------------------ hooks
    def on_position_closed(
        self,
        symbol: str,
        context: SymbolContext,
        position: Position,
        reason: str,
    ) -> None:
        """Optional hook for cleanup / cooldown bookkeeping after an exit."""

    def describe(self) -> Dict[str, Any]:
        """Summary used by ``--status`` and startup logs."""
        return {
            "name": self.name,
            "display_name": self.display_name,
            "timeframes": self.required_timeframes,
            "warmup_bars": {role: self.bars_for(role) for role in self.required_timeframes},
        }
