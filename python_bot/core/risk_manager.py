import math
from typing import Tuple, Dict, Any

class RiskManager:
    """
    Handles risk limits, stop distance validation, and position lot size calculations.
    """
    def __init__(self, account_balance: float = 10000.0, risk_percent: float = 1.0,
                 max_stop_gold_points: float = 600.0, max_stop_forex_pips: float = 100.0):
        self.account_balance = account_balance
        self.risk_percent = risk_percent
        self.max_stop_gold_points = max_stop_gold_points
        self.max_stop_forex_pips = max_stop_forex_pips

    def is_gold(self, symbol: str) -> bool:
        return "XAU" in symbol.upper() or "GOLD" in symbol.upper()

    def get_pip_size(self, symbol: str) -> float:
        if self.is_gold(symbol):
            return 0.01  # 1 point in Gold = 0.01
        elif "JPY" in symbol.upper():
            return 0.01  # 1 pip in JPY = 0.01
        else:
            return 0.0001 # 1 pip in standard Forex = 0.0001

    def calculate_stop_distance_points(self, symbol: str, entry_price: float, stop_loss: float) -> float:
        distance = abs(entry_price - stop_loss)
        if self.is_gold(symbol):
            # Gold price difference $1.00 = 100 points
            return round(distance * 100.0, 2)
        elif "JPY" in symbol.upper():
            # JPY price difference 0.01 = 1 pip = 10 points
            return round((distance / 0.01) * 10.0, 2)
        else:
            # Forex price difference 0.0001 = 1 pip = 10 points
            return round((distance / 0.0001) * 10.0, 2)

    def validate_stop_distance(self, symbol: str, entry_price: float, stop_loss: float) -> Tuple[bool, str]:
        if entry_price <= 0 or stop_loss <= 0:
            return False, "Invalid entry or stop loss price (<= 0)"

        price_diff = abs(entry_price - stop_loss)
        if price_diff <= 0:
            return False, "Stop loss equal to entry price (Risk distance <= 0)"

        if self.is_gold(symbol):
            points = price_diff * 100.0 # $1.00 = 100 points
            if points > self.max_stop_gold_points:
                return False, f"Gold stop distance {points:.1f} points exceeds limit of {self.max_stop_gold_points:.1f} points"
        else:
            pip_size = self.get_pip_size(symbol)
            pips = price_diff / pip_size
            if pips > self.max_stop_forex_pips:
                return False, f"Forex stop distance {pips:.1f} pips exceeds limit of {self.max_stop_forex_pips:.1f} pips"

        return True, "Valid"

    def calculate_lot_size(self, symbol: str, entry_price: float, stop_loss: float,
                           min_lot: float = 0.01, max_lot: float = 100.0, lot_step: float = 0.01) -> float:
        """
        Calculates position lot size based on account balance, risk percentage, and risk distance.
        Floors the calculated lot size to respect lot step and avoid exceeding requested risk %.
        """
        valid, msg = self.validate_stop_distance(symbol, entry_price, stop_loss)
        if not valid:
            return 0.0

        risk_amount = self.account_balance * (self.risk_percent / 100.0)
        price_diff = abs(entry_price - stop_loss)

        if self.is_gold(symbol):
            # 1 Standard lot XAUUSD = 100 oz. $1 price change = $100 profit/loss per lot.
            loss_per_lot = price_diff * 100.0
        elif "JPY" in symbol.upper():
            # Standard lot = 100k units. JPY pip (0.01) = ~1000 JPY / entry_price in USD.
            # Approximation for standard 100k units ($10 / pip for quote USD, or adjusted)
            pips = price_diff / 0.01
            loss_per_lot = pips * 10.0
        else:
            # Forex standard lot = 100,000 units. 1 pip (0.0001) = $10 per lot.
            pips = price_diff / 0.0001
            loss_per_lot = pips * 10.0

        if loss_per_lot <= 0:
            return 0.0

        raw_lots = risk_amount / loss_per_lot

        # Floor lot size to nearest lot_step (add small epsilon to handle float precision e.g. 0.19999999999999998)
        steps = math.floor(round(raw_lots / lot_step, 6))
        floored_lots = round(steps * lot_step, 2)

        if floored_lots < min_lot:
            return 0.0  # Reject if normalized lot becomes less than minimum lot
        if floored_lots > max_lot:
            floored_lots = max_lot

        return floored_lots
