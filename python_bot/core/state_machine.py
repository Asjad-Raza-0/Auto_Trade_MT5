"""
Per-symbol context store with JSON persistence.

The bot must survive a restart mid-trade: open positions, daily counters and the
strategy's own scratchpad all round-trip through ``bot_state.json``. Writes are
atomic (temp file + replace) so a crash during a write cannot leave a truncated
state file behind.
"""
import json
import logging
import os
from datetime import date
from typing import Dict, List, Optional

from python_bot.models import SymbolContext, SymbolState

logger = logging.getLogger(__name__)


class StateMachineManager:
    def __init__(self, symbols: List[str], persistence_file: str = "bot_state.json"):
        self.persistence_file = persistence_file
        self.contexts: Dict[str, SymbolContext] = {
            symbol: SymbolContext(symbol=symbol) for symbol in symbols
        }
        self.meta: Dict[str, object] = {}
        self.load_state()

    # ------------------------------------------------------------------ access
    def get_context(self, symbol: str) -> SymbolContext:
        if symbol not in self.contexts:
            self.contexts[symbol] = SymbolContext(symbol=symbol)
        return self.contexts[symbol]

    def set_state(self, symbol: str, new_state: SymbolState, reason: str = "") -> None:
        context = self.get_context(symbol)
        if context.state is not new_state:
            logger.info(
                f"[{symbol}] {context.state.value} -> {new_state.value}"
                + (f" ({reason})" if reason else "")
            )
            context.state = new_state
        if reason:
            context.last_rejection_reason = reason

    def reset_symbol(self, symbol: str, reason: str = "") -> None:
        """Clear setup progress. Deliberately does NOT clear an open position."""
        context = self.get_context(symbol)
        context.state = SymbolState.SCANNING
        context.strategy_data = {}
        context.last_rejection_reason = reason
        logger.info(f"[{symbol}] Context reset ({reason})")

    def open_position_count(self) -> int:
        return sum(1 for c in self.contexts.values() if c.position is not None)

    def positions_for(self, symbol: str) -> int:
        context = self.contexts.get(symbol)
        return 1 if context is not None and context.position is not None else 0

    def roll_day(self, today: Optional[str] = None) -> bool:
        """Reset per-symbol daily counters on a date change."""
        today = today or str(date.today())
        rolled = False
        for context in self.contexts.values():
            if context.trading_day != today:
                context.trading_day = today
                context.trades_today = 0
                context.realized_pnl_today = 0.0
                rolled = True
        return rolled

    # ------------------------------------------------------------- persistence
    def save_state(self) -> None:
        payload = {
            "meta": self.meta,
            "symbols": {symbol: ctx.to_dict() for symbol, ctx in self.contexts.items()},
        }
        temp_path = f"{self.persistence_file}.tmp"
        try:
            with open(temp_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, default=str)
            os.replace(temp_path, self.persistence_file)
        except Exception as exc:
            logger.error(f"Could not save state to {self.persistence_file}: {exc}")
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def load_state(self) -> None:
        if not os.path.exists(self.persistence_file):
            return
        try:
            with open(self.persistence_file, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception as exc:
            logger.error(
                f"Could not load state from {self.persistence_file}: {exc}. "
                f"Starting from a clean state — open positions will be re-adopted from the broker."
            )
            return

        self.meta = payload.get("meta", {}) or {}
        symbols = payload.get("symbols", payload)  # tolerate the older flat layout
        restored = 0
        for symbol, data in symbols.items():
            if not isinstance(data, dict) or "symbol" not in data:
                continue
            try:
                self.contexts[symbol] = SymbolContext.from_dict(data)
                restored += 1
            except Exception as exc:
                logger.error(f"Could not restore state for {symbol}: {exc}")

        open_positions = self.open_position_count()
        logger.info(
            f"Restored state for {restored} symbol(s) from {self.persistence_file}"
            + (f" — {open_positions} open position(s) still tracked" if open_positions else "")
        )

    def summary(self) -> Dict[str, object]:
        return {
            symbol: {
                "state": ctx.state.value,
                "broker_symbol": ctx.broker_symbol,
                "position": ctx.position.to_dict() if ctx.position else None,
                "trades_today": ctx.trades_today,
                "realized_pnl_today": round(ctx.realized_pnl_today, 2),
                "last_reason": ctx.last_rejection_reason,
            }
            for symbol, ctx in self.contexts.items()
        }
