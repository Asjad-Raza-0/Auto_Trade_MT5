"""
Broker registry.

ADDING A BROKER: subclass ``BaseBroker``, then register it here. The engine picks
one by ``config.json -> general.broker``.
"""
import logging
from typing import Any, Dict, List, Type

from python_bot.brokers.base_broker import BaseBroker
from python_bot.brokers.mt5_broker import MT5Broker, MT5NotAvailableError
from python_bot.brokers.paper_broker import PaperBroker, classify_instrument, default_symbol_info

logger = logging.getLogger(__name__)

BROKER_REGISTRY: Dict[str, Type[BaseBroker]] = {}


def register_broker(name: str, broker_cls: Type[BaseBroker]) -> None:
    if not issubclass(broker_cls, BaseBroker):
        raise TypeError(f"{broker_cls!r} must subclass BaseBroker")
    BROKER_REGISTRY[name.strip().lower()] = broker_cls


def available_brokers() -> List[str]:
    return sorted(BROKER_REGISTRY.keys())


def build_broker(name: str, config: Dict[str, Any]) -> BaseBroker:
    """
    Build a broker from its config section.

    ``mt5``   -> keys: login, password, server, terminal_path, magic_number,
                 deviation_points
    ``paper`` -> keys: balance, currency, data_provider, magic_number,
                 exit_check_timeframe, spread_ticks, symbols
    """
    key = (name or "").strip().lower()
    if key not in BROKER_REGISTRY:
        raise KeyError(
            f"Unknown broker '{name}'. Registered: {', '.join(available_brokers())}"
        )
    return BROKER_REGISTRY[key](**config)


register_broker("mt5", MT5Broker)
register_broker("metatrader5", MT5Broker)
register_broker("paper", PaperBroker)
register_broker("dryrun", PaperBroker)

__all__ = [
    "BaseBroker",
    "MT5Broker",
    "MT5NotAvailableError",
    "PaperBroker",
    "BROKER_REGISTRY",
    "register_broker",
    "available_brokers",
    "build_broker",
    "classify_instrument",
    "default_symbol_info",
]
