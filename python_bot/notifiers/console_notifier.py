import logging
from python_bot.models import TradeSignal
from python_bot.notifiers.base_notifier import BaseNotifier

logger = logging.getLogger(__name__)

class ConsoleNotifier(BaseNotifier):
    """
    Fallback console & log file notifier.
    """
    @property
    def name(self) -> str:
        return "console"

    def send_signal(self, signal: TradeSignal) -> bool:
        msg = (
            f"\n======================================================\n"
            f"🚨 TRIDENT STRATEGY ALERT 🚨\n"
            f"Symbol: {signal.symbol} | Action: {signal.direction}\n"
            f"Entry: {signal.entry_price:.5f} | SL: {signal.stop_loss:.5f}\n"
            f"Risk Distance: {signal.risk_distance_points:.1f} pts | Risk: {signal.risk_percent}%\n"
            f"Calculated Lots: {signal.calculated_lots:.2f}\n"
            f"FVG CE: {signal.fvg.ce:.5f} | FVG ID: {signal.fvg.id}\n"
            f"Notes: {signal.notes}\n"
            f"======================================================\n"
        )
        logger.info(msg)
        print(msg)
        return True
