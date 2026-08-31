"""PROJECT EDGE v4 - candidata intradia aislada para backtest.

La v4 NO esta conectada al runner PAPER. Reutiliza las mismas variables
causales y el mismo plan de riesgo de v3, pero cambia el contexto de entrada:
1H define la direccion y 4H solo bloquea una oposicion estructural + EMA clara.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from engine.decision.project_edge_v3 import (
    ProjectEdgeV3,
    ProjectEdgeV3Config,
)


@dataclass(frozen=True)
class ProjectEdgeV4Config(ProjectEdgeV3Config):
    """Reglas predefinidas antes de ejecutar periodos fuera de muestra."""

    adx_minimum: float = 30.0
    efficiency_minimum: float = 0.30
    max_trigger_distance_atr: float = 1.0

    def __post_init__(self) -> None:
        super().__post_init__()
        if not 0 < self.efficiency_minimum <= 1:
            raise ValueError("efficiency_minimum debe estar entre 0 y 1.")
        if self.max_trigger_distance_atr <= 0:
            raise ValueError("max_trigger_distance_atr debe ser mayor que cero.")


class ProjectEdgeV4(ProjectEdgeV3):
    """Candidata experimental: genera decisiones, nunca ejecuta ordenes."""

    def __init__(self, config: ProjectEdgeV4Config | None = None) -> None:
        super().__init__(config or ProjectEdgeV4Config())
        self.config: ProjectEdgeV4Config

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
    def _opposite(direction: str) -> str:
        return "BEARISH" if direction == "LONG" else "BULLISH"

    def quality_score(
        self,
        *,
        adx: float,
        efficiency: float,
        macro_aligned: bool,
        thirty_aligned: bool,
        fvg: bool,
        adx_rising: bool,
    ) -> float:
        """Puntaje fijo para elegir un solo simbolo cuando ambos confirman."""
        score = min(max(adx, 0.0) / 50.0, 1.0) * 40.0
        score += min(max(efficiency, 0.0) / 0.60, 1.0) * 30.0
        score += 10.0 if macro_aligned else 0.0
        score += 10.0 if thirty_aligned else 0.0
        score += 5.0 if fvg else 0.0
        score += 5.0 if adx_rising else 0.0
        return float(score)

    def decide_snapshot(
        self,
        snapshot: dict[str, Any] | pd.Series,
    ) -> dict[str, Any]:
        """Evalua solo informacion conocida al cierre de la vela actual."""
        values = dict(snapshot)
        states = {
            timeframe: str(
                values.get(f"state_{timeframe}", "UNDEFINED")
            ).upper()
            for timeframe in self.REQUIRED_TIMEFRAMES
        }
        for timeframe, state in states.items():
            if state in {"NAN", "NONE"}:
                states[timeframe] = "UNDEFINED"

        one_hour = states["1H"]
        direction = (
            "LONG" if one_hour == "BULLISH"
            else "SHORT" if one_hour == "BEARISH"
            else None
        )
        checks: dict[str, bool] = {
            "direction_1h": direction is not None,
        }
        atr_15m = self._clean_number(values.get("pe_atr_15M"))
        if direction is None:
            return {
                "strategy": "PROJECT_EDGE_V4_INTRADAY",
                "decision": "WAIT",
                "direction": None,
                "can_execute": False,
                "reason": "1H todavia no define una direccion estructural.",
                "checks": checks,
                "states": states,
                "atr_15m": atr_15m,
                "quality_score": 0.0,
                "diagnostics": self.diagnostic_snapshot(values, states, None),
                "config": asdict(self.config),
            }

        side = "long" if direction == "LONG" else "short"
        opposite = self._opposite(direction)
        ema_1h_ok = self._ema_direction_ok(
            self._clean_number(values.get("pe_ema_fast_1H")),
            self._clean_number(values.get("pe_ema_slow_1H")),
            self._clean_number(values.get("pe_ema_slope_1H")),
            direction,
        )
        ema_4h_opposite = self._ema_direction_ok(
            self._clean_number(values.get("pe_ema_fast_4H")),
            self._clean_number(values.get("pe_ema_slow_4H")),
            self._clean_number(values.get("pe_ema_slope_4H")),
            "SHORT" if direction == "LONG" else "LONG",
        )
        macro_not_opposed = not (
            states["4H"] == opposite and ema_4h_opposite
        )
        thirty_not_opposed = states["30M"] != opposite
        adx = self._clean_number(values.get("pe_adx_1H"))
        efficiency = self._clean_number(
            values.get("pe_efficiency_ratio_1H")
        )
        adx_ok = adx is not None and adx >= self.config.adx_minimum
        efficiency_ok = (
            efficiency is not None
            and efficiency >= self.config.efficiency_minimum
        )
        pullback_ok = self._clean_bool(
            values.get(f"pe_pullback_{side}_15M")
        )
        trigger_ok = self._clean_bool(
            values.get(f"pe_trigger_{side}_5M")
        )
        atr_5m = self._clean_number(values.get("pe_atr_5M"))
        close_5m = self._clean_number(values.get("pe_close_5M"))
        distance_pct = self._clean_number(
            values.get("pe_distance_from_ema_pct_5M")
        )
        distance_ok = bool(
            atr_5m is not None
            and atr_5m > 0
            and close_5m is not None
            and close_5m > 0
            and distance_pct is not None
            and abs(distance_pct) * close_5m
            <= atr_5m * self.config.max_trigger_distance_atr
        )
        fvg = self._clean_bool(
            values.get(f"pe_fvg_{side}_15M")
        ) or self._clean_bool(values.get(f"pe_fvg_{side}_5M"))
        atr_ok = atr_15m is not None and atr_15m > 0

        checks.update(
            {
                "ema_1h": ema_1h_ok,
                "macro_4h_not_strongly_opposed": macro_not_opposed,
                "structure_30m_not_opposed": thirty_not_opposed,
                "adx_1h": adx_ok,
                "efficiency_1h": efficiency_ok,
                "pullback_15m": pullback_ok,
                "trigger_5m": trigger_ok,
                "trigger_not_extended": distance_ok,
                "atr_15m": atr_ok,
                "fvg_confluence": fvg,
            }
        )
        required = (
            "direction_1h",
            "ema_1h",
            "macro_4h_not_strongly_opposed",
            "structure_30m_not_opposed",
            "adx_1h",
            "efficiency_1h",
            "pullback_15m",
            "trigger_5m",
            "trigger_not_extended",
            "atr_15m",
        )
        can_execute = all(checks[name] for name in required)
        score = self.quality_score(
            adx=adx or 0.0,
            efficiency=efficiency or 0.0,
            macro_aligned=states["4H"] == states["1H"],
            thirty_aligned=states["30M"] == states["1H"],
            fvg=fvg,
            adx_rising=self._clean_bool(values.get("pe_adx_rising_1H")),
        )
        if can_execute:
            decision = f"READY_{direction}"
            reason = (
                "Direccion 1H, calidad ADX/eficiencia, retroceso 15M y "
                "gatillo 5M confirmados; 4H no presenta oposicion fuerte."
            )
        else:
            decision = f"WATCH_{direction}"
            missing = [name for name in required if not checks[name]]
            reason = "Faltan condiciones v4: " + ", ".join(missing) + "."

        return {
            "strategy": "PROJECT_EDGE_V4_INTRADAY",
            "decision": decision,
            "direction": direction,
            "can_execute": can_execute,
            "reason": reason,
            "checks": checks,
            "states": states,
            "atr_15m": atr_15m,
            "quality_score": score,
            "diagnostics": self.diagnostic_snapshot(values, states, direction),
            "config": asdict(self.config),
        }

    def build_trade_plan(
        self,
        decision: dict[str, Any],
        entry_price: float,
        account_equity: float,
    ) -> dict[str, Any]:
        """Usa sin cambios el plan monetario conservador de v3."""
        translated = dict(decision)
        translated["strategy"] = "PROJECT_EDGE_V3"
        plan = super().build_trade_plan(
            decision=translated,
            entry_price=entry_price,
            account_equity=account_equity,
        )
        if plan.get("approved"):
            plan["reason"] = "Riesgo v4 aprobado solo para backtest PAPER."
        return plan
