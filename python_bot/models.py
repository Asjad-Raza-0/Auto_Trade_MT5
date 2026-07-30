"""
Strategy-agnostic data models shared by every layer of the bot.

DESIGN RULE (important for anyone extending this codebase):
    Nothing in this file may mention a specific strategy's concepts.
    A strategy that needs to carry extra information (a zone, a trendline, an
    indicator reading, ...) puts it in the free-form ``metadata`` dict of
    ``TradeSignal`` / ``Position``, or in ``SymbolContext.strategy_data``.
    That is what keeps the engine, brokers and notifiers reusable when the
    strategy is swapped out.
"""
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Direction(str, Enum):
    """Trade / bias direction."""
    LONG = "LONG"
    SHORT = "SHORT"
    NONE = "NONE"

    @property
    def sign(self) -> int:
        """+1 for LONG, -1 for SHORT, 0 for NONE. Lets price maths stay branch-free."""
        if self is Direction.LONG:
            return 1
        if self is Direction.SHORT:
            return -1
        return 0

    @property
    def opposite(self) -> "Direction":
        if self is Direction.LONG:
            return Direction.SHORT
        if self is Direction.SHORT:
            return Direction.LONG
        return Direction.NONE


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP = "STOP"


class SymbolState(str, Enum):
    """
    Generic per-symbol lifecycle. Deliberately strategy-neutral: a strategy that
    tracks finer-grained progress stores it in ``SymbolContext.strategy_data``.
    """
    SCANNING = "SCANNING"            # looking for a setup
    SETUP_FORMING = "SETUP_FORMING"  # some conditions met, not all
    POSITION_OPEN = "POSITION_OPEN"  # live trade being managed
    COOLDOWN = "COOLDOWN"            # blocked for N bars after a trade/signal
    DISABLED = "DISABLED"            # risk limit hit / symbol unavailable


class SwingKind(str, Enum):
    HIGH = "HIGH"
    LOW = "LOW"


class ZoneKind(str, Enum):
    SUPPORT = "SUPPORT"
    RESISTANCE = "RESISTANCE"


class TrendlineKind(str, Enum):
    ASCENDING = "ASCENDING"    # drawn across swing LOWS
    DESCENDING = "DESCENDING"  # drawn across swing HIGHS


class ManagementActionType(str, Enum):
    MOVE_STOP = "MOVE_STOP"
    MODIFY_TAKE_PROFIT = "MODIFY_TAKE_PROFIT"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"
    CLOSE = "CLOSE"
    SCALE_IN = "SCALE_IN"


class TradeEventType(str, Enum):
    ENTRY = "ENTRY"                  # position opened
    PARTIAL_TP = "PARTIAL_TP"        # first target hit, part of the position banked
    TP_HIT = "TP_HIT"                # final target hit
    SL_HIT = "SL_HIT"                # stop loss hit
    BREAKEVEN = "BREAKEVEN"          # stop moved to entry
    SCALED_IN = "SCALED_IN"          # additional position opened
    CLOSED = "CLOSED"                # closed for any other reason (time stop, zone exit, manual)
    INFO = "INFO"
    ERROR = "ERROR"


# ---------------------------------------------------------------------------
# Price data
# ---------------------------------------------------------------------------

@dataclass
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def range(self) -> float:
        return self.high - self.low

    @property
    def body(self) -> float:
        return abs(self.open - self.close)

    @property
    def upper_wick(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_wick(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def is_bullish(self) -> bool:
        return self.close >= self.open


@dataclass
class SwingPoint:
    """A confirmed fractal pivot on some timeframe."""
    index: int
    time: datetime
    price: float
    kind: SwingKind

    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "time": self.time.isoformat() if self.time else None,
            "price": self.price,
            "kind": self.kind.value,
        }


@dataclass
class Zone:
    """A horizontal support/resistance band built from clustered swing points."""
    kind: ZoneKind
    timeframe: str
    top: float
    bottom: float
    touches: int = 0
    first_touch_time: Optional[datetime] = None
    last_touch_time: Optional[datetime] = None
    rejection_wicks: int = 0

    @property
    def mid(self) -> float:
        return (self.top + self.bottom) / 2.0

    @property
    def height(self) -> float:
        return max(0.0, self.top - self.bottom)

    @property
    def level(self) -> float:
        """The price the zone defends: its far edge in the direction price approaches from."""
        return self.bottom if self.kind is ZoneKind.SUPPORT else self.top

    def contains(self, price: float, tolerance: float = 0.0) -> bool:
        return (self.bottom - tolerance) <= price <= (self.top + tolerance)

    def distance_to(self, price: float) -> float:
        if self.contains(price):
            return 0.0
        return min(abs(price - self.top), abs(price - self.bottom))

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "timeframe": self.timeframe,
            "top": self.top,
            "bottom": self.bottom,
            "mid": self.mid,
            "touches": self.touches,
            "rejection_wicks": self.rejection_wicks,
            "first_touch_time": self.first_touch_time.isoformat() if self.first_touch_time else None,
            "last_touch_time": self.last_touch_time.isoformat() if self.last_touch_time else None,
        }


