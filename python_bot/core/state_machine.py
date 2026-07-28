import os
import json
import logging
from typing import Dict, Optional, List
from python_bot.models import SymbolState, SymbolContext, FVG

logger = logging.getLogger(__name__)

class StateMachineManager:
    """
    Manages per-symbol state machines and state persistence across restarts.
    """
    def __init__(self, symbols: List[str], persistence_file: str = "bot_state.json"):
        self.persistence_file = persistence_file
        self.contexts: Dict[str, SymbolContext] = {
            sym: SymbolContext(symbol=sym) for sym in symbols
        }
        self.load_state()

    def get_context(self, symbol: str) -> SymbolContext:
        if symbol not in self.contexts:
            self.contexts[symbol] = SymbolContext(symbol=symbol)
        return self.contexts[symbol]

    def set_state(self, symbol: str, new_state: SymbolState, reason: str = ""):
        ctx = self.get_context(symbol)
        if ctx.state != new_state:
            logger.info(f"[{symbol}] State transition: {ctx.state.value} -> {new_state.value} ({reason})")
            ctx.state = new_state
            if reason:
                ctx.last_rejection_reason = reason
            self.save_state()

    def set_active_fvg(self, symbol: str, fvg: Optional[FVG]):
        ctx = self.get_context(symbol)
        ctx.active_fvg = fvg
        self.save_state()

    def reset_symbol(self, symbol: str, reason: str = ""):
        """Resets symbol to WAIT_FOR_DAILY_FILTER or initial state."""
        ctx = self.get_context(symbol)
        logger.info(f"[{symbol}] Resetting state machine ({reason})")
        ctx.state = SymbolState.WAIT_FOR_DAILY_FILTER
        ctx.active_fvg = None
        ctx.doji_candle_time = None
        ctx.doji_high = None
        ctx.confirmation_candle_time = None
        ctx.last_rejection_reason = reason
        self.save_state()

    def save_state(self):
        try:
            data = {sym: ctx.to_dict() for sym, ctx in self.contexts.items()}
            with open(self.persistence_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving state to {self.persistence_file}: {e}")

    def load_state(self):
        if not os.path.exists(self.persistence_file):
            return
        try:
            with open(self.persistence_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            for sym, ctx_dict in data.items():
                self.contexts[sym] = SymbolContext.from_dict(ctx_dict)
            logger.info(f"Successfully loaded state machine context for {len(data)} symbols from {self.persistence_file}")
        except Exception as e:
            logger.error(f"Error loading state from {self.persistence_file}: {e}")
