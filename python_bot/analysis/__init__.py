"""
Reusable price-action analysis primitives.

These are deliberately strategy-free building blocks. A new strategy should
compose them rather than re-implement swing/zone/trendline maths:

    from python_bot.analysis import (
        last_atr, find_swing_points, build_zones, find_active_zone,
        read_structure, detect_break_of_structure, fit_trendline,
        detect_trendline_break,
    )
"""
from python_bot.analysis.indicators import atr, ema, last_atr, sma, true_range
from python_bot.analysis.structure import (
    StructureRead,
    detect_break_of_structure,
    detect_retest,
    read_structure,
    structure_stop_level,
)
from python_bot.analysis.swings import filter_swings, find_swing_points, last_swings
from python_bot.analysis.trendlines import (
    detect_trendline_break,
    fit_trendline,
    trendline_kind_for,
)
from python_bot.analysis.zones import (
    build_zones,
    detect_exhaustion,
    detect_reaction,
    find_active_zone,
    next_zone_beyond,
)

__all__ = [
    "atr", "ema", "last_atr", "sma", "true_range",
    "find_swing_points", "filter_swings", "last_swings",
    "build_zones", "find_active_zone", "next_zone_beyond",
    "detect_exhaustion", "detect_reaction",
    "StructureRead", "read_structure", "detect_break_of_structure",
    "structure_stop_level", "detect_retest",
    "fit_trendline", "detect_trendline_break", "trendline_kind_for",
]
