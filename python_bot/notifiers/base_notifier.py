from abc import ABC, abstractmethod
from python_bot.models import TradeSignal

class BaseNotifier(ABC):
    """
    Abstract Interface for Notification Channels.
    """
    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def send_signal(self, signal: TradeSignal) -> bool:
        """
        Formats and sends a TradeSignal alert. Returns True if successfully sent.
        """
        pass
