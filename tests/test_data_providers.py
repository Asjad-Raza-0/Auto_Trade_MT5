import pytest
import pandas as pd
from python_bot.data_providers.mock_provider import MockDataProvider

def test_mock_data_provider():
    provider = MockDataProvider()
    df = provider.get_candles("XAUUSD", "30m", outputsize=50)
    
    assert df is not None
    assert len(df) == 50
    assert list(df.columns) == ["time", "open", "high", "low", "close", "volume"]
    assert df["high"].max() >= df["low"].min()
