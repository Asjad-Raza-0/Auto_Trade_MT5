"""Console / log-file notifier. Always enabled so nothing is ever lost."""
import logging
from typing import Iterable, List, Optional

from python_bot.models import TradeEvent
from python_bot.notifiers.base_notifier import BaseNotifier
from python_bot.notifiers.formatting import format_plain

logger = logging.getLogger(__name__)


class ConsoleNotifier(BaseNotifier):
    def __init__(self, event_filter: Optional[Iterable[str]] = None):
        super().__init__(event_filter)
        self.events: List[TradeEvent] = []   # kept in memory so tests can assert on them

    @property
    def name(self) -> str:
        return "console"

    def send_event(self, event: TradeEvent) -> bool:
        self.events.append(event)
        block = "\n" + "=" * 64 + "\n" + format_plain(event) + "\n" + "=" * 64
        for emit in (logger.info, print):
            try:
                emit(block)
            except (UnicodeEncodeError, OSError):
                # Windows consoles in a legacy code page choke on the emoji.
                emit(block.encode("ascii", "ignore").decode("ascii"))
        return True
