import os
import pytest
from python_bot.models import SymbolState
from python_bot.core.state_machine import StateMachineManager

def test_state_machine_transitions_and_persistence(tmp_path):
    test_file = str(tmp_path / "test_state.json")
    sm = StateMachineManager(symbols=["XAUUSD", "EURUSD"], persistence_file=test_file)

    # Initial state
    ctx = sm.get_context("XAUUSD")
    assert ctx.state == SymbolState.WAIT_FOR_DAILY_FILTER

    # Transition
    sm.set_state("XAUUSD", SymbolState.WAIT_FOR_DOJI, reason="Bullish FVG detected")
    assert ctx.state == SymbolState.WAIT_FOR_DOJI

    # Verify persistent file creation
    assert os.path.exists(test_file)

    # Load into new manager
    sm2 = StateMachineManager(symbols=["XAUUSD", "EURUSD"], persistence_file=test_file)
    ctx2 = sm2.get_context("XAUUSD")
    assert ctx2.state == SymbolState.WAIT_FOR_DOJI
