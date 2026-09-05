"""PROJECT EDGE v6 - candidata de scalping intradia BTC/ETH.

Esta estrategia esta aislada del runner AUTO vigente. Usa 1H solo como contexto,
15M para formar el setup y 5M como gatillo. 4H funciona unicamente como veto
cuando estructura y EMA presentan una oposicion fuerte.

No ejecuta ordenes ni se conecta a un broker.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import pandas as pd

from engine.decision.project_edge_v3 import ProjectEdgeV3, ProjectEdgeV3Config


@dataclass(frozen=True)
class ProjectEdgeV6Config(ProjectEdgeV3Config):
    # Perfil intradia/scalp: menor riesgo y menor permanencia esperada.
    adx_minimum: float = 20.0
    stop_atr_multiple: float = 1.0
    minimum_stop_pct: float = 0.004
    maximum_stop_pct: float = 0.015
    gross_reward_risk: float = 1.5
    minimum_net_reward_risk: float = 1.0
    risk_pct: float = 0.003
    cooldown_minutes: int = 15
    loss_guard_minutes: int = 180

    # Filtros especificos v6.
    max_trigger_distance_atr: float = 1.0
    strong_adx_15m: float = 28.0

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.max_trigger_distance_atr <= 0:
            raise ValueError("max_trigger_distance_atr debe ser mayor que cero.")
        if self.strong_adx_15m < self.adx_minimum:
            raise ValueError("strong_adx_15m debe ser >= adx_minimum.")


class ProjectEdgeV6(ProjectEdgeV3):
    """Candidata SCALP: 1H contexto, 15M setup, 5M gatillo."""

    DIAGNOSTIC_FIELDS = ProjectEdgeV3.DIAGNOSTIC_FIELDS + (
        "context_direction_1h",
        "setup_type",
        "adx_15m",
        "trigger_distance_atr_5m",
    )

    def __init__(self, config: ProjectEdgeV6Config | None = None) -> None:
        super().__init__(config or ProjectEdgeV6Config())
        self.config: ProjectEdgeV6Config

    @staticmethod
    def _ema_direction(
        fast: float | None,
        slow: float | None,
    ) -> str | None:
        if fast is None or slow is None:
            return None
        if fast > slow:
            return "LONG"
        if fast < slow:
            return "SHORT"
        return None

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
    def _opposite_state(direction: str) -> str:
        return "BEARISH" if direction == "LONG" else "BULLISH"

    def _context_direction(
        self,
        values: dict[str, Any],
        states: dict[str, str],
    ) -> str | None:
        fast = self._clean_number(values.get("pe_ema_fast_1H"))
        slow = self._clean_number(values.get("pe_ema_slow_1H"))
        direction = self._ema_direction(fast, slow)
        if direction is None:
            return None
        if states["1H"] == self._opposite_state(direction):
            return None
        return direction

    def decide_snapshot(self, snapshot: dict[str, Any] | pd.Series) -> dict[str, Any]:
        values = dict(snapshot)
        states = {
            timeframe: str(values.get(f"state_{timeframe}", "UNDEFINED")).upper()
            for timeframe in self.REQUIRED_TIMEFRAMES
        }
        for timeframe, state in states.items():
            if state in {"NAN", "NONE"}:
                states[timeframe] = "UNDEFINED"

        direction = self._context_direction(values, states)
        atr_15m = self._clean_number(values.get("pe_atr_15M"))
        checks: dict[str, bool] = {"context_1h": direction is not None}

        if direction is None:
            return {
                "strategy": "PROJECT_EDGE_V6_SCALP",
                "decision": "WAIT",
                "direction": None,
                "setup_type": None,
                "can_execute": False,
                "reason": "1H no ofrece contexto EMA util para scalping.",
                "checks": checks,
                "states": states,
                "atr_15m": atr_15m,
                "quality_score": 0.0,
                "diagnostics": self._diagnostics(
                    values, states, None, None, float("inf")
                ),
                "config": asdict(self.config),
            }

        side = "long" if direction == "LONG" else "short"
        expected = "BULLISH" if direction == "LONG" else "BEARISH"
        opposite = self._opposite_state(direction)

        # 4H no debe alinear la entrada. Solo veta una oposicion clara.
        ema_4h_opposite = self._ema_direction_ok(
            self._clean_number(values.get("pe_ema_fast_4H")),
            self._clean_number(values.get("pe_ema_slow_4H")),
            self._clean_number(values.get("pe_ema_slope_4H")),
            "SHORT" if direction == "LONG" else "LONG",
        )
        macro_not_strongly_opposed = not (
            states["4H"] == opposite and ema_4h_opposite
        )

        ema_15m_ok = self._ema_direction_ok(
            self._clean_number(values.get("pe_ema_fast_15M")),
            self._clean_number(values.get("pe_ema_slow_15M")),
            self._clean_number(values.get("pe_ema_slope_15M")),
            direction,
        )
        pullback_15m = self._clean_bool(
            values.get(f"pe_pullback_{side}_15M")
        )

        adx_15m = self._clean_number(values.get("pe_adx_15M"))
        adx_rising_15m = self._clean_bool(values.get("pe_adx_rising_15M"))
        adx_ok = bool(
            adx_15m is not None
            and adx_15m >= self.config.adx_minimum
            and (
                adx_rising_15m
                or adx_15m >= self.config.strong_adx_15m
            )
        )

        # Setup A: retroceso 15M dentro del contexto 1H.
        pullback_setup = pullback_15m and states["15M"] != opposite
        # Setup B: continuacion 15M con EMA/estructura alineadas y fuerza.
        momentum_setup = (
            states["15M"] == expected
            and ema_15m_ok
            and adx_ok
        )

        setup_type = None
        if pullback_setup:
            setup_type = "SCALP_PULLBACK"
        elif momentum_setup:
            setup_type = "SCALP_MOMENTUM"

        trigger_5m = self._clean_bool(values.get(f"pe_trigger_{side}_5M"))
        atr_5m = self._clean_number(values.get("pe_atr_5M"))
        close_5m = self._clean_number(values.get("pe_close_5M"))
        distance_pct = self._clean_number(
            values.get("pe_distance_from_ema_pct_5M")
        )
        trigger_distance_atr = float("inf")
        if (
            atr_5m is not None
            and atr_5m > 0
            and close_5m is not None
            and close_5m > 0
            and distance_pct is not None
        ):
            trigger_distance_atr = abs(distance_pct) * close_5m / atr_5m
        trigger_not_extended = (
            trigger_distance_atr <= self.config.max_trigger_distance_atr
        )
        atr_ok = atr_15m is not None and atr_15m > 0
        fvg = self._clean_bool(values.get(f"pe_fvg_{side}_15M")) or self._clean_bool(
            values.get(f"pe_fvg_{side}_5M")
        )

        checks.update(
            {
                "macro_4h_not_strongly_opposed": macro_not_strongly_opposed,
                "setup_15m": setup_type is not None,
                "adx_15m": adx_ok,
                "trigger_5m": trigger_5m,
                "trigger_not_extended": trigger_not_extended,
                "atr_15m": atr_ok,
                "fvg_confluence": fvg,
            }
        )
        required = (
            "context_1h",
            "macro_4h_not_strongly_opposed",
            "setup_15m",
            "adx_15m",
            "trigger_5m",
            "trigger_not_extended",
            "atr_15m",
        )
        can_execute = all(checks[name] for name in required)

        score = 0.0
        if setup_type is not None:
            score += 25.0 if setup_type == "SCALP_PULLBACK" else 20.0
            score += min(
                max(
                    ((adx_15m or 0.0) - self.config.adx_minimum) / 20.0,
                    0.0,
                ),
                1.0,
            ) * 25.0
            score += 15.0 if states["15M"] == expected else 5.0
            score += 5.0 if fvg else 0.0
            if trigger_distance_atr != float("inf"):
                proximity = 1.0 - min(
                    trigger_distance_atr / self.config.max_trigger_distance_atr,
                    1.0,
                )
                score += proximity * 20.0

        if can_execute:
            decision_name = f"READY_{direction}"
            reason = (
                f"{setup_type}: contexto 1H, setup 15M y gatillo 5M confirmados."
            )
        else:
            decision_name = f"WATCH_{direction}"
            missing = [name for name in required if not checks[name]]
            reason = "Faltan condiciones v6: " + ", ".join(missing) + "."

        return {
            "strategy": "PROJECT_EDGE_V6_SCALP",
            "decision": decision_name,
            "direction": direction,
            "setup_type": setup_type,
            "can_execute": can_execute,
            "reason": reason,
            "checks": checks,
            "states": states,
            "atr_15m": atr_15m,
            "quality_score": float(score),
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
        base.update(
            {
                "context_direction_1h": direction,
                "setup_type": setup_type,
                "adx_15m": self._clean_number(values.get("pe_adx_15M")),
                "trigger_distance_atr_5m": (
                    None
                    if trigger_distance_atr == float("inf")
                    else float(trigger_distance_atr)
                ),
            }
        )
        return base
