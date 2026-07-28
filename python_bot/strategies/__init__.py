"""
Strategy package containing BaseStrategy interface and strategy implementations.
"""
import logging
from typing import Type, Dict, Any
from python_bot.strategies.base_strategy import BaseStrategy
from python_bot.strategies.trident_strategy import TridentStrategy

logger = logging.getLogger(__name__)

STRATEGY_REGISTRY: Dict[str, Type[BaseStrategy]] = {
    "trident_v2": TridentStrategy,
    "trident": TridentStrategy,
}

def register_strategy(name: str, strategy_cls: Type[BaseStrategy]):
    """Registers a new strategy class in the registry."""
    STRATEGY_REGISTRY[name.lower()] = strategy_cls

def get_strategy(
    strategy_name: str,
    risk_manager,
    session_manager,
    strategy_params: Dict[str, Any]
) -> BaseStrategy:
    """
    Factory function to instantiate a strategy by its registered name.
    """
    key = strategy_name.lower()
    if key not in STRATEGY_REGISTRY:
        logger.warning(f"Strategy '{strategy_name}' not found in registry. Defaulting to TridentStrategy.")
        key = "trident_v2"
    
    strategy_cls = STRATEGY_REGISTRY[key]
    
    # Instantiate with parameters if required
    if strategy_cls == TridentStrategy:
        return TridentStrategy(
            risk_manager=risk_manager,
            session_manager=session_manager,
            doji_threshold=strategy_params.get("doji_threshold", 0.10)
        )
    
    return strategy_cls()

__all__ = ["BaseStrategy", "TridentStrategy", "STRATEGY_REGISTRY", "register_strategy", "get_strategy"]

