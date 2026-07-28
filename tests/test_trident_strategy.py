import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import pytz

from python_bot.models import SymbolContext, SymbolState
from python_bot.strategies.trident_strategy import TridentStrategy
from python_bot.core.risk_manager import RiskManager
from python_bot.core.session_manager import SessionManager

def create_mock_daily_df(num_bars: int = 220) -> pd.DataFrame:
    """Generates synthetic Daily dataframe with EMA5 > EMA9 > EMA13 > EMA21 and Close > EMA200."""
    now = datetime.utcnow()
    times = [now - timedelta(days=num_bars - i) for i in range(num_bars)]
    
    # Uptrend prices from 2000 up to 2400
    closes = list(np.linspace(2000.0, 2400.0, num_bars))
    opens = [c - 2.0 for c in closes]
    highs = [c + 3.0 for c in closes]
    lows = [c - 4.0 for c in closes]

    return pd.DataFrame({
        "time": times,
        "open": opens,
        "high": highs,
        "low": lows,
        "close": closes,
        "volume": [1000.0] * num_bars
    })

def test_trident_strategy_evaluation():
    sm = SessionManager(start_str="00:00", end_str="23:59") # Force always in session for unit test
    rm = RiskManager(account_balance=10000.0, risk_percent=1.0)
    strategy = TridentStrategy(risk_manager=rm, session_manager=sm, doji_threshold=0.10)

    df_daily = create_mock_daily_df(220)
    
    # Construct M30 candles forming FVG -> Doji -> Confirmation
    base_time = datetime(2026, 7, 28, 4, 0, 0)
    t0 = base_time - timedelta(minutes=90)
    t1 = base_time - timedelta(minutes=60)
    t2 = base_time - timedelta(minutes=30)
    t3 = base_time
    t4 = base_time + timedelta(minutes=30)

    # Candle A (-3): High = 2374.00
    # Candle B (-2): Low = 2375.50, High = 2378.00
    # Candle C (-1): Low = 2380.50 -> FVG: Top = 2380.50, Bottom = 2374.00, CE = 2377.25
    c_a = {"time": t0, "open": 2370.0, "high": 2374.0, "low": 2368.0, "close": 2373.0, "volume": 100}
    c_b = {"time": t1, "open": 2376.0, "high": 2378.0, "low": 2375.5, "close": 2377.0, "volume": 100}
    c_c = {"time": t2, "open": 2377.0, "high": 2384.0, "low": 2380.5, "close": 2383.0, "volume": 100}

    # Doji (t3): Low <= CE (2377.0 <= 2377.25) & Close > CE (2377.30 > 2377.25)
    # Open = 2377.30, Close = 2377.30, High = 2382.00, Low = 2377.00
    c_doji = {"time": t3, "open": 2377.30, "high": 2382.00, "low": 2377.00, "close": 2377.30, "volume": 100}

    # Confirmation (t4): Close < High(Doji) (2379.0 < 2382.0)
    c_conf = {"time": t4, "open": 2380.00, "high": 2381.00, "low": 2376.00, "close": 2379.00, "volume": 100}

    df_m30 = pd.DataFrame([c_a, c_b, c_c, c_doji, c_conf])

    ctx = SymbolContext(symbol="XAUUSD")
    
    signal, reason = strategy.evaluate_signal("XAUUSD", df_daily, df_m30, ctx)

    assert signal is not None, f"Expected signal but got None: {reason}"
    assert signal.symbol == "XAUUSD"
    assert signal.direction == "BUY_LIMIT"
    assert signal.entry_price == 2380.50
    assert signal.stop_loss == 2375.50
    assert signal.calculated_lots > 0
