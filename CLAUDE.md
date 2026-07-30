- Always ask questions if needed, never guess by yourself.
- Make use of graphify if needed and at last after completion of work update by using "graphify ." command.

# 1-Minute Structure Scalper — MetaTrader 5 Auto-Trading Bot

## Overview
A modular Python auto-trading bot implementing a **1-Minute Structure Scalper** (strategy id `scalp_1m_v1`): 5-minute zone-reaction bias, 1-minute structure-break entries, partial take-profit + breakeven + time-stop management. It trades **live through MetaTrader 5** or fully simulated through a built-in **paper broker** (`--dry-run`), on Windows or any OS.

Default symbols: **US30, XAUUSD** (configurable). Both long and short setups.

## Running it

```bash
python python_bot/main.py --dry-run --once   # one simulated scan cycle
python python_bot/main.py --dry-run          # continuous simulated loop
python python_bot/main.py --list-symbols     # how logical names resolve at the broker
python python_bot/main.py --test-alert       # prove Telegram/Discord credentials work
python python_bot/main.py --status           # account/symbol/position status as JSON
python python_bot/main.py --close-all        # close every position this bot owns
python python_bot/main.py                    # LIVE trading via MT5
```

Useful overrides: `--strategy NAME`, `--symbols US30,XAUUSD`, `--config PATH`, `--env PATH`, `--log-level DEBUG`.

Tests: `python -m pytest tests/ -q` (45 tests, no MT5 or network needed).

See **GUIDE.md** for the full test-first-then-go-live walkthrough.

## Architecture

Every layer is swappable behind an abstract base + registry. The engine
(`python_bot/core/engine.py`) knows nothing about any concrete strategy, broker,
data feed or notifier.

```
├── CLAUDE.md / GUIDE.md             # This file / test & go-live walkthrough
├── config.json                      # All tunables (see below)
├── .env.example                     # Secrets template -> copy to .env
├── requirements.txt                 # MetaTrader5 dep is Windows-only marker
├── pytest.ini                       # testpaths=tests, asyncio_mode=auto
│
├── python_bot/
│   ├── main.py                      # CLI entrypoint (flags above)
│   ├── config.py                    # Config class: config.json + .env merge
│   ├── models.py                    # Dataclasses & enums: Candle frames contract,
│   │                                #   Direction, SymbolState (SCANNING/SETUP_FORMING/
│   │                                #   POSITION_OPEN/COOLDOWN/DISABLED), Zone, TradeSignal,
│   │                                #   Position, ManagementAction, TradeEvent, SymbolInfo...
│   ├── analysis/                    # Reusable price-action primitives (pure functions)
│   │   ├── indicators.py            #   last_atr
│   │   ├── swings.py                #   find_swing_points, filter_swings
│   │   ├── zones.py                 #   build_zones, find_active_zone, next_zone_beyond,
│   │   │                            #   detect_exhaustion, detect_reaction
│   │   ├── structure.py             #   read_structure (HH_HL/LH_LL), detect_break_of_structure,
│   │   │                            #   structure_stop_level, detect_retest
│   │   └── trendlines.py            #   fit_trendline, detect_trendline_break, trendline_kind_for
│   ├── core/
│   │   ├── engine.py                # MarketEngine: wiring, startup, scan loop
│   │   ├── position_manager.py      # Executes ManagementActions, syncs broker deals,
│   │   │                            #   emits TP_HIT/SL_HIT/CLOSED events, adopts orphans
│   │   ├── risk_manager.py          # Sizing via tick_size/tick_value + daily gates
│   │   ├── session_manager.py       # OPTIONAL session window (disabled by default = 24/5)
│   │   ├── state_machine.py         # Per-symbol SymbolContext + atomic JSON persistence
│   │   └── symbol_resolver.py       # Logical name -> broker spelling (aliases + overrides)
│   ├── brokers/                     # BROKER_REGISTRY: "mt5", "paper"/"dryrun"
│   │   ├── base_broker.py           #   BaseBroker contract
│   │   ├── mt5_broker.py            #   MetaTrader5 package (Windows)
│   │   └── paper_broker.py          #   In-memory sim: pessimistic SL-first fills,
│   │                                #   lazy price pull from its data_provider
│   ├── data_providers/              # PROVIDER_REGISTRY: "broker", "yfinance",
│   │   │                            #   "twelvedata", "mock"
│   │   └── base_provider.py         #   CONTRACT: columns time/open/high/low/close/volume,
│   │                                #   oldest first, COMPLETED candles only, None on failure
│   ├── strategies/                  # STRATEGY_REGISTRY: "scalp_1m_v1" (+aliases
│   │   │                            #   "scalp_1m", "structure_scalper")
│   │   ├── base_strategy.py         #   BaseStrategy interface (see below)
│   │   └── scalp_1m_strategy.py     #   The 4-module scalper
│   └── notifiers/                   # NotifierHub fan-out: console, telegram, discord
│
└── tests/                           # Pytest suite — runs fully offline
    ├── conftest.py                  # Deterministic synthetic candle builders
    ├── test_analysis.py             # ATR/swings/zones/structure/trendlines
    ├── test_data_providers.py       # Provider contract via MockDataProvider
    ├── test_risk_manager.py         # Sizing + daily gates
    ├── test_session_manager.py      # Session window / DST
    └── test_state_machine.py        # Persistence round-trip
```

