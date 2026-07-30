# GUIDE — From Zero to Live Trading

This walks you through, in order:

1. [Setup](#1-setup)
2. [Verify the code works (offline tests)](#2-verify-the-code-works)
3. [Test the bot with simulated money (dry run)](#3-dry-run--simulated-trading)
4. [Test against a real MT5 **demo** account](#4-mt5-demo-account--the-real-rehearsal)
5. [Go live](#5-going-live)
6. [Operating it day to day](#6-day-to-day-operation)
7. [Troubleshooting](#7-troubleshooting)

**Do not skip stages.** Each stage catches a class of problem the previous one cannot.

---

## 1. Setup

Requirements: Python 3.10+ (3.14 tested), Windows for live MT5 trading
(dry-run and tests work on any OS).

```bash
pip install -r requirements.txt
```

Create your secrets file:

```bash
copy .env.example .env
```

Then edit `.env`:

- **Telegram alerts** (recommended before anything else):
  1. Message `@BotFather` on Telegram → `/newbot` → copy the token into `TELEGRAM_BOT_TOKEN`.
  2. Message `@userinfobot` to get your numeric id → `TELEGRAM_CHAT_ID`.
  3. **Send your new bot any message once** (bots cannot message you first).
- **MT5 credentials** — leave blank for now; simplest is to let the bot attach to
  whatever account the running MT5 terminal is logged into (section 4).

`.env` is git-ignored. Never commit it.

---

## 2. Verify the code works

Runs fully offline — no broker, no network, no API keys:

```bash
python -m pytest tests/ -q
```

Expected: **45 passed**. If anything fails, stop and fix it before going further.

Prove your alert channel works:

```bash
python python_bot/main.py --test-alert
```

You should receive a "TEST ALERT" message on Telegram (and see it in the console).

---

## 3. Dry run — simulated trading

`--dry-run` swaps in the built-in **paper broker** (starts with a simulated
$10,000, fills orders against candle data, places **no real orders**) and pulls
free market data from yfinance. No MT5 needed, works on any OS.

One scan cycle, then exit — good first smoke test:

```bash
python python_bot/main.py --dry-run --once
```

What a healthy startup looks like:

```
[SymbolResolver] US30: exact match -> 'US30'
[SymbolResolver] XAUUSD: exact match -> 'XAUUSD'
[Startup] US30 -> US30: digits 2, tick 0.01 = 0.0100/lot, ...
Scan cycle complete — 0 event(s) emitted.
```

Then let it run continuously (scans every 15s, Ctrl+C to stop):

```bash
python python_bot/main.py --dry-run
```

Let it run during active market hours (US session for US30) for at least a few
hours — ideally a couple of days. You are watching for:

- **ENTRY alerts** with sensible prices, stops and targets (`bot_execution.log`
  keeps everything).
- Rejection reasons per symbol that make sense (`[M1 bias] ...`, `[M2 structure] ...`
  at DEBUG level: add `--log-level DEBUG`).
- Simulated fills, partials (`TP1 ... banking 50%`), breakevens and closes in the log.
- No crashes, no repeated errors.

**Dry-run caveats** (why this stage alone is not enough):

- yfinance 1m data is *delayed* and index/gold tickers are futures proxies
  (`^DJI`, `GC=F`) — prices differ from your broker's CFD feed.
- Weekends/market closed = no fresh candles = no signals. That's normal.
- Paper fills are idealised (no slippage, no requotes).

Signals will be rare by design — the strategy demands 3 confirmations. Hours with
0 events is normal behaviour, not a bug.

---

## 4. MT5 demo account — the real rehearsal

This is the stage that actually rehearses live trading: real broker feed, real
symbol names, real contract specs, real order placement — with demo money.

### 4.1 Get a demo account

1. Install MetaTrader 5 from your broker (or metatrader5.com).
2. In MT5: `File -> Open an Account` → pick your broker → **Demo** → note login,
   password, server.
3. Make sure the symbols you want (US30/XAUUSD or your broker's spelling) are
   visible in Market Watch (right-click → Symbols → enable them).
4. Enable algo trading: `Tools -> Options -> Expert Advisors -> Allow algorithmic trading`.

### 4.2 Point the bot at it

Easiest path — leave `MT5_LOGIN`/`MT5_PASSWORD`/`MT5_SERVER` **blank** in `.env`,
log the MT5 terminal itself into the demo account, and keep the terminal running.
The bot attaches to the logged-in terminal.

Alternatively fill the three `MT5_*` values in `.env` and the bot will log in itself.

### 4.3 Resolve symbol names

Every broker spells instruments differently (`US30`, `US30Cash`, `DJ30`, ...):

```bash
python python_bot/main.py --list-symbols
```

The resolver auto-matches known aliases. If it picks wrong (or fails), pin the
exact name in `config.json`:

```json
"mt5": {
  "symbol_overrides": { "US30": "US30Cash", "XAUUSD": "XAUUSD.a" }
}
```

### 4.4 Run it

`config.json` already defaults to `broker: "mt5"` and `data_provider: "broker"`
(the broker's own feed — the right choice for live/demo), so plainly:

```bash
python python_bot/main.py --once     # one cycle against the demo account
python python_bot/main.py            # continuous
```

**Run on demo for at least 1–2 weeks.** Check daily:

- Entries/exits match what the log says the strategy decided.
- Lot sizes are what you expect (~1% risk: check the `[Risk]` log lines).
- Partials at 3R and breakeven moves actually appear on the MT5 position.
- The 30-minute time stop closes stale trades.
- Restart the bot mid-trade at least once — it must re-adopt the open position
  (watch for the `[Startup] ... adopted` line) and keep managing it.
- `python python_bot/main.py --status` shows sane account/position JSON.

---

## 5. Going live

Only after demo behaved correctly for 1–2 weeks.

### 5.1 Pre-flight checklist

- [ ] All 45 tests pass: `python -m pytest tests/ -q`
- [ ] Demo period showed correct entries, sizing, partials, breakeven, time stop
- [ ] Telegram alerts arriving reliably
- [ ] You have read `config.json -> risk` and agree with every number
- [ ] You understand the max theoretical daily loss:
      `max_daily_loss_percent` (3%) halts trading for the day
- [ ] The machine running the bot stays on 24/5 (VPS or an always-on PC;
      MT5 terminal must also be running if you attach to it)

### 5.2 Start small

In `config.json`, consider for the first weeks:

```json
"risk": {
  "risk_percent": 0.25,          // quarter size until trust is earned
  "max_open_positions": 1,
  "max_daily_trades": 3
}
```

Optionally trade one symbol first: `--symbols US30`.

### 5.3 Switch the terminal/credentials to the live account

Exactly as in 4.2 but with the live login. Everything else stays the same —
that's the point of rehearsing on demo.

```bash
python python_bot/main.py --once     # one live cycle, watch it like a hawk
python python_bot/main.py            # go
```

The **magic number** (`mt5.magic_number`, default 250730) tags every order the
bot places, so it only ever manages/closes *its own* positions — your manual
trades on the same account are untouched.

### 5.4 Emergency stops

```bash
python python_bot/main.py --close-all     # close every bot-owned position, then exit
```

Or simply stop the bot (Ctrl+C) — open positions **stay running on the broker**
with their SL/TP intact; the bot re-adopts them on restart. Killing the bot does
NOT close trades: if you want them closed, use `--close-all` or do it in MT5.

---

## 6. Day-to-day operation

- `bot_execution.log` — everything the bot did and why (every rejection included).
- `bot_state.json` — persisted per-symbol state; delete it only if you want a
  totally clean slate (open positions get re-adopted from the broker anyway).
- `--status` — quick JSON health check while the bot is stopped.
- Daily counters (trades, loss limit) reset automatically at date change.
- Tune thresholds in `config.json -> strategy_parameters`; the log's rejection
  reasons tell you which module ([M1]-[M4]) is filtering out setups.
- Restart-safe by design: state file + orphan adoption. Restarting is always safe.

Optional: restrict trading hours via `config.json -> session`
(`"enabled": true`, e.g. `"start": "09:30", "end": "10:00"` NY time) —
by default the session filter is off and the bot trades 24/5.

---

## 7. Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `broker returned no symbols` (live) | MT5 terminal not running / not logged in / algo trading disabled |
| `... not offered by the broker` | Wrong spelling — run `--list-symbols`, set `mt5.symbol_overrides` |
| No signals for hours | Normal. Strategy needs 3 confirmations. Use `--log-level DEBUG` to see per-cycle rejection reasons |
| No 1m/5m data in dry-run | Market closed, or yfinance throttling — wait and retry |
| Telegram silent | Token/chat-id wrong, or you never messaged the bot first. `--test-alert` to verify |
| `MetaTrader5 package not available` | Live MT5 needs Windows + `pip install MetaTrader5` |
| Lots = 0, trade skipped | Stop too wide for `max_stop_points`, below broker min distance, or balance too small for `volume_min` at 1% risk — the log line says which |
| Bot restarted mid-trade | Fine. It re-adopts its positions by magic number on startup |
