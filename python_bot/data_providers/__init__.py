"""
Data-provider registry.

``config.json -> general.data_provider`` picks one:

    "broker"     use the trading broker's own feed (DEFAULT, recommended)
    "twelvedata" TwelveData REST API
    "yfinance"   free yfinance data (delayed, 1m capped at ~7 days)
    "mock"       deterministic synthetic candles

ADDING A PROVIDER: subclass ``BaseDataProvider``, honour the contract documented
in ``base_provider.py``, then register it here.
"""
import logging
from typing import Dict, List, Type

from python_bot.data_providers.base_provider import BaseDataProvider
from python_bot.data_providers.broker_provider import BrokerDataProvider
from python_bot.data_providers.mock_provider import MockDataProvider
from python_bot.data_providers.twelvedata_provider import TwelveDataProvider
from python_bot.data_providers.yfinance_provider import YFinanceProvider

logger = logging.getLogger(__name__)

PROVIDER_REGISTRY: Dict[str, Type[BaseDataProvider]] = {
    "broker": BrokerDataProvider,
    "twelvedata": TwelveDataProvider,
    "yfinance": YFinanceProvider,
    "mock": MockDataProvider,
}


def register_provider(name: str, provider_cls: Type[BaseDataProvider]) -> None:
    if not issubclass(provider_cls, BaseDataProvider):
        raise TypeError(f"{provider_cls!r} must subclass BaseDataProvider")
    PROVIDER_REGISTRY[name.strip().lower()] = provider_cls


def available_providers() -> List[str]:
    return sorted(PROVIDER_REGISTRY.keys())


__all__ = [
    "BaseDataProvider",
    "BrokerDataProvider",
    "TwelveDataProvider",
    "YFinanceProvider",
    "MockDataProvider",
    "PROVIDER_REGISTRY",
    "register_provider",
    "available_providers",
]