### Engine scan cycle (`MarketEngine.run_scan_cycle`)
1. Reconcile positions with the broker → prompt TP_HIT / SL_HIT / CLOSED alerts.
2. Refresh balance, roll daily counters.
3. Per symbol, **only on a NEW completed bar** of the strategy's fastest timeframe:
   - position open? → `strategy.manage_position()` → broker actions
   - no position? → `strategy.evaluate()` → risk sizing → market order → ENTRY alert
4. Persist state (`bot_state.json`, atomic write).

A signal can never fire twice on the same candle (`last_signal_bar_time` guard).

## Strategy Specification: 1-Minute Structure Scalper (`scalp_1m_v1`)

Timeframes: bias = **5m** (`htf`), execution = **1m** (`ltf`). Both directions.
All thresholds live in `config.json -> strategy_parameters`.

- **Module 1 — HTF bias (5m)**: find S/R zones with ≥ `zone_min_touches` touches
  (clustered within `zone_cluster_atr_mult`×ATR); price must have recently reached
  into one (`zone_proximity_atr_mult`×ATR, probed by recent wick extreme, not close),
  show exhaustion (rejection wicks ≥ `exhaustion_wick_ratio`) and a reaction away.
  Support reaction → LONG bias; resistance → SHORT.
- **Module 2 — LTF structure (1m)**: swing sequence must read HH/HL (long) or LH/LL
  (short) and the latest completed 1m candle must **close** beyond the last confirmed
  swing extreme (break of structure). Wick-only pokes don't count.
- **Module 3 — Confirmations** (need `min_confirmations`, default 3):
  HTF_ZONE_REACTION (mandatory) + SR_BREAK (mandatory) + TRENDLINE_BREAK and/or RETEST.
- **Module 4 — Entry & management**: MARKET at the triggering candle close.
  SL just beyond the last 1m structure level + `sl_buffer_atr_mult`×ATR, clamped to
  [`min_stop_atr_mult`, `max_stop_atr_mult`]×ATR (too-wide structure = no trade).
  Partial `partial_close_percent`% at `partial_rr` (1:3) then SL→breakeven; runner to
  `final_rr` (1:5) capped by the next opposing 1m zone (`use_zone_take_profit`).
  Breakeven also triggers on clearing the secondary swing/zone. Time stop at
  `max_trade_duration_minutes` (30). Zone-reaction exit when in ≥ `zone_exit_min_rr`R.
  Optional scale-in (`enable_scale_in`, off).

## Risk management (`config.json -> risk`)
- `risk_percent` (1%) of live balance per trade, sized from broker `tick_size`/`tick_value`
  (works for indices, metals, forex, JPY with no special cases). Lots are **floored**
  to `volume_step`, never rounded up.
- Hard caps: `max_stop_points` per symbol, broker `stops_level` respected,
  `max_open_positions` (2), `max_positions_per_symbol` (1), `max_daily_trades` (6),
  `max_daily_loss_percent` (3% → halt until tomorrow).

## Adding / swapping a strategy
1. Subclass `BaseStrategy` in `python_bot/strategies/`; implement `name`,
   `required_timeframes` (role→timeframe dict), `evaluate(symbol, data, context)
   -> (TradeSignal|None, reason)` and optionally `manage_position(...) ->
   [ManagementAction]`.
2. Register in `python_bot/strategies/__init__.py`: `register_strategy("my_name", MyClass)`.
3. Select via `config.json -> general.strategy_name` (or `--strategy my_name`).

The engine, risk manager, notifiers and persistence all pick it up automatically.
The same pattern applies to brokers (`brokers/__init__.py`) and data providers
(`data_providers/__init__.py`).

## Configuration & secrets
- `config.json` — everything tunable; `general.broker`: `mt5` | `paper`,
  `general.data_provider`: `broker` | `yfinance` | `twelvedata` | `mock`.
- `.env` (from `.env.example`) — MT5 login, `TELEGRAM_BOT_TOKEN`/`TELEGRAM_CHAT_ID`,
  `DISCORD_WEBHOOK_URL`, `TWELVEDATA_API_KEY`. Never commit `.env`.
- `--dry-run` forces broker=paper + data_provider=yfinance at runtime, no config edits.

## Gotchas worth knowing
- Data-provider contract violations silently corrupt signals — completed candles
  only, oldest first (`base_provider.py` documents it; tests enforce it).
- yfinance 1m data is delayed and capped at ~7 days; index/metal tickers are futures
  proxies (`^DJI`, `GC=F`) whose prices differ from broker CFDs. Research only.
- The paper broker fills SL before TP when one bar covers both (pessimistic on purpose).
- `bot_state.json` survives restarts; orphan positions are re-adopted from the broker
  by magic number (`mt5.magic_number`, default 250730).
- `tests/` is a package — import helpers as `from tests.conftest import ...`.
