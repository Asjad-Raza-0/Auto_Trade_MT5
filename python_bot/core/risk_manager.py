"""
Position sizing and risk gates.

Sizing is instrument-agnostic: it uses the broker's own ``tick_size`` and
``tick_value``, so indices (US30), metals (XAUUSD), JPY pairs and ordinary forex
all size correctly with no special cases:

    loss_per_lot = (price_risk / tick_size) * tick_value
    lots         = risk_amount / loss_per_lot     (floored to volume_step)

Flooring — never rounding — guarantees the realised risk is at or under the
requested percentage.
"""
import logging
import math
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

from python_bot.models import SymbolInfo

logger = logging.getLogger(__name__)


@dataclass
class DailyStats:
    """Per-day counters used by the daily risk gates."""
    day: str = ""
    trades: int = 0
    realized_pnl: float = 0.0
    start_balance: float = 0.0

    def to_dict(self) -> Dict[str, float]:
        return {
            "day": self.day,
            "trades": self.trades,
            "realized_pnl": self.realized_pnl,
            "start_balance": self.start_balance,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "DailyStats":
        return cls(
            day=data.get("day", ""),
            trades=int(data.get("trades", 0)),
            realized_pnl=float(data.get("realized_pnl", 0.0)),
            start_balance=float(data.get("start_balance", 0.0)),
        )


class RiskManager:
    """
    All risk decisions live here. ``max_stop_points`` is a per-symbol ceiling on
    the stop distance in *points* (1 point = 1 ``SymbolInfo.point``), with a
    ``"default"`` key as the catch-all.
    """

    def __init__(
        self,
        risk_percent: float = 1.0,
        max_stop_points: Optional[Dict[str, float]] = None,
        max_open_positions: int = 2,
        max_positions_per_symbol: int = 1,
        max_daily_trades: int = 6,
        max_daily_loss_percent: float = 3.0,
        account_balance: float = 10000.0,
        min_risk_reward: float = 0.0,
    ):
        self.risk_percent = float(risk_percent)
        self.max_stop_points = {k.upper(): float(v) for k, v in (max_stop_points or {}).items()}
        self.max_open_positions = int(max_open_positions)
        self.max_positions_per_symbol = int(max_positions_per_symbol)
        self.max_daily_trades = int(max_daily_trades)
        self.max_daily_loss_percent = float(max_daily_loss_percent)
        self.account_balance = float(account_balance)
        self.min_risk_reward = float(min_risk_reward)
        self.daily = DailyStats(day=str(date.today()), start_balance=float(account_balance))

    # ------------------------------------------------------------------ balance
    def set_account_balance(self, balance: float) -> None:
        """Called every cycle with the live broker balance."""
        if balance and balance > 0:
            self.account_balance = float(balance)
            if self.daily.start_balance <= 0:
                self.daily.start_balance = float(balance)

    @property
    def risk_amount(self) -> float:
        return self.account_balance * (self.risk_percent / 100.0)

    # ------------------------------------------------------------- distance
    def stop_distance_points(self, entry: float, stop_loss: float, info: SymbolInfo) -> float:
        point = info.point if info and info.point > 0 else 0.00001
        return abs(entry - stop_loss) / point

    def max_points_for(self, symbol: str) -> Optional[float]:
        limit = self.max_stop_points.get(symbol.upper())
        if limit is None:
            limit = self.max_stop_points.get("DEFAULT")
        return limit

    def validate_stop(
        self, symbol: str, entry: float, stop_loss: float, info: SymbolInfo
    ) -> Tuple[bool, str]:
        if entry <= 0 or stop_loss <= 0:
            return False, f"invalid prices (entry {entry}, stop {stop_loss})"
        if abs(entry - stop_loss) <= 0:
            return False, "stop loss equals entry price"

        points = self.stop_distance_points(entry, stop_loss, info)

        broker_min = info.stops_level_points if info else 0.0
        if broker_min > 0 and points < broker_min:
            return False, (
                f"stop distance {points:.0f} points is below the broker minimum "
                f"({broker_min:.0f} points) — the order would be rejected"
            )

        limit = self.max_points_for(symbol)
        if limit is not None and points > limit:
            return False, (
                f"stop distance {points:.0f} points exceeds the {symbol} limit of {limit:.0f} points"
            )

        return True, f"stop distance {points:.0f} points OK"

    # ------------------------------------------------------------------ sizing
    def calculate_lots(
        self, symbol: str, entry: float, stop_loss: float, info: SymbolInfo
    ) -> Tuple[float, str]:
        """Returns (lots, reason). ``lots == 0`` means do not trade."""
        valid, message = self.validate_stop(symbol, entry, stop_loss, info)
        if not valid:
            return 0.0, message

        if info is None or info.tick_size <= 0 or info.tick_value <= 0:
            return 0.0, (
                f"missing contract specs for {symbol} "
                f"(tick_size/tick_value) — cannot size the position safely"
            )

        price_risk = abs(entry - stop_loss)
        loss_per_lot = (price_risk / info.tick_size) * info.tick_value
        if loss_per_lot <= 0:
            return 0.0, "computed loss-per-lot is zero"

        raw_lots = self.risk_amount / loss_per_lot

        step = info.volume_step if info.volume_step > 0 else 0.01
        steps = math.floor(round(raw_lots / step, 8))
        lots = round(steps * step, 8)

        if lots < info.volume_min:
            return 0.0, (
                f"risking {self.risk_percent:.2f}% ({self.risk_amount:.2f}) over a "
                f"{price_risk:.5f} stop needs {raw_lots:.4f} lots, below the "
                f"{info.volume_min} minimum — trade skipped rather than over-risked"
            )
        if lots > info.volume_max:
            lots = info.volume_max

        actual_risk = lots * loss_per_lot
        return lots, (
            f"{lots} lots (risking {actual_risk:.2f} = "
            f"{actual_risk / self.account_balance * 100:.2f}% of {self.account_balance:.2f})"
        )

    def validate_risk_reward(self, entry: float, stop_loss: float, take_profit: float) -> Tuple[bool, str]:
        risk = abs(entry - stop_loss)
        if risk <= 0:
            return False, "zero risk distance"
        rr = abs(take_profit - entry) / risk
        if self.min_risk_reward > 0 and rr < self.min_risk_reward:
            return False, f"risk:reward {rr:.2f} is below the {self.min_risk_reward:.2f} minimum"
        return True, f"risk:reward {rr:.2f}"

    # ------------------------------------------------------------- daily gates
    def roll_day(self, today: Optional[str] = None) -> bool:
        """Reset the daily counters when the date changes. Returns True if rolled."""
        today = today or str(date.today())
        if self.daily.day == today:
            return False
        logger.info(
            f"[Risk] New trading day {today} — resetting daily counters "
            f"(previous: {self.daily.trades} trades, {self.daily.realized_pnl:+.2f} P/L)"
        )
        self.daily = DailyStats(day=today, start_balance=self.account_balance)
        return True

    def record_trade_opened(self) -> None:
        self.daily.trades += 1

    def record_trade_closed(self, profit: float) -> None:
        self.daily.realized_pnl += float(profit)

    def check_can_trade(
        self, symbol: str, open_positions_total: int, open_positions_symbol: int
    ) -> Tuple[bool, str]:
        """Every gate that must pass before a new position is allowed."""
        if self.max_positions_per_symbol > 0 and open_positions_symbol >= self.max_positions_per_symbol:
            return False, (
                f"{symbol} already has {open_positions_symbol} open position(s) "
                f"(max {self.max_positions_per_symbol})"
            )
        if self.max_open_positions > 0 and open_positions_total >= self.max_open_positions:
            return False, (
                f"{open_positions_total} positions open across all symbols "
                f"(max {self.max_open_positions})"
            )
        if self.max_daily_trades > 0 and self.daily.trades >= self.max_daily_trades:
            return False, (
                f"daily trade limit reached ({self.daily.trades}/{self.max_daily_trades})"
            )
        if self.max_daily_loss_percent > 0 and self.daily.start_balance > 0:
            loss_percent = -self.daily.realized_pnl / self.daily.start_balance * 100.0
            if loss_percent >= self.max_daily_loss_percent:
                return False, (
                    f"daily loss limit hit ({loss_percent:.2f}% >= "
                    f"{self.max_daily_loss_percent:.2f}%) — trading halted until tomorrow"
                )
        return True, "risk gates passed"

    def describe(self) -> Dict[str, object]:
        return {
            "risk_percent": self.risk_percent,
            "account_balance": self.account_balance,
            "risk_amount": round(self.risk_amount, 2),
            "max_open_positions": self.max_open_positions,
            "max_positions_per_symbol": self.max_positions_per_symbol,
            "max_daily_trades": self.max_daily_trades,
            "max_daily_loss_percent": self.max_daily_loss_percent,
            "max_stop_points": self.max_stop_points,
            "today": self.daily.to_dict(),
        }
