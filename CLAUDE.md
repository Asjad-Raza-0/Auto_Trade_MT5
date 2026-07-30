- Always ask questions if needed, never guess by yourself.
- Make use of graphify if needed and at last after completion of work update by using "graphify ." command.

# TG Capital Trading Alert Bot & MQL5 EA Architecture

## Overview
This repository provides an institutional-grade, modular trading alert system and MetaTrader 5 Expert Advisor implementing the **TG Capital London EMA Stack + FVG Trident Strategy v2.0**.

The codebase is built with dual implementation:
1. **Python Alert Bot Engine** (Optimized for 24/7 deployment via GitHub Actions Free Cloud Runner or VPS):
   - Automated 24/7 market scanner running via `.github/workflows/alert_bot.yml` every 5 minutes.
   - Modular Strategy Architecture (`BaseStrategy` & `STRATEGY_REGISTRY`) allowing instant strategy swapping/extension.
   - Multi-provider market data system (TwelveData API, YFinance, MetaTrader 5 / MetaAPI).
   - Async scanner, State Machine per symbol, Telegram/Discord instant alerts with rich formatting.
   - Automated timezone & DST conversion (America/New_York session window: 03:00 - 06:30).
   - Full persistence, risk management, and multi-symbol execution logic.
2. **MQL5 EA Suite** (MetaTrader 5 Native):
   - Fully modular MQL5 architecture following SOLID principles across 17+ `.mqh` files and `TGCapitalEA.mq5`.
   - Embedded Telegram WebRequest notification capability.

---

## 🔌 How AI / LLMs (or Developers) Can Add or Swap Strategies Instantly

The Python engine features a **Plug-and-Play Strategy Architecture**. To switch to a completely new strategy (e.g., *ICT Silver Bullet*, *RSI Mean Reversion*, *MACD Breakout*), follow these **2 simple steps**:

### Step 1: Create a new Strategy File in `python_bot/strategies/`
Inherit from `BaseStrategy` and implement `evaluate_daily_filter` and `evaluate_signal`:

```python
# python_bot/strategies/my_new_strategy.py
from python_bot.strategies.base_strategy import BaseStrategy
from python_bot.models import TradeSignal, SymbolContext

class MyNewStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "my_new_strategy"

    def evaluate_daily_filter(self, symbol, df_daily):
        return True, "Daily trend OK"

    def evaluate_signal(self, symbol, df_daily, df_m30, context):
        # Your custom setup logic here
        return None, "No setup"
```

### Step 2: Register & Select in `config.json`
In `python_bot/strategies/__init__.py`:
```python
from python_bot.strategies.my_new_strategy import MyNewStrategy
register_strategy("my_new_strategy", MyNewStrategy)
```

In `config.json`:
```json
"general": {
  "strategy_name": "my_new_strategy"
}
```

That's it! The `MarketEngine`, `GitHub Actions` runner, risk manager, and notifier channels will automatically run your new strategy.

---

## Strategy Specification: TG Capital London EMA Stack + FVG Trident Strategy v2.0

### 1. General Rules
- **Timeframes**: Trend = Daily (1D), Execution = M30 (30-minute).
- **Trading Session**: 03:00 to 06:30 `America/New_York` (NY Time). Automatic DST handling. Pending orders expire at exactly 06:30 NY time.
- **Direction**: Long Only (Buy Limit orders / Bullish setups only).
- **Symbols**: XAUUSD (Gold), EURUSD, USDJPY, GBPUSD, AUDUSD, USDCAD, USDCHF, EURGBP (configurable).
- **Multi-Symbol Rule**: If multiple symbols produce entry signals on the same completed M30 candle, only execute/alert for the **first valid symbol** based on the order in the symbol configuration list.

### 2. Daily Trend Filter
Evaluated on **COMPLETED Daily candles**:
1. `Close > EMA200`
2. `EMA5 > EMA9 > EMA13 > EMA21` (EMA calculated on Close price)
*If any condition fails, reject setup and immediately cancel existing pending orders on Daily candle open.*

### 3. Setup Pattern (M30 Completed Candles)
1. **Bullish Fair Value Gap (FVG)**:
   - Evaluated across 3 completed candles: $A$ (oldest), $B$ (middle), $C$ (newest).
   - Condition: `High(A) < Low(C)`.
   - `FVG Top = Low(C)`, `FVG Bottom = High(A)`.
   - `Consequent Encroachment (CE) = (Top + Bottom) / 2`.
   - Deterministic FVG ID = `hash(symbol, candle_c_time, top, bottom)`.
   - Only newest FVG remains active; newer FVG replaces previous pending orders.
2. **Doji Candle**:
   - Must occur AFTER FVG forms.
   - `abs(Open - Close) <= Threshold * (High - Low)` (default threshold = 0.10).
   - `Low(Doji) <= CE` AND `Close(Doji) > CE`.
   - Use FIRST valid Doji after FVG.
