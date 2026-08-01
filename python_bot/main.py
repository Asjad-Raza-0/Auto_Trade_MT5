"""
CLI entry point.

    python -m python_bot.main --list-symbols   # what your broker really calls things
    python -m python_bot.main --test-alert     # prove Telegram works
    python -m python_bot.main --dry-run --once # one cycle, simulated broker
    python -m python_bot.main --once           # one live cycle
    python -m python_bot.main                  # continuous live trading
    python -m python_bot.main --status         # account + position snapshot
    python -m python_bot.main --close-all      # flatten every bot position
"""
import argparse
import asyncio
import json
import logging
from logging.handlers import RotatingFileHandler
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from python_bot.config import Config          # noqa: E402
from python_bot.core.engine import MarketEngine  # noqa: E402

logger = logging.getLogger("scalp_bot")


def setup_logging(
    level: str,
    log_file: str,
    max_bytes: int = 10 * 1024 * 1024,
    backup_count: int = 5,
) -> None:
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    if log_file:
        try:
            handlers.append(
                RotatingFileHandler(
                    log_file,
                    maxBytes=max_bytes,
                    backupCount=backup_count,
                    encoding="utf-8",
                )
            )
        except OSError as exc:
            print(f"Warning: could not open log file {log_file}: {exc}")

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=handlers,
        force=True,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="1-Minute Structure Scalper — MetaTrader 5 auto-trading bot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--config", default="config.json", help="path to config.json")
    parser.add_argument("--env", default=".env", help="path to the .env file")
    parser.add_argument("--once", action="store_true", help="run one scan cycle and exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="use the simulated paper broker — places NO real orders")
    parser.add_argument("--list-symbols", action="store_true",
                        help="print the broker's symbol names and how they resolve, then exit")
    parser.add_argument("--test-alert", action="store_true",
                        help="send one test notification and exit")
    parser.add_argument("--status", action="store_true",
                        help="print account, symbol and position status as JSON, then exit")
    parser.add_argument("--close-all", action="store_true",
                        help="close every position this bot owns, then exit")
    parser.add_argument("--strategy", help="override general.strategy_name")
    parser.add_argument("--symbols", help="override general.symbols (comma-separated)")
    parser.add_argument("--log-level", help="DEBUG, INFO, WARNING or ERROR")
    parser.add_argument("--log-max-mb", type=int, help="max megabytes per log file before rotating (default: 10)")
    parser.add_argument("--log-backup-count", type=int, help="number of rotated log backups to keep (default: 5)")
    parser.add_argument("--clean-logs", action="store_true", help="truncate/delete active log files and exit")
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> Config:
    config = Config(args.config, args.env)
    if args.dry_run:
        config.data["general"]["broker"] = "paper"
        config.data["general"]["data_provider"] = "yfinance"
    if args.strategy:
        config.data["general"]["strategy_name"] = args.strategy
    if args.symbols:
        config.data["general"]["symbols"] = [s.strip() for s in args.symbols.split(",") if s.strip()]
    if args.log_level:
        config.data["general"]["log_level"] = args.log_level
    if args.log_max_mb is not None:
        config.data["general"]["log_max_mb"] = args.log_max_mb
    if args.log_backup_count is not None:
        config.data["general"]["log_backup_count"] = args.log_backup_count
    return config


def cmd_list_symbols(engine: MarketEngine) -> int:
    from python_bot.core.symbol_resolver import resolve_symbol

    if not engine.broker.connect():
        print("Could not connect to the broker.")
        return 1

    available = engine.broker.list_symbols()
    print(f"\nBroker '{engine.broker.name}' offers {len(available)} symbols.\n")

    print("Configured symbols resolve as follows:")
    overrides = engine.config.symbol_overrides
    for logical in engine.config.symbols:
        resolved, reason = resolve_symbol(logical, available, overrides.get(logical))
        marker = "OK " if resolved else "!! "
        print(f"  {marker}{logical:<12} -> {resolved or '(unresolved)'}   [{reason}]")

    print("\nSymbols matching your configured names (paste the right one into")
    print("config.json -> mt5.symbol_overrides if the guess above is wrong):")
    needles = [s.upper()[:3] for s in engine.config.symbols]
    matches = [s for s in available if any(n in s.upper() for n in needles)]
    for symbol in sorted(matches)[:60]:
        print(f"    {symbol}")
    if not matches:
        print("    (no close matches — here are the first 60 symbols on the account)")
        for symbol in sorted(available)[:60]:
            print(f"    {symbol}")

    engine.broker.disconnect()
    return 0


def cmd_status(engine: MarketEngine) -> int:
    if not engine.start():
        return 1
    print(json.dumps(engine.status(), indent=2, default=str))
    engine.shutdown()
    return 0


def cmd_close_all(engine: MarketEngine) -> int:
    if not engine.broker.connect():
        print("Could not connect to the broker.")
        return 1
    results = engine.positions.close_all()
    if not results:
        print("No open positions belonging to this bot.")
    for ticket, ok, message in results:
        print(f"  #{ticket}: {'closed' if ok else 'FAILED — ' + message}")
    engine.broker.disconnect()
    return 0 if all(ok for _, ok, _ in results) else 1


def cmd_clean_logs(config: Config) -> int:
    log_file = config.log_file
    cleaned = 0
    if os.path.exists(log_file):
        try:
            with open(log_file, "w", encoding="utf-8") as handle:
                handle.truncate(0)
            print(f"Truncated main log file: {log_file}")
            cleaned += 1
        except Exception as exc:
            print(f"Failed to truncate {log_file}: {exc}")

    for i in range(1, 100):
        backup_file = f"{log_file}.{i}"
        if os.path.exists(backup_file):
            try:
                os.remove(backup_file)
                print(f"Removed backup log file: {backup_file}")
                cleaned += 1
            except Exception as exc:
                print(f"Failed to remove backup file {backup_file}: {exc}")

    if cleaned == 0:
        print("No log files found to clean.")
    else:
        print(f"Successfully cleaned {cleaned} log file(s).")
    return 0


def main() -> int:
    args = parse_args()
    config = build_config(args)

    if args.clean_logs:
        return cmd_clean_logs(config)

    setup_logging(
        config.log_level,
        config.log_file,
        max_bytes=config.log_max_bytes,
        backup_count=config.log_backup_count,
    )

    logger.info("=" * 70)
    logger.info("1-Minute Structure Scalper — MetaTrader 5 auto-trading bot")
    logger.info("=" * 70)
    for key, value in config.describe().items():
        logger.info(f"  {key:<22}: {value}")

    if args.dry_run:
        logger.warning("DRY RUN — simulated broker, no real orders will be placed.")

    engine = MarketEngine(config)

    if args.list_symbols:
        return cmd_list_symbols(engine)
    if args.test_alert:
        engine.send_test_alert()
        return 0
    if args.status:
        return cmd_status(engine)
    if args.close_all:
        return cmd_close_all(engine)

    if args.once:
        if not engine.start():
            return 1
        events = engine.run_scan_cycle()
        logger.info(f"Scan cycle complete — {len(events)} event(s) emitted.")
        engine.shutdown()
        return 0

    try:
        asyncio.run(engine.start_async_loop())
    except KeyboardInterrupt:
        logger.info("Interrupted — shutting down.")
    finally:
        engine.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
