"""
Strategy package containing BaseStrategy interface and strategy implementations.
"""
from python_bot.strategies.base_strategy import BaseStrategy
from python_bot.strategies.trident_strategy import TridentStrategy

__all__ = ["BaseStrategy", "TridentStrategy"]
