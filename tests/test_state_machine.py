"""Tests for the per-symbol context store and its JSON persistence."""
import os

from python_bot.core.state_machine import StateMachineManager
from python_bot.models import SymbolState


def test_state_machine_transitions_and_persistence(tmp_path):
    state_file = str(tmp_path / "test_state.json")
    sm = StateMachineManager(symbols=["XAUUSD", "EURUSD"], persistence_file=state_file)

    # Every symbol starts out scanning.
    ctx = sm.get_context("XAUUSD")
    assert ctx.state == SymbolState.SCANNING

    sm.set_state("XAUUSD", SymbolState.SETUP_FORMING, reason="HTF zone reached")
    assert ctx.state == SymbolState.SETUP_FORMING
    assert ctx.last_rejection_reason == "HTF zone reached"

    sm.save_state()
    assert os.path.exists(state_file)

    # A fresh manager must restore the persisted state.
    sm2 = StateMachineManager(symbols=["XAUUSD", "EURUSD"], persistence_file=state_file)
    assert sm2.get_context("XAUUSD").state == SymbolState.SETUP_FORMING
    assert sm2.get_context("EURUSD").state == SymbolState.SCANNING


def test_reset_clears_setup_but_keeps_position_slot():
    sm = StateMachineManager(symbols=["XAUUSD"], persistence_file="unused.json")
    ctx = sm.get_context("XAUUSD")
    ctx.strategy_data = {"zone": 39000.0}
    sm.set_state("XAUUSD", SymbolState.SETUP_FORMING)

    sm.reset_symbol("XAUUSD", reason="daily filter flipped")
    assert ctx.state == SymbolState.SCANNING
    assert ctx.strategy_data == {}


def test_unknown_symbol_gets_a_fresh_context():
    sm = StateMachineManager(symbols=["XAUUSD"], persistence_file="unused.json")
    ctx = sm.get_context("GBPUSD")
    assert ctx.symbol == "GBPUSD"
    assert ctx.state == SymbolState.SCANNING


def test_corrupt_state_file_falls_back_to_clean_state(tmp_path):
    state_file = tmp_path / "corrupt.json"
    state_file.write_text("{ this is not json", encoding="utf-8")

    sm = StateMachineManager(symbols=["XAUUSD"], persistence_file=str(state_file))
    assert sm.get_context("XAUUSD").state == SymbolState.SCANNING


def test_roll_day_resets_per_symbol_counters():
    sm = StateMachineManager(symbols=["XAUUSD"], persistence_file="unused.json")
    ctx = sm.get_context("XAUUSD")
    ctx.trading_day = "2026-07-29"
    ctx.trades_today = 3
    ctx.realized_pnl_today = -120.0

    assert sm.roll_day("2026-07-30") is True
    assert ctx.trades_today == 0
    assert ctx.realized_pnl_today == 0.0
    assert sm.roll_day("2026-07-30") is False
