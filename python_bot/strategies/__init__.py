"""
Strategy registry — the single place the bot learns that a strategy exists.

ADDING A STRATEGY (2 steps, no other file needs to change):

    1. Create ``python_bot/strategies/my_strategy.py`` with a class that subclasses
       ``BaseStrategy`` and takes a single ``params`` dict:

           class MyStrategy(BaseStrategy):
               def __init__(self, params=None):
                   super().__init__(params)
                   self.threshold = self.p("threshold", 1.5)

               @property
               def name(self): return "my_strategy"

               @property
               def required_timeframes(self): return {"htf": "1h", "ltf": "5m"}

               def evaluate(self, symbol, data, context):
                   return None, "no setup"

    2. Register it below, then set ``"strategy_name": "my_strategy"`` in
       ``config.json`` and put its tunables under ``strategy_parameters``.

Because every strategy is constructed as ``cls(strategy_parameters)``, the
factory never needs per-strategy special cases.
"""
import logging
from typing import Any, Dict, List, Optional, Type

from python_bot.strategies.base_strategy import BaseStrategy
from python_bot.strategies.scalp_1m_strategy import OneMinuteScalpStrategy

logger = logging.getLogger(__name__)

STRATEGY_REGISTRY: Dict[str, Type[BaseStrategy]] = {}

DEFAULT_STRATEGY = "scalp_1m_v1"


def register_strategy(name: str, strategy_cls: Type[BaseStrategy]) -> None:
    """Register (or override) a strategy under ``name``. Case-insensitive."""
    if not issubclass(strategy_cls, BaseStrategy):
        raise TypeError(f"{strategy_cls!r} must subclass BaseStrategy")
    STRATEGY_REGISTRY[name.strip().lower()] = strategy_cls


def available_strategies() -> List[str]:
    return sorted(STRATEGY_REGISTRY.keys())


def get_strategy(
    strategy_name: str,
    strategy_params: Optional[Dict[str, Any]] = None,
) -> BaseStrategy:
    """
    Build a strategy by registry name. Raises ``KeyError`` for unknown names —
    silently falling back to a different strategy on a live trading account would
    be far worse than refusing to start.
    """
    key = (strategy_name or "").strip().lower()
    if key not in STRATEGY_REGISTRY:
        raise KeyError(
            f"Unknown strategy '{strategy_name}'. Registered: {', '.join(available_strategies())}. "
            f"Add it in python_bot/strategies/__init__.py via register_strategy()."
        )
    return STRATEGY_REGISTRY[key](strategy_params or {})


# --- registrations ---------------------------------------------------------
register_strategy("scalp_1m_v1", OneMinuteScalpStrategy)
register_strategy("scalp_1m", OneMinuteScalpStrategy)          # convenience alias
register_strategy("structure_scalper", OneMinuteScalpStrategy)  # convenience alias

__all__ = [
    "BaseStrategy",
    "OneMinuteScalpStrategy",
    "STRATEGY_REGISTRY",
    "DEFAULT_STRATEGY",
    "register_strategy",
    "available_strategies",
    "get_strategy",
]
