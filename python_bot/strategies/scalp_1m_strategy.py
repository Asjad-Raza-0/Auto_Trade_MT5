"""
1-Minute Structure Scalper (``scalp_1m_v1``)
============================================

Direct implementation of the strategy spec in ``Query/New_Scalping_Strategy``.
Every rule below maps to a numbered module in that document.

Module 1 — HTF bias (5m)
    Find support/resistance zones with >= ``zone_min_touches`` touches, confirm
    price is *reacting* off one (rejection wicks = exhaustion) and has started
    moving away from it. Support reaction -> LONG bias, resistance -> SHORT.

Module 2 — LTF structure alignment (1m)
    The 1m swing sequence must read HH/HL for a long, LH/LL for a short. Then the
    latest completed 1m candle must CLOSE beyond the most recent confirmed swing
    extreme ("take out the previous high/low") — no entry before that.

Module 3 — Three confirmations
    1. HTF zone reaction (mandatory)
    2. 1m trendline break
    3. 1m S/R (structure) break — mandatory, same candle
    (+ optional retest of the broken level as a 4th)
    ``min_confirmations`` (default 3) must be satisfied.

Module 4 — Trade management
    Entry  : MARKET at the close of the triggering 1m candle.
    Stop   : just beyond the immediate 1m structure (last HL / LH) + ATR buffer.
    Target : partial ``partial_close_percent`` at ``partial_rr`` (1:3), stop to
             breakeven, runner to ``final_rr`` (1:5) or the next opposing 1m zone,
             whichever comes first.
    Breakeven: also moves to entry once price clears the secondary high/low.
    Time stop: flat after ``max_trade_duration_minutes`` (spec: done in 30 min).
    Scale-in: optional, off by default.

Every threshold is a ``config.json -> strategy_parameters`` key. Tune there
first; only edit this file when the *logic* changes.
"""
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from python_bot.analysis import (
    build_zones,
    detect_break_of_structure,
    detect_exhaustion,
    detect_reaction,
    detect_retest,
    detect_trendline_break,
    find_active_zone,
    find_swing_points,
    fit_trendline,
    last_atr,
    next_zone_beyond,
    read_structure,
    structure_stop_level,
    trendline_kind_for,
)
from python_bot.analysis.structure import StructureRead
from python_bot.models import (
    Direction,
    ManagementAction,
    ManagementActionType,
    OrderType,
    Position,
    SymbolContext,
    TradeEventType,
    TradeSignal,
    Zone,
    ZoneKind,
)
from python_bot.strategies.base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class OneMinuteScalpStrategy(BaseStrategy):
    """1-minute structure scalper with 5-minute directional bias."""

    def __init__(self, params: Optional[Dict[str, Any]] = None):
        super().__init__(params)

        # --- timeframes (changing these is enough to run the same logic on 15m/3m)
        self.htf = str(self.p("htf_timeframe", "5m"))
        self.ltf = str(self.p("ltf_timeframe", "1m"))
        self.htf_bars = self.p("htf_bars", 400)
        self.ltf_bars = self.p("ltf_bars", 300)
        self.atr_period = self.p("atr_period", 14)

        # --- Module 1: HTF zones & bias
        self.swing_lookback_htf = self.p("swing_lookback_htf", 3)
        self.zone_min_touches = self.p("zone_min_touches", 3)
        self.zone_cluster_atr_mult = self.p("zone_cluster_atr_mult", 0.35)
        self.zone_proximity_atr_mult = self.p("zone_proximity_atr_mult", 1.0)
        self.exhaustion_wick_ratio = self.p("exhaustion_wick_ratio", 0.5)
        self.exhaustion_lookback = self.p("exhaustion_lookback", 6)
        self.reaction_bars = self.p("reaction_bars", 3)

        # --- Module 2: LTF structure
        self.swing_lookback_ltf = self.p("swing_lookback_ltf", 2)
        self.structure_min_swings = self.p("structure_min_swings", 2)
        self.bos_buffer_atr_mult = self.p("bos_buffer_atr_mult", 0.0)

        # --- Module 3: confirmations
        self.trendline_lookback = self.p("trendline_lookback", 40)
        self.trendline_min_touches = self.p("trendline_min_touches", 2)
        self.trendline_tolerance_atr_mult = self.p("trendline_tolerance_atr_mult", 0.10)
        self.trendline_break_buffer_atr_mult = self.p("trendline_break_buffer_atr_mult", 0.0)
        self.min_confirmations = self.p("min_confirmations", 3)
        self.require_retest = self.p("require_retest", False)
        self.retest_lookback = self.p("retest_lookback", 10)

        # --- Module 4: risk / targets
        self.ltf_zone_min_touches = self.p("ltf_zone_min_touches", 2)
        self.sl_buffer_atr_mult = self.p("sl_buffer_atr_mult", 0.15)
        self.min_stop_atr_mult = self.p("min_stop_atr_mult", 0.5)
        self.max_stop_atr_mult = self.p("max_stop_atr_mult", 4.0)
        self.partial_rr = self.p("partial_rr", 3.0)
        self.final_rr = self.p("final_rr", 5.0)
        self.partial_close_percent = self.p("partial_close_percent", 50.0)
        self.use_zone_take_profit = self.p("use_zone_take_profit", True)
        self.breakeven_on_secondary_level = self.p("breakeven_on_secondary_level", True)
        self.breakeven_rr = self.p("breakeven_rr", 1.0)
        self.zone_exit_enabled = self.p("zone_exit_enabled", True)
        self.zone_exit_min_rr = self.p("zone_exit_min_rr", 1.0)
        self.max_trade_duration_minutes = self.p("max_trade_duration_minutes", 30)
        self.close_after_max_duration = self.p("close_after_max_duration", True)
        self.enable_scale_in = self.p("enable_scale_in", False)
        self.max_scale_ins = self.p("max_scale_ins", 1)

    # ------------------------------------------------------------------ identity
    @property
    def name(self) -> str:
        return "scalp_1m_v1"

    @property
    def display_name(self) -> str:
        return f"1-Minute Structure Scalper ({self.htf} bias / {self.ltf} entry)"

    @property
    def required_timeframes(self) -> Dict[str, str]:
        return {"htf": self.htf, "ltf": self.ltf}

    @property
    def warmup_bars(self) -> Dict[str, int]:
        return {"htf": self.htf_bars, "ltf": self.ltf_bars}

    # ------------------------------------------------------------------ evaluate
    def evaluate(
        self,
        symbol: str,
        data: Dict[str, pd.DataFrame],
        context: SymbolContext,
    ) -> Tuple[Optional[TradeSignal], str]:
        df_htf = data.get("htf")
        df_ltf = data.get("ltf")

        min_htf = 2 * self.swing_lookback_htf + self.exhaustion_lookback + self.atr_period
        min_ltf = max(self.atr_period + 5, 2 * self.swing_lookback_ltf + 20)

        if df_htf is None or len(df_htf) < min_htf:
            return None, f"insufficient {self.htf} bars (need >= {min_htf}, have {0 if df_htf is None else len(df_htf)})"
        if df_ltf is None or len(df_ltf) < min_ltf:
            return None, f"insufficient {self.ltf} bars (need >= {min_ltf}, have {0 if df_ltf is None else len(df_ltf)})"

        atr_htf = last_atr(df_htf, self.atr_period)
        atr_ltf = last_atr(df_ltf, self.atr_period)
        bar_time = _bar_time(df_ltf, -1)
        entry_price = float(df_ltf["close"].iloc[-1])

        if context.last_signal_bar_time is not None and bar_time is not None \
                and context.last_signal_bar_time == bar_time:
            return None, f"already signalled on {self.ltf} bar {bar_time}"

        # --- Module 1 -------------------------------------------------------
        bias, htf_zone, bias_reason = self._htf_bias(df_htf, atr_htf)
        if bias is Direction.NONE or htf_zone is None:
            return None, f"[M1 bias] {bias_reason}"

        # --- Module 2 -------------------------------------------------------
        swings_ltf = find_swing_points(df_ltf, self.swing_lookback_ltf)
        structure = read_structure(swings_ltf, self.structure_min_swings)
        if structure.bias is not bias:
            return None, (
                f"[M2 structure] {self.htf} bias {bias.value} but {self.ltf} structure is "
                f"{structure.pattern} ({structure.detail})"
            )

        bos, bos_reason = detect_break_of_structure(
            df_ltf, structure, bias, buffer=atr_ltf * self.bos_buffer_atr_mult
        )
        if bos is None:
            return None, f"[M2 break] {bos_reason}"

        # --- Module 3 -------------------------------------------------------
        confirmations: List[str] = ["HTF_ZONE_REACTION", "SR_BREAK"]
        confirmation_notes: List[str] = [bias_reason, bos_reason]

        tl_kind = trendline_kind_for(bias)
        line, line_reason = fit_trendline(
            df_ltf,
            swings_ltf,
            tl_kind,
            lookback_bars=self.trendline_lookback,
            tolerance=atr_ltf * self.trendline_tolerance_atr_mult,
            min_touches=self.trendline_min_touches,
        )
        tl_break = None
        if line is not None:
            tl_break, tl_reason = detect_trendline_break(
                df_ltf, line, bias, buffer=atr_ltf * self.trendline_break_buffer_atr_mult
            )
            if tl_break is not None:
                confirmations.append("TRENDLINE_BREAK")
                confirmation_notes.append(tl_reason)
            else:
                confirmation_notes.append(tl_reason)
        else:
            confirmation_notes.append(line_reason)

        retest_ok, retest_reason = detect_retest(
            df_ltf,
            float(bos["level"]),
            bias,
            lookback=self.retest_lookback,
            tolerance=atr_ltf * 0.1,
        )
        if retest_ok:
            confirmations.append("RETEST")
        confirmation_notes.append(retest_reason)

        if self.require_retest and not retest_ok:
            return None, f"[M3] retest required but not found: {retest_reason}"

        if len(confirmations) < self.min_confirmations:
            return None, (
                f"[M3] only {len(confirmations)}/{self.min_confirmations} confirmations "
                f"({', '.join(confirmations)}) | " + " | ".join(confirmation_notes)
            )

        # --- Module 4: stop loss -------------------------------------------
        struct_level = structure_stop_level(structure, bias)
        if struct_level is None:
            return None, "[M4] no 1m structure level available for the stop loss"

        stop_loss, risk, stop_note = self._build_stop(entry_price, struct_level, bias, atr_ltf)
        if stop_loss is None:
            return None, f"[M4] {stop_note}"

        # --- Module 4: targets ---------------------------------------------
        opposing_zones = self._opposing_zones(df_ltf, swings_ltf, bias, atr_ltf)
        partial_tp, final_tp, tp_note = self._build_targets(
            entry_price, risk, bias, opposing_zones
        )
        breakeven_trigger = self._breakeven_trigger(
            entry_price, risk, bias, opposing_zones, structure, partial_tp
        )

        signal = TradeSignal(
            symbol=symbol,
            direction=bias,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=final_tp,
            order_type=OrderType.MARKET,
            partial_take_profit=partial_tp,
            partial_close_percent=self.partial_close_percent,
            breakeven_trigger=breakeven_trigger,
            risk_reward=abs(final_tp - entry_price) / risk if risk > 0 else 0.0,
            confirmations=confirmations,
            strategy_name=self.name,
            bar_time=bar_time,
            notes=(
                f"{bias.value} scalp | {len(confirmations)} confirmations "
                f"({', '.join(confirmations)}) | {stop_note} | {tp_note}"
            ),
            metadata={
                "htf_timeframe": self.htf,
                "ltf_timeframe": self.ltf,
                "htf_zone": htf_zone.to_dict(),
                "htf_bias_reason": bias_reason,
                "structure": structure.to_dict(),
                "break_of_structure": {
                    "level": float(bos["level"]),
                    "close": float(bos["close"]),
                    "side": bos["side"],
                },
                "trendline": line.to_dict() if line is not None else None,
                "trendline_broken": tl_break is not None,
                "retest": retest_ok,
                "atr_htf": atr_htf,
                "atr_ltf": atr_ltf,
                "structure_stop_level": struct_level,
                "partial_rr": self.partial_rr,
                "final_rr_target": self.final_rr,
                "max_trade_duration_minutes": self.max_trade_duration_minutes,
                "confirmation_notes": confirmation_notes,
            },
        )

        context.strategy_data["last_bias"] = bias.value
        context.strategy_data["last_setup_bar"] = bar_time.isoformat() if bar_time else None

        return signal, (
            f"SIGNAL {bias.value} {symbol} @ {entry_price:.5f} SL {stop_loss:.5f} "
            f"TP {final_tp:.5f} ({signal.risk_reward:.1f}R) | {', '.join(confirmations)}"
        )

    # ------------------------------------------------------------ Module 1 impl
    def _htf_bias(
        self, df_htf: pd.DataFrame, atr_htf: float
    ) -> Tuple[Direction, Optional[Zone], str]:
        """
        Establish the higher-timeframe directional bias from a zone reaction.
        Returns (direction, zone, reason).
        """
        swings = find_swing_points(df_htf, self.swing_lookback_htf)
        if not swings:
            return Direction.NONE, None, f"no confirmed swings on {self.htf}"

        tolerance = atr_htf * self.zone_cluster_atr_mult
        proximity = atr_htf * self.zone_proximity_atr_mult

        # Proximity is measured from how far price REACHED into the zone recently,
        # not from the last close. After a rejection the close can sit an ATR or
        # more above a support the candle's wick clearly tagged — that is exactly
        # the setup we are looking for, so probing with the close would miss it.
        window = df_htf.iloc[-self.exhaustion_lookback:] if self.exhaustion_lookback > 0 else df_htf
        recent_low = float(window["low"].min())
        recent_high = float(window["high"].max())

        supports = build_zones(
            df_htf, swings, ZoneKind.SUPPORT, tolerance, self.htf,
            min_touches=self.zone_min_touches, wick_ratio=self.exhaustion_wick_ratio,
        )
        resistances = build_zones(
            df_htf, swings, ZoneKind.RESISTANCE, tolerance, self.htf,
            min_touches=self.zone_min_touches, wick_ratio=self.exhaustion_wick_ratio,
        )

        if not supports and not resistances:
            return Direction.NONE, None, (
                f"no {self.htf} zone with >= {self.zone_min_touches} touches"
            )

        notes: List[str] = []
        # Support reaction -> long bias; resistance reaction -> short bias.
        for zones, direction, probe in (
            (supports, Direction.LONG, recent_low),
            (resistances, Direction.SHORT, recent_high),
        ):
            zone = find_active_zone(zones, probe, proximity)
            if zone is None:
                notes.append(
                    f"recent {'low' if direction is Direction.LONG else 'high'} {probe:.5f} "
                    f"not within {proximity:.5f} of any qualifying "
                    f"{'support' if direction is Direction.LONG else 'resistance'}"
                )
                continue

            exhausted, exh_note = detect_exhaustion(
                df_htf, zone, lookback=self.exhaustion_lookback,
                wick_ratio=self.exhaustion_wick_ratio,
            )
            if not exhausted:
                notes.append(f"{zone.kind.value} zone {zone.bottom:.5f}-{zone.top:.5f}: {exh_note}")
                continue

            reacting, react_note = detect_reaction(df_htf, zone, direction, self.reaction_bars)
            if not reacting:
                notes.append(f"{zone.kind.value} zone {zone.bottom:.5f}-{zone.top:.5f}: {react_note}")
                continue

            return direction, zone, (
                f"{self.htf} {zone.kind.value} {zone.bottom:.5f}-{zone.top:.5f} "
                f"({zone.touches} touches) | {exh_note} | {react_note}"
            )

        return Direction.NONE, None, "; ".join(notes) if notes else "no qualifying zone reaction"

    # ------------------------------------------------------------ Module 4 impl
    def _opposing_zones(
        self, df_ltf: pd.DataFrame, swings_ltf: List, trade_direction: Direction, atr_ltf: float
    ) -> List[Zone]:
        """
        The 1m zones standing in the way of ``trade_direction``: resistances for a
        long, supports for a short. Used as runner targets and as exit triggers.
        """
        kind = ZoneKind.RESISTANCE if trade_direction is Direction.LONG else ZoneKind.SUPPORT
        return build_zones(
            df_ltf,
            swings_ltf,
            kind,
            atr_ltf * self.zone_cluster_atr_mult,
            self.ltf,
            min_touches=self.ltf_zone_min_touches,
            wick_ratio=self.exhaustion_wick_ratio,
        )

    def _build_stop(
        self, entry: float, struct_level: float, direction: Direction, atr_ltf: float
    ) -> Tuple[Optional[float], float, str]:
        """
        Stop just beyond the immediate 1m structure, widened to a sane minimum and
        rejected if the structure is too wide to be a scalp.
        """
        buffer = atr_ltf * self.sl_buffer_atr_mult
        min_risk = atr_ltf * self.min_stop_atr_mult
        max_risk = atr_ltf * self.max_stop_atr_mult

        if direction is Direction.LONG:
            stop = struct_level - buffer
            if stop >= entry:
                return None, 0.0, f"structure low {struct_level:.5f} is not below entry {entry:.5f}"
            risk = entry - stop
            if risk < min_risk:
                stop = entry - min_risk
                risk = min_risk
        else:
            stop = struct_level + buffer
            if stop <= entry:
                return None, 0.0, f"structure high {struct_level:.5f} is not above entry {entry:.5f}"
            risk = stop - entry
            if risk < min_risk:
                stop = entry + min_risk
                risk = min_risk

        if risk > max_risk:
            return None, 0.0, (
                f"stop distance {risk:.5f} exceeds {self.max_stop_atr_mult}x ATR "
                f"({max_risk:.5f}) — structure too wide for a scalp"
            )

        return stop, risk, f"SL {stop:.5f} ({risk:.5f} risk, {risk / atr_ltf:.2f}x ATR)"

    def _build_targets(
        self, entry: float, risk: float, direction: Direction, opposing_zones: List[Zone]
    ) -> Tuple[float, float, str]:
        """
        Partial target at ``partial_rr``; runner at ``final_rr`` but capped by the
        next opposing 1m zone when ``use_zone_take_profit`` is on (spec: "exit when
        price reaches the next support/resistance zone, not a dollar amount").
        """
        sign = direction.sign
        partial_tp = entry + sign * self.partial_rr * risk
        final_tp = entry + sign * self.final_rr * risk
        note = f"TP1 {partial_tp:.5f} (1:{self.partial_rr:g}), TP2 {final_tp:.5f} (1:{self.final_rr:g})"

        if not self.use_zone_take_profit or not opposing_zones:
            return partial_tp, final_tp, note

        zone = next_zone_beyond(opposing_zones, entry, direction, min_distance=risk)
        if zone is None:
            return partial_tp, final_tp, note

        zone_edge = zone.bottom if direction is Direction.LONG else zone.top
        beyond_partial = (zone_edge > partial_tp) if direction is Direction.LONG else (zone_edge < partial_tp)
        closer_than_final = (zone_edge < final_tp) if direction is Direction.LONG else (zone_edge > final_tp)

        if beyond_partial and closer_than_final:
            final_tp = zone_edge
            note = (
                f"TP1 {partial_tp:.5f} (1:{self.partial_rr:g}), TP2 capped at opposing "
                f"{self.ltf} zone {zone_edge:.5f} ({abs(zone_edge - entry) / risk:.1f}R, "
                f"{zone.touches} touches)"
            )
        elif not beyond_partial:
            note += f" | warning: opposing zone {zone_edge:.5f} sits inside the 1:{self.partial_rr:g} target"

        return partial_tp, final_tp, note

    def _breakeven_trigger(
        self,
        entry: float,
        risk: float,
        direction: Direction,
        opposing_zones: List[Zone],
        structure: StructureRead,
        partial_tp: float,
    ) -> float:
        """
        "Move SL to breakeven once price clears the secondary high/low or a
        significant 1m zone." Uses the nearest of (next opposing zone edge,
        secondary swing extreme) at least 0.5R away, else falls back to
        ``breakeven_rr``.
        """
        min_distance = 0.5 * risk
        candidates: List[float] = []

        zone = next_zone_beyond(opposing_zones, entry, direction, min_distance=min_distance)
        if zone is not None:
            candidates.append(zone.bottom if direction is Direction.LONG else zone.top)

        pivots = structure.highs if direction is Direction.LONG else structure.lows
        for pivot in reversed(pivots):
            if direction is Direction.LONG and pivot.price > entry + min_distance:
                candidates.append(pivot.price)
                break
            if direction is Direction.SHORT and pivot.price < entry - min_distance:
                candidates.append(pivot.price)
                break

        if candidates:
            trigger = min(candidates) if direction is Direction.LONG else max(candidates)
        else:
            trigger = entry + direction.sign * self.breakeven_rr * risk

        # Never later than the partial target — the partial always banks + moves to BE.
        if direction is Direction.LONG:
            return min(trigger, partial_tp)
        return max(trigger, partial_tp)

    # ----------------------------------------------------------- position mgmt
    def manage_position(
        self,
        symbol: str,
        data: Dict[str, pd.DataFrame],
        context: SymbolContext,
        position: Position,
    ) -> List[ManagementAction]:
        df_ltf = data.get("ltf")
        if df_ltf is None or len(df_ltf) == 0:
            return []

        high = float(df_ltf["high"].iloc[-1])
        low = float(df_ltf["low"].iloc[-1])
        close = float(df_ltf["close"].iloc[-1])
        favourable_extreme = high if position.is_long else low
        actions: List[ManagementAction] = []

        # 1. Partial target -> bank part of the position and go risk-free.
        if (
            position.partial_take_profit is not None
            and not position.partial_done
            and position.partial_close_percent > 0
            and position.is_favourable(favourable_extreme, position.partial_take_profit)
        ):
            actions.append(ManagementAction(
                action=ManagementActionType.PARTIAL_CLOSE,
                percent=position.partial_close_percent,
                reason=(
                    f"TP1 {position.partial_take_profit:.5f} reached "
                    f"({position.rr_at(position.partial_take_profit):.1f}R) — banking "
                    f"{position.partial_close_percent:.0f}%"
                ),
                event_type=TradeEventType.PARTIAL_TP,
                metadata={"target": position.partial_take_profit},
            ))
            if not position.breakeven_done:
                actions.append(ManagementAction(
                    action=ManagementActionType.MOVE_STOP,
                    price=position.entry_price,
                    reason="stop to breakeven after banking TP1",
                    event_type=TradeEventType.BREAKEVEN,
                ))
            return actions

        # 2. Breakeven once the secondary high/low is cleared.
        if (
            self.breakeven_on_secondary_level
            and not position.breakeven_done
            and position.breakeven_trigger is not None
            and position.is_favourable(favourable_extreme, position.breakeven_trigger)
        ):
            actions.append(ManagementAction(
                action=ManagementActionType.MOVE_STOP,
                price=position.entry_price,
                reason=(
                    f"price cleared secondary level {position.breakeven_trigger:.5f} "
                    f"— stop to breakeven"
                ),
                event_type=TradeEventType.BREAKEVEN,
            ))

        # 3. Time stop — the spec wants the scalp done inside 30 minutes.
        if self.close_after_max_duration and self.max_trade_duration_minutes > 0:
            age = datetime.utcnow() - position.opened_at
            if age > timedelta(minutes=self.max_trade_duration_minutes):
                actions.append(ManagementAction(
                    action=ManagementActionType.CLOSE,
                    reason=(
                        f"max trade duration {self.max_trade_duration_minutes} min exceeded "
                        f"(open {age.total_seconds() / 60:.0f} min, "
                        f"{position.rr_at(close):+.1f}R)"
                    ),
                    event_type=TradeEventType.CLOSED,
                ))
                return actions

        # 4. Dynamic zone exit: strong reaction at the next opposing zone while in profit.
        if self.zone_exit_enabled and position.rr_at(close) >= self.zone_exit_min_rr:
            zone_action = self._zone_exit_action(df_ltf, position, close)
            if zone_action is not None:
                actions.append(zone_action)
                return actions

        # 5. Optional scale-in on a fresh structure break in our favour.
        if self.enable_scale_in and position.scale_in_count < self.max_scale_ins:
            scale_action = self._scale_in_action(df_ltf, position)
            if scale_action is not None:
                actions.append(scale_action)

        return actions

    def _zone_exit_action(
        self, df_ltf: pd.DataFrame, position: Position, close: float
    ) -> Optional[ManagementAction]:
        atr_ltf = last_atr(df_ltf, self.atr_period)
        swings = find_swing_points(df_ltf, self.swing_lookback_ltf)
        zones = self._opposing_zones(df_ltf, swings, position.direction, atr_ltf)
        zone = find_active_zone(zones, close, atr_ltf * 0.5)
        if zone is None:
            return None

        exhausted, note = detect_exhaustion(
            df_ltf, zone, lookback=2, wick_ratio=self.exhaustion_wick_ratio
        )
        if not exhausted:
            return None

        return ManagementAction(
            action=ManagementActionType.CLOSE,
            reason=(
                f"price reacting at opposing {self.ltf} zone "
                f"{zone.bottom:.5f}-{zone.top:.5f} ({note}) at {position.rr_at(close):+.1f}R"
            ),
            event_type=TradeEventType.CLOSED,
            metadata={"zone": zone.to_dict()},
        )

    def _scale_in_action(
        self, df_ltf: pd.DataFrame, position: Position
    ) -> Optional[ManagementAction]:
        """
        Spec: "if price breaks another S/R zone and retests it, a second position
        can be opened". Off unless ``enable_scale_in`` is true.
        """
        atr_ltf = last_atr(df_ltf, self.atr_period)
        swings = find_swing_points(df_ltf, self.swing_lookback_ltf)
        structure = read_structure(swings, self.structure_min_swings)
        if structure.bias is not position.direction:
            return None

        bos, bos_reason = detect_break_of_structure(
            df_ltf, structure, position.direction, buffer=atr_ltf * self.bos_buffer_atr_mult
        )
        if bos is None:
            return None

        retest_ok, retest_reason = detect_retest(
            df_ltf, float(bos["level"]), position.direction,
            lookback=self.retest_lookback, tolerance=atr_ltf * 0.1,
        )
        if not retest_ok:
            return None

        return ManagementAction(
            action=ManagementActionType.SCALE_IN,
            reason=f"scale-in: {bos_reason}; {retest_reason}",
            event_type=TradeEventType.SCALED_IN,
            metadata={"break_level": float(bos["level"])},
        )


def _bar_time(df: pd.DataFrame, index: int) -> Optional[datetime]:
    if df is None or len(df) == 0:
        return None
    value = df["time"].iloc[index] if "time" in df.columns else df.index[index]
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime()
    if isinstance(value, datetime):
        return value
    return None