@dataclass
class Trendline:
    """A straight line fitted through two or more swing points, in bar-index space."""
    kind: TrendlineKind
    slope: float                 # price change per bar
    intercept: float             # price at bar index 0
    start_index: int
    end_index: int
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    touches: int = 2

    def value_at(self, index: int) -> float:
        return self.intercept + self.slope * index

    def to_dict(self) -> Dict[str, Any]:
        return {
            "kind": self.kind.value,
            "slope": self.slope,
            "intercept": self.intercept,
            "start_index": self.start_index,
            "end_index": self.end_index,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "touches": self.touches,
        }


# ---------------------------------------------------------------------------
# Broker-facing models
# ---------------------------------------------------------------------------

@dataclass
class SymbolInfo:
    """
    Instrument contract specification, normalised across brokers.
    ``tick_size`` + ``tick_value`` are all the risk manager needs to size any
    instrument (forex, metals, indices, crypto) without special-casing.
    """
    name: str
    digits: int = 5
    point: float = 0.00001
    tick_size: float = 0.00001
    tick_value: float = 1.0          # account-currency P/L for 1 lot moving 1 tick
    volume_min: float = 0.01
    volume_step: float = 0.01
    volume_max: float = 100.0
    stops_level_points: float = 0.0  # broker minimum SL/TP distance, in points
    contract_size: float = 100000.0
    currency_profit: str = "USD"
    tradable: bool = True

    def normalize_price(self, price: float) -> float:
        return round(price, self.digits)


@dataclass
class AccountInfo:
    login: int = 0
    balance: float = 0.0
    equity: float = 0.0
    margin_free: float = 0.0
    currency: str = "USD"
    leverage: int = 100
    server: str = ""
    name: str = ""
    is_demo: bool = True


@dataclass
class BrokerPosition:
    """A position as the broker currently reports it."""
    ticket: int
    symbol: str
    direction: Direction
    lots: float
    entry_price: float
    stop_loss: float = 0.0
    take_profit: float = 0.0
    profit: float = 0.0
    price_current: float = 0.0
    opened_at: Optional[datetime] = None
    magic: int = 0
    comment: str = ""


@dataclass
class ClosedDeal:
    """A closing deal pulled from broker history — used to classify TP vs SL exits."""
    deal_ticket: int
    position_ticket: int
    symbol: str
    volume: float
    price: float
    profit: float
    reason: str = "OTHER"   # "SL" | "TP" | "MANUAL" | "EXPERT" | "OTHER"
    time: Optional[datetime] = None
    comment: str = ""


@dataclass
class OrderResult:
    ok: bool
    ticket: int = 0
    price: float = 0.0
    volume: float = 0.0
    retcode: int = 0
    message: str = ""


# ---------------------------------------------------------------------------
# Strategy output
# ---------------------------------------------------------------------------

