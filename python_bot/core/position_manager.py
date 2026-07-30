"""
Position lifecycle: open, manage, detect exits, emit events.

This is where "automatic trading with Telegram alerts on entry / target / stop"
actually happens. It sits between the strategy (which decides *what* to do) and
the broker (which does it), and it is the only place that turns broker state
changes into ``TradeEvent``s.

Exit classification order:
  1. the broker's own deal ``reason`` (MT5 reports SL / TP explicitly) — authoritative
  2. otherwise, compare the fill price against the position's SL/TP
  3. otherwise, fall back to the sign of the realised P/L
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

from python_bot.brokers.base_broker import BaseBroker
from python_bot.core.risk_manager import RiskManager
from python_bot.models import (
    BrokerPosition,
    ClosedDeal,
    Direction,
    ManagementAction,
    ManagementActionType,
    Position,
    SymbolContext,
    SymbolState,
    TradeEvent,
    TradeEventType,
    TradeSignal,
)

logger = logging.getLogger(__name__)


class PositionManager:
    def __init__(
        self,
        broker: BaseBroker,
        risk_manager: RiskManager,
        magic_number: int = 250730,
        order_comment_prefix: str = "scalp1m",
        deal_lookback_minutes: int = 240,
    ):
        self.broker = broker
        self.risk = risk_manager
        self.magic_number = int(magic_number)
        self.order_comment_prefix = order_comment_prefix
        self.deal_lookback_minutes = int(deal_lookback_minutes)
        # Deals already turned into events, so a restart never double-notifies.
        self._seen_deals: set = set()

    # ------------------------------------------------------------------ opening
    def open_position(
        self, signal: TradeSignal, broker_symbol: str, context: SymbolContext
    ) -> Tuple[Optional[Position], List[TradeEvent]]:
        """Place the market order described by ``signal``. Returns (position, events)."""
        comment = f"{self.order_comment_prefix} {signal.direction.value.lower()}"
        result = self.broker.place_market_order(
            symbol=broker_symbol,
            direction=signal.direction,
            lots=signal.calculated_lots,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            comment=comment,
            magic=self.magic_number,
        )

        if not result.ok:
            event = TradeEvent(
                event_type=TradeEventType.ERROR,
                symbol=signal.symbol,
                direction=signal.direction,
                title="ORDER REJECTED",
                message=f"{result.message} (retcode {result.retcode})",
                strategy_name=signal.strategy_name,
            )
            logger.error(f"[{signal.symbol}] Order rejected: {result.message}")
            return None, [event]

        fill_price = result.price or signal.entry_price
        filled_lots = result.volume or signal.calculated_lots

        # Resolve the real ticket: order_send returns an order/deal id, and the
        # position id can differ. Match on symbol + magic to be certain.
        ticket = self._resolve_ticket(broker_symbol, result.ticket)

        position = Position.from_signal(
            signal, ticket=ticket, fill_price=fill_price,
            lots=filled_lots, magic=self.magic_number,
        )
        context.position = position
        context.state = SymbolState.POSITION_OPEN
        context.trades_today += 1
        self.risk.record_trade_opened()

        slippage = (fill_price - signal.entry_price) * signal.direction.sign
        event = TradeEvent(
            event_type=TradeEventType.ENTRY,
            symbol=signal.symbol,
            direction=signal.direction,
            price=fill_price,
            entry_price=fill_price,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            lots=filled_lots,
            ticket=ticket,
            strategy_name=signal.strategy_name,
            signal=signal,
            message=(
                f"{signal.notes} | filled at {fill_price} "
                f"(slippage {slippage:+.5f} vs signal price {signal.entry_price})"
            ),
            metadata={"broker_symbol": broker_symbol, "signal": signal.to_dict()},
        )
        logger.info(
            f"[{signal.symbol}] OPENED #{ticket} {signal.direction.value} {filled_lots} lots "
            f"@ {fill_price} SL {signal.stop_loss} TP {signal.take_profit}"
        )
        return position, [event]

    def _resolve_ticket(self, broker_symbol: str, fallback: int) -> int:
        try:
            positions = self.broker.get_open_positions(symbol=broker_symbol, magic=self.magic_number)
            if positions:
                return max(p.ticket for p in positions)
        except Exception as exc:
            logger.warning(f"[PositionManager] Could not resolve ticket for {broker_symbol}: {exc}")
        return fallback

    # --------------------------------------------------------------- management
    def apply_actions(
        self, context: SymbolContext, actions: List[ManagementAction]
    ) -> List[TradeEvent]:
        """Execute strategy management actions against the broker."""
        position = context.position
        if position is None or not actions:
            return []

        events: List[TradeEvent] = []
        for action in actions:
            if action.action is ManagementActionType.MOVE_STOP:
                events += self._move_stop(position, action)
            elif action.action is ManagementActionType.MODIFY_TAKE_PROFIT:
                events += self._modify_tp(position, action)
            elif action.action is ManagementActionType.PARTIAL_CLOSE:
                events += self._partial_close(position, action)
            elif action.action is ManagementActionType.CLOSE:
                events += self._close(position, action)
            elif action.action is ManagementActionType.SCALE_IN:
                events += self._scale_in(context, position, action)
        return events

    def _move_stop(self, position: Position, action: ManagementAction) -> List[TradeEvent]:
        new_stop = action.price
        if new_stop is None:
            return []
        result = self.broker.modify_position(position.ticket, stop_loss=new_stop)
        if not result.ok:
            logger.error(f"[{position.symbol}] Failed to move stop to {new_stop}: {result.message}")
            return []

        position.stop_loss = new_stop
        if abs(new_stop - position.entry_price) < 1e-9:
            position.breakeven_done = True
        logger.info(f"[{position.symbol}] Stop moved to {new_stop} — {action.reason}")

        if action.event_type is None:
            return []
        return [TradeEvent(
            event_type=action.event_type,
            symbol=position.symbol,
            direction=position.direction,
            entry_price=position.entry_price,
            stop_loss=new_stop,
            take_profit=position.take_profit,
            lots=position.lots,
            ticket=position.ticket,
            strategy_name=position.strategy_name,
            message=action.reason,
        )]

    def _modify_tp(self, position: Position, action: ManagementAction) -> List[TradeEvent]:
        if action.price is None:
            return []
        result = self.broker.modify_position(position.ticket, take_profit=action.price)
        if not result.ok:
            logger.error(f"[{position.symbol}] Failed to modify TP: {result.message}")
            return []
        position.take_profit = action.price
        logger.info(f"[{position.symbol}] Take profit moved to {action.price} — {action.reason}")
        return []

    def _partial_close(self, position: Position, action: ManagementAction) -> List[TradeEvent]:
        volume = action.volume
        if volume is None:
            percent = action.percent if action.percent is not None else 50.0
            volume = position.initial_lots * (percent / 100.0)

        volume = self.broker.normalize_volume(position.symbol, volume)
        info = self.broker.get_symbol_info(position.symbol)
        remainder = round(position.lots - volume, 8)

        # Refuse a partial that would leave an untradeable remainder behind.
        if volume <= 0 or (info is not None and 0 < remainder < info.volume_min):
            logger.info(
                f"[{position.symbol}] Skipping partial close: position of {position.lots} lots "
                f"cannot be split (min volume {getattr(info, 'volume_min', 'n/a')}). "
                f"Letting the runner go to the final target instead."
            )
            position.partial_done = True   # do not retry every bar
            return []

        result = self.broker.close_position(position.ticket, volume=volume)
        if not result.ok:
            logger.error(f"[{position.symbol}] Partial close failed: {result.message}")
            return []

        position.lots = remainder
        position.partial_done = True
        exit_price = result.price or (action.metadata or {}).get("target", 0.0)
        rr = position.rr_at(exit_price) if exit_price else 0.0
        profit = self._deal_profit_for(position.ticket, volume)

        logger.info(
            f"[{position.symbol}] PARTIAL CLOSE {volume} lots @ {exit_price} "
            f"({rr:+.2f}R) — {action.reason}"
        )
        return [TradeEvent(
            event_type=action.event_type or TradeEventType.PARTIAL_TP,
            symbol=position.symbol,
            direction=position.direction,
            price=exit_price,
            entry_price=position.entry_price,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            lots=volume,
            profit=profit,
            rr=rr,
            ticket=position.ticket,
            strategy_name=position.strategy_name,
            message=f"{action.reason} | {remainder:g} lots still running to {position.take_profit}",
        )]

    def _close(self, position: Position, action: ManagementAction) -> List[TradeEvent]:
        result = self.broker.close_position(position.ticket)
        if not result.ok:
            logger.error(f"[{position.symbol}] Close failed: {result.message}")
            return []
        # The closure itself is reported by ``sync()`` from the broker's deal
        # record, which carries the authoritative price and P/L.
        logger.info(f"[{position.symbol}] Close requested — {action.reason}")
        position.metadata["close_reason"] = action.reason
        return []

    def _scale_in(
        self, context: SymbolContext, position: Position, action: ManagementAction
    ) -> List[TradeEvent]:
        """
        Opens an additional position in the same direction. The extra position is
        managed by its server-side SL/TP only (no partial/breakeven handling), and
        is tracked in ``context.strategy_data['scale_in_tickets']``.
        """
        info = self.broker.get_symbol_info(position.symbol)
        lots = self.broker.normalize_volume(position.symbol, position.initial_lots)
        if lots <= 0 or info is None:
            return []

        result = self.broker.place_market_order(
            symbol=position.symbol,
            direction=position.direction,
            lots=lots,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            comment=f"{self.order_comment_prefix} scale",
            magic=self.magic_number,
        )
        if not result.ok:
            logger.error(f"[{position.symbol}] Scale-in rejected: {result.message}")
            return []

        position.scale_in_count += 1
        tickets = context.strategy_data.setdefault("scale_in_tickets", [])
        tickets.append(result.ticket)
        self.risk.record_trade_opened()

        logger.info(f"[{position.symbol}] SCALED IN {lots} lots @ {result.price} — {action.reason}")
        return [TradeEvent(
            event_type=TradeEventType.SCALED_IN,
            symbol=position.symbol,
            direction=position.direction,
            price=result.price,
            entry_price=result.price,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            lots=lots,
            ticket=result.ticket,
            strategy_name=position.strategy_name,
            message=action.reason,
        )]

    # ---------------------------------------------------------------- syncing
    def sync(self, contexts: Dict[str, SymbolContext]) -> List[TradeEvent]:
        """
        Reconcile tracked positions against the broker, every cycle.

        Emits TP_HIT / SL_HIT / CLOSED for anything that disappeared, and keeps
        SL/TP/volume in step with the broker when they were changed externally.
        """
        try:
            open_positions = self.broker.get_open_positions(magic=self.magic_number)
        except Exception as exc:
            logger.error(f"[PositionManager] Could not read open positions: {exc}")
            return []

        by_ticket: Dict[int, BrokerPosition] = {p.ticket: p for p in open_positions}
        deals = self._recent_deals()
        events: List[TradeEvent] = []

        for context in contexts.values():
            position = context.position
            if position is None:
                continue

            live = by_ticket.get(position.ticket)
            if live is not None:
                # Still open — trust the broker for SL/TP/volume.
                position.stop_loss = live.stop_loss or position.stop_loss
                position.take_profit = live.take_profit or position.take_profit
                position.lots = live.lots
                if abs(position.stop_loss - position.entry_price) < 1e-9:
                    position.breakeven_done = True
                context.state = SymbolState.POSITION_OPEN
                continue

            # Gone from the broker: it was closed.
            event = self._closure_event(position, deals.get(position.ticket, []))
            events.append(event)
            self.risk.record_trade_closed(event.profit)
            context.realized_pnl_today += event.profit
            context.position = None
            context.state = SymbolState.SCANNING
            logger.info(
                f"[{position.symbol}] Position #{position.ticket} closed as "
                f"{event.event_type.value} ({event.rr:+.2f}R, P/L {event.profit:+.2f})"
            )

        return events

    def _recent_deals(self) -> Dict[int, List[ClosedDeal]]:
        since = datetime.utcnow() - timedelta(minutes=self.deal_lookback_minutes)
        try:
            deals = self.broker.get_closed_deals(since)
        except Exception as exc:
            logger.warning(f"[PositionManager] Could not read deal history: {exc}")
            return {}

        grouped: Dict[int, List[ClosedDeal]] = {}
        for deal in deals:
            grouped.setdefault(deal.position_ticket, []).append(deal)
        return grouped

    def _closure_event(self, position: Position, deals: List[ClosedDeal]) -> TradeEvent:
        """Turn a vanished position into a classified TP/SL/CLOSED event."""
        # Only count deals not already reported (partial closes emit their own event).
        fresh = [d for d in deals if d.deal_ticket not in self._seen_deals]
        for deal in fresh:
            self._seen_deals.add(deal.deal_ticket)

        profit = sum(d.profit for d in fresh)
        volume = sum(d.volume for d in fresh) or position.lots
        final = fresh[-1] if fresh else None
        exit_price = final.price if final else position.stop_loss
        reason_note = position.metadata.get("close_reason", "")

        event_type, title = self._classify(position, final, exit_price, profit)
        rr = position.rr_at(exit_price) if exit_price else 0.0

        message = reason_note or (
            f"closed by broker ({final.reason})" if final else "closed (no deal record found)"
        )
        if position.partial_done:
            message += " | TP1 was already banked earlier"

        return TradeEvent(
            event_type=event_type,
            symbol=position.symbol,
            direction=position.direction,
            price=exit_price,
            entry_price=position.entry_price,
            stop_loss=position.stop_loss,
            take_profit=position.take_profit,
            lots=volume,
            profit=profit,
            rr=rr,
            ticket=position.ticket,
            strategy_name=position.strategy_name,
            title=title,
            message=message,
        )

    def _classify(
        self,
        position: Position,
        final: Optional[ClosedDeal],
        exit_price: float,
        profit: float,
    ) -> Tuple[TradeEventType, str]:
        # 1. Broker-reported reason is authoritative.
        if final is not None:
            if final.reason == "TP":
                return TradeEventType.TP_HIT, ""
            if final.reason == "SL":
                if position.breakeven_done and abs(exit_price - position.entry_price) < 1e-9:
                    return TradeEventType.CLOSED, "STOPPED AT BREAKEVEN"
                return TradeEventType.SL_HIT, ""

        # 2. Compare the exit price against the levels.
        if exit_price > 0:
            tolerance = max(position.initial_risk * 0.05, 1e-9)
            if position.take_profit and abs(exit_price - position.take_profit) <= tolerance:
                return TradeEventType.TP_HIT, ""
            if position.stop_loss and abs(exit_price - position.stop_loss) <= tolerance:
                if position.breakeven_done and abs(position.stop_loss - position.entry_price) < 1e-9:
                    return TradeEventType.CLOSED, "STOPPED AT BREAKEVEN"
                return TradeEventType.SL_HIT, ""

        # 3. Fall back to the P/L sign.
        if profit > 0:
            return TradeEventType.TP_HIT, "CLOSED IN PROFIT"
        if profit < 0:
            return TradeEventType.SL_HIT, "CLOSED AT A LOSS"
        return TradeEventType.CLOSED, ""

    def _deal_profit_for(self, ticket: int, volume: float) -> float:
        """Realised P/L of the most recent unreported deal on ``ticket``."""
        deals = self._recent_deals().get(ticket, [])
        fresh = [d for d in deals if d.deal_ticket not in self._seen_deals]
        if not fresh:
            return 0.0
        for deal in fresh:
            self._seen_deals.add(deal.deal_ticket)
        return sum(d.profit for d in fresh)

    # ------------------------------------------------------------------- utils
    def close_all(self) -> List[Tuple[int, bool, str]]:
        """Flatten every position this bot owns. Used by ``--close-all``."""
        results: List[Tuple[int, bool, str]] = []
        for position in self.broker.get_open_positions(magic=self.magic_number):
            result = self.broker.close_position(position.ticket)
            results.append((position.ticket, result.ok, result.message))
            logger.info(
                f"[CloseAll] #{position.ticket} {position.symbol}: "
                f"{'closed' if result.ok else 'FAILED — ' + result.message}"
            )
        return results

    def adopt_orphans(self, contexts: Dict[str, SymbolContext],
                      symbol_map: Dict[str, str]) -> List[str]:
        """
        After a restart, re-attach to positions the bot opened previously but is no
        longer tracking, so they are still managed and still reported. Returns
        notes for the log.
        """
        tracked = {c.position.ticket for c in contexts.values() if c.position}
        reverse = {broker: logical for logical, broker in symbol_map.items()}
        notes: List[str] = []

        for live in self.broker.get_open_positions(magic=self.magic_number):
            if live.ticket in tracked:
                continue
            logical = reverse.get(live.symbol)
            if logical is None or logical not in contexts:
                notes.append(
                    f"#{live.ticket} on {live.symbol} is not a configured symbol — left alone"
                )
                continue

            context = contexts[logical]
            if context.position is not None:
                continue

            risk = abs(live.entry_price - live.stop_loss) if live.stop_loss else 0.0
            context.position = Position(
                ticket=live.ticket,
                symbol=logical,
                direction=live.direction,
                entry_price=live.entry_price,
                stop_loss=live.stop_loss,
                take_profit=live.take_profit,
                lots=live.lots,
                initial_lots=live.lots,
                initial_stop_loss=live.stop_loss or live.entry_price - risk * live.direction.sign,
                opened_at=live.opened_at or datetime.utcnow(),
                breakeven_done=bool(live.stop_loss) and abs(live.stop_loss - live.entry_price) < 1e-9,
                # Unknown whether TP1 was banked, so assume it was: never
                # partial-close a position twice.
                partial_done=True,
                strategy_name="adopted",
                magic=live.magic,
            )
            context.state = SymbolState.POSITION_OPEN
            notes.append(
                f"adopted #{live.ticket} {live.direction.value} {live.lots} {live.symbol} "
                f"@ {live.entry_price} (SL {live.stop_loss} TP {live.take_profit})"
            )
        return notes
