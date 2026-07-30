# 1-Minute Structure Scalper — MetaTrader 5 Auto-Trading Bot

A modular Python auto-trading bot for MetaTrader 5 implementing a **1-minute
structure scalping strategy**: 5-minute zone-reaction bias, 1-minute
structure-break entries, and automated trade management (partial take-profit,
breakeven, time stop). Trades **live through MT5** or fully simulated through a
built-in **paper broker** — no MT5 or Windows required for testing.

- **Strategy**: `scalp_1m_v1` — both long and short setups
- **Default symbols**: US30, XAUUSD (configurable)
- **Alerts**: Telegram, Discord, console
- **Restart-safe**: persisted state + orphan position re-adoption by magic number

> **New here? Read [GUIDE.md](GUIDE.md)** — the step-by-step walkthrough from
> offline tests → dry run → MT5 demo → live trading.
>
> **Architecture details live in [CLAUDE.md](CLAUDE.md).**

---

## Quick start

```bash
pip install -r requirements.txt
copy .env.example .env        # then fill in Telegram (and later MT5) credentials

python -m pytest tests/ -q                   # 45 offline tests — verify the code
python python_bot/main.py --test-alert      # verify Telegram works
python python_bot/main.py --dry-run --once  # one simulated scan cycle
python python_bot/main.py --dry-run         # continuous simulated trading
python python_bot/main.py                   # LIVE trading via MT5 (see GUIDE.md first!)
```

All CLI flags:

| Flag | Purpose |
|---|---|
| `--dry-run` | Paper broker + free yfinance data — **no real orders** |
| `--once` | One scan cycle, then exit |
| `--list-symbols` | Show how logical symbol names resolve at your broker |
| `--test-alert` | Send one test notification through every channel |
| `--status` | Print account/symbol/position status as JSON |
| `--close-all` | Close every position this bot owns, then exit |
| `--strategy NAME` / `--symbols A,B` | Override config at launch |
| `--config PATH` / `--env PATH` / `--log-level LEVEL` | Plumbing |

---

## The strategy in one paragraph

On the 5-minute chart the bot finds support/resistance zones with at least 3
touches and waits for price to reach one, get rejected (exhaustion wicks) and
start moving away — that sets the directional bias. On the 1-minute chart the
swing structure must agree (HH/HL for longs, LH/LL for shorts) and a candle must
*close* through the last swing extreme. With at least 3 confirmations (zone
reaction + structure break + trendline break and/or retest) it enters at market:
stop just beyond the last 1-minute structure, 50% banked at 3R with the stop
moved to breakeven, runner to 5R or the next opposing zone, everything flat
after 30 minutes. Risk per trade is 1% of live balance, with daily
trade-count and loss-percent circuit breakers. Every threshold is a
`config.json -> strategy_parameters` key.

---

## Project structure

```
├── README.md / GUIDE.md / CLAUDE.md     # This file / go-live walkthrough / architecture
├── config.json                          # All tunables: symbols, risk, strategy params
├── .env.example                         # Secrets template (MT5, Telegram, Discord)
├── requirements.txt / pytest.ini
│
├── python_bot/
│   ├── main.py                          # CLI entrypoint
│   ├── config.py                        # config.json + .env loader
│   ├── models.py                        # Dataclasses & enums shared by every layer
│   ├── analysis/                        # Pure price-action primitives:
│   │                                    #   ATR, swings, zones, structure, trendlines
│   ├── core/                            # Engine, position manager, risk manager,
│   │                                    #   session filter, state persistence, symbol resolver
│   ├── brokers/                         # "mt5" (live) and "paper" (simulation)
│   ├── data_providers/                  # "broker", "yfinance", "twelvedata", "mock"
│   ├── strategies/                      # "scalp_1m_v1" + plug-in registry
│   └── notifiers/                       # Telegram, Discord, console fan-out
│
├── tests/                               # Offline pytest suite (45 tests)
├── Query/                               # Strategy specification documents
└── legacy/                              # Previous Trident-bot deployment artifacts
```

Every layer (strategy, broker, data feed, notifier) sits behind an abstract base
class and a registry — swapping any of them is a config change, not an engine
change.

## Adding your own strategy

1. Subclass `BaseStrategy` in `python_bot/strategies/your_strategy.py` and
   implement `name`, `required_timeframes`, and
   `evaluate(symbol, data, context) -> (TradeSignal | None, reason)`
   (plus optional `manage_position(...)` for in-trade management).
2. Register it in `python_bot/strategies/__init__.py`:
   `register_strategy("your_name", YourStrategy)`.
3. Select it: `config.json -> general.strategy_name`, or `--strategy your_name`.

The engine, risk sizing, persistence and alert channels adapt automatically.

---

## Safety notes

- The bot only manages positions carrying its **magic number**
  (`mt5.magic_number`) — your manual trades on the same account are untouched.
- Stopping the bot does **not** close trades; they keep their SL/TP on the
  broker and are re-adopted on restart. Use `--close-all` to flatten.
- Daily circuit breakers: max trades/day and max daily loss % halt trading
  until the next day.
- Start on a **demo account**. [GUIDE.md](GUIDE.md) is the checklist.
