"""Telegram Bot API notifier."""
import logging
from typing import Iterable, Optional

import requests

from python_bot.models import Direction, TradeEvent, TradeEventType
from python_bot.notifiers.base_notifier import BaseNotifier
from python_bot.notifiers.formatting import DIRECTION_ICON, price_format, style_for

logger = logging.getLogger(__name__)


class TelegramNotifier(BaseNotifier):
    def __init__(self, bot_token: str, chat_id: str,
                 event_filter: Optional[Iterable[str]] = None, timeout: float = 10.0):
        super().__init__(event_filter)
        self.bot_token = bot_token
        self.chat_id = str(chat_id)
        self.timeout = timeout
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"

    @property
    def name(self) -> str:
        return "telegram"

    def format_message(self, event: TradeEvent) -> str:
        icon, label = style_for(event)
        fmt = price_format(event.symbol)
        rows = [f"{icon} <b>{label}</b>", f"<b>{event.symbol}</b>"]

        if event.direction is not Direction.NONE:
            rows.append(DIRECTION_ICON[event.direction])
        rows.append("")

        if event.event_type is TradeEventType.ENTRY:
            rows += [
                f"📍 Entry: <code>{fmt.format(event.entry_price)}</code>",
                f"🛑 Stop loss: <code>{fmt.format(event.stop_loss)}</code>",
                f"🏁 Take profit: <code>{fmt.format(event.take_profit)}</code>",
                f"📦 Size: <code>{event.lots:g}</code> lots",
            ]
            signal = event.signal
            if signal is not None:
                if signal.partial_take_profit:
                    rows.append(
                        f"🎯 TP1: <code>{fmt.format(signal.partial_take_profit)}</code> "
                        f"(close {signal.partial_close_percent:g}%, then SL → breakeven)"
                    )
                if signal.risk_reward:
                    rows.append(f"⚖️ Planned R:R: <code>1:{signal.risk_reward:.1f}</code>")
                if signal.confirmations:
                    rows.append(f"✅ Confirmations: <code>{', '.join(signal.confirmations)}</code>")
        else:
            if event.price:
                rows.append(f"💵 Exit price: <code>{fmt.format(event.price)}</code>")
            if event.lots:
                rows.append(f"📦 Volume: <code>{event.lots:g}</code> lots")
            if event.rr:
                rows.append(f"📊 Result: <code>{event.rr:+.2f}R</code>")
            if event.profit:
                sign = "🟢" if event.profit > 0 else "🔴"
                rows.append(f"{sign} P/L: <code>{event.profit:+.2f}</code>")

        if event.ticket:
            rows.append(f"🎫 Ticket: <code>#{event.ticket}</code>")
        if event.message:
            rows.append(f"\n💬 {event.message}")
        rows.append(f"\n🕒 {event.timestamp.strftime('%Y-%m-%d %H:%M:%S')} UTC")
        if event.strategy_name:
            rows.append(f"<i>{event.strategy_name}</i>")

        return "\n".join(rows)

    def send_event(self, event: TradeEvent) -> bool:
        if not self.bot_token or not self.chat_id:
            logger.warning("[Telegram] bot_token or chat_id missing — alert not sent.")
            return False

        payload = {
            "chat_id": self.chat_id,
            "text": self.format_message(event),
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        try:
            data = requests.post(self.api_url, json=payload, timeout=self.timeout).json()
            if data.get("ok"):
                logger.info(f"[Telegram] Sent {event.event_type.value} for {event.symbol}")
                return True
            logger.error(f"[Telegram] API error: {data.get('description')}")
            return False
        except Exception as exc:
            logger.error(f"[Telegram] Request failed: {exc}")
            return False
