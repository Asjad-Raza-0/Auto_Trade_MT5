"""
MetaTrader 5 broker adapter (live execution + price data).

Requires the official ``MetaTrader5`` package and a running MT5 terminal on the
same Windows machine, with **Algo Trading enabled** in the terminal
(Tools -> Options -> Expert Advisors -> Allow algorithmic trading).

The package is imported lazily so the rest of the bot — and the whole test suite —
runs on any OS without MetaTrader installed.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

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

# Logical timeframe string -> MT5 constant name (resolved after import).
TIMEFRAME_NAMES: Dict[str, str] = {
    "1m": "TIMEFRAME_M1", "2m": "TIMEFRAME_M2", "3m": "TIMEFRAME_M3",
    "4m": "TIMEFRAME_M4", "5m": "TIMEFRAME_M5", "6m": "TIMEFRAME_M6",
    "10m": "TIMEFRAME_M10", "12m": "TIMEFRAME_M12", "15m": "TIMEFRAME_M15",
    "20m": "TIMEFRAME_M20", "30m": "TIMEFRAME_M30",
    "1h": "TIMEFRAME_H1", "2h": "TIMEFRAME_H2", "3h": "TIMEFRAME_H3",
    "4h": "TIMEFRAME_H4", "6h": "TIMEFRAME_H6", "8h": "TIMEFRAME_H8",
    "12h": "TIMEFRAME_H12",
    "1d": "TIMEFRAME_D1", "1w": "TIMEFRAME_W1", "1M": "TIMEFRAME_MN1",
}


class MT5NotAvailableError(RuntimeError):
    """Raised when the MetaTrader5 package or terminal cannot be reached."""


class MT5Broker(BaseBroker):
    """
    Live MT5 adapter.

    Config (``config.json -> mt5``):
        login / password / server   optional — omit to attach to the terminal's
                                    already-logged-in account
        terminal_path               optional path to terminal64.exe
        magic_number                tags this bot's orders so it never touches
                                    manual trades or another EA's positions
        deviation_points            max slippage for market orders
    """

    def __init__(
        self,
        login: int = 0,
        password: str = "",
        server: str = "",
        terminal_path: str = "",
        magic_number: int = 250730,
        deviation_points: int = 20,
        timeout_ms: int = 60000,
    ):
        self.login = int(login or 0)
        self.password = password or ""
        self.server = server or ""
        self.terminal_path = terminal_path or ""
        self.magic_number = int(magic_number)
        self.deviation_points = int(deviation_points)
        self.timeout_ms = int(timeout_ms)

        self._mt5: Any = None
        self._connected = False
        self._symbol_cache: Dict[str, SymbolInfo] = {}
        self._selected: set = set()

    # -------------------------------------------------------------- lifecycle
    @property
    def name(self) -> str:
        return "mt5"

    @property
    def mt5(self) -> Any:
        """The MetaTrader5 module, imported on first use."""
        if self._mt5 is None:
            try:
                import MetaTrader5 as mt5_module  # noqa: N813
            except ImportError as exc:
                raise MT5NotAvailableError(
                    "The 'MetaTrader5' package is not installed (Windows only). "
                    "Install it with `pip install MetaTrader5`, or run the bot with "
                    "`--dry-run` to use the simulated paper broker instead."
                ) from exc
            self._mt5 = mt5_module
        return self._mt5

    def connect(self) -> bool:
        if self._connected:
            return True

        mt5 = self.mt5
        kwargs: Dict[str, Any] = {"timeout": self.timeout_ms}
        if self.terminal_path:
            kwargs["path"] = self.terminal_path
        if self.login:
            kwargs.update({"login": self.login, "password": self.password, "server": self.server})

        if not mt5.initialize(**kwargs):
            code, message = mt5.last_error()
            logger.error(f"[MT5] initialize() failed: ({code}) {message}")
            return False

        # An explicit login is only needed when credentials were supplied.
        if self.login and not mt5.login(self.login, password=self.password, server=self.server):
            code, message = mt5.last_error()
            logger.error(f"[MT5] login({self.login}) failed: ({code}) {message}")
            mt5.shutdown()
            return False

        self._connected = True
        account = self.get_account()
        if account:
            mode = "DEMO" if account.is_demo else "*** LIVE ***"
            logger.info(
                f"[MT5] Connected: {account.name} #{account.login} on {account.server} "
                f"[{mode}] | balance {account.balance:.2f} {account.currency} "
                f"| leverage 1:{account.leverage}"
            )
            if not account.is_demo:
                logger.warning(
                    "[MT5] This is a LIVE account, not a demo. Orders will use real money."
                )
        terminal = mt5.terminal_info()
        if terminal is not None and not getattr(terminal, "trade_allowed", True):
            logger.error(
                "[MT5] Algo trading is DISABLED in the terminal. Enable "
                "Tools -> Options -> Expert Advisors -> 'Allow algorithmic trading', "
                "or the bot cannot place orders."
            )
        return True

    def disconnect(self) -> None:
        if self._connected and self._mt5 is not None:
            self._mt5.shutdown()
        self._connected = False
        self._selected.clear()

    @property
    def is_connected(self) -> bool:
        return self._connected

    # ------------------------------------------------------------ account info
    def get_account(self) -> Optional[AccountInfo]:
        info = self.mt5.account_info()
        if info is None:
            return None
        trade_mode = getattr(info, "trade_mode", 0)
        return AccountInfo(
            login=int(info.login),
            balance=float(info.balance),
            equity=float(info.equity),
            margin_free=float(info.margin_free),
            currency=str(info.currency),
            leverage=int(info.leverage),
            server=str(info.server),
            name=str(info.name),
            # ACCOUNT_TRADE_MODE_DEMO == 0, CONTEST == 1, REAL == 2
            is_demo=int(trade_mode) != 2,
        )

    def list_symbols(self) -> List[str]:
        symbols = self.mt5.symbols_get()
        if not symbols:
            return []
        return [s.name for s in symbols]

    def _select(self, symbol: str) -> bool:
        """Make sure the symbol is in Market Watch, otherwise no data/orders."""
        if symbol in self._selected:
            return True
        if self.mt5.symbol_select(symbol, True):
            self._selected.add(symbol)
            return True
        logger.error(f"[MT5] symbol_select('{symbol}') failed — is the symbol name correct?")
        return False

    def get_symbol_info(self, symbol: str) -> Optional[SymbolInfo]:
        if symbol in self._symbol_cache:
            return self._symbol_cache[symbol]
        if not self._select(symbol):
            return None

        raw = self.mt5.symbol_info(symbol)
        if raw is None:
            return None

        tick_value = float(getattr(raw, "trade_tick_value", 0.0) or 0.0)
        tick_size = float(getattr(raw, "trade_tick_size", 0.0) or 0.0)
        point = float(getattr(raw, "point", 0.0) or 0.0)
        if tick_size <= 0:
            tick_size = point if point > 0 else 0.00001

        info = SymbolInfo(
            name=raw.name,
            digits=int(raw.digits),
            point=point if point > 0 else tick_size,
            tick_size=tick_size,
            tick_value=tick_value if tick_value > 0 else 1.0,
            volume_min=float(raw.volume_min),
            volume_step=float(raw.volume_step) if raw.volume_step > 0 else 0.01,
            volume_max=float(raw.volume_max),
            stops_level_points=float(getattr(raw, "trade_stops_level", 0) or 0),
            contract_size=float(getattr(raw, "trade_contract_size", 0.0) or 0.0),
            currency_profit=str(getattr(raw, "currency_profit", "USD")),
            tradable=int(getattr(raw, "trade_mode", 4)) != 0,  # SYMBOL_TRADE_MODE_DISABLED == 0
        )
        self._symbol_cache[symbol] = info
        return info

    # -------------------------------------------------------------- price data
    def _timeframe(self, timeframe: str) -> Optional[int]:
        key = TIMEFRAME_NAMES.get(timeframe) or TIMEFRAME_NAMES.get(timeframe.lower())
        if key is None:
            logger.error(
                f"[MT5] Unsupported timeframe '{timeframe}'. "
                f"Supported: {', '.join(sorted(TIMEFRAME_NAMES))}"
            )
            return None
        return getattr(self.mt5, key)

    def get_candles(self, symbol: str, timeframe: str, count: int) -> Optional[pd.DataFrame]:
        """
        COMPLETED candles only — start_pos=1 deliberately skips bar 0, which is
        the bar still forming. Every strategy relies on this.
        """
        tf = self._timeframe(timeframe)
        if tf is None or not self._select(symbol):
            return None

        rates = self.mt5.copy_rates_from_pos(symbol, tf, 1, int(count))
        if rates is None or len(rates) == 0:
            code, message = self.mt5.last_error()
            logger.warning(
                f"[MT5] No {timeframe} candles for {symbol}: ({code}) {message}"
            )
            return None

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        volume_col = "tick_volume" if "tick_volume" in df.columns else "real_volume"
        df["volume"] = df[volume_col].astype(float) if volume_col in df.columns else 0.0
        for col in ("open", "high", "low", "close"):
            df[col] = df[col].astype(float)
        return df[["time", "open", "high", "low", "close", "volume"]].reset_index(drop=True)

    def get_current_price(self, symbol: str, direction: Direction = Direction.NONE) -> float:
        if not self._select(symbol):
            return 0.0
        tick = self.mt5.symbol_info_tick(symbol)
        if tick is None:
            return 0.0
        if direction is Direction.LONG:
            return float(tick.ask)
        if direction is Direction.SHORT:
            return float(tick.bid)
        return (float(tick.bid) + float(tick.ask)) / 2.0

    # ---------------------------------------------------------------- trading
    def get_open_positions(
        self, symbol: Optional[str] = None, magic: Optional[int] = None
    ) -> List[BrokerPosition]:
        raw = self.mt5.positions_get(symbol=symbol) if symbol else self.mt5.positions_get()
        if raw is None:
            return []

        wanted_magic = self.magic_number if magic is None else magic
        positions: List[BrokerPosition] = []
        for p in raw:
            if wanted_magic and int(p.magic) != int(wanted_magic):
                continue  # never touch manual trades or other EAs
            positions.append(BrokerPosition(
                ticket=int(p.ticket),
                symbol=str(p.symbol),
                direction=Direction.LONG if int(p.type) == self.mt5.POSITION_TYPE_BUY else Direction.SHORT,
                lots=float(p.volume),
                entry_price=float(p.price_open),
                stop_loss=float(p.sl),
                take_profit=float(p.tp),
                profit=float(p.profit),
                price_current=float(p.price_current),
                opened_at=datetime.utcfromtimestamp(int(p.time)),
                magic=int(p.magic),
                comment=str(p.comment),
            ))
        return positions

    def _filling_modes(self, symbol: str) -> List[int]:
        """
        Brokers accept different filling policies; try the one they advertise
        first, then the usual fallbacks. Wrong filling mode is the single most
        common cause of "Unsupported filling mode" order rejections.
        """
        mt5 = self.mt5
        raw = mt5.symbol_info(symbol)
        modes: List[int] = []
        if raw is not None:
            flags = int(getattr(raw, "filling_mode", 0) or 0)
            # SYMBOL_FILLING_FOK = 1, SYMBOL_FILLING_IOC = 2 (bit flags)
            if flags & 1:
                modes.append(mt5.ORDER_FILLING_FOK)
            if flags & 2:
                modes.append(mt5.ORDER_FILLING_IOC)
        for fallback in (mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_RETURN):
            if fallback not in modes:
                modes.append(fallback)
        return modes

    def _send(self, request: Dict[str, Any], symbol: str, what: str) -> OrderResult:
        """Send a request, retrying across filling modes on filling-related errors."""
        mt5 = self.mt5
        last: Optional[OrderResult] = None

        for filling in self._filling_modes(symbol):
            attempt = dict(request)
            attempt["type_filling"] = filling
            result = mt5.order_send(attempt)

            if result is None:
                code, message = mt5.last_error()
                last = OrderResult(ok=False, retcode=code, message=f"{what}: order_send returned None ({message})")
                logger.error(f"[MT5] {last.message}")
                continue

            retcode = int(result.retcode)
            if retcode in (mt5.TRADE_RETCODE_DONE, mt5.TRADE_RETCODE_PLACED, mt5.TRADE_RETCODE_DONE_PARTIAL):
                return OrderResult(
                    ok=True,
                    ticket=int(getattr(result, "order", 0) or getattr(result, "deal", 0) or 0),
                    price=float(getattr(result, "price", 0.0) or 0.0),
                    volume=float(getattr(result, "volume", 0.0) or 0.0),
                    retcode=retcode,
                    message=str(getattr(result, "comment", "")),
                )

            last = OrderResult(
                ok=False, retcode=retcode,
                message=f"{what} rejected: retcode {retcode} ({getattr(result, 'comment', '')})",
            )
            logger.error(f"[MT5] {last.message}")

            if retcode not in (
                mt5.TRADE_RETCODE_INVALID_FILL,
                mt5.TRADE_RETCODE_UNSUPPORTED_FILL_POLICY,
            ):
                break  # not a filling problem — retrying other modes will not help

        return last or OrderResult(ok=False, message=f"{what}: no result")

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
        mt5 = self.mt5
        if not self._select(symbol):
            return OrderResult(ok=False, message=f"symbol '{symbol}' could not be selected")

        info = self.get_symbol_info(symbol)
        if info is None:
            return OrderResult(ok=False, message=f"no symbol info for '{symbol}'")

        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return OrderResult(ok=False, message=f"no tick data for '{symbol}'")

        is_long = direction is Direction.LONG
        price = float(tick.ask if is_long else tick.bid)

        request: Dict[str, Any] = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(lots),
            "type": mt5.ORDER_TYPE_BUY if is_long else mt5.ORDER_TYPE_SELL,
            "price": price,
            "deviation": self.deviation_points,
            "magic": int(magic or self.magic_number),
            "comment": (comment or "")[:31],  # MT5 truncates at 31 chars
            "type_time": mt5.ORDER_TIME_GTC,
        }
        if stop_loss:
            request["sl"] = info.normalize_price(stop_loss)
        if take_profit:
            request["tp"] = info.normalize_price(take_profit)

        return self._send(request, symbol, f"{direction.value} {lots} {symbol}")

    def modify_position(
        self, ticket: int, stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None
    ) -> OrderResult:
        mt5 = self.mt5
        raw = mt5.positions_get(ticket=int(ticket))
        if not raw:
            return OrderResult(ok=False, message=f"position #{ticket} not found")

        position = raw[0]
        info = self.get_symbol_info(position.symbol)
        new_sl = float(position.sl) if stop_loss is None else float(stop_loss)
        new_tp = float(position.tp) if take_profit is None else float(take_profit)
        if info is not None:
            new_sl = info.normalize_price(new_sl)
            new_tp = info.normalize_price(new_tp)

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "position": int(ticket),
            "symbol": position.symbol,
            "sl": new_sl,
            "tp": new_tp,
            "magic": int(position.magic),
        }
        return self._send(request, position.symbol, f"modify #{ticket} SL/TP")

    def close_position(self, ticket: int, volume: Optional[float] = None) -> OrderResult:
        mt5 = self.mt5
        raw = mt5.positions_get(ticket=int(ticket))
        if not raw:
            return OrderResult(ok=False, message=f"position #{ticket} not found")

        position = raw[0]
        symbol = position.symbol
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return OrderResult(ok=False, message=f"no tick data for '{symbol}'")

        is_long = int(position.type) == mt5.POSITION_TYPE_BUY
        close_volume = float(position.volume) if volume is None else float(volume)
        close_volume = min(close_volume, float(position.volume))
        if close_volume <= 0:
            return OrderResult(ok=False, message="close volume resolved to 0")

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": close_volume,
            "type": mt5.ORDER_TYPE_SELL if is_long else mt5.ORDER_TYPE_BUY,
            "position": int(ticket),
            "price": float(tick.bid if is_long else tick.ask),
            "deviation": self.deviation_points,
            "magic": int(position.magic),
            "comment": "bot close",
            "type_time": mt5.ORDER_TIME_GTC,
        }
        return self._send(request, symbol, f"close {close_volume} of #{ticket}")

    def get_closed_deals(self, since: datetime) -> List[ClosedDeal]:
        mt5 = self.mt5
        # A small look-back cushion protects against terminal/server clock skew.
        deals = mt5.history_deals_get(since - timedelta(minutes=5), datetime.utcnow() + timedelta(minutes=5))
        if deals is None:
            return []

        reason_map = {
            getattr(mt5, "DEAL_REASON_SL", 4): "SL",
            getattr(mt5, "DEAL_REASON_TP", 5): "TP",
            getattr(mt5, "DEAL_REASON_CLIENT", 0): "MANUAL",
            getattr(mt5, "DEAL_REASON_EXPERT", 3): "EXPERT",
        }

        results: List[ClosedDeal] = []
        for d in deals:
            # DEAL_ENTRY_OUT == 1, DEAL_ENTRY_OUT_BY == 3 — only exits matter here.
            if int(getattr(d, "entry", 0)) not in (1, 3):
                continue
            if self.magic_number and int(getattr(d, "magic", 0)) != self.magic_number:
                continue
            results.append(ClosedDeal(
                deal_ticket=int(d.ticket),
                position_ticket=int(getattr(d, "position_id", 0)),
                symbol=str(d.symbol),
                volume=float(d.volume),
                price=float(d.price),
                profit=float(d.profit) + float(getattr(d, "commission", 0.0)) + float(getattr(d, "swap", 0.0)),
                reason=reason_map.get(int(getattr(d, "reason", -1)), "OTHER"),
                time=datetime.utcfromtimestamp(int(d.time)),
                comment=str(getattr(d, "comment", "")),
            ))
        return results