@dataclass
class TradeSignal:
    """
    What a strategy returns when it wants a trade. Strategy-neutral on purpose:
    everything specific to how the setup was found goes in ``metadata`` /
    ``confirmations``.

    ``calculated_lots`` is left at 0 by strategies — the engine sizes the trade
    through the RiskManager using live broker specs.
    """
    symbol: str
    direction: Direction
    entry_price: float
    stop_loss: float
    take_profit: float
    order_type: OrderType = OrderType.MARKET
    partial_take_profit: Optional[float] = None   # first target; bot closes part of the position here
    partial_close_percent: float = 0.0            # % of the position to bank at partial_take_profit
    breakeven_trigger: Optional[float] = None     # price at which SL moves to entry
    risk_percent: float = 1.0
    calculated_lots: float = 0.0
    risk_distance_points: float = 0.0
    risk_reward: float = 0.0
    confirmations: List[str] = field(default_factory=list)
    strategy_name: str = ""
    bar_time: Optional[datetime] = None           # the completed candle that triggered it
    timestamp: datetime = field(default_factory=datetime.utcnow)
    notes: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def risk_distance(self) -> float:
        return abs(self.entry_price - self.stop_loss)

    @property
    def reward_distance(self) -> float:
        return abs(self.take_profit - self.entry_price)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "direction": self.direction.value,
            "order_type": self.order_type.value,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "partial_take_profit": self.partial_take_profit,
            "partial_close_percent": self.partial_close_percent,
            "breakeven_trigger": self.breakeven_trigger,
            "risk_percent": self.risk_percent,
            "calculated_lots": self.calculated_lots,
            "risk_distance_points": self.risk_distance_points,
            "risk_reward": self.risk_reward,
            "confirmations": list(self.confirmations),
            "strategy_name": self.strategy_name,
            "bar_time": self.bar_time.isoformat() if self.bar_time else None,
            "timestamp": self.timestamp.isoformat(),
            "notes": self.notes,
            "metadata": self.metadata,
        }


@dataclass
class ManagementAction:
    """An instruction from ``BaseStrategy.manage_position`` for the engine to execute."""
    action: ManagementActionType
    reason: str = ""
    price: Optional[float] = None      # new SL/TP for MOVE_STOP / MODIFY_TAKE_PROFIT
    volume: Optional[float] = None     # lots for PARTIAL_CLOSE / SCALE_IN
    percent: Optional[float] = None    # alternative to volume for PARTIAL_CLOSE
    event_type: Optional[TradeEventType] = None  # event to emit if the action succeeds
    metadata: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Position tracking (bot-side mirror of the broker position)
# ---------------------------------------------------------------------------

@dataclass
class Position:
    ticket: int
    symbol: str
    direction: Direction
    entry_price: float
    stop_loss: float
    take_profit: float
    lots: float
    initial_lots: float
    initial_stop_loss: float
    opened_at: datetime
    partial_take_profit: Optional[float] = None
    partial_close_percent: float = 0.0
    breakeven_trigger: Optional[float] = None
    partial_done: bool = False
    breakeven_done: bool = False
    scale_in_count: int = 0
    strategy_name: str = ""
    magic: int = 0
    bar_time: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_long(self) -> bool:
        return self.direction is Direction.LONG

    @property
    def initial_risk(self) -> float:
        return abs(self.entry_price - self.initial_stop_loss)

    def rr_at(self, price: float) -> float:
        """How many R the position is up at ``price`` (negative when losing)."""
        risk = self.initial_risk
        if risk <= 0:
            return 0.0
        return ((price - self.entry_price) * self.direction.sign) / risk

    def is_favourable(self, price: float, target: float) -> bool:
        """True once ``price`` has reached ``target`` in the trade's direction."""
        if self.is_long:
            return price >= target
        return price <= target

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ticket": self.ticket,
            "symbol": self.symbol,
            "direction": self.direction.value,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "lots": self.lots,
            "initial_lots": self.initial_lots,
            "initial_stop_loss": self.initial_stop_loss,
            "opened_at": self.opened_at.isoformat() if self.opened_at else None,
            "partial_take_profit": self.partial_take_profit,
            "partial_close_percent": self.partial_close_percent,
            "breakeven_trigger": self.breakeven_trigger,
            "partial_done": self.partial_done,
            "breakeven_done": self.breakeven_done,
            "scale_in_count": self.scale_in_count,
            "strategy_name": self.strategy_name,
            "magic": self.magic,
            "bar_time": self.bar_time.isoformat() if self.bar_time else None,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Position":
        def _dt(key: str) -> Optional[datetime]:
            raw = data.get(key)
            return datetime.fromisoformat(raw) if raw else None

        return cls(
            ticket=int(data["ticket"]),
            symbol=data["symbol"],
            direction=Direction(data["direction"]),
            entry_price=float(data["entry_price"]),
            stop_loss=float(data["stop_loss"]),
            take_profit=float(data["take_profit"]),
            lots=float(data["lots"]),
            initial_lots=float(data.get("initial_lots", data["lots"])),
            initial_stop_loss=float(data.get("initial_stop_loss", data["stop_loss"])),
            opened_at=_dt("opened_at") or datetime.utcnow(),
            partial_take_profit=data.get("partial_take_profit"),
            partial_close_percent=float(data.get("partial_close_percent", 0.0)),
            breakeven_trigger=data.get("breakeven_trigger"),
            partial_done=bool(data.get("partial_done", False)),
            breakeven_done=bool(data.get("breakeven_done", False)),
            scale_in_count=int(data.get("scale_in_count", 0)),
            strategy_name=data.get("strategy_name", ""),
            magic=int(data.get("magic", 0)),
            bar_time=_dt("bar_time"),
            metadata=data.get("metadata", {}) or {},
        )

    @classmethod
    def from_signal(cls, signal: TradeSignal, ticket: int, fill_price: float,
                    lots: float, magic: int = 0) -> "Position":
        return cls(
            ticket=ticket,
            symbol=signal.symbol,
            direction=signal.direction,
            entry_price=fill_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            lots=lots,
            initial_lots=lots,
            initial_stop_loss=signal.stop_loss,
            opened_at=datetime.utcnow(),
            partial_take_profit=signal.partial_take_profit,
            partial_close_percent=signal.partial_close_percent,
            breakeven_trigger=signal.breakeven_trigger,
            strategy_name=signal.strategy_name,
            magic=magic,
            bar_time=signal.bar_time,
            metadata=dict(signal.metadata),
        )


