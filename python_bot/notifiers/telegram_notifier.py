import logging
import requests
from python_bot.models import TradeSignal
from python_bot.notifiers.base_notifier import BaseNotifier

logger = logging.getLogger(__name__)

class TelegramNotifier(BaseNotifier):
    """
    Sends rich alert messages via Telegram Bot API.
    """
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    @property
    def name(self) -> str:
        return "telegram"

    def format_message(self, signal: TradeSignal) -> str:
        fvg = signal.fvg
        sym = signal.symbol
        is_gold = "XAU" in sym.upper() or "GOLD" in sym.upper()
        price_fmt = "{:.2f}" if is_gold or "JPY" in sym.upper() else "{:.5f}"

        entry_str = price_fmt.format(signal.entry_price)
        sl_str = price_fmt.format(signal.stop_loss)
        fvg_top_str = price_fmt.format(fvg.top)
        fvg_bot_str = price_fmt.format(fvg.bottom)
        fvg_ce_str = price_fmt.format(fvg.ce)

        dist_unit = "points" if is_gold else "pips/points"

        msg = (
            f"🚨 <b>TRIDENT STRATEGY ALERT</b> 🚨\n\n"
            f"📈 <b>Symbol</b>: <code>{signal.symbol}</code>\n"
            f"🎯 <b>Action</b>: <code>{signal.direction}</code>\n"
            f"📍 <b>Entry Price (FVG Top)</b>: <code>{entry_str}</code>\n"
            f"🛑 <b>Stop Loss (Candle B Low)</b>: <code>{sl_str}</code>\n"
            f"📏 <b>Risk Distance</b>: <code>{signal.risk_distance_points:.1f} {dist_unit}</code>\n"
            f"⚖️ <b>Risk %</b>: <code>{signal.risk_percent}%</code>\n"
            f"📦 <b>Calculated Size</b>: <code>{signal.calculated_lots:.2f} Lots</code>\n\n"
            f"🔍 <b>FVG Parameters</b>:\n"
            f"   • Top: <code>{fvg_top_str}</code>\n"
            f"   • Bottom: <code>{fvg_bot_str}</code>\n"
            f"   • CE Level: <code>{fvg_ce_str}</code>\n"
            f"   • FVG ID: <code>{fvg.id}</code>\n\n"
            f"🕒 <b>Time</b>: <code>{signal.timestamp.strftime('%Y-%m-%d %H:%M:%S')}</code>\n"
            f"💡 <b>Notes</b>: {signal.notes}"
        )
        return msg

    def send_signal(self, signal: TradeSignal) -> bool:
        if not self.bot_token or not self.chat_id:
            logger.warning("[TelegramNotifier] Token or Chat ID missing. Alert logged locally.")
            return False

        message_text = self.format_message(signal)
        payload = {
            "chat_id": self.chat_id,
            "text": message_text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }

        try:
            res = requests.post(self.api_url, json=payload, timeout=10)
            data = res.json()
            if data.get("ok"):
                logger.info(f"[TelegramNotifier] Signal alert sent for {signal.symbol} successfully!")
                return True
            else:
                logger.error(f"[TelegramNotifier] Telegram API error: {data.get('description')}")
                return False
        except Exception as e:
            logger.error(f"[TelegramNotifier] Request exception: {e}")
            return False
