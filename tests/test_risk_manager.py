"""Tests for position sizing and the risk gates."""
import pytest

from python_bot.core.risk_manager import RiskManager
from python_bot.models import SymbolInfo

GOLD = SymbolInfo(name="XAUUSD", digits=2, point=0.01, tick_size=0.01,
                  tick_value=1.0, volume_min=0.01, volume_step=0.01,
                  volume_max=100.0, contract_size=100.0)

EURUSD = SymbolInfo(name="EURUSD", digits=5, point=0.00001, tick_size=0.00001,
                    tick_value=1.0, volume_min=0.01, volume_step=0.01,
                    volume_max=100.0, contract_size=100000.0)


def make_rm(**overrides) -> RiskManager:
    defaults = dict(
        risk_percent=1.0,
        account_balance=10000.0,
        max_stop_points={"XAUUSD": 600.0, "DEFAULT": 1000.0},
    )
    defaults.update(overrides)
    return RiskManager(**defaults)


# ------------------------------------------------------------------- sizing
def test_gold_stop_distance_and_lots():
    rm = make_rm()

    # Entry 2350.00, SL 2345.00: $5.00 = 500 points, under the 600-point cap.
    valid, msg = rm.validate_stop("XAUUSD", 2350.00, 2345.00, GOLD)
    assert valid is True, msg
    assert rm.stop_distance_points(2350.00, 2345.00, GOLD) == pytest.approx(500.0)

    # Risk 1% of $10,000 = $100. Loss per lot = (5.00 / 0.01) * $1 = $500.
    lots, reason = rm.calculate_lots("XAUUSD", 2350.00, 2345.00, GOLD)
    assert lots == pytest.approx(0.20), reason


def test_gold_excessive_stop_rejection():
    rm = make_rm()

    # $7.00 = 700 points > the 600-point cap.
    valid, msg = rm.validate_stop("XAUUSD", 2350.00, 2343.00, GOLD)
    assert valid is False
    assert "exceeds" in msg

    lots, _ = rm.calculate_lots("XAUUSD", 2350.00, 2343.00, GOLD)
    assert lots == 0.0


def test_forex_stop_distance_and_lots():
    rm = make_rm()

    # 50 pips = 500 points on a 5-digit pair, under the 1000-point default cap.
    valid, msg = rm.validate_stop("EURUSD", 1.1000, 1.0950, EURUSD)
    assert valid is True, msg

    # $100 risk over a $500-per-lot stop -> 0.20 lots.
    lots, reason = rm.calculate_lots("EURUSD", 1.1000, 1.0950, EURUSD)
    assert lots == pytest.approx(0.20), reason


def test_lots_are_floored_to_volume_step():
    rm = make_rm(risk_percent=0.75)  # $75 / $500 = 0.15 raw lots — exact step
    lots, _ = rm.calculate_lots("XAUUSD", 2350.00, 2345.00, GOLD)
    assert lots == pytest.approx(0.15)

    rm = make_rm(risk_percent=0.77)  # $77 / $500 = 0.154 -> floors to 0.15
    lots, _ = rm.calculate_lots("XAUUSD", 2350.00, 2345.00, GOLD)
    assert lots == pytest.approx(0.15)


def test_stop_below_broker_minimum_is_rejected():
    strict = SymbolInfo(name="XAUUSD", digits=2, point=0.01, tick_size=0.01,
                        tick_value=1.0, stops_level_points=100.0)
    rm = make_rm()
    valid, msg = rm.validate_stop("XAUUSD", 2350.00, 2349.50, strict)  # 50 points
    assert valid is False
    assert "broker minimum" in msg


def test_too_small_position_is_skipped_not_over_risked():
    rm = make_rm(account_balance=100.0)  # $1 risk over a $500-per-lot stop
    lots, reason = rm.calculate_lots("XAUUSD", 2350.00, 2345.00, GOLD)
    assert lots == 0.0
    assert "minimum" in reason


# ------------------------------------------------------------- daily gates
def test_daily_trade_limit_blocks_new_positions():
    rm = make_rm(max_daily_trades=2)
    for _ in range(2):
        rm.record_trade_opened()
    can, reason = rm.check_can_trade("XAUUSD", 0, 0)
    assert can is False
    assert "daily trade limit" in reason


def test_daily_loss_limit_halts_trading():
    rm = make_rm(max_daily_loss_percent=3.0)
    rm.record_trade_closed(-400.0)  # 4% of the $10,000 start balance
    can, reason = rm.check_can_trade("XAUUSD", 0, 0)
    assert can is False
    assert "daily loss limit" in reason


def test_position_caps():
    rm = make_rm(max_open_positions=2, max_positions_per_symbol=1)
    assert rm.check_can_trade("XAUUSD", 0, 0)[0] is True
    assert rm.check_can_trade("XAUUSD", 1, 1)[0] is False   # symbol cap
    assert rm.check_can_trade("EURUSD", 2, 0)[0] is False   # global cap


def test_roll_day_resets_counters():
    rm = make_rm()
    rm.record_trade_opened()
    rm.record_trade_closed(-50.0)
    assert rm.roll_day("2099-01-01") is True
    assert rm.daily.trades == 0
    assert rm.daily.realized_pnl == 0.0
    assert rm.roll_day("2099-01-01") is False  # same day -> no reset
