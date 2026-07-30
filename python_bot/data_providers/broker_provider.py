"""
Broker-backed data provider — the default and strongly recommended source.

Decisions must be made on the SAME prices that will fill the orders. Mixing a
third-party feed with MT5 execution means your 1m candles disagree with your
broker's by a few points, which on a 1-minute scalp is the difference between a
signal and no signal.
"""
import logging
from typing import Optional

import pandas as pd

from python_bot.brokers.base_broker import BaseBroker
from python_bot.data_providers.base_provider import BaseDataProvider

logger = logging.getLogger(__name__)


class BrokerDataProvider(BaseDataProvider):
    def __init__(self, broker: BaseBroker):
        self.broker = broker

    @property
    def name(self) -> str:
        return f"broker:{self.broker.name}"

    def get_candles(self, symbol: str, timeframe: str, count: int = 300) -> Optional[pd.DataFrame]:
        try:
            return self.validate(self.broker.get_candles(symbol, timeframe, count))
        except Exception as exc:
            logger.error(f"[{self.name}] {symbol} {timeframe}: {exc}")
            return None
