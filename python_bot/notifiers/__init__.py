"""
Notification channels.

ADDING A CHANNEL: subclass ``BaseNotifier``, implement ``send_event``, then add
it to the hub in ``python_bot/core/engine.py::MarketEngine._build_notifiers``.
Which event types a channel receives is controlled per-channel in ``config.json``
via ``notify_events``.
"""
from python_bot.notifiers.base_notifier import BaseNotifier, NotifierHub
from python_bot.notifiers.console_notifier import ConsoleNotifier
from python_bot.notifiers.discord_notifier import DiscordNotifier
from python_bot.notifiers.formatting import format_plain
from python_bot.notifiers.telegram_notifier import TelegramNotifier

__all__ = [
    "BaseNotifier",
    "NotifierHub",
    "ConsoleNotifier",
    "TelegramNotifier",
    "DiscordNotifier",
    "format_plain",
]
