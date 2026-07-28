from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime

class SymbolState(str, Enum):
    WAIT_FOR_DAILY_FILTER = "WAIT_FOR_DAILY_FILTER"
    WAIT_FOR_SESSION = "WAIT_FOR_SESSION"
    WAIT_FOR_FVG = "WAIT_FOR_FVG"
    WAIT_FOR_DOJI = "WAIT_FOR_DOJI"
    WAIT_FOR_CONFIRMATION = "WAIT_FOR_CONFIRMATION"
    PLACE_PENDING_ORDER = "PLACE_PENDING_ORDER"
    WAIT_FOR_FILL = "WAIT_FOR_FILL"
    MANAGE_POSITION = "MANAGE_POSITION"
    EXIT = "EXIT"

@dataclass
class Candle:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

    @property
    def is_doji(self, threshold: float = 0.10) -> bool:
        rng = self.high - self.low
        if rng <= 0:
            return False
        body = abs(self.open - self.close)
        return (body / rng) <= threshold

@dataclass
class FVG:
    id: str
    symbol: str
    candle_c_time: datetime
    top: float       # Low of Candle C
    bottom: float    # High of Candle A
    size: float      # Top - Bottom
    ce: float        # Consequent Encroachment = (Top + Bottom) / 2

@dataclass
class DojiPattern:
    time: datetime
    open: float
    high: float
    low: float
    close: float
    ratio: float

@dataclass
class ConfirmationPattern:
    time: datetime
    open: float
    high: float
    low: float
    close: float

@dataclass
class TradeSignal:
    symbol: str
    direction: str                     # "BUY_LIMIT" or "BUY"
    entry_price: float
    stop_loss: float
    risk_percent: float
    calculated_lots: float
    risk_distance_points: float
    fvg: FVG
    timestamp: datetime
    strategy_name: str = "TG Capital Trident v2.0"
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "direction": self.direction,
            "entry_price": self.entry_price,
            "stop_loss": self.stop_loss,
            "risk_percent": self.risk_percent,
            "calculated_lots": self.calculated_lots,
            "risk_distance_points": self.risk_distance_points,
            "fvg_id": self.fvg.id,
            "fvg_top": self.fvg.top,
            "fvg_bottom": self.fvg.bottom,
            "fvg_ce": self.fvg.ce,
            "timestamp": self.timestamp.isoformat(),
            "strategy_name": self.strategy_name,
            "notes": self.notes
        }

@dataclass
class SymbolContext:
    symbol: str
    state: SymbolState = SymbolState.WAIT_FOR_DAILY_FILTER
    active_fvg: Optional[FVG] = None
    doji_candle_time: Optional[datetime] = None
    doji_high: Optional[float] = None
    confirmation_candle_time: Optional[datetime] = None
    last_processed_m30_time: Optional[datetime] = None
    last_processed_daily_time: Optional[datetime] = None
    last_signal_candle_time: Optional[datetime] = None
    last_rejection_reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "state": self.state.value,
            "active_fvg": {
                "id": self.active_fvg.id,
                "symbol": self.active_fvg.symbol,
                "candle_c_time": self.active_fvg.candle_c_time.isoformat(),
                "top": self.active_fvg.top,
                "bottom": self.active_fvg.bottom,
                "size": self.active_fvg.size,
                "ce": self.active_fvg.ce
            } if self.active_fvg else None,
            "doji_candle_time": self.doji_candle_time.isoformat() if self.doji_candle_time else None,
            "doji_high": self.doji_high,
            "confirmation_candle_time": self.confirmation_candle_time.isoformat() if self.confirmation_candle_time else None,
            "last_processed_m30_time": self.last_processed_m30_time.isoformat() if self.last_processed_m30_time else None,
            "last_processed_daily_time": self.last_processed_daily_time.isoformat() if self.last_processed_daily_time else None,
            "last_signal_candle_time": self.last_signal_candle_time.isoformat() if self.last_signal_candle_time else None,
            "last_rejection_reason": self.last_rejection_reason
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SymbolContext":
        fvg_data = data.get("active_fvg")
        active_fvg = None
        if fvg_data:
            active_fvg = FVG(
                id=fvg_data["id"],
                symbol=fvg_data["symbol"],
                candle_c_time=datetime.fromisoformat(fvg_data["candle_c_time"]),
                top=fvg_data["top"],
                bottom=fvg_data["bottom"],
                size=fvg_data["size"],
                ce=fvg_data["ce"]
            )
        return cls(
            symbol=data["symbol"],
            state=SymbolState(data.get("state", SymbolState.WAIT_FOR_DAILY_FILTER.value)),
            active_fvg=active_fvg,
            doji_candle_time=datetime.fromisoformat(data["doji_candle_time"]) if data.get("doji_candle_time") else None,
            doji_high=data.get("doji_high"),
            confirmation_candle_time=datetime.fromisoformat(data["confirmation_candle_time"]) if data.get("confirmation_candle_time") else None,
            last_processed_m30_time=datetime.fromisoformat(data["last_processed_m30_time"]) if data.get("last_processed_m30_time") else None,
            last_processed_daily_time=datetime.fromisoformat(data["last_processed_daily_time"]) if data.get("last_processed_daily_time") else None,
            last_signal_candle_time=datetime.fromisoformat(data["last_signal_candle_time"]) if data.get("last_signal_candle_time") else None,
            last_rejection_reason=data.get("last_rejection_reason", "")
        )