# ---------------------------------------------------------------------------
# Notification events
# ---------------------------------------------------------------------------

@dataclass
class TradeEvent:
    """
    The single unit of notification. Notifiers only ever format a TradeEvent,
    which is why adding a strategy never requires touching a notifier.
    """
    event_type: TradeEventType
    symbol: str
    timestamp: datetime = field(default_factory=datetime.utcnow)
    direction: Direction = Direction.NONE
    price: float = 0.0
    lots: float = 0.0
    entry_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    profit: float = 0.0
    rr: float = 0.0
    ticket: int = 0
    strategy_name: str = ""
    title: str = ""
    message: str = ""
    signal: Optional[TradeSignal] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_type": self.event_type.value,
            "symbol": self.symbol,
            "timestamp": self.timestamp.isoformat(),
            "direction": self.direction.value,
            "price": self.price,
            "lots": self.lots,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "profit": self.profit,
            "rr": self.rr,
            "ticket": self.ticket,
            "strategy_name": self.strategy_name,
            "title": self.title,
            "message": self.message,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Per-symbol state
# ---------------------------------------------------------------------------

@dataclass
class SymbolContext:
    """
    Everything the bot remembers about one symbol between scan cycles.
    ``strategy_data`` is the strategy's private scratchpad — it is persisted as
    JSON, so keep it to primitives (str/int/float/bool/list/dict).
    """
    symbol: str
    broker_symbol: str = ""
    state: SymbolState = SymbolState.SCANNING
    position: Optional[Position] = None
    last_bar_times: Dict[str, str] = field(default_factory=dict)   # timeframe role -> ISO bar time
    last_signal_bar_time: Optional[datetime] = None
    cooldown_until_bar: int = 0
    trades_today: int = 0
    realized_pnl_today: float = 0.0
    trading_day: str = ""
    last_rejection_reason: str = ""
    strategy_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "broker_symbol": self.broker_symbol,
            "state": self.state.value,
            "position": self.position.to_dict() if self.position else None,
            "last_bar_times": dict(self.last_bar_times),
            "last_signal_bar_time": self.last_signal_bar_time.isoformat() if self.last_signal_bar_time else None,
            "cooldown_until_bar": self.cooldown_until_bar,
            "trades_today": self.trades_today,
            "realized_pnl_today": self.realized_pnl_today,
            "trading_day": self.trading_day,
            "last_rejection_reason": self.last_rejection_reason,
            "strategy_data": self.strategy_data,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SymbolContext":
        pos_data = data.get("position")
        return cls(
            symbol=data["symbol"],
            broker_symbol=data.get("broker_symbol", ""),
            state=SymbolState(data.get("state", SymbolState.SCANNING.value)),
            position=Position.from_dict(pos_data) if pos_data else None,
            last_bar_times=data.get("last_bar_times", {}) or {},
            last_signal_bar_time=(
                datetime.fromisoformat(data["last_signal_bar_time"])
                if data.get("last_signal_bar_time") else None
            ),
            cooldown_until_bar=int(data.get("cooldown_until_bar", 0)),
            trades_today=int(data.get("trades_today", 0)),
            realized_pnl_today=float(data.get("realized_pnl_today", 0.0)),
            trading_day=data.get("trading_day", ""),
            last_rejection_reason=data.get("last_rejection_reason", ""),
            strategy_data=data.get("strategy_data", {}) or {},
        )
