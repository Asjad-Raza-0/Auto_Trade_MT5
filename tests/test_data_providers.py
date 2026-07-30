"""Tests for the data-provider contract via the mock provider."""
from python_bot.data_providers.base_provider import REQUIRED_COLUMNS, BaseDataProvider
from python_bot.data_providers.mock_provider import MockDataProvider

from tests.conftest import bullish_ltf_frame


def test_generated_candles_honour_the_contract():
    provider = MockDataProvider()
    df = provider.get_candles("XAUUSD", "30m", count=50)

    assert df is not None
    assert len(df) == 50
    assert list(df.columns) == REQUIRED_COLUMNS
    assert (df["high"] >= df["low"]).all()
    assert (df["high"] >= df[["open", "close"]].max(axis=1)).all()
    assert (df["low"] <= df[["open", "close"]].min(axis=1)).all()
    assert df["time"].is_monotonic_increasing, "candles must be oldest first"


def test_generation_is_deterministic():
    a = MockDataProvider(seed=7).get_candles("EURUSD", "1m", count=30)
    b = MockDataProvider(seed=7).get_candles("EURUSD", "1m", count=30)
    assert a.equals(b), "same seed must produce identical data"


def test_preset_candles_are_returned_verbatim():
    provider = MockDataProvider()
    frame = bullish_ltf_frame()
    provider.set_candles("US30", "1m", frame)

    df = provider.get_candles("US30", "1m", count=len(frame))
    assert df is not None
    assert len(df) == len(frame)
    assert df["close"].iloc[-1] == frame["close"].iloc[-1]

    # Requesting fewer bars returns only the newest ones.
    tail = provider.get_candles("US30", "1m", count=5)
    assert len(tail) == 5
    assert tail["close"].iloc[-1] == frame["close"].iloc[-1]


def test_validate_rejects_broken_frames():
    frame = bullish_ltf_frame()
    assert BaseDataProvider.validate(None) is None
    assert BaseDataProvider.validate(frame.iloc[0:0]) is None
    assert BaseDataProvider.validate(frame.drop(columns=["volume"])) is None
    assert BaseDataProvider.validate(frame) is not None
