import hashlib
import logging
from typing import Optional, Tuple, List
import pandas as pd
import numpy as np
from datetime import datetime

from python_bot.models import TradeSignal, SymbolContext, SymbolState, FVG, Candle
from python_bot.strategies.base_strategy import BaseStrategy
from python_bot.core.risk_manager import RiskManager
from python_bot.core.session_manager import SessionManager

logger = logging.getLogger(__name__)

def calculate_ema(series: pd.Series, period: int) -> pd.Series:
    """Calculates Exponential Moving Average (EMA)."""
    return series.ewm(span=period, adjust=False).mean()

class TridentStrategy(BaseStrategy):
    """
    TG Capital London EMA Stack + FVG Trident Strategy v2.0
    """
    def __init__(self, risk_manager: Optional[RiskManager] = None,
                 session_manager: Optional[SessionManager] = None,
                 doji_threshold: float = 0.10):
        self.risk_manager = risk_manager or RiskManager()
        self.session_manager = session_manager or SessionManager()
        self.doji_threshold = doji_threshold

    @property
    def name(self) -> str:
        return "trident_v2"

    def evaluate_daily_filter(self, symbol: str, df_daily: pd.DataFrame) -> Tuple[bool, str]:
        """
        Evaluates Daily Trend Filter on completed Daily candle.
        Conditions:
        - Close > EMA200
        - EMA5 > EMA9 > EMA13 > EMA21
        """
        if df_daily is None or len(df_daily) < 200:
            return False, f"Insufficient Daily historical bars (need >= 200, got {0 if df_daily is None else len(df_daily)})"

        # Copy data and compute EMAs
        df = df_daily.copy()
        for p in [5, 9, 13, 21, 200]:
            df[f"ema_{p}"] = calculate_ema(df["close"], p)

        # Use last COMPLETED Daily candle (index -2 if live unclosed bar is -1, or -1 if closed data passed)
        # We ensure completed candle check
        last_completed = df.iloc[-2] if len(df) >= 2 else df.iloc[-1]

        close_val = last_completed["close"]
        ema5 = last_completed["ema_5"]
        ema9 = last_completed["ema_9"]
        ema13 = last_completed["ema_13"]
        ema21 = last_completed["ema_21"]
        ema200 = last_completed["ema_200"]

        if close_val <= ema200:
            return False, f"Daily Close ({close_val:.5f}) <= EMA200 ({ema200:.5f})"

        if not (ema5 > ema9 > ema13 > ema21):
            return False, f"Daily EMA stack broken: EMA5({ema5:.5f}) EMA9({ema9:.5f}) EMA13({ema13:.5f}) EMA21({ema21:.5f})"

        return True, "Daily EMA Stack filter PASSED (Close > EMA200 & EMA5 > EMA9 > EMA13 > EMA21)"

    def generate_fvg_id(self, symbol: str, candle_c_time: datetime, top: float, bottom: float) -> str:
        raw_str = f"{symbol}_{candle_c_time.isoformat()}_{top:.5f}_{bottom:.5f}"
        return "fvg_" + hashlib.md5(raw_str.encode("utf-8")).hexdigest()[:12]

    def detect_latest_fvg(self, symbol: str, df_m30: pd.DataFrame) -> Optional[FVG]:
        """
        Detects Bullish FVG across 3 completed M30 candles: A (oldest), B (middle), C (newest).
        Condition: High(A) < Low(C).
        Top = Low(C), Bottom = High(A).
        """
        if df_m30 is None or len(df_m30) < 4:
            return None

        # Iterate back through recent completed candles to find the newest FVG
        for i in range(len(df_m30) - 1, 1, -1):
            candle_c = df_m30.iloc[i]
            candle_b = df_m30.iloc[i - 1]
            candle_a = df_m30.iloc[i - 2]

            high_a = candle_a["high"]
            low_c = candle_c["low"]

            if high_a < low_c:
                top = low_c
                bottom = high_a
                size = top - bottom
                if size <= 0:
                    continue
                ce = (top + bottom) / 2.0
                c_time = candle_c["time"] if "time" in candle_c else candle_c.name
                if isinstance(c_time, str):
                    c_time = datetime.fromisoformat(c_time)

                fvg_id = self.generate_fvg_id(symbol, c_time, top, bottom)
                return FVG(
                    id=fvg_id,
                    symbol=symbol,
                    candle_c_time=c_time,
                    top=top,
                    bottom=bottom,
                    size=size,
                    ce=ce
                )
        return None

    def evaluate_signal(
        self,
        symbol: str,
        df_daily: pd.DataFrame,
        df_m30: pd.DataFrame,
        context: SymbolContext
    ) -> Tuple[Optional[TradeSignal], str]:
        """
        Evaluates full Trident strategy setup for the symbol.
        """
        # Step 1: Check Daily Filter
        daily_ok, daily_msg = self.evaluate_daily_filter(symbol, df_daily)
        if not daily_ok:
            if context.state != SymbolState.WAIT_FOR_DAILY_FILTER:
                context.state = SymbolState.WAIT_FOR_DAILY_FILTER
                context.active_fvg = None
            return None, f"Daily Filter Failed: {daily_msg}"

        # Step 2: Check Trading Session (03:00 - 06:30 NY)
        if not self.session_manager.is_in_session():
            return None, "Outside trading session (Allowed: 03:00 - 06:30 America/New_York)"

        if df_m30 is None or len(df_m30) < 5:
            return None, "Insufficient M30 bars"

        # Step 3: Detect / Update FVG
        latest_fvg = self.detect_latest_fvg(symbol, df_m30)
        if latest_fvg is not None:
            if context.active_fvg is None or context.active_fvg.id != latest_fvg.id:
                # Replace with newest FVG as per prompt rule
                context.active_fvg = latest_fvg
                context.doji_candle_time = None
                context.doji_high = None
                context.confirmation_candle_time = None
                context.state = SymbolState.WAIT_FOR_DOJI
                logger.info(f"[{symbol}] Detected new Bullish FVG: Top={latest_fvg.top:.5f}, Bottom={latest_fvg.bottom:.5f}, CE={latest_fvg.ce:.5f}")

        if context.active_fvg is None:
            return None, "No active Bullish FVG found"

        fvg = context.active_fvg

        # Step 4: Detect Doji AFTER FVG forms
        # We search M30 candles following FVG Candle C time
        m30_rows = []
        for idx, row in df_m30.iterrows():
            row_time = row["time"] if "time" in row else idx
            if isinstance(row_time, str):
                row_time = datetime.fromisoformat(row_time)
            if row_time > fvg.candle_c_time:
                m30_rows.append((row_time, row))

        if not m30_rows:
            return None, f"Waiting for Doji after FVG Candle C ({fvg.candle_c_time})"

        # Find first valid Doji
        doji_idx = None
        doji_candle = None
        for i, (r_time, row) in enumerate(m30_rows):
            high_val = row["high"]
            low_val = row["low"]
            open_val = row["open"]
            close_val = row["close"]
            rng = high_val - low_val

            if rng <= 0:
                continue

            body = abs(open_val - close_val)
            ratio = body / rng

            if ratio <= self.doji_threshold:
                # Doji condition: Low(Doji) <= CE AND Close(Doji) > CE
                if low_val <= fvg.ce and close_val > fvg.ce:
                    doji_idx = i
                    doji_candle = (r_time, row)
                    context.doji_candle_time = r_time
                    context.doji_high = high_val
                    context.state = SymbolState.WAIT_FOR_CONFIRMATION
                    break

        if doji_candle is None:
            return None, f"Active FVG present (ID: {fvg.id}), waiting for valid Doji (Low <= CE ({fvg.ce:.5f}) & Close > CE)"

        # Step 5: Check Confirmation Candle
        # Must be IMMEDIATELY NEXT completed M30 candle after the Doji
        if doji_idx + 1 >= len(m30_rows):
            return None, f"Valid Doji found at {context.doji_candle_time}, waiting for confirmation candle"

        conf_time, conf_row = m30_rows[doji_idx + 1]
        conf_close = conf_row["close"]

        # Valid only if Close(Confirmation) < High(Doji)
        if conf_close >= context.doji_high:
            # Rejection rule: Confirmation candle failed
            return None, f"Confirmation failed: Close({conf_close:.5f}) >= Doji High({context.doji_high:.5f})"

        context.confirmation_candle_time = conf_time
        context.state = SymbolState.PLACE_PENDING_ORDER

        # Step 6: Determine Stop Loss (Low of Candle B of FVG)
        # Locate Candle B for the FVG
        candle_b_low = fvg.bottom  # Fallback to bottom if exact B not found
        for i in range(len(df_m30) - 1, 1, -1):
            row_c = df_m30.iloc[i]
            c_time = row_c["time"] if "time" in row_c else row_c.name
            if isinstance(c_time, str):
                c_time = datetime.fromisoformat(c_time)
            if c_time == fvg.candle_c_time:
                candle_b_low = df_m30.iloc[i - 1]["low"]
                break

        entry_price = fvg.top
        stop_loss = candle_b_low

        # Step 7: Risk Management & Lot Calculation
        valid_stop, stop_msg = self.risk_manager.validate_stop_distance(symbol, entry_price, stop_loss)
        if not valid_stop:
            return None, f"Risk rejection: {stop_msg}"

        lots = self.risk_manager.calculate_lot_size(symbol, entry_price, stop_loss)
        if lots <= 0:
            return None, "Lot calculation resulted in 0 (exceeds risk limits or below min lot)"

        dist_pts = self.risk_manager.calculate_stop_distance_points(symbol, entry_price, stop_loss)

        signal = TradeSignal(
            symbol=symbol,
            direction="BUY_LIMIT",
            entry_price=entry_price,
            stop_loss=stop_loss,
            risk_percent=self.risk_manager.risk_percent,
            calculated_lots=lots,
            risk_distance_points=dist_pts,
            fvg=fvg,
            timestamp=datetime.now(),
            strategy_name=self.name,
            notes=f"Confirmed setup: Doji at {context.doji_candle_time}, Confirmed at {conf_time}"
        )

        return signal, "VALID_SIGNAL_DETECTED"
