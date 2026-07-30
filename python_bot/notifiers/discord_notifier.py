"""Discord webhook notifier."""
import logging
from typing import Iterable, Optional

import requests

from python_bot.models import Direction, TradeEvent, TradeEventType
from python_bot.notifiers.base_notifier import BaseNotifier
from python_bot.notifiers.formatting import DIRECTION_ICON, price_format, style_for

logger = logging.getLogger(__name__)

COLOURS = {
    TradeEventType.ENTRY: 3066993,       # green
    TradeEventType.PARTIAL_TP: 3447003,  # blue
    TradeEventType.TP_HIT: 2067276,      # dark green
    TradeEventType.SL_HIT: 15158332,     # red
    TradeEventType.BREAKEVEN: 10181046,  # purple
    TradeEventType.SCALED_IN: 15844367,  # gold
    TradeEventType.CLOSED: 9807270,      # grey
    TradeEventType.ERROR: 15105570,      # orange
}


class DiscordNotifier(BaseNotifier):
    def __init__(self, webhook_url: str, event_filter: Optional[Iterable[str]] = None,
                 timeout: float = 10.0):
        super().__init__(event_filter)
        self.webhook_url = webhook_url
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "discord"

    def send_event(self, event: TradeEvent) -> bool:
        if not self.webhook_url:
            return False

        icon, label = style_for(event)
        fmt = price_format(event.symbol)
        fields = []

        if event.direction is not Direction.NONE:
            fields.append({"name": "Direction", "value": DIRECTION_ICON[event.direction], "inline": True})
        if event.lots:
            fields.append({"name": "Size", "value": f"{event.lots:g} lots", "inline": True})
        if event.entry_price:
            fields.append({"name": "Entry", "value": fmt.format(event.entry_price), "inline": True})
        if event.stop_loss:
            fields.append({"name": "Stop loss", "value": fmt.format(event.stop_loss), "inline": True})
        if event.take_profit:
            fields.append({"name": "Take profit", "value": fmt.format(event.take_profit), "inline": True})
        if event.price and event.event_type is not TradeEventType.ENTRY:
            fields.append({"name": "Exit price", "value": fmt.format(event.price), "inline": True})
        if event.rr:
            fields.append({"name": "Result", "value": f"{event.rr:+.2f}R", "inline": True})
        if event.profit:
            fields.append({"name": "P/L", "value": f"{event.profit:+.2f}", "inline": True})
        if event.signal is not None and event.signal.confirmations:
            fields.append({"name": "Confirmations",
                           "value": ", ".join(event.signal.confirmations), "inline": False})
        if event.message:
            fields.append({"name": "Note", "value": event.message[:1024], "inline": False})

        embed = {
            "title": f"{icon} {label}: {event.symbol}",
            "color": COLOURS.get(event.event_type, 9807270),
            "fields": fields,
            "footer": {
                "text": f"{event.strategy_name or 'bot'} • "
                        f"{event.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC"
            },
        }

        try:
            response = requests.post(self.webhook_url, json={"embeds": [embed]}, timeout=self.timeout)
            if response.status_code in (200, 204):
                logger.info(f"[Discord] Sent {event.event_type.value} for {event.symbol}")
                return True
            logger.error(f"[Discord] Webhook error {response.status_code}: {response.text}")
            return False
        except Exception as exc:
            logger.error(f"[Discord] Request failed: {exc}")
            return False
