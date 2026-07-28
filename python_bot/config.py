import os
import json
from typing import Dict, Any, List, Optional

def load_dotenv(env_path: str = ".env"):
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip("'").strip('"')
                    if k:
                        os.environ[k] = v

class Config:
    def __init__(self, config_file: str = "config.json", env_file: str = ".env"):
        load_dotenv(env_file)
        self.config_file = config_file
        self.data: Dict[str, Any] = {}
        self.load()

    def load(self):
        if os.path.exists(self.config_file):
            with open(self.config_file, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        else:
            self.data = self._defaults()

    def _defaults(self) -> Dict[str, Any]:
        return {
            "general": {
                "symbols": ["XAUUSD", "EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "USDCAD", "USDCHF", "EURGBP"],
                "scan_interval_seconds": 60,
                "strategy_name": "trident_v2",
                "data_provider": "twelvedata",
                "account_balance": 10000.0,
                "risk_percent": 1.0,
                "state_persistence_file": "bot_state.json"
            },
            "twelvedata": {
                "api_key": os.getenv("TWELVEDATA_API_KEY", "YOUR_TWELVEDATA_API_KEY"),
                "rate_limit_pause_seconds": 8
            },
            "yfinance": {
                "symbol_mapping": {
                    "XAUUSD": "GC=F",
                    "EURUSD": "EURUSD=X",
                    "USDJPY": "JPY=X",
                    "GBPUSD": "GBPUSD=X",
                    "AUDUSD": "AUDUSD=X",
                    "USDCAD": "CAD=X",
                    "USDCHF": "CHF=X",
                    "EURGBP": "EURGBP=X"
                }
            },
            "telegram": {
                "enabled": True,
                "bot_token": os.getenv("TELEGRAM_BOT_TOKEN", ""),
                "chat_id": os.getenv("TELEGRAM_CHAT_ID", "")
            },
            "discord": {
                "enabled": False,
                "webhook_url": os.getenv("DISCORD_WEBHOOK_URL", "")
            },
            "strategy_parameters": {
                "doji_threshold": 0.10,
                "ema_periods": [5, 9, 13, 21, 200],
                "session_start_ny": "03:00",
                "session_end_ny": "06:30",
                "session_timezone": "America/New_York",
                "max_stop_gold_points": 600.0,
                "max_stop_forex_pips": 100.0
            }
        }

    @property
    def symbols(self) -> List[str]:
        return self.data.get("general", {}).get("symbols", ["XAUUSD", "EURUSD"])

    @property
    def scan_interval(self) -> int:
        return self.data.get("general", {}).get("scan_interval_seconds", 60)

    @property
    def data_provider_name(self) -> str:
        return self.data.get("general", {}).get("data_provider", "twelvedata")

    @property
    def strategy_name(self) -> str:
        return self.data.get("general", {}).get("strategy_name", "trident_v2")

    @property
    def account_balance(self) -> float:
        return float(self.data.get("general", {}).get("account_balance", 10000.0))

    @property
    def risk_percent(self) -> float:
        return float(self.data.get("general", {}).get("risk_percent", 1.0))

    @property
    def state_persistence_file(self) -> str:
        return self.data.get("general", {}).get("state_persistence_file", "bot_state.json")

    @property
    def twelvedata_api_key(self) -> str:
        env_key = os.getenv("TWELVEDATA_API_KEY")
        if env_key:
            return env_key
        return self.data.get("twelvedata", {}).get("api_key", "")

    @property
    def telegram_bot_token(self) -> str:
        return os.getenv("TELEGRAM_BOT_TOKEN") or self.data.get("telegram", {}).get("bot_token", "")

    @property
    def telegram_chat_id(self) -> str:
        return os.getenv("TELEGRAM_CHAT_ID") or self.data.get("telegram", {}).get("chat_id", "")

    @property
    def telegram_enabled(self) -> bool:
        return self.data.get("telegram", {}).get("enabled", True)

    @property
    def discord_enabled(self) -> bool:
        return self.data.get("discord", {}).get("enabled", False)

    @property
    def discord_webhook_url(self) -> str:
        return os.getenv("DISCORD_WEBHOOK_URL") or self.data.get("discord", {}).get("webhook_url", "")

    @property
    def strategy_params(self) -> Dict[str, Any]:
        return self.data.get("strategy_parameters", {})
