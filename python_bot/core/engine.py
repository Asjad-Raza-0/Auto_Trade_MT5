"""
The trading engine — wires every layer together and owns the scan loop.

Per cycle:
  1. reconcile positions with the broker  -> TP_HIT / SL_HIT / CLOSED alerts
  2. refresh balance and roll daily counters
  3. for each symbol, if a NEW completed bar of the strategy's fastest timeframe:
       a. open position?  -> strategy.manage_position() -> broker actions
       b. no position?    -> strategy.evaluate() -> size -> place order -> ENTRY alert
  4. persist state

Step 1 runs every cycle so exit alerts are prompt; step 3 runs only on a new bar
so a signal can never fire twice on the same candle.

NOTHING in this file knows what the strategy actually does. Swapping the strategy
requires no change here.
"""
import asyncio
import logging
from datetime import date, datetime
from typing import Dict, List, Optional

import pandas as pd

from python_bot.brokers import build_broker
from python_bot.brokers.base_broker import BaseBroker
from python_bot.config import Config
from python_bot.core.position_manager import PositionManager
from python_bot.core.risk_manager import RiskManager
from python_bot.core.session_manager import SessionManager
from python_bot.core.state_machine import StateMachineManager
from python_bot.core.symbol_resolver import resolve_all
from python_bot.data_providers import PROVIDER_REGISTRY
from python_bot.data_providers.base_provider import BaseDataProvider
from python_bot.data_providers.broker_provider import BrokerDataProvider
from python_bot.models import SymbolContext, SymbolState, TradeEvent, TradeEventType
from python_bot.notifiers import (
    ConsoleNotifier,
    DiscordNotifier,
    NotifierHub,
    TelegramNotifier,
)
from python_bot.strategies import get_strategy
from python_bot.strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class MarketEngine:
    def __init__(
        self,
        config: Config,
        broker: Optional[BaseBroker] = None,
        strategy: Optional[BaseStrategy] = None,
        data_provider: Optional[BaseDataProvider] = None,
        notifier_hub: Optional[NotifierHub] = None,
    ):
        self.config = config
        self.strategy = strategy or get_strategy(config.strategy_name, config.strategy_params)
        self.broker = broker or build_broker(config.broker_name, self._broker_config())
        self.data_provider = data_provider or self._build_data_provider()

        # In --dry-run the candles come from an external feed (e.g. yfinance),
        # so give the paper broker that feed for fills and SL/TP simulation.
        # Never hand it a BrokerDataProvider — that would just call back into
        # the paper broker itself.
        if (
            getattr(self.broker, "name", "") == "paper"
            and getattr(self.broker, "data_provider", None) is None
            and not isinstance(self.data_provider, BrokerDataProvider)
        ):
            self.broker.data_provider = self.data_provider

        self.session = SessionManager(**config.session_config)
        self.risk = RiskManager(**config.risk_config)
        self.state = StateMachineManager(config.symbols, config.state_persistence_file)
        self.positions = PositionManager(
            broker=self.broker,
            risk_manager=self.risk,
            magic_number=config.magic_number,
        )
        self.notifiers = notifier_hub or self._build_notifiers()

        self.symbol_map: Dict[str, str] = {}   # logical -> broker symbol
        self._connected = False
        self._started = False

    # ------------------------------------------------------------------ wiring
    def _broker_config(self) -> Dict:
        name = self.config.broker_name.lower()
        if name in ("mt5", "metatrader5"):
            return self.config.mt5_config
        if name in ("paper", "dryrun"):
            return {
                "balance": self.config.risk_config["account_balance"],
                "magic_number": self.config.magic_number,
                "exit_check_timeframe": self.strategy.required_timeframes.get("ltf", "1m"),
                "symbols": self.config.symbols,
            }
        return {}

    def _build_data_provider(self) -> BaseDataProvider:
        name = self.config.data_provider_name.lower()
        if name == "broker":
            return BrokerDataProvider(self.broker)
        provider_cls = PROVIDER_REGISTRY.get(name)
        if provider_cls is None:
            logger.warning(
                f"Unknown data_provider '{name}' — falling back to the broker feed."
            )
            return BrokerDataProvider(self.broker)
        return provider_cls(**self.config.provider_config(name))

    def _build_notifiers(self) -> NotifierHub:
        hub = NotifierHub([ConsoleNotifier(self.config.console_events)])

        if self.config.telegram_enabled:
            token, chat_id = self.config.telegram_bot_token, self.config.telegram_chat_id
            if token and chat_id:
                hub.add(TelegramNotifier(token, chat_id, self.config.telegram_events))
            else:
                logger.warning(
                    "Telegram is enabled but TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID are missing "
                    "— set them in .env. Alerts will only go to the console."
                )

        if self.config.discord_enabled and self.config.discord_webhook_url:
            hub.add(DiscordNotifier(self.config.discord_webhook_url, self.config.discord_events))

        return hub

    # ------------------------------------------------------------------ startup
    def start(self) -> bool:
        """Connect, resolve symbols, adopt orphan positions. Returns False to abort."""
        if self._started:
            return True

        logger.info("=" * 70)
        logger.info(f"Strategy   : {self.strategy.display_name} [{self.strategy.name}]")
        logger.info(f"Timeframes : {self.strategy.required_timeframes}")
        logger.info(f"Broker     : {self.broker.name}")
        logger.info(f"Data feed  : {self.data_provider.name}")
        logger.info(f"Session    : {self.session.describe()}")
        logger.info(f"Alerts     : {', '.join(self.notifiers.channel_names)}")
        logger.info("=" * 70)

        if not self.broker.connect():
            logger.error("Broker connection failed — the bot cannot start.")
            return False
        self._connected = True

        if not self._resolve_symbols():
            return False

        self._refresh_balance()

        notes = self.positions.adopt_orphans(self.state.contexts, self.symbol_map)
        for note in notes:
            logger.info(f"[Startup] {note}")

        self.state.meta["last_start"] = datetime.utcnow().isoformat()
        self.state.save_state()
        self._started = True
        return True

    def _resolve_symbols(self) -> bool:
        try:
            available = self.broker.list_symbols()
        except Exception as exc:
            logger.error(f"Could not list broker symbols: {exc}")
            return False

        overrides = self.config.symbol_overrides
        if not self.config.auto_detect_symbols:
            # Strict mode: only exact names and explicit overrides.
            resolved, failures = {}, {}
            for logical in self.config.symbols:
                candidate = overrides.get(logical, logical)
                if candidate in available:
                    resolved[logical] = candidate
                else:
                    failures[logical] = (
                        f"'{candidate}' not offered by the broker and auto_detect_symbols is off"
                    )
        else:
            resolved, failures = resolve_all(self.config.symbols, available, overrides)

        for logical, reason in failures.items():
            logger.error(f"[Startup] {logical}: {reason}")
            self.state.get_context(logical).state = SymbolState.DISABLED
            self.state.get_context(logical).last_rejection_reason = reason

        if not resolved:
            logger.error(
                "None of the configured symbols could be resolved on this account. "
                "Run `python -m python_bot.main --list-symbols` to see the real names, "
                "then set mt5.symbol_overrides in config.json."
            )
            return False

        self.symbol_map = resolved
        for logical, broker_symbol in resolved.items():
            context = self.state.get_context(logical)
            context.broker_symbol = broker_symbol
            if context.state is SymbolState.DISABLED:
                context.state = SymbolState.SCANNING

            info = self.broker.get_symbol_info(broker_symbol)
            if info is None:
                logger.warning(f"[Startup] No contract specs for {broker_symbol} — sizing may fail.")
            elif not info.tradable:
                logger.error(f"[Startup] {broker_symbol} is not tradable on this account.")
                context.state = SymbolState.DISABLED
            else:
                logger.info(
                    f"[Startup] {logical} -> {broker_symbol}: digits {info.digits}, "
                    f"tick {info.tick_size} = {info.tick_value:.4f}/lot, "
                    f"volume {info.volume_min}-{info.volume_max} step {info.volume_step}"
                )
        return True

    def _refresh_balance(self) -> None:
        if not self.config.use_live_balance:
            return
        account = self.broker.get_account()
        if account is not None and account.balance > 0:
            self.risk.set_account_balance(account.balance)

    # -------------------------------------------------------------- scan cycle
    def run_scan_cycle(self) -> List[TradeEvent]:
        """One full pass. Returns the events emitted (handy for tests)."""
        if not self._started and not self.start():
            return []

        events: List[TradeEvent] = []

        # 1. Exits first, every cycle, so alerts are prompt.
        events += self.positions.sync(self.state.contexts)

        # 2. Balance + day roll.
        self._refresh_balance()
        today = str(date.today())
        self.risk.roll_day(today)
        self.state.roll_day(today)

        # 3. Per-symbol work.
        session_open, session_reason = self.session.is_open()
        for logical, broker_symbol in self.symbol_map.items():
            context = self.state.get_context(logical)
            if context.state is SymbolState.DISABLED:
                continue
            try:
                events += self._process_symbol(logical, broker_symbol, context,
                                               session_open, session_reason)
            except Exception as exc:
                logger.error(f"[{logical}] Scan failed: {exc}", exc_info=True)

        # 4. Persist and deliver.
        self.state.save_state()
        self.notifiers.notify_all(events)
        return events

    def _process_symbol(
        self,
        logical: str,
        broker_symbol: str,
        context: SymbolContext,
        session_open: bool,
        session_reason: str,
    ) -> List[TradeEvent]:
        data = self._fetch_data(broker_symbol)
        if data is None:
            context.last_rejection_reason = "market data unavailable"
            return []

        ltf_role = self._fastest_role()
        bar_time = _last_bar_time(data[ltf_role])
        if bar_time is None:
            return []

        # Only act on a NEW completed bar.
        previous = context.last_bar_times.get(ltf_role)
        if previous == bar_time.isoformat():
            return []
        context.last_bar_times[ltf_role] = bar_time.isoformat()

        # Manage an open position.
        if context.position is not None:
            actions = self.strategy.manage_position(logical, data, context, context.position)
            if actions:
                logger.info(
                    f"[{logical}] {len(actions)} management action(s): "
                    + "; ".join(f"{a.action.value} ({a.reason})" for a in actions)
                )
            return self.positions.apply_actions(context, actions)

        # Look for a new entry.
        if not session_open:
            context.last_rejection_reason = session_reason
            return []

        can_trade, gate_reason = self.risk.check_can_trade(
            logical, self.state.open_position_count(), self.state.positions_for(logical)
        )
        if not can_trade:
            context.state = SymbolState.COOLDOWN
            context.last_rejection_reason = gate_reason
            logger.info(f"[{logical}] Skipped: {gate_reason}")
            return []

        signal, reason = self.strategy.evaluate(logical, data, context)
        context.last_rejection_reason = reason

        if signal is None:
            context.state = SymbolState.SCANNING
            logger.debug(f"[{logical}] {reason}")
            return []

        logger.info(f"[{logical}] {reason}")
        return self._execute_signal(signal, broker_symbol, context, bar_time)

    def _execute_signal(self, signal, broker_symbol: str, context: SymbolContext,
                        bar_time: datetime) -> List[TradeEvent]:
        info = self.broker.get_symbol_info(broker_symbol)
        if info is None:
            logger.error(f"[{signal.symbol}] No contract specs — cannot size the trade.")
            return []

        # Price the entry off the live quote, not the last close, so SL/TP
        # distances reflect what the order will actually fill at.
        live_price = self.broker.get_current_price(broker_symbol, signal.direction)
        if live_price > 0:
            drift = (live_price - signal.entry_price) * signal.direction.sign
            if drift > 0 and abs(signal.entry_price - signal.stop_loss) > 0:
                drift_r = drift / abs(signal.entry_price - signal.stop_loss)
                if drift_r > 0.5:
                    reason = (
                        f"price already moved {drift_r:.2f}R past the signal price "
                        f"({signal.entry_price:.5f} -> {live_price:.5f}) — entry skipped"
                    )
                    context.last_rejection_reason = reason
                    logger.info(f"[{signal.symbol}] {reason}")
                    return []

        ok, rr_reason = self.risk.validate_risk_reward(
            signal.entry_price, signal.stop_loss, signal.take_profit
        )
        if not ok:
            context.last_rejection_reason = rr_reason
            logger.info(f"[{signal.symbol}] Skipped: {rr_reason}")
            return []

        lots, size_reason = self.risk.calculate_lots(
            signal.symbol, signal.entry_price, signal.stop_loss, info
        )
        if lots <= 0:
            context.last_rejection_reason = size_reason
            logger.info(f"[{signal.symbol}] Skipped: {size_reason}")
            return []

        signal.calculated_lots = lots
        signal.risk_percent = self.risk.risk_percent
        signal.risk_distance_points = self.risk.stop_distance_points(
            signal.entry_price, signal.stop_loss, info
        )
        signal.notes = f"{signal.notes} | {size_reason}"

        context.last_signal_bar_time = bar_time
        position, events = self.positions.open_position(signal, broker_symbol, context)
        if position is None:
            context.state = SymbolState.SCANNING
        return events

    # ------------------------------------------------------------------ helpers
    def _fastest_role(self) -> str:
        """The role whose timeframe is shortest — that is the bot's heartbeat."""
        roles = self.strategy.required_timeframes
        return min(roles, key=lambda role: _timeframe_minutes(roles[role]))

    def _fetch_data(self, broker_symbol: str) -> Optional[Dict[str, pd.DataFrame]]:
        data: Dict[str, pd.DataFrame] = {}
        for role, timeframe in self.strategy.required_timeframes.items():
            df = self.data_provider.get_candles(
                broker_symbol, timeframe, self.strategy.bars_for(role)
            )
            if df is None or len(df) == 0:
                logger.warning(f"[{broker_symbol}] No {timeframe} data from {self.data_provider.name}")
                return None
            data[role] = df
        return data

    # -------------------------------------------------------------------- loops
    async def start_async_loop(self) -> None:
        if not self.start():
            return
        interval = self.config.scan_interval
        logger.info(f"Scanning every {interval}s. Ctrl+C to stop.")
        while True:
            try:
                self.run_scan_cycle()
            except Exception as exc:
                logger.error(f"Scan cycle error: {exc}", exc_info=True)
            await asyncio.sleep(interval)

    def shutdown(self) -> None:
        try:
            self.state.save_state()
        finally:
            if self._connected:
                self.broker.disconnect()
                self._connected = False
        logger.info("Engine shut down. Open positions were left running on the broker.")

    # -------------------------------------------------------------------- info
    def status(self) -> Dict:
        account = self.broker.get_account() if self._connected else None
        return {
            "strategy": self.strategy.describe(),
            "broker": self.broker.name,
            "connected": self._connected,
            "account": account.__dict__ if account else None,
            "symbol_map": self.symbol_map,
            "risk": self.risk.describe(),
            "session": self.session.describe(),
            "symbols": self.state.summary(),
        }

    def send_test_alert(self) -> None:
        """Push one dummy event through every channel to prove credentials work."""
        symbol = self.config.symbols[0] if self.config.symbols else "US30"
        self.notifiers.notify(TradeEvent(
            event_type=TradeEventType.ENTRY,
            symbol=symbol,
            title="TEST ALERT",
            message="If you can read this, your notification channels are configured correctly.",
            strategy_name=self.strategy.display_name,
        ))


def _timeframe_minutes(timeframe: str) -> int:
    units = {"m": 1, "h": 60, "d": 1440, "w": 10080}
    text = (timeframe or "1m").strip()
    suffix = text[-1].lower()
    try:
        return int(text[:-1]) * units.get(suffix, 1)
    except ValueError:
        return 1


def _last_bar_time(df: pd.DataFrame) -> Optional[datetime]:
    if df is None or len(df) == 0 or "time" not in df.columns:
        return None
    value = df["time"].iloc[-1]
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return value if isinstance(value, datetime) else None