3. **Confirmation Candle**:
   - Must be the IMMEDIATELY NEXT completed M30 candle after the Doji.
   - `Close(Confirmation) < High(Doji)`.

### 4. Entry & Risk Management
- **Entry Price**: `BUY LIMIT` at `FVG Top`.
- **Stop Loss**: `Low(Candle B)` (Exact, no buffer/ATR).
- **Max Stop Distance**:
  - Gold (XAUUSD): 600 points ($6.00).
  - Forex: 100 pips (1000 points for 5-digit / 100 points for JPY).
- **Risk Size**: 1% Account Balance default (floor lot size according to broker step/min lot limits).

---

## Codebase Structure

```
├── CLAUDE.md                        # Documentation and architecture roadmap
├── README.md                        # Deployment & operational guide
├── requirements.txt                 # Python dependencies
├── pytest.ini                      # Test runner configuration
├── docker-compose.yml              # Docker compose service definition
├── Dockerfile                       # Container image build spec
├── tgcapital-bot.service            # Systemd background service definition
├── config.json                      # Bot configuration file
│
├── python_bot/                      # Python Trading Alert Bot Engine
│   ├── __init__.py
│   ├── main.py                      # Application entrypoint & CLI runner
│   ├── config.py                    # Settings & environment parser
│   ├── models.py                    # Data classes (Candle, FVG, Signal, State)
│   ├── core/                        # Core bot engine modules
│   │   ├── __init__.py
│   │   ├── engine.py                # Async Market Scanner & scheduler
│   │   ├── state_machine.py         # Per-symbol state machine & persistence
│   │   ├── risk_manager.py          # Position sizing & max stop calculation
│   │   └── session_manager.py       # NY Session & DST timezone conversion
│   ├── strategies/                  # Strategy module (Extensible interface)
│   │   ├── __init__.py
│   │   ├── base_strategy.py         # Abstract Strategy Interface
│   │   └── trident_strategy.py      # TG Capital FVG Trident Implementation
│   ├── data_providers/              # Data Provider adapters (Extensible)
│   │   ├── __init__.py
│   │   ├── base_provider.py         # Abstract Data Provider Interface
│   │   ├── twelvedata_provider.py   # TwelveData REST API adapter
│   │   ├── yfinance_provider.py     # YFinance zero-cost fallback adapter
│   │   └── mock_provider.py         # Mock Data Provider for backtesting & testing
│   └── notifiers/                   # Notification channels
│       ├── __init__.py
│       ├── base_notifier.py         # Abstract Notifier Interface
│       ├── telegram_notifier.py     # Telegram Bot API integration
│       ├── discord_notifier.py      # Discord Webhook integration
│       └── console_notifier.py     # Console / Logging fallback
│
├── tests/                           # Automated Test Suite (Pytest)
│   ├── test_trident_strategy.py
│   ├── test_data_providers.py
│   ├── test_session_manager.py
│   ├── test_state_machine.py
│   └── test_risk_manager.py
│
└── mql5_ea/                          # MetaTrader 5 Expert Advisor Suite
    ├── TGCapitalEA.mq5              # Main EA file
    └── Include/
        ├── Constants.mqh
        ├── Enums.mqh
        ├── Utilities.mqh
        ├── Logger.mqh
        ├── BrokerInfo.mqh
        ├── DataCache.mqh
        ├── SymbolManager.mqh
        ├── SessionManager.mqh
        ├── EMAFilter.mqh
        ├── FVGDetector.mqh
        ├── DojiDetector.mqh
        ├── ConfirmationValidator.mqh
        ├── RiskManager.mqh
        ├── TradeManager.mqh
        ├── VisualizationManager.mqh
        ├── StateMachine.mqh
        ├── Version.mqh
        └── TelegramNotifier.mqh
```

---

## Development Milestones
- [x] Workspace Analysis & Git Init
- [x] Project Documentation (CLAUDE.md)
- [ ] Modular Python Trading Alert Bot Engine
  - [ ] Abstract Strategy Interface & Trident Strategy Implementation
  - [ ] Pluggable Data Providers (TwelveData, YFinance, Mock)
  - [ ] Session & Timezone Manager (NY 03:00 - 06:30 DST aware)
  - [ ] Per-Symbol State Machine & Persistence
  - [ ] Risk Manager & Position Sizing
  - [ ] Telegram & Discord Alert Notifiers
  - [ ] Async Engine & Multi-Symbol Priority Execution
- [ ] Comprehensive Test Suite (100% Pass Rate)
- [ ] Full MQL5 EA Suite (17+ Modular files with 0 errors/warnings specification)
- [ ] VPS Deployment Artifacts (Docker, Systemd, config.json)
- [ ] Complete User Guide (README.md)
