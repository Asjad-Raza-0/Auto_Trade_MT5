import pytest
from python_bot.core.risk_manager import RiskManager

def test_gold_stop_distance_and_lots():
    rm = RiskManager(account_balance=10000.0, risk_percent=1.0, max_stop_gold_points=600.0)
    
    # Gold entry 2350.00, SL 2345.00 ($5.00 diff = 500 points <= 600 max points)
    valid, msg = rm.validate_stop_distance("XAUUSD", 2350.00, 2345.00)
    assert valid is True

    pts = rm.calculate_stop_distance_points("XAUUSD", 2350.00, 2345.00)
    assert pts == 500.0

    # Risk 1% of $10,000 = $100.
    # Gold loss per lot for $5.00 diff = $500.
    # Raw lots = $100 / $500 = 0.20 lots.
    lots = rm.calculate_lot_size("XAUUSD", 2350.00, 2345.00)
    assert lots == 0.20

def test_gold_excessive_stop_rejection():
    rm = RiskManager(account_balance=10000.0, risk_percent=1.0, max_stop_gold_points=600.0)
    
    # Gold entry 2350.00, SL 2343.00 ($7.00 diff = 700 points > 600 max points)
    valid, msg = rm.validate_stop_distance("XAUUSD", 2350.00, 2343.00)
    assert valid is False
    assert "exceeds limit" in msg

    lots = rm.calculate_lot_size("XAUUSD", 2350.00, 2343.00)
    assert lots == 0.0

def test_forex_stop_distance_and_lots():
    rm = RiskManager(account_balance=10000.0, risk_percent=1.0, max_stop_forex_pips=100.0)
    
    # EURUSD entry 1.1000, SL 1.0950 (50 pips <= 100 max pips)
    valid, msg = rm.validate_stop_distance("EURUSD", 1.1000, 1.0950)
    assert valid is True

    # Risk 1% of $10,000 = $100. 50 pips = 50 * $10 = $500 loss per lot.
    # Lots = 100 / 500 = 0.20 lots.
    lots = rm.calculate_lot_size("EURUSD", 1.1000, 1.0950)
    assert lots == 0.20
