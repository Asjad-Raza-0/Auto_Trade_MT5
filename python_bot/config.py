"""
Configuration loader.

Precedence: environment variable > ``config.json`` > built-in default.
Secrets (MT5 password, Telegram token) belong in ``.env``, never in
``config.json`` — that file is meant to be committable.
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def load_dotenv(env_path: str = ".env") -> None:
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            if key:
                os.environ[key] = value.strip().strip("'").strip('"')


DEFAULTS: Dict[str, Any] = {
    "general": {
        "symbols": ["US30", "XAUUSD"],
        "strategy_name": "scalp_1m_v1",
        "broker": "mt5",
        "data_provider": "broker",
        "scan_interval_seconds": 15,
        "state_persistence_file": "bot_state.json",
        "log_file": "bot_execution.log",
        "log_level": "INFO",
        "log_max_mb": 10,
        "log_backup_count": 5,
    },
    "mt5": {
        "login": 0,
        "password": "",
        "server": "",
        "terminal_path": "",
        "magic_number": 250730,
        "deviation_points": 20,
        "auto_detect_symbols": True,
        "symbol_overrides": {},
    },
    "risk": {
        "risk_percent": 1.0,
        "use_live_balance": True,
        "account_balance_fallback": 10000.0,
        "max_open_positions": 2,
        "max_positions_per_symbol": 1,
        "max_daily_trades": 6,
        "max_daily_loss_percent": 3.0,
        "min_risk_reward": 0.0,
        "max_stop_points": {"US30": 3000.0, "XAUUSD": 600.0, "default": 1500.0},
    },
    "session": {
        "enabled": False,
        "start": "09:30",
        "end": "10:00",
        "timezone": "America/New_York",
        "trade_days": [0, 1, 2, 3, 4],
    },
    "telegram": {
        "enabled": True,
        "bot_token": "",
        "chat_id": "",
        "notify_events": ["ENTRY", "PARTIAL_TP", "TP_HIT", "SL_HIT", "ERROR"],
    },
    "discord": {
        "enabled": False,
        "webhook_url": "",
        "notify_events": ["ENTRY", "PARTIAL_TP", "TP_HIT", "SL_HIT", "ERROR"],
    },
    "console": {
        "notify_events": None,   # null = log every event type
    },
    "twelvedata": {"api_key": "", "rate_limit_pause_seconds": 8},
    "yfinance": {"symbol_mapping": {}},
    "strategy_parameters": {},
}


def _deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class Config:
    def __init__(self, config_file: str = "config.json", env_file: str = ".env"):
        load_dotenv(env_file)
        self.config_file = config_file
        self.data: Dict[str, Any] = dict(DEFAULTS)
        self.load()

    def load(self) -> None:
        if not os.path.exists(self.config_file):
            logger.warning(
                f"{self.config_file} not found — running on built-in defaults. "
                f"Copy config.example.json to config.json to customise."
            )
            return
        with open(self.config_file, "r", encoding="utf-8") as handle:
            self.data = _deep_merge(DEFAULTS, json.load(handle))

    # ------------------------------------------------------------------ access
    def section(self, name: str) -> Dict[str, Any]:
        value = self.data.get(name, {})
        return value if isinstance(value, dict) else {}

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self.section(section).get(key, default)

    # ----------------------------------------------------------------- general
    @property
    def symbols(self) -> List[str]:
        return list(self.get("general", "symbols", ["US30", "XAUUSD"]))

    @property
    def strategy_name(self) -> str:
        return str(self.get("general", "strategy_name", "scalp_1m_v1"))

    @property
    def broker_name(self) -> str:
        return str(self.get("general", "broker", "mt5"))

    @property
    def data_provider_name(self) -> str:
        return str(self.get("general", "data_provider", "broker"))

    @property
    def scan_interval(self) -> int:
        return int(self.get("general", "scan_interval_seconds", 15))

    @property
    def state_persistence_file(self) -> str:
        return str(self.get("general", "state_persistence_file", "bot_state.json"))

    @property
    def log_file(self) -> str:
        return str(self.get("general", "log_file", "bot_execution.log"))

    @property
    def log_level(self) -> str:
        return str(os.getenv("LOG_LEVEL") or self.get("general", "log_level", "INFO")).upper()

    @property
    def log_max_mb(self) -> int:
        val = os.getenv("LOG_MAX_MB")
        if val:
            try:
                return int(val)
            except ValueError:
                pass
        return int(self.get("general", "log_max_mb", 10))

    @property
    def log_max_bytes(self) -> int:
        return max(1024 * 1024, self.log_max_mb * 1024 * 1024)

    @property
    def log_backup_count(self) -> int:
        val = os.getenv("LOG_BACKUP_COUNT")
        if val:
            try:
                return int(val)
            except ValueError:
                pass
        return max(1, int(self.get("general", "log_backup_count", 5)))

    @property
    def strategy_params(self) -> Dict[str, Any]:
        return self.section("strategy_parameters")

    # --------------------------------------------------------------------- mt5
    @property
    def mt5_config(self) -> Dict[str, Any]:
        section = self.section("mt5")
        return {
            "login": int(os.getenv("MT5_LOGIN") or section.get("login", 0) or 0),
            "password": os.getenv("MT5_PASSWORD") or section.get("password", ""),
            "server": os.getenv("MT5_SERVER") or section.get("server", ""),
            "terminal_path": os.getenv("MT5_TERMINAL_PATH") or section.get("terminal_path", ""),
            "magic_number": int(section.get("magic_number", 250730)),
            "deviation_points": int(section.get("deviation_points", 20)),
        }

    @property
    def magic_number(self) -> int:
        return int(self.get("mt5", "magic_number", 250730))

    @property
    def symbol_overrides(self) -> Dict[str, str]:
        overrides = self.get("mt5", "symbol_overrides", {}) or {}
        return {k: v for k, v in overrides.items() if v}

    @property
    def auto_detect_symbols(self) -> bool:
        return bool(self.get("mt5", "auto_detect_symbols", True))

    # -------------------------------------------------------------------- risk
    @property
    def risk_config(self) -> Dict[str, Any]:
        section = self.section("risk")
        return {
            "risk_percent": float(section.get("risk_percent", 1.0)),
            "max_stop_points": section.get("max_stop_points", {}) or {},
            "max_open_positions": int(section.get("max_open_positions", 2)),
            "max_positions_per_symbol": int(section.get("max_positions_per_symbol", 1)),
            "max_daily_trades": int(section.get("max_daily_trades", 6)),
            "max_daily_loss_percent": float(section.get("max_daily_loss_percent", 3.0)),
            "account_balance": float(section.get("account_balance_fallback", 10000.0)),
            "min_risk_reward": float(section.get("min_risk_reward", 0.0)),
        }

    @property
    def use_live_balance(self) -> bool:
        return bool(self.get("risk", "use_live_balance", True))

    # ----------------------------------------------------------------- session
    @property
    def session_config(self) -> Dict[str, Any]:
        section = self.section("session")
        return {
            "enabled": bool(section.get("enabled", False)),
            "start": section.get("start", "09:30"),
            "end": section.get("end", "10:00"),
            "timezone": section.get("timezone", "America/New_York"),
            "trade_days": section.get("trade_days", [0, 1, 2, 3, 4]),
        }

    # --------------------------------------------------------------- notifiers
    @property
    def telegram_enabled(self) -> bool:
        return bool(self.get("telegram", "enabled", True))

    @property
    def telegram_bot_token(self) -> str:
        return os.getenv("TELEGRAM_BOT_TOKEN") or str(self.get("telegram", "bot_token", ""))

    @property
    def telegram_chat_id(self) -> str:
        return os.getenv("TELEGRAM_CHAT_ID") or str(self.get("telegram", "chat_id", ""))

    @property
    def telegram_events(self) -> Optional[List[str]]:
        return self.get("telegram", "notify_events", None)

    @property
    def discord_enabled(self) -> bool:
        return bool(self.get("discord", "enabled", False))

    @property
    def discord_webhook_url(self) -> str:
        return os.getenv("DISCORD_WEBHOOK_URL") or str(self.get("discord", "webhook_url", ""))

    @property
    def discord_events(self) -> Optional[List[str]]:
        return self.get("discord", "notify_events", None)

    @property
    def console_events(self) -> Optional[List[str]]:
        return self.get("console", "notify_events", None)

    # --------------------------------------------------------------- providers
    @property
    def twelvedata_api_key(self) -> str:
        return os.getenv("TWELVEDATA_API_KEY") or str(self.get("twelvedata", "api_key", ""))

    def provider_config(self, name: str) -> Dict[str, Any]:
        """Constructor kwargs for the named data provider."""
        key = name.lower()
        if key == "twelvedata":
            return {
                "api_key": self.twelvedata_api_key,
                "rate_limit_pause": float(self.get("twelvedata", "rate_limit_pause_seconds", 8)),
            }
        if key == "yfinance":
            return {"symbol_mapping": self.get("yfinance", "symbol_mapping", {}) or {}}
        return {}

    def describe(self) -> Dict[str, Any]:
        """Config summary for startup logging, with secrets redacted."""
        return {
            "symbols": self.symbols,
            "strategy": self.strategy_name,
            "broker": self.broker_name,
            "data_provider": self.data_provider_name,
            "scan_interval_seconds": self.scan_interval,
            "risk_percent": self.risk_config["risk_percent"],
            "max_open_positions": self.risk_config["max_open_positions"],
            "session": "enabled" if self.session_config["enabled"] else "disabled (24/5)",
            "log_rotation": f"{self.log_file} ({self.log_max_mb}MB max x {self.log_backup_count} backups)",
            "telegram": "configured" if (self.telegram_enabled and self.telegram_bot_token) else "off",
            "discord": "configured" if (self.discord_enabled and self.discord_webhook_url) else "off",
        }
