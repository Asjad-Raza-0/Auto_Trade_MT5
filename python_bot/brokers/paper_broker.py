"""
Simulated broker — used by ``--dry-run`` and by the whole test suite.

It implements the same ``BaseBroker`` contract as ``MT5Broker`` but fills orders
against candle data instead of a real venue, so the engine, risk manager,
position manager and notifiers can all be exercised on any OS with no MetaTrader
installation.

Exit simulation is intentionally pessimistic: when a bar's range covers both the
stop and the target, the STOP is taken. Never let a backtest flatter you.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd

from python_bot.brokers.base_broker import BaseBroker
from python_bot.models import (
    AccountInfo,
    BrokerPosition,
    ClosedDeal,
    Direction,
    OrderResult,
    SymbolInfo,
)

logger = logging.getLogger(__name__)

# Sensible contract specs per instrument class, used when nothing better is known.
# tick_value = account-currency P/L for 1.0 lot moving 1 tick.
FALLBACK_SPECS: Dict[str, Dict[str, float]] = {
    "INDEX": {"digits": 2, "tick_size": 0.01, "tick_value": 0.01, "contract_size": 1.0},
    "GOLD":  {"digits": 2, "tick_size": 0.01, "tick_value": 1.00, "contract_size": 100.0},
    "JPY":   {"digits": 3, "tick_size": 0.001, "tick_value": 1.00, "contract_size": 100000.0},
    "FOREX": {"digits": 5, "tick_size": 0.00001, "tick_value": 1.00, "contract_size": 100000.0},
    "CRYPTO": {"digits": 2, "tick_size": 0.01, "tick_value": 0.01, "contract_size": 1.0},
}

INDEX_TOKENS = ("US30", "DJI", "DJ30", "WS30", "NAS", "US100", "USTEC", "SPX", "US500",
                "GER", "DAX", "DE40", "UK100", "FTSE", "JP225", "NIKKEI")
CRYPTO_TOKENS = ("BTC", "ETH", "XRP", "SOL", "LTC", "DOGE")


def classify_instrument(symbol: str) -> str:
    """Best-effort instrument class from the symbol name."""
    upper = (symbol or "").upper()
    if any(token in upper for token in INDEX_TOKENS):
        return "INDEX"
    if "XAU" in upper or "GOLD" in upper:
        return "GOLD"
    if any(token in upper for token in CRYPTO_TOKENS):
        return "CRYPTO"
    if "JPY" in upper:
        return "JPY"
    return "FOREX"


def default_symbol_info(symbol: str) -> SymbolInfo:
    spec = FALLBACK_SPECS[classify_instrument(symbol)]
    return SymbolInfo(
        name=symbol,
        digits=int(spec["digits"]),
        point=spec["tick_size"],
        tick_size=spec["tick_size"],
        tick_value=spec["tick_value"],
        volume_min=0.01,
        volume_step=0.01,
        volume_max=100.0,
        stops_level_points=0.0,
        contract_size=spec["contract_size"],
        tradable=True,
    )


class PaperBroker(BaseBroker):
    """
    In-memory broker.

    Price sources, in priority order:
      1. candles injected with ``set_candles(symbol, timeframe, df)`` (tests)
      2. a ``BaseDataProvider`` passed as ``data_provider`` (``--dry-run``)
    """

    def __init__(
        self,
        balance: float = 10000.0,
        currency: str = "USD",
        data_provider=None,
        magic_number: int = 250730,
        exit_check_timeframe: str = "1m",
        spread_ticks: float = 0.0,
        symbols: Optional[List[str]] = None,
    ):
        self.balance = float(balance)
        self.starting_balance = float(balance)
        self.currency = currency
        self.data_provider = data_provider
        self.magic_number = int(magic_number)
        self.exit_check_timeframe = exit_check_timeframe
        self.spread_ticks = float(spread_ticks)

        self._connected = False
        self._next_ticket = 1000
        self._positions: Dict[int, BrokerPosition] = {}
        self._deals: List[ClosedDeal] = []
        self._candles: Dict[Tuple[str, str], pd.DataFrame] = {}
        self._symbol_info: Dict[str, SymbolInfo] = {}
        self._prices: Dict[str, float] = {}
        self._last_exit_bar: Dict[int, datetime] = {}

        # Pre-register the configured symbols so list_symbols() offers them
        # before any candle has been injected or fetched.
        for symbol in symbols or []:
            self._symbol_info[symbol] = default_symbol_info(symbol)

    # -------------------------------------------------------------- lifecycle
    @property
    def name(self) -> str:
        return "paper"

    def connect(self) -> bool:
        self._connected = True
        logger.info(
            f"[Paper] Simulated broker connected — balance {self.balance:.2f} {self.currency}. "
            f"NO REAL ORDERS WILL BE PLACED."
        )
        return True

    def disconnect(self) -> None:
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------- test setup
    def set_candles(self, symbol: str, timeframe: str, df: pd.DataFrame) -> None:
        self._candles[(symbol, timeframe)] = df.reset_index(drop=True)
        if len(df):
            self._prices[symbol] = float(df["close"].iloc[-1])

    def set_symbol_info(self, symbol: str, info: SymbolInfo) -> None:
        self._symbol_info[symbol] = info

    def set_price(self, symbol: str, price: float) -> None:
        self._prices[symbol] = float(price)

    # ------------------------------------------------------------ account info
    def get_account(self) -> Optional[AccountInfo]:
        floating = sum(self._floating_profit(p) for p in self._positions.values())
        return AccountInfo(
            login=0,
            balance=self.balance,
            equity=self.balance + floating,
            margin_free=self.balance + floating,
            currency=self.currency,
            leverage=100,
            server="paper",
            name="Paper Trading",
            is_demo=True,
        )

    def list_symbols(self) -> List[str]:
        names = {symbol for symbol, _ in self._candles}
        names.update(self._symbol_info)
        names.update(self._prices)
        return sorted(names)

    def get_symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        if symbol not in self._symbol_info:
            self._symbol_info[symbol] = default_symbol_info(symbol)
        return self._symbol_info[symbol]

    # -------------------------------------------------------------- price data
    def get_candles(self, symbol: str, timeframe: str, count: int) -> Optional[pd.DataFrame]:
        key = (symbol, timeframe)
        if key in self._candles:
            df = self._candles[key]
            return df.tail(count).reset_index(drop=True)
        if self.data_provider is not None:
            df = self.data_provider.get_candles(symbol, timeframe, count)
            if df is not None and len(df):
                self._prices[symbol] = float(df["close"].iloc[-1])
            return df
        return None

    def get_current_price(self, symbol: str, direction: Direction = Direction.NONE) -> float:
        price = self._prices.get(symbol, 0.0)
        if price <= 0 and self.data_provider is not None:
            # No candle has flowed through this broker yet — pull one so a
            # market order in --dry-run can fill on the latest close.
            df = self.data_provider.get_candles(symbol, self.exit_check_timeframe, 2)
            if df is not None and len(df):
                price = float(df["close"].iloc[-1])
                self._prices[symbol] = price
        if price <= 0:
            return 0.0
        if self.spread_ticks <= 0:
            return price
        info = self.get_symbol_info(symbol)
        half = (self.spread_ticks / 2.0) * (info.tick_size if info else 0.0)
        if direction is Direction.LONG:
            return price + half
        if direction is Direction.SHORT:
            return price - half
        return price

    # ---------------------------------------------------------------- trading
    def get_open_positions(
        self, symbol: Optional[str] = None, magic: Optional[int] = None
    ) -> List[BrokerPosition]:
        self._evaluate_exits()
        positions = list(self._positions.values())
        if symbol:
            positions = [p for p in positions if p.symbol == symbol]
        wanted_magic = self.magic_number if magic is None else magic
        if wanted_magic:
            positions = [p for p in positions if p.magic == wanted_magic]
        for p in positions:
            p.price_current = self._prices.get(p.symbol, p.entry_price)
            p.profit = self._floating_profit(p)
        return positions

    def place_market_order(
        self,
        symbol: str,
        direction: Direction,
        lots: float,
        stop_loss: float = 0.0,
        take_profit: float = 0.0,
        comment: str = "",
        magic: int = 0,
    ) -> OrderResult:
        price = self.get_current_price(symbol, direction)
        if price <= 0:
            return OrderResult(ok=False, message=f"paper broker has no price for '{symbol}'")

        self._next_ticket += 1
        ticket = self._next_ticket
        self._positions[ticket] = BrokerPosition(
            ticket=ticket,
            symbol=symbol,
            direction=direction,
            lots=float(lots),
            entry_price=price,
            stop_loss=float(stop_loss),
            take_profit=float(take_profit),
            price_current=price,
            opened_at=datetime.utcnow(),
            magic=int(magic or self.magic_number),
            comment=comment,
        )
        logger.info(
            f"[Paper] OPEN #{ticket} {direction.value} {lots} {symbol} @ {price} "
            f"SL {stop_loss} TP {take_profit}"
        )
        return OrderResult(ok=True, ticket=ticket, price=price, volume=float(lots),
                           message="paper fill")

    def modify_position(
        self, ticket: int, stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> OrderResult:
        position = self._positions.get(int(ticket))
        if position is None:
            return OrderResult(ok=False, message=f"position #{ticket} not found")
        if stop_loss is not None:
            position.stop_loss = float(stop_loss)
        if take_profit is not None:
            position.take_profit = float(take_profit)
        return OrderResult(ok=True, ticket=int(ticket), message="paper modify")

    def close_position(self, ticket: int, volume: Optional[float] = None) -> OrderResult:
        position = self._positions.get(int(ticket))
        if position is None:
            return OrderResult(ok=False, message=f"position #{ticket} not found")

        price = self._prices.get(position.symbol, position.entry_price)
        close_volume = float(position.lots) if volume is None else min(float(volume), position.lots)
        if close_volume <= 0:
            return OrderResult(ok=False, message="close volume resolved to 0")

        self._book_exit(position, price, close_volume, reason="MANUAL")
        return OrderResult(ok=True, ticket=int(ticket), price=price, volume=close_volume,
                           message="paper close")

    def get_closed_deals(self, since: datetime) -> List[ClosedDeal]:
        return [d for d in self._deals if d.time is None or d.time >= since]

    # ---------------------------------------------------------------- internal
    def _floating_profit(self, position: BrokerPosition) -> float:
        price = self._prices.get(position.symbol, position.entry_price)
        return self._profit_for(position, price, position.lots)

    def _profit_for(self, position: BrokerPosition, price: float, volume: float) -> float:
        info = self.get_symbol_info(position.symbol)
        if info is None or info.tick_size <= 0:
            return 0.0
        move = (price - position.entry_price) * position.direction.sign
        return (move / info.tick_size) * info.tick_value * volume

    def _book_exit(self, position: BrokerPosition, price: float, volume: float,
                   reason: str) -> None:
        profit = self._profit_for(position, price, volume)
        self.balance += profit
        self._deals.append(ClosedDeal(
            deal_ticket=len(self._deals) + 1,
            position_ticket=position.ticket,
            symbol=position.symbol,
            volume=volume,
            price=price,
            profit=profit,
            reason=reason,
            time=datetime.utcnow(),
            comment=position.comment,
        ))
        remaining = round(position.lots - volume, 8)
        if remaining <= 0:
            self._positions.pop(position.ticket, None)
            self._last_exit_bar.pop(position.ticket, None)
            logger.info(
                f"[Paper] CLOSE #{position.ticket} {position.symbol} @ {price} "
                f"({reason}) P/L {profit:+.2f} | balance {self.balance:.2f}"
            )
        else:
            position.lots = remaining
            logger.info(
                f"[Paper] PARTIAL #{position.ticket} {position.symbol} {volume} @ {price} "
                f"({reason}) P/L {profit:+.2f} | {remaining} lots left"
            )

    def _evaluate_exits(self) -> None:
        """
        Walk the newest completed exit-timeframe bar for each open position and
        trigger SL/TP. Stop wins ties — the pessimistic assumption.
        """
        for position in list(self._positions.values()):
            df = self._candles.get((position.symbol, self.exit_check_timeframe))
            if (df is None or len(df) == 0) and self.data_provider is not None:
                df = self.data_provider.get_candles(
                    position.symbol, self.exit_check_timeframe, 2
                )
            if df is None or len(df) == 0:
                continue

            bar_time = df["time"].iloc[-1] if "time" in df.columns else None
            if isinstance(bar_time, pd.Timestamp):
                bar_time = bar_time.to_pydatetime()
            if bar_time is not None and self._last_exit_bar.get(position.ticket) == bar_time:
                continue
            if bar_time is not None:
                self._last_exit_bar[position.ticket] = bar_time

            high = float(df["high"].iloc[-1])
            low = float(df["low"].iloc[-1])
            self._prices[position.symbol] = float(df["close"].iloc[-1])

            is_long = position.direction is Direction.LONG
            hit_sl = position.stop_loss > 0 and (low <= position.stop_loss if is_long else high >= position.stop_loss)
            hit_tp = position.take_profit > 0 and (high >= position.take_profit if is_long else low <= position.take_profit)

            if hit_sl:
                self._book_exit(position, position.stop_loss, position.lots, reason="SL")
            elif hit_tp:
                self._book_exit(position, position.take_profit, position.lots, reason="TP")
