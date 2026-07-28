import logging
import requests
from python_bot.models import TradeSignal
from python_bot.notifiers.base_notifier import BaseNotifier

logger = logging.getLogger(__name__)

class DiscordNotifier(BaseNotifier):
    """
    Sends signal alerts to Discord Webhook channel.
    """
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    @property
    def name(self) -> str:
        return "discord"

    def send_signal(self, signal: TradeSignal) -> bool:
        if not self.webhook_url:
            return False

        fvg = signal.fvg
        embed = {
            "title": f"🚨 TRIDENT STRATEGY ALERT: {signal.symbol}",
            "color": 3066993, # Green/Teal
            "fields": [
                {"name": "Action", "value": signal.direction, "inline": True},
                {"name": "Entry Price (FVG Top)", "value": f"{signal.entry_price:.5f}", "inline": True},
                {"name": "Stop Loss", "value": f"{signal.stop_loss:.5f}", "inline": True},
                {"name": "Risk %", "value": f"{signal.risk_percent}%", "inline": True},
                {"name": "Lots", "value": f"{signal.calculated_lots:.2f}", "inline": True},
                {"name": "Stop Distance", "value": f"{signal.risk_distance_points:.1f} pts", "inline": True},
                {"name": "FVG CE Level", "value": f"{fvg.ce:.5f}", "inline": False},
                {"name": "Notes", "value": signal.notes, "inline": False}
            ],
            "footer": {"text": f"TG Capital Trident Bot v2.0 • {signal.timestamp.strftime('%Y-%m-%d %H:%M:%S')}"}
        }

        payload = {"embeds": [embed]}
        try:
            res = requests.post(self.webhook_url, json=payload, timeout=10)
            if res.status_code in [200, 204]:
                logger.info(f"[DiscordNotifier] Alert sent for {signal.symbol}")
                return True
            else:
                logger.error(f"[DiscordNotifier] Discord webhook error: {res.status_code} {res.text}")
                return False
        except Exception as e:
            logger.error(f"[DiscordNotifier] Exception: {e}")
            return False
