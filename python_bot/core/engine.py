import time
import asyncio
import logging
from typing import List, Dict, Optional
from datetime import datetime

from python_bot.config import Config
from python_bot.models import TradeSignal, SymbolState
from python_bot.core.session_manager import SessionManager
from python_bot.core.risk_manager import RiskManager
from python_bot.core.state_machine import StateMachineManager
from python_bot.strategies.base_strategy import BaseStrategy
from python_bot.strategies.trident_strategy import TridentStrategy
from python_bot.data_providers.base_provider import BaseDataProvider
from python_bot.data_providers.twelvedata_provider import TwelveDataProvider
from python_bot.data_providers.yfinance_provider import YFinanceProvider
from python_bot.data_providers.mock_provider import MockDataProvider
from python_bot.notifiers.base_notifier import BaseNotifier
from python_bot.notifiers.telegram_notifier import TelegramNotifier
from python_bot.notifiers.discord_notifier import DiscordNotifier
from python_bot.notifiers.console_notifier import ConsoleNotifier

logger = logging.getLogger(__name__)

class MarketEngine:
    """
    Main Market Engine managing data fetching, strategy evaluation,
    multi-symbol priority execution, and notification delivery.
    """
    def __init__(self, config: Config, data_provider: Optional[BaseDataProvider] = None,
                 strategy: Optional[BaseStrategy] = None, notifiers: Optional[List[BaseNotifier]] = None):
        self.config = config
        self.session_mgr = SessionManager(
            start_str=config.strategy_params.get("session_start_ny", "03:00"),
            end_str=config.strategy_params.get("session_end_ny", "06:30"),
            tz_name=config.strategy_params.get("session_timezone", "America/New_York")
        )
        self.risk_mgr = RiskManager(
            account_balance=config.account_balance,
            risk_percent=config.risk_percent,
            max_stop_gold_points=config.strategy_params.get("max_stop_gold_points", 600.0),
            max_stop_forex_pips=config.strategy_params.get("max_stop_forex_pips", 100.0)
        )
        self.state_mgr = StateMachineManager(
            symbols=config.symbols,
            persistence_file=config.state_persistence_file
        )

        # Initialize Strategy
        self.strategy = strategy or TridentStrategy(
            risk_manager=self.risk_mgr,
            session_manager=self.session_mgr,
            doji_threshold=config.strategy_params.get("doji_threshold", 0.10)
        )

        # Initialize Data Provider
        if data_provider:
            self.data_provider = data_provider
        else:
            p_name = config.data_provider_name.lower()
            if p_name == "twelvedata":
                self.data_provider = TwelveDataProvider(api_key=config.twelvedata_api_key)
            elif p_name == "yfinance":
                self.data_provider = YFinanceProvider(symbol_mapping=config.data.get("yfinance", {}).get("symbol_mapping"))
            elif p_name == "mock":
                self.data_provider = MockDataProvider()
            else:
                logger.warning(f"Unknown data provider '{p_name}'. Falling back to YFinance Provider.")
                self.data_provider = YFinanceProvider()

        # Initialize Notifiers
        if notifiers:
            self.notifiers = notifiers
        else:
            self.notifiers = [ConsoleNotifier()]
            if config.telegram_enabled and config.telegram_bot_token and config.telegram_chat_id:
                self.notifiers.append(TelegramNotifier(config.telegram_bot_token, config.telegram_chat_id))
            if config.discord_enabled and config.discord_webhook_url:
                self.notifiers.append(DiscordNotifier(config.discord_webhook_url))

        self.last_traded_m30_candle: Optional[datetime] = None

    def broadcast_signal(self, signal: TradeSignal):
        logger.info(f"Broadcasting Trade Signal for {signal.symbol} across {len(self.notifiers)} channels...")
        for n in self.notifiers:
            try:
                n.send_signal(signal)
            except Exception as e:
                logger.error(f"Notifier {n.name} failed: {e}")

    def run_scan_cycle(self):
        """
        Executes a single market scan cycle over all configured symbols.
        Respects multi-symbol priority rule.
        """
        ny_now = self.session_mgr.get_ny_now()
        is_dst = self.session_mgr.is_dst_active()
        logger.info(f"--- Starting Scan Cycle | NY Time: {ny_now.strftime('%Y-%m-%d %H:%M:%S %Z')} (DST: {is_dst}) ---")

        # 1. Check if past session expiry (06:30 NY)
        if self.session_mgr.is_session_expired():
            logger.info("Past session end time (06:30 NY). Expiring/cancelling pending state for all symbols...")
            for sym in self.config.symbols:
                ctx = self.state_mgr.get_context(sym)
                if ctx.state in [SymbolState.PLACE_PENDING_ORDER, SymbolState.WAIT_FOR_CONFIRMATION, SymbolState.WAIT_FOR_DOJI]:
                    self.state_mgr.reset_symbol(sym, reason="Session expired at 06:30 NY")
            return

        # 2. Iterate symbols in configured priority order
        symbol_signal_found = False

        for symbol in self.config.symbols:
            ctx = self.state_mgr.get_context(symbol)

            # Fetch Daily and M30 candles
            df_daily = self.data_provider.get_candles(symbol, "1d", outputsize=250)
            df_m30 = self.data_provider.get_candles(symbol, "30m", outputsize=100)

            if df_daily is None or df_m30 is None:
                logger.warning(f"[{symbol}] Could not retrieve price data from {self.data_provider.name}. Skipping cycle.")
                continue

            last_m30_time = df_m30.iloc[-1]["time"] if "time" in df_m30.columns else df_m30.iloc[-1].name
            if isinstance(last_m30_time, str):
                last_m30_time = datetime.fromisoformat(last_m30_time)

            ctx.last_processed_m30_time = last_m30_time

            # Multi-symbol rule check: If signal already triggered on this same M30 candle for a prior symbol, skip
            if self.last_traded_m30_candle == last_m30_time:
                logger.info(f"[{symbol}] Signal already processed on current completed M30 candle ({last_m30_time}). Skipping priority.")
                continue

            # Evaluate Strategy
            signal, reason = self.strategy.evaluate_signal(symbol, df_daily, df_m30, ctx)

            if signal is not None:
                # Check duplicate signal on same candle
                if ctx.last_signal_candle_time == last_m30_time:
                    logger.info(f"[{symbol}] Signal already sent for M30 candle {last_m30_time}")
                    continue

                logger.info(f"🎯 VALID TRIDENT SIGNAL GENERATED FOR {symbol}!")
                ctx.last_signal_candle_time = last_m30_time
                self.last_traded_m30_candle = last_m30_time
                self.state_mgr.save_state()

                # Broadcast alert
                self.broadcast_signal(signal)

                # Stop processing other symbols on this candle per multi-symbol rule
                symbol_signal_found = True
                break
            else:
                logger.debug(f"[{symbol}] Status: {ctx.state.value} | Note: {reason}")

    async def start_async_loop(self):
        """Runs the continuous async scanner loop."""
        logger.info(f"Starting Trading Alert Bot async loop with {self.config.scan_interval}s interval...")
        while True:
            try:
                self.run_scan_cycle()
            except Exception as e:
                logger.error(f"Error in scan cycle: {e}", exc_info=True)
            await asyncio.sleep(self.config.scan_interval)
