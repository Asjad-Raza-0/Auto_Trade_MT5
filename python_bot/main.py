import sys
import os
import argparse
import asyncio
import logging
from datetime import datetime

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from python_bot.config import Config
from python_bot.core.engine import MarketEngine
from python_bot.models import TradeSignal, FVG

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot_execution.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("TG_Capital_Bot")

def parse_args():
    parser = argparse.ArgumentParser(description="TG Capital London EMA Stack + FVG Trident Trading Alert Bot")
    parser.add_argument("--config", type=str, default="config.json", help="Path to config.json")
    parser.add_argument("--provider", type=str, choices=["twelvedata", "yfinance", "mock"], help="Override market data provider")
    parser.add_argument("--once", action="store_true", help="Run a single scan cycle and exit")
    parser.add_argument("--test-alert", action="store_true", help="Send a test alert notification to verify Telegram/Discord credentials")
    return parser.parse_args()

def main():
    args = parse_args()
    logger.info("==================================================================")
    logger.info("Starting TG Capital London EMA Stack + FVG Trident Trading Alert Bot v2.0")
    logger.info("==================================================================")

    config = Config(args.config)
    if args.provider:
        config.data["general"]["data_provider"] = args.provider

    engine = MarketEngine(config)

    if args.test_alert:
        logger.info("Sending test alert notification...")
        test_fvg = FVG(
            id="fvg_test_12345",
            symbol="XAUUSD",
            candle_c_time=datetime.utcnow(),
            top=2380.50,
            bottom=2374.00,
            size=6.50,
            ce=2377.25
        )
        test_sig = TradeSignal(
            symbol="XAUUSD",
            direction="BUY_LIMIT",
            entry_price=2380.50,
            stop_loss=2374.00,
            risk_percent=1.0,
            calculated_lots=0.20,
            risk_distance_points=600.0,
            fvg=test_fvg,
            timestamp=datetime.now(),
            strategy_name="trident_v2",
            notes="TEST ALERT VERIFICATION"
        )
        engine.broadcast_signal(test_sig)
        logger.info("Test alert broadcast completed.")
        return

    if args.once:
        logger.info("Running single scan cycle...")
        engine.run_scan_cycle()
        logger.info("Scan cycle completed.")
        return

    # Run async continuous scanner loop
    try:
        asyncio.run(engine.start_async_loop())
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received. Shutting down bot gracefully.")

if __name__ == "__main__":
    main()
