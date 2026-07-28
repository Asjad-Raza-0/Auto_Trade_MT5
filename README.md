# TG Capital Trading Alert Bot & MQL5 EA Suite

Institutional-grade, modular trading alert bot and MetaTrader 5 Expert Advisor implementing the **TG Capital London EMA Stack + FVG Trident Strategy v2.0**.

This project provides a **Dual Implementation**:
1. **Python 3 Alert Bot Engine** – Built for 24/7 background operation on Linux VPS servers (e.g. **Oracle Cloud Free Tier**). Features a pluggable strategy pattern (`BaseStrategy`), multi-provider data feeds (TwelveData & YFinance), per-symbol state machine persistence, and instant Telegram/Discord alerts.
2. **MetaTrader 5 MQL5 EA Suite** – Native MQL5 Expert Advisor codebase adhering strictly to SOLID OOP principles across 17+ `.mqh` files and `TGCapitalEA.mq5`, complete with WebRequest Telegram notifications.

---

## Strategy Specification: TG Capital London EMA Stack + FVG Trident Strategy v2.0

### Core Rules
- **Timeframes**: Trend = Daily (1D), Execution = M30 (30-minute).
- **Trading Session**: 03:00 to 06:30 `America/New_York` (NY Time). Automatic DST handling. Pending orders expire at exactly 06:30 NY time.
- **Direction**: Long Only (Buy Limit / Bullish setups only).
- **Default Symbols**: `XAUUSD`, `EURUSD`, `USDJPY`, `GBPUSD`, `AUDUSD`, `USDCAD`, `USDCHF`, `EURGBP`.
- **Multi-Symbol Priority Rule**: If multiple symbols produce entry signals on the same completed M30 candle, execute/alert ONLY for the **first valid symbol** based on the configured symbol list order.

### Setup Logic
1. **Daily Trend Filter**:
   - Evaluated on completed Daily candles:
     - `Close > EMA200`
     - `EMA5 > EMA9 > EMA13 > EMA21` (calculated on Close price)
2. **Bullish Fair Value Gap (FVG)**:
   - Evaluated across 3 completed M30 candles: $A$ (oldest), $B$ (middle), $C$ (newest).
   - Condition: `High(A) < Low(C)`.
   - `FVG Top = Low(C)`, `FVG Bottom = High(A)`, `CE = (Top + Bottom) / 2`.
   - Only newest FVG remains active; newer FVG replaces previous pending order.
3. **Doji Candle**:
   - Occurs AFTER FVG forms.
   - `abs(Open - Close) <= Threshold * (High - Low)` (default threshold = 0.10).
   - `Low(Doji) <= CE` AND `Close(Doji) > CE`. Uses first valid Doji.
4. **Confirmation Candle**:
   - IMMEDIATELY NEXT completed M30 candle after Doji.
   - `Close(Confirmation) < High(Doji)`.
5. **Entry & Stop Loss**:
   - **Entry**: `BUY LIMIT` at `FVG Top`.
   - **Stop Loss**: `Low(Candle B)` (of the FVG pattern).
   - **Max Stop Distance**: Gold (XAUUSD) <= 600 points ($6.00), Forex <= 100 pips.
   - **Risk Size**: 1% Account Balance default (floor lot size according to broker step/min lot limits).

---

## Project Structure

