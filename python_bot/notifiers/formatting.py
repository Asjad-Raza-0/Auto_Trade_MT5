"""
Shared event-to-text formatting so Telegram, Discord and the console all describe
a trade the same way.
"""
from typing import Tuple

from python_bot.models import Direction, TradeEvent, TradeEventType

EVENT_STYLE = {
    TradeEventType.ENTRY:      ("🟢", "TRADE TAKEN"),
    TradeEventType.PARTIAL_TP: ("🎯", "PARTIAL TARGET HIT"),
    TradeEventType.TP_HIT:     ("🏆", "TARGET HIT"),
    TradeEventType.SL_HIT:     ("🛑", "STOP LOSS HIT"),
    TradeEventType.BREAKEVEN:  ("🔒", "STOP MOVED TO BREAKEVEN"),
    TradeEventType.SCALED_IN:  ("➕", "SCALED IN"),
    TradeEventType.CLOSED:     ("⚪", "TRADE CLOSED"),
    TradeEventType.INFO:       ("ℹ️", "INFO"),
    TradeEventType.ERROR:      ("⚠️", "ERROR"),
}

DIRECTION_ICON = {Direction.LONG: "📈 BUY", Direction.SHORT: "📉 SELL", Direction.NONE: "—"}


def style_for(event: TradeEvent) -> Tuple[str, str]:
    icon, label = EVENT_STYLE.get(event.event_type, ("•", event.event_type.value))
    return icon, (event.title or label)


def price_format(symbol: str) -> str:
    """Digits sensible for the instrument, used for display only."""
    upper = symbol.upper()
    if any(token in upper for token in ("US30", "DJI", "NAS", "SPX", "US500", "GER", "DAX",
                                        "UK100", "JP225", "BTC", "ETH", "XAU", "XAG", "OIL")):
        return "{:.2f}"
    if "JPY" in upper:
        return "{:.3f}"
    return "{:.5f}"


def format_plain(event: TradeEvent) -> str:
    """Single multi-line plain-text rendering used by the console notifier."""
    icon, label = style_for(event)
    fmt = price_format(event.symbol)
    lines = [f"{icon} {label} — {event.symbol}"]

    if event.direction is not Direction.NONE:
        lines.append(f"  Direction     : {DIRECTION_ICON[event.direction]}")
    if event.lots:
        lines.append(f"  Size          : {event.lots:g} lots")
    if event.entry_price:
        lines.append(f"  Entry         : {fmt.format(event.entry_price)}")
    if event.stop_loss:
        lines.append(f"  Stop loss     : {fmt.format(event.stop_loss)}")
    if event.take_profit:
        lines.append(f"  Take profit   : {fmt.format(event.take_profit)}")
    if event.price and event.event_type is not TradeEventType.ENTRY:
        lines.append(f"  Exit price    : {fmt.format(event.price)}")
    if event.rr:
        lines.append(f"  Result        : {event.rr:+.2f}R")
    if event.profit:
        lines.append(f"  P/L           : {event.profit:+.2f}")
    if event.ticket:
        lines.append(f"  Ticket        : #{event.ticket}")

    signal = event.signal
    if signal is not None:
        if signal.partial_take_profit:
            lines.append(f"  TP1 (partial) : {fmt.format(signal.partial_take_profit)}"
                         f" ({signal.partial_close_percent:g}%)")
        if signal.confirmations:
            lines.append(f"  Confirmations : {', '.join(signal.confirmations)}")
        if signal.risk_reward:
            lines.append(f"  Planned R:R   : 1:{signal.risk_reward:.1f}")

    if event.message:
        lines.append(f"  Note          : {event.message}")
    if event.strategy_name:
        lines.append(f"  Strategy      : {event.strategy_name}")
    lines.append(f"  Time (UTC)    : {event.timestamp.strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(lines)
