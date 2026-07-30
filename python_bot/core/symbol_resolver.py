"""
Broker symbol-name resolution.

Every broker spells the same instrument differently — US30 might be ``US30``,
``US30Cash``, ``DJI30``, ``[DJI30]``, ``US30.cash`` or ``WS30``; gold might be
``XAUUSD``, ``XAUUSD.a``, ``GOLD`` or ``XAUUSDm``. This module maps the logical
name used in ``config.json`` to whatever the connected terminal actually offers.

Resolution order:
  1. explicit override from ``config.json -> mt5.symbol_overrides``
  2. exact match
  3. case-insensitive exact match
  4. alias/prefix match on the normalised name (punctuation stripped), preferring
     the candidate closest in length to the alias
"""
import logging
import re
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Logical name -> spellings brokers use, most canonical first.
SYMBOL_ALIASES: Dict[str, List[str]] = {
    "US30": ["US30", "USA30", "DJI30", "DJ30", "DOW30", "WS30", "US30CASH", "DJIA", "YM"],
    "NAS100": ["NAS100", "USTEC", "NDX100", "US100", "NQ100", "TECH100"],
    "SPX500": ["SPX500", "US500", "SP500", "SPX", "ES500"],
    "GER40": ["GER40", "DE40", "DAX40", "GER30", "DE30", "DAX"],
    "UK100": ["UK100", "FTSE100", "FTSE"],
    "JP225": ["JP225", "NIKKEI", "JPN225"],
    "XAUUSD": ["XAUUSD", "GOLD", "XAU", "GOLDSPOT"],
    "XAGUSD": ["XAGUSD", "SILVER", "XAG"],
    "USOIL": ["USOIL", "WTI", "CRUDE", "XTIUSD", "OIL"],
    "BTCUSD": ["BTCUSD", "BITCOIN", "BTC"],
}


def normalize(name: str) -> str:
    """Upper-case and strip everything that is not a letter or digit."""
    return re.sub(r"[^A-Z0-9]", "", (name or "").upper())


def aliases_for(logical: str) -> List[str]:
    """Alias list for a logical name; falls back to the name itself."""
    key = normalize(logical)
    for canonical, aliases in SYMBOL_ALIASES.items():
        if key == normalize(canonical) or key in [normalize(a) for a in aliases]:
            return [canonical] + [a for a in aliases if normalize(a) != normalize(canonical)]
    return [logical]


def resolve_symbol(
    logical: str,
    available: List[str],
    override: Optional[str] = None,
) -> Tuple[Optional[str], str]:
    """
    Map ``logical`` onto one of ``available``. Returns (broker_symbol, reason).

    ``override`` short-circuits everything — but is still validated against the
    broker list so a typo fails loudly at startup instead of at order time.
    """
    if override:
        if override in available:
            return override, f"config override -> '{override}'"
        ci = _case_insensitive_match(override, available)
        if ci:
            return ci, f"config override '{override}' matched '{ci}' (case-insensitive)"
        return None, (
            f"config override '{override}' is not offered by the broker "
            f"(checked {len(available)} symbols)"
        )

    if not available:
        return None, "broker returned no symbols"

    if logical in available:
        return logical, f"exact match -> '{logical}'"

    ci = _case_insensitive_match(logical, available)
    if ci:
        return ci, f"case-insensitive match -> '{ci}'"

    candidates: List[Tuple[int, int, str]] = []
    for alias in aliases_for(logical):
        norm_alias = normalize(alias)
        if not norm_alias:
            continue
        for candidate in available:
            norm_candidate = normalize(candidate)
            if norm_candidate == norm_alias:
                candidates.append((0, 0, candidate))
            elif norm_candidate.startswith(norm_alias):
                candidates.append((1, len(norm_candidate) - len(norm_alias), candidate))
            elif norm_alias in norm_candidate:
                candidates.append((2, len(norm_candidate) - len(norm_alias), candidate))

    if not candidates:
        return None, (
            f"no broker symbol matches '{logical}' or its aliases "
            f"({', '.join(aliases_for(logical))}). Set mt5.symbol_overrides in config.json "
            f"— run `python -m python_bot.main --list-symbols` to see the real names."
        )

    candidates.sort(key=lambda c: (c[0], c[1], len(c[2])))
    best = candidates[0][2]
    alternatives = [c[2] for c in candidates[1:4]]
    reason = f"fuzzy match -> '{best}'"
    if alternatives:
        reason += f" (other candidates: {', '.join(alternatives)})"
    return best, reason


def _case_insensitive_match(name: str, available: List[str]) -> Optional[str]:
    lowered = (name or "").lower()
    for candidate in available:
        if candidate.lower() == lowered:
            return candidate
    return None


def resolve_all(
    logical_symbols: List[str],
    available: List[str],
    overrides: Optional[Dict[str, str]] = None,
) -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Resolve a whole list. Returns (resolved, failures) where ``resolved`` maps
    logical -> broker symbol and ``failures`` maps logical -> reason.
    """
    overrides = overrides or {}
    resolved: Dict[str, str] = {}
    failures: Dict[str, str] = {}

    for logical in logical_symbols:
        override = overrides.get(logical) or overrides.get(logical.upper()) or None
        broker_symbol, reason = resolve_symbol(logical, available, override)
        if broker_symbol:
            resolved[logical] = broker_symbol
            logger.info(f"[SymbolResolver] {logical}: {reason}")
        else:
            failures[logical] = reason
            logger.error(f"[SymbolResolver] {logical}: {reason}")

    return resolved, failures