```
.
├── GEMINI.md                        # Project architecture & development log
├── README.md                        # Complete user & deployment guide
├── config.json                      # Bot parameters, symbols, and API keys
├── requirements.txt                 # Python dependencies
├── pytest.ini                      # Test runner configuration
├── Dockerfile                       # Container deployment spec
├── docker-compose.yml              # Docker compose service definition
├── tgcapital-bot.service            # Systemd service definition for Linux VPS
│
├── python_bot/                      # Python Trading Alert Bot Engine
│   ├── main.py                      # CLI entrypoint runner
│   ├── config.py                    # Settings parser
│   ├── models.py                    # Data models (Candle, FVG, Signal, Context)
│   ├── core/                        # Core bot engine modules
│   │   ├── engine.py                # Async scanner & priority scheduler
│   │   ├── session_manager.py       # NY Session 03:00 - 06:30 & DST converter
│   │   ├── risk_manager.py          # Stop distance & lot calculation
│   │   └── state_machine.py         # State machine & persistence manager
│   ├── strategies/                  # Extensible Strategy Architecture
│   │   ├── base_strategy.py         # Abstract Strategy Interface
│   │   └── trident_strategy.py      # Trident Strategy implementation
│   ├── data_providers/              # Data Provider Adapters
│   │   ├── base_provider.py         # Abstract Data Provider Interface
│   │   ├── twelvedata_provider.py   # TwelveData REST API adapter
│   │   ├── yfinance_provider.py     # YFinance zero-cost fallback adapter
│   │   └── mock_provider.py         # Mock data generator for testing
│   └── notifiers/                   # Notification Channels
│       ├── base_notifier.py         # Abstract Notifier Interface
│       ├── telegram_notifier.py     # Telegram Bot API integration
│       ├── discord_notifier.py      # Discord Webhook integration
│       └── console_notifier.py     # Local console/log fallback
│
├── tests/                           # Pytest Test Suite
│   ├── test_trident_strategy.py
│   ├── test_data_providers.py
│   ├── test_session_manager.py
│   ├── test_state_machine.py
│   └── test_risk_manager.py
│
└── mql5_ea/                          # MetaTrader 5 Expert Advisor Suite
    ├── TGCapitalEA.mq5              # Main Expert Advisor file
    └── Include/                     # Modular MQL5 headers
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

## How to Change or Add New Strategies in the Future

The Python bot is designed using the **Strategy Pattern**. To swap or add a new strategy:

1. Create a new strategy class in `python_bot/strategies/` inheriting from `BaseStrategy`:
```python
from python_bot.strategies.base_strategy import BaseStrategy
from python_bot.models import TradeSignal, SymbolContext

class MyNewStrategy(BaseStrategy):
    @property
    def name(self) -> str:
        return "my_new_strategy"

    def evaluate_daily_filter(self, symbol: str, df_daily: pd.DataFrame):
        # Your custom daily filter logic
        return True, "Filter passed"

    def evaluate_signal(self, symbol, df_daily, df_m30, context):
        # Your custom entry signal logic
        return signal, "Reason"
```
2. In `config.json`, change `"strategy_name": "my_new_strategy"`.

---

## Deployment on Oracle Free VPS (Linux Ubuntu)

### Step 1: Obtain Telegram Credentials
1. Open Telegram and search for `@BotFather`.
2. Send `/newbot` and follow instructions to get your **Bot Token**.
3. Search for `@userinfobot` or add your bot to your channel/group to get your **Chat ID**.

### Step 2: Configure `config.json`
Edit `config.json`:
```json
{
  "general": {
    "data_provider": "twelvedata",
    "account_balance": 10000.0,
    "risk_percent": 1.0
  },
  "twelvedata": {
    "api_key": "YOUR_TWELVEDATA_API_KEY"
  },
  "telegram": {
    "enabled": true,
    "bot_token": "123456789:ABCdef...",
    "chat_id": "987654321"
  }
}
```

### Step 3: Run Setup Options on VPS

#### Option A: Native Systemd Background Service (Recommended)
```bash
# Clone repository
git clone <your-repo-url> /home/ubuntu/tgcapital-bot
cd /home/ubuntu/tgcapital-bot

# Install requirements
python3 -m pip install -r requirements.txt

# Test alert
python3 -m python_bot.main --test-alert

# Install systemd service
sudo cp tgcapital-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable tgcapital-bot
sudo systemctl start tgcapital-bot

# Check service status & logs
sudo systemctl status tgcapital-bot
journalctl -u tgcapital-bot -f
```

#### Option B: Docker Container Deployment
```bash
cd /home/ubuntu/tgcapital-bot
docker-compose up -d --build
docker-compose logs -f
```

---

## Running Unit Tests
To run the automated test suite and confirm 0 errors:
```bash
python -m pytest -v
```

---

## MetaTrader 5 MQL5 EA Setup Guide

1. Open MetaTrader 5 and click **File -> Open Data Folder**.
2. Navigate to `MQL5/Experts/` and copy the contents of `mql5_ea/` into it:
   - Copy `mql5_ea/TGCapitalEA.mq5` into `MQL5/Experts/`
   - Copy `mql5_ea/Include/` directory into `MQL5/Experts/Include/` or `MQL5/Include/`
3. Open MetaEditor (F4 in MT5), select `TGCapitalEA.mq5` and press **Compile (F7)**.
4. Verify compilation finishes with **0 errors and 0 warnings**.
5. Attach `TGCapitalEA` to any single chart (e.g. `XAUUSD M30`). It acts as a **one-chart multi-symbol scanner** for all configured symbols.
