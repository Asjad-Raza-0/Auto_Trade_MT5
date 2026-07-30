"""
Notification abstraction.

Notifiers only ever format a ``TradeEvent`` — they know nothing about strategies.
That is why swapping the strategy never requires touching this layer.
"""
from abc import ABC, abstractmethod
from typing import Iterable, List, Optional, Set

from python_bot.models import TradeEvent, TradeEventType


class BaseNotifier(ABC):
    """
    Subclasses implement ``send_event``. ``event_filter`` decides which event
    types this channel cares about (None = everything).
    """

    def __init__(self, event_filter: Optional[Iterable[str]] = None):
        self.event_filter: Optional[Set[TradeEventType]] = None
        if event_filter is not None:
            self.event_filter = {
                value if isinstance(value, TradeEventType) else TradeEventType(value)
                for value in event_filter
            }

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def send_event(self, event: TradeEvent) -> bool:
        """Deliver the event. Return True on success."""

    def wants(self, event: TradeEvent) -> bool:
        return self.event_filter is None or event.event_type in self.event_filter


class NotifierHub:
    """
    Fans one event out to every channel, applying each channel's filter and
    never letting a broken channel break the trading loop.
    """

    def __init__(self, notifiers: Optional[List[BaseNotifier]] = None):
        self.notifiers: List[BaseNotifier] = list(notifiers or [])

    def add(self, notifier: BaseNotifier) -> None:
        self.notifiers.append(notifier)

    def notify(self, event: TradeEvent) -> None:
        import logging

        logger = logging.getLogger(__name__)
        for notifier in self.notifiers:
            if not notifier.wants(event):
                continue
            try:
                notifier.send_event(event)
            except Exception as exc:
                logger.error(
                    f"[NotifierHub] {notifier.name} failed on {event.event_type.value}: {exc}"
                )

    def notify_all(self, events: Iterable[TradeEvent]) -> None:
        for event in events:
            self.notify(event)

    @property
    def channel_names(self) -> List[str]:
        return [n.name for n in self.notifiers]
