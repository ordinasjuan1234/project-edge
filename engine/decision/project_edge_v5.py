"""PROJECT EDGE v5 - candidata dual setup BTC/ETH, exclusiva de backtest.

No esta conectada al runner PAPER. Mantiene el plan monetario conservador de v3,
pero separa dos setups intradia y agrega un veto explicito por costo/riesgo.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from engine.decision.project_edge_v3 import ProjectEdgeV3, ProjectEdgeV3Config


@dataclass(frozen=True)
class ProjectEdgeV5Config(ProjectEdgeV3Config):
    adx_strong: float = 30.0
    max_trigger_distance_atr: float = 0.75
    max_cost_risk_ratio: float = 0.35
    breakout_lookback: int = 4

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.adx_strong < self.adx_minimum:
            raise ValueError("adx_strong debe ser >= adx_minimum.")
        if self.max_trigger_distance_atr <= 0:
            raise ValueError("max_trigger_distance_atr debe ser mayor que cero.")
        if not 0 < self.max_cost_risk_ratio < 1:
            raise ValueError("max_cost_risk_ratio debe estar entre 0 y 1.")
        if self.breakout_lookback < 1:
            raise ValueError("breakout_lookback debe ser >= 1.")


class ProjectEdgeV5(ProjectEdgeV3):
    """Candidata aislada: decide setups, nunca ejecuta ordenes."""

    FEATURE_FIELDS = ProjectEdgeV3.FEATURE_FIELDS + (
        "pe_breakout_long",
        "pe_breakout_short",
    )
    DIAGNOSTIC_FIELDS = ProjectEdgeV3.DIAGNOSTIC_FIELDS + (
        "regime_direction",
        "setup_type",
        "breakout_30m",
        "trigger_distance_atr_5m",
    )

    def __init__(self, config: ProjectEdgeV5Config | None = None) -> None:
        super().__init__(config or ProjectEdgeV5Config())
        self.config: ProjectEdgeV5Config

    @staticmethod
    def _ema_direction_ok(
        fast: float | None,
        slow: float | None,
        slope: float | None,
        direction: str,
    ) -> bool:
        if fast is None or slow is None or slope is None:
            return False
        if direction == "LONG":
            return fast > slow and slope > 0
        return fast < slow and slope < 0

    @staticmethod
    def _slope_direction_ok(slope: float | None, direction: str) -> bool:
        if slope is None:
            return False
        return slope > 0 if direction == "LONG" else slope < 0

    @staticmethod
    def _opposite_state(direction: str) -> str:
        return "BEARISH" if direction == "LONG" else "BULLISH"

    def add_features(self, data: pd.DataFrame) -> pd.DataFrame:
        result = super().add_features(data)
        if {"structure_break", "break_direction"}.issubset(result.columns):
            structural = result["structure_break"].isin(["BOS", "CHoCH"])
            broke_up = structural & result["break_direction"].eq("UP")
            broke_down = structural & result["break_direction"].eq("DOWN")
            result["pe_breakout_long"] = broke_up.rolling(
                self.config.breakout_lookback,
                min_periods=1,
            ).max().astype(bool)
            result["pe_breakout_short"] = broke_down.rolling(
                self.config.breakout_lookback,
                min_periods=1,
            ).max().astype(bool)
        else:
            result["pe_breakout_long"] = False
            result["pe_breakout_short"] = False
        return result

    def _regime_direction(
        self,
        values: dict[str, Any],
        states: dict[str, str],
    ) -> str | None:
        fast = self._clean_number(values.get("pe_ema_fast_1H"))
        slow = self._clean_number(values.get("pe_ema_slow_1H"))
        slope = self._clean_number(values.get("pe_ema_slope_1H"))
        if self._ema_direction_ok(fast, slow, slope, "LONG") and states["1H"] != "BEARISH":
            return "LONG"
        if self._ema_direction_ok(fast, slow, slope, "SHORT") and states["1H"] != "BULLISH":
            return "SHORT"
        return None

    def _quality_score(
        self,
        *,
        direction: str,
        states: dict[str, str],
        adx: float,
        adx_rising: bool,
        setup_type: str,
        fvg: bool,
        trigger_distance_atr: float,
    ) -> float:
        expected = "BULLISH" if direction == "LONG" else "BEARISH"
        score = min(max((adx - self.config.adx_minimum) / 20.0, 0.0), 1.0) * 25.0
        score += 20.0 if setup_type == "PULLBACK_CONTINUATION" else 15.0
        score += 10.0 if states["1H"] == expected else 0.0
        score += 10.0 if states["4H"] == expected else 0.0
        score += 5.0 if fvg else 0.0
        score += 5.0 if adx_rising else 0.0
        proximity = 1.0 - min(
            max(trigger_distance_atr / self.config.max_trigger_distance_atr, 0.0),
            1.0,
        )
        score += proximity * 15.0
        return float(score)

    def decide_snapshot(self, snapshot: dict[str, Any] | pd.Series) -> dict[str, Any]:
        values = dict(snapshot)
        states = {
            timeframe: str(values.get(f"state_{timeframe}", "UNDEFINED")).upper()
            for timeframe in self.REQUIRED_TIMEFRAMES
        }
        for timeframe, state in states.items():
            if state in {"NAN", "NONE"}:
                states[timeframe] = "UNDEFINED"

        direction = self._regime_direction(values, states)
        checks: dict[str, bool] = {"regime_1h": direction is not None}
        atr_15m = self._clean_number(values.get("pe_atr_15M"))
        if direction is None:
            return {
                "strategy": "PROJECT_EDGE_V5_DUAL_SETUP",
                "decision": "WAIT",
                "direction": None,
                "setup_type": None,
                "can_execute": False,
                "reason": "1H no define un regimen EMA/estructura util.",
                "checks": checks,
                "states": states,
                "atr_15m": atr_15m,
                "quality_score": 0.0,
                "diagnostics": self._diagnostics(values, states, None, None, 0.0),
                "config": asdict(self.config),
            }

        side = "long" if direction == "LONG" else "short"
        expected = "BULLISH" if direction == "LONG" else "BEARISH"
        opposite = self._opposite_state(direction)

        ema_4h_opposite = self._ema_direction_ok(
            self._clean_number(values.get("pe_ema_fast_4H")),
            self._clean_number(values.get("pe_ema_slow_4H")),
            self._clean_number(values.get("pe_ema_slope_4H")),
            "SHORT" if direction == "LONG" else "LONG",
        )
        macro_not_strongly_opposed = not (
            states["4H"] == opposite and ema_4h_opposite
        )

        ema_30m_ok = self._ema_direction_ok(
            self._clean_number(values.get("pe_ema_fast_30M")),
            self._clean_number(values.get("pe_ema_slow_30M")),
            self._clean_number(values.get("pe_ema_slope_30M")),
            direction,
        )
        slope_30m_ok = self._slope_direction_ok(
            self._clean_number(values.get("pe_ema_slope_30M")),
            direction,
        )
        breakout_30m = self._clean_bool(values.get(f"pe_breakout_{side}_30M"))
        setup_a_context = states["30M"] == expected and ema_30m_ok
        setup_b_context = (
            states["30M"] != opposite
            and breakout_30m
            and slope_30m_ok
        )

        pullback_ok = self._clean_bool(values.get(f"pe_pullback_{side}_15M"))
        trigger_ok = self._clean_bool(values.get(f"pe_trigger_{side}_5M"))

        adx = self._clean_number(values.get("pe_adx_1H"))
        adx_rising = self._clean_bool(values.get("pe_adx_rising_1H"))
        adx_ok = bool(
            adx is not None
            and adx >= self.config.adx_minimum
            and (adx_rising or adx >= self.config.adx_strong)
        )

        atr_5m = self._clean_number(values.get("pe_atr_5M"))
        close_5m = self._clean_number(values.get("pe_close_5M"))
        distance_pct = self._clean_number(values.get("pe_distance_from_ema_pct_5M"))
        trigger_distance_atr = float("inf")
        if (
            atr_5m is not None
            and atr_5m > 0
            and close_5m is not None
            and close_5m > 0
            and distance_pct is not None
        ):
            trigger_distance_atr = abs(distance_pct) * close_5m / atr_5m
        distance_ok = trigger_distance_atr <= self.config.max_trigger_distance_atr
        atr_ok = atr_15m is not None and atr_15m > 0
        fvg = self._clean_bool(values.get(f"pe_fvg_{side}_15M")) or self._clean_bool(
            values.get(f"pe_fvg_{side}_5M")
        )

        setup_type = None
        if setup_a_context:
            setup_type = "PULLBACK_CONTINUATION"
        elif setup_b_context:
            setup_type = "BREAKOUT_RETEST"

        checks.update(
            {
                "macro_4h_not_strongly_opposed": macro_not_strongly_opposed,
                "setup_30m": setup_type is not None,
                "adx_1h": adx_ok,
                "pullback_15m": pullback_ok,
                "trigger_5m": trigger_ok,
                "trigger_not_extended": distance_ok,
                "atr_15m": atr_ok,
                "fvg_confluence": fvg,
            }
        )
        required = (
            "regime_1h",
            "macro_4h_not_strongly_opposed",
            "setup_30m",
            "adx_1h",
            "pullback_15m",
            "trigger_5m",
            "trigger_not_extended",
            "atr_15m",
        )
        can_execute = all(checks[name] for name in required)
        score = self._quality_score(
            direction=direction,
            states=states,
            adx=adx or 0.0,
            adx_rising=adx_rising,
            setup_type=setup_type or "BREAKOUT_RETEST",
            fvg=fvg,
            trigger_distance_atr=(trigger_distance_atr if trigger_distance_atr != float("inf") else self.config.max_trigger_distance_atr),
        ) if setup_type is not None else 0.0

        if can_execute:
            decision_name = f"READY_{direction}"
            reason = f"{setup_type}: regimen 1H, contexto 30M, pullback 15M y trigger 5M confirmados."
        else:
            decision_name = f"WATCH_{direction}"
            missing = [name for name in required if not checks[name]]
            reason = "Faltan condiciones v5: " + ", ".join(missing) + "."

        return {
            "strategy": "PROJECT_EDGE_V5_DUAL_SETUP",
            "decision": decision_name,
            "direction": direction,
            "setup_type": setup_type,
            "can_execute": can_execute,
            "reason": reason,
            "checks": checks,
            "states": states,
            "atr_15m": atr_15m,
            "quality_score": score,
            "diagnostics": self._diagnostics(
                values,
                states,
                direction,
                setup_type,
                trigger_distance_atr,
            ),
            "config": asdict(self.config),
        }

    def _diagnostics(
        self,
        values: dict[str, Any],
        states: dict[str, str],
        direction: str | None,
        setup_type: str | None,
        trigger_distance_atr: float,
    ) -> dict[str, Any]:
        base = super().diagnostic_snapshot(values, states, direction)
        side = "long" if direction == "LONG" else "short" if direction == "SHORT" else None
        base.update(
            {
                "regime_direction": direction,
                "setup_type": setup_type,
                "breakout_30m": self._clean_bool(values.get(f"pe_breakout_{side}_30M")) if side else False,
                "trigger_distance_atr_5m": None if trigger_distance_atr == float("inf") else float(trigger_distance_atr),
            }
        )
        return base

    def build_trade_plan(
        self,
        decision: dict[str, Any],
        entry_price: float,
        account_equity: float,
    ) -> dict[str, Any]:
        plan = super().build_trade_plan(decision, entry_price, account_equity)
        if not plan.get("approved"):
            return plan
        risk_budget = float(plan.get("risk_budget", 0.0))
        estimated_cost = float(plan.get("estimated_cost", 0.0))
        ratio = estimated_cost / risk_budget if risk_budget > 0 else float("inf")
        plan["estimated_cost_risk_ratio"] = float(ratio)
        if ratio > self.config.max_cost_risk_ratio:
            plan["approved"] = False
            plan["reason"] = (
                "Costo estimado excesivo para v5: "
                f"{ratio:.2%} del presupuesto de riesgo."
            )
            return plan
        plan["reason"] = "Riesgo y costo v5 aprobados para PAPER backtest."
        return plan
