"""PROJECT EDGE v3 - estrategia propia de tendencia y retroceso.

Este modulo comparte exactamente las mismas reglas entre el runner PAPER
y el backtest historico. No ejecuta ordenes ni se conecta a un broker.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import math
from typing import Any, Iterable

import pandas as pd


@dataclass(frozen=True)
class ProjectEdgeV3Config:
    ema_fast_period: int = 20
    ema_slow_period: int = 50
    ema_slope_lookback: int = 3
    adx_period: int = 14
    adx_minimum: float = 25.0
    pullback_lookback: int = 8
    trigger_lookback: int = 3
    stop_atr_multiple: float = 1.5
    minimum_stop_pct: float = 0.006
    maximum_stop_pct: float = 0.03
    gross_reward_risk: float = 2.0
    minimum_net_reward_risk: float = 1.5
    risk_pct: float = 0.005
    max_exposure_pct: float = 1.0
    fee_rate: float = 0.001
    slippage_rate: float = 0.0002
    cooldown_minutes: int = 30
    loss_guard_losses: int = 3
    loss_guard_minutes: int = 240

    def __post_init__(self) -> None:
        if self.ema_fast_period < 2:
            raise ValueError("ema_fast_period debe ser >= 2.")
        if self.ema_slow_period <= self.ema_fast_period:
            raise ValueError("ema_slow_period debe superar ema_fast_period.")
        if self.ema_slope_lookback < 1:
            raise ValueError("ema_slope_lookback debe ser >= 1.")
        if self.adx_period < 2:
            raise ValueError("adx_period debe ser >= 2.")
        if self.adx_minimum <= 0:
            raise ValueError("adx_minimum debe ser mayor que cero.")
        if self.pullback_lookback < 1 or self.trigger_lookback < 1:
            raise ValueError("Los lookbacks deben ser >= 1.")
        if self.stop_atr_multiple <= 0:
            raise ValueError("stop_atr_multiple debe ser mayor que cero.")
        if not 0 < self.minimum_stop_pct <= self.maximum_stop_pct < 1:
            raise ValueError("Los limites del stop son invalidos.")
        if self.gross_reward_risk <= 0 or self.minimum_net_reward_risk <= 0:
            raise ValueError("Las relaciones riesgo/beneficio deben ser positivas.")
        if not 0 < self.risk_pct <= 0.05:
            raise ValueError("risk_pct debe estar entre 0 y 0.05.")
        if not 0 < self.max_exposure_pct <= 1:
            raise ValueError("max_exposure_pct debe estar entre 0 y 1.")
        if not 0 <= self.fee_rate < 0.1:
            raise ValueError("fee_rate debe estar entre 0 y 0.1.")
        if not 0 <= self.slippage_rate < 0.1:
            raise ValueError("slippage_rate debe estar entre 0 y 0.1.")
        if self.cooldown_minutes < 0:
            raise ValueError("cooldown_minutes no puede ser negativo.")
        if self.loss_guard_losses < 1 or self.loss_guard_minutes < 0:
            raise ValueError("La proteccion por perdidas es invalida.")


class ProjectEdgeV3:
    """Genera señales causales y planes de riesgo para PAPER."""

    REQUIRED_TIMEFRAMES = ("4H", "1H", "30M", "15M", "5M")
    FEATURE_FIELDS = (
        "pe_close",
        "pe_ema_fast",
        "pe_ema_slow",
        "pe_ema_slope",
        "pe_ema_gap_pct",
        "pe_ema_slope_pct",
        "pe_distance_from_ema_pct",
        "pe_atr",
        "pe_atr_pct",
        "pe_adx",
        "pe_adx_delta",
        "pe_adx_rising",
        "pe_efficiency_ratio",
        "pe_pullback_long",
        "pe_pullback_short",
        "pe_pullback_depth_long_pct",
        "pe_pullback_depth_short_pct",
        "pe_trigger_long",
        "pe_trigger_short",
        "pe_fvg_long",
        "pe_fvg_short",
    )
    DIAGNOSTIC_FIELDS = (
        "state_4h",
        "state_1h",
        "state_30m",
        "state_15m",
        "state_5m",
        "adx_1h",
        "adx_delta_1h",
        "ema_gap_pct_4h",
        "ema_gap_pct_1h",
        "ema_slope_pct_4h",
        "ema_slope_pct_1h",
        "efficiency_ratio_1h",
        "atr_pct_15m",
        "pullback_depth_pct_15m",
        "distance_from_ema_pct_5m",
        "fvg_confluence",
    )

    def __init__(self, config: ProjectEdgeV3Config | None = None) -> None:
        self.config = config or ProjectEdgeV3Config()

    @staticmethod
    def _validate_ohlc(data: pd.DataFrame) -> None:
        required = {"open", "high", "low", "close"}
        missing = required.difference(data.columns)
        if missing:
            raise ValueError(f"Faltan columnas OHLC: {sorted(missing)}")
        if data.empty:
            raise ValueError("El DataFrame OHLC esta vacio.")

    def add_features(self, data: pd.DataFrame) -> pd.DataFrame:
        """Agrega indicadores causales sin usar datos futuros."""
        self._validate_ohlc(data)
        result = data.copy()
        high = pd.to_numeric(result["high"], errors="coerce")
        low = pd.to_numeric(result["low"], errors="coerce")
        close = pd.to_numeric(result["close"], errors="coerce")
        open_price = pd.to_numeric(result["open"], errors="coerce")
        if pd.concat([high, low, close, open_price], axis=1).isna().any().any():
            raise ValueError("Los datos OHLC contienen valores invalidos.")

        fast = self.config.ema_fast_period
        slow = self.config.ema_slow_period
        adx_period = self.config.adx_period
        result["pe_close"] = close
        result["pe_ema_fast"] = close.ewm(
            span=fast,
            adjust=False,
            min_periods=fast,
        ).mean()
        result["pe_ema_slow"] = close.ewm(
            span=slow,
            adjust=False,
            min_periods=slow,
        ).mean()
        result["pe_ema_slope"] = (
            result["pe_ema_fast"]
            - result["pe_ema_fast"].shift(self.config.ema_slope_lookback)
        )
        safe_close = close.replace(0.0, float("nan"))
        result["pe_ema_gap_pct"] = (
            (result["pe_ema_fast"] - result["pe_ema_slow"]).abs()
            / safe_close
        )
        result["pe_ema_slope_pct"] = result["pe_ema_slope"] / safe_close
        result["pe_distance_from_ema_pct"] = (
            close - result["pe_ema_fast"]
        ) / safe_close

        previous_close = close.shift(1)
        true_range = pd.concat(
            [
                high - low,
                (high - previous_close).abs(),
                (low - previous_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = true_range.ewm(
            alpha=1.0 / adx_period,
            adjust=False,
            min_periods=adx_period,
        ).mean()
        result["pe_atr"] = atr
        result["pe_atr_pct"] = atr / safe_close

        up_move = high.diff()
        down_move = -low.diff()
        plus_dm = up_move.where(
            (up_move > down_move) & (up_move > 0),
            0.0,
        )
        minus_dm = down_move.where(
            (down_move > up_move) & (down_move > 0),
            0.0,
        )
        plus_smoothed = plus_dm.ewm(
            alpha=1.0 / adx_period,
            adjust=False,
            min_periods=adx_period,
        ).mean()
        minus_smoothed = minus_dm.ewm(
            alpha=1.0 / adx_period,
            adjust=False,
            min_periods=adx_period,
        ).mean()
        plus_di = 100.0 * plus_smoothed / atr.replace(0.0, float("nan"))
        minus_di = 100.0 * minus_smoothed / atr.replace(0.0, float("nan"))
        denominator = (plus_di + minus_di).replace(0.0, float("nan"))
        dx = 100.0 * (plus_di - minus_di).abs() / denominator
        result["pe_adx"] = dx.ewm(
            alpha=1.0 / adx_period,
            adjust=False,
            min_periods=adx_period,
        ).mean()
        result["pe_adx_delta"] = (
            result["pe_adx"]
            - result["pe_adx"].shift(self.config.ema_slope_lookback)
        )
        result["pe_adx_rising"] = (
            result["pe_adx_delta"] > 0
        )
        efficiency_path = close.diff().abs().rolling(
            self.config.ema_fast_period,
            min_periods=self.config.ema_fast_period,
        ).sum()
        efficiency_move = (
            close - close.shift(self.config.ema_fast_period)
        ).abs()
        result["pe_efficiency_ratio"] = (
            efficiency_move / efficiency_path.replace(0.0, float("nan"))
        )

        touched_long = low <= result["pe_ema_fast"]
        touched_short = high >= result["pe_ema_fast"]
        recent_long_touch = touched_long.rolling(
            self.config.pullback_lookback,
            min_periods=1,
        ).max().astype(bool)
        recent_short_touch = touched_short.rolling(
            self.config.pullback_lookback,
            min_periods=1,
        ).max().astype(bool)
        result["pe_pullback_long"] = (
            recent_long_touch
            & (close > result["pe_ema_fast"])
            & (close >= open_price)
        )
        result["pe_pullback_short"] = (
            recent_short_touch
            & (close < result["pe_ema_fast"])
            & (close <= open_price)
        )
        long_depth = (
            (result["pe_ema_fast"] - low)
            / result["pe_ema_fast"].replace(0.0, float("nan"))
        ).clip(lower=0.0)
        short_depth = (
            (high - result["pe_ema_fast"])
            / result["pe_ema_fast"].replace(0.0, float("nan"))
        ).clip(lower=0.0)
        result["pe_pullback_depth_long_pct"] = long_depth.rolling(
            self.config.pullback_lookback,
            min_periods=1,
        ).max()
        result["pe_pullback_depth_short_pct"] = short_depth.rolling(
            self.config.pullback_lookback,
            min_periods=1,
        ).max()

        crossed_long = (
            (close > result["pe_ema_fast"])
            & (close.shift(1) <= result["pe_ema_fast"].shift(1))
        )
        crossed_short = (
            (close < result["pe_ema_fast"])
            & (close.shift(1) >= result["pe_ema_fast"].shift(1))
        )
        recent_long_cross = crossed_long.rolling(
            self.config.trigger_lookback,
            min_periods=1,
        ).max().astype(bool)
        recent_short_cross = crossed_short.rolling(
            self.config.trigger_lookback,
            min_periods=1,
        ).max().astype(bool)
        if {"structure_break", "break_direction"}.issubset(result.columns):
            structure_break = result["structure_break"].isin(["BOS", "CHoCH"])
            broke_up = structure_break & result["break_direction"].eq("UP")
            broke_down = structure_break & result["break_direction"].eq("DOWN")
            recent_up_break = broke_up.rolling(
                self.config.trigger_lookback,
                min_periods=1,
            ).max().astype(bool)
            recent_down_break = broke_down.rolling(
                self.config.trigger_lookback,
                min_periods=1,
            ).max().astype(bool)
        else:
            recent_up_break = pd.Series(False, index=result.index)
            recent_down_break = pd.Series(False, index=result.index)

        result["pe_trigger_long"] = (
            (recent_long_cross | recent_up_break)
            & (close > result["pe_ema_fast"])
            & (close >= open_price)
        )
        result["pe_trigger_short"] = (
            (recent_short_cross | recent_down_break)
            & (close < result["pe_ema_fast"])
            & (close <= open_price)
        )

        if {"active_fvg_type", "active_fvg_state"}.issubset(result.columns):
            active = result["active_fvg_state"].isin(["ACTIVE", "PARTIAL"])
            result["pe_fvg_long"] = active & result["active_fvg_type"].eq("BULLISH")
            result["pe_fvg_short"] = active & result["active_fvg_type"].eq("BEARISH")
        else:
            result["pe_fvg_long"] = False
            result["pe_fvg_short"] = False

        return result

    @staticmethod
    def _clean_number(value: Any) -> float | None:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _clean_bool(value: Any) -> bool:
        if value is None:
            return False
        try:
            if pd.isna(value):
                return False
        except (TypeError, ValueError):
            pass
        return bool(value)

    def snapshot_from_mtf(self, mtf_result: dict[str, Any]) -> dict[str, Any]:
        analyses = mtf_result.get("analyses")
        states = mtf_result.get("states")
        if not isinstance(analyses, dict) or not isinstance(states, dict):
            raise ValueError("El resultado multitemporal esta incompleto.")

        snapshot: dict[str, Any] = {}
        for timeframe in self.REQUIRED_TIMEFRAMES:
            if timeframe not in analyses or timeframe not in states:
                raise ValueError(f"Falta la temporalidad {timeframe}.")
            enriched = self.add_features(analyses[timeframe])
            latest = enriched.iloc[-1]
            snapshot[f"state_{timeframe}"] = str(states[timeframe]).upper()
            for field in self.FEATURE_FIELDS:
                snapshot[f"{field}_{timeframe}"] = latest.get(field)
        return snapshot

    def decide_mtf(self, mtf_result: dict[str, Any]) -> dict[str, Any]:
        return self.decide_snapshot(self.snapshot_from_mtf(mtf_result))

    def diagnostic_snapshot(
        self,
        values: dict[str, Any],
        states: dict[str, str],
        direction: str | None,
    ) -> dict[str, Any]:
        """Resume variables causales para estudiar la señal sin modificarla."""
        side = None
        if direction == "LONG":
            side = "long"
        elif direction == "SHORT":
            side = "short"

        fvg_confluence = False
        if side is not None:
            fvg_confluence = self._clean_bool(
                values.get(f"pe_fvg_{side}_15M")
            ) or self._clean_bool(values.get(f"pe_fvg_{side}_5M"))

        pullback_depth = None
        if side is not None:
            pullback_depth = self._clean_number(
                values.get(f"pe_pullback_depth_{side}_pct_15M")
            )

        diagnostics = {
            "state_4h": states["4H"],
            "state_1h": states["1H"],
            "state_30m": states["30M"],
            "state_15m": states["15M"],
            "state_5m": states["5M"],
            "adx_1h": self._clean_number(values.get("pe_adx_1H")),
            "adx_delta_1h": self._clean_number(
                values.get("pe_adx_delta_1H")
            ),
            "ema_gap_pct_4h": self._clean_number(
                values.get("pe_ema_gap_pct_4H")
            ),
            "ema_gap_pct_1h": self._clean_number(
                values.get("pe_ema_gap_pct_1H")
            ),
            "ema_slope_pct_4h": self._clean_number(
                values.get("pe_ema_slope_pct_4H")
            ),
            "ema_slope_pct_1h": self._clean_number(
                values.get("pe_ema_slope_pct_1H")
            ),
            "efficiency_ratio_1h": self._clean_number(
                values.get("pe_efficiency_ratio_1H")
            ),
            "atr_pct_15m": self._clean_number(values.get("pe_atr_pct_15M")),
            "pullback_depth_pct_15m": pullback_depth,
            "distance_from_ema_pct_5m": self._clean_number(
                values.get("pe_distance_from_ema_pct_5M")
            ),
            "fvg_confluence": fvg_confluence,
        }
        return {
            field: diagnostics.get(field)
            for field in self.DIAGNOSTIC_FIELDS
        }

    def decide_snapshot(self, snapshot: dict[str, Any] | pd.Series) -> dict[str, Any]:
        """Evalua una fotografia ya alineada temporalmente."""
        values = dict(snapshot)
        states = {
            timeframe: str(values.get(f"state_{timeframe}", "UNDEFINED")).upper()
            for timeframe in self.REQUIRED_TIMEFRAMES
        }
        for timeframe, state in states.items():
            if state in {"NAN", "NONE"}:
                states[timeframe] = "UNDEFINED"

        macro = states["4H"]
        one_hour = states["1H"]
        direction: str | None = None
        if macro == one_hour == "BULLISH":
            direction = "LONG"
        elif macro == one_hour == "BEARISH":
            direction = "SHORT"

        checks: dict[str, bool] = {
            "macro_4h_1h": direction is not None,
        }
        if direction is None:
            return {
                "strategy": "PROJECT_EDGE_V3",
                "decision": "WAIT",
                "direction": None,
                "can_execute": False,
                "reason": "4H y 1H todavia no comparten una tendencia definida.",
                "checks": checks,
                "states": states,
                "atr_15m": self._clean_number(values.get("pe_atr_15M")),
                "diagnostics": self.diagnostic_snapshot(
                    values,
                    states,
                    direction,
                ),
                "config": asdict(self.config),
            }

        long_side = direction == "LONG"
        ema_fast_4h = self._clean_number(values.get("pe_ema_fast_4H"))
        ema_slow_4h = self._clean_number(values.get("pe_ema_slow_4H"))
        ema_slope_4h = self._clean_number(values.get("pe_ema_slope_4H"))
        ema_fast_1h = self._clean_number(values.get("pe_ema_fast_1H"))
        ema_slow_1h = self._clean_number(values.get("pe_ema_slow_1H"))
        ema_slope_1h = self._clean_number(values.get("pe_ema_slope_1H"))
        adx_1h = self._clean_number(values.get("pe_adx_1H"))

        if long_side:
            ema_4h_ok = bool(
                ema_fast_4h is not None
                and ema_slow_4h is not None
                and ema_slope_4h is not None
                and ema_fast_4h > ema_slow_4h
                and ema_slope_4h > 0
            )
            ema_1h_ok = bool(
                ema_fast_1h is not None
                and ema_slow_1h is not None
                and ema_slope_1h is not None
                and ema_fast_1h > ema_slow_1h
                and ema_slope_1h > 0
            )
            lower_states_ok = all(
                states[timeframe] != "BEARISH"
                for timeframe in ("30M", "15M", "5M")
            )
        else:
            ema_4h_ok = bool(
                ema_fast_4h is not None
                and ema_slow_4h is not None
                and ema_slope_4h is not None
                and ema_fast_4h < ema_slow_4h
                and ema_slope_4h < 0
            )
            ema_1h_ok = bool(
                ema_fast_1h is not None
                and ema_slow_1h is not None
                and ema_slope_1h is not None
                and ema_fast_1h < ema_slow_1h
                and ema_slope_1h < 0
            )
            lower_states_ok = all(
                states[timeframe] != "BULLISH"
                for timeframe in ("30M", "15M", "5M")
            )

        adx_ok = bool(
            adx_1h is not None
            and adx_1h >= self.config.adx_minimum
            and self._clean_bool(values.get("pe_adx_rising_1H"))
        )
        pullback_ok = self._clean_bool(
            values.get(f"pe_pullback_{'long' if long_side else 'short'}_15M")
        )
        trigger_ok = self._clean_bool(
            values.get(f"pe_trigger_{'long' if long_side else 'short'}_5M")
        )
        fvg_confluence = self._clean_bool(
            values.get(f"pe_fvg_{'long' if long_side else 'short'}_15M")
        ) or self._clean_bool(
            values.get(f"pe_fvg_{'long' if long_side else 'short'}_5M")
        )
        atr_15m = self._clean_number(values.get("pe_atr_15M"))

        checks.update(
            {
                "ema_4h": ema_4h_ok,
                "ema_1h": ema_1h_ok,
                "adx_1h": adx_ok,
                "lower_timeframes_no_conflict": lower_states_ok,
                "pullback_15m": pullback_ok,
                "trigger_5m": trigger_ok,
                "atr_15m": atr_15m is not None and atr_15m > 0,
                # El FVG suma contexto pero no puede crear ni bloquear la señal.
                "fvg_confluence": fvg_confluence,
            }
        )
        required_checks = (
            "macro_4h_1h",
            "ema_4h",
            "ema_1h",
            "adx_1h",
            "lower_timeframes_no_conflict",
            "pullback_15m",
            "trigger_5m",
            "atr_15m",
        )
        can_execute = all(checks[name] for name in required_checks)
        if can_execute:
            decision = f"READY_{direction}"
            reason = (
                "Tendencia 4H/1H, fuerza ADX, retroceso 15M y "
                "gatillo 5M confirmados."
            )
        else:
            decision = f"WATCH_{direction}"
            missing = [name for name in required_checks if not checks[name]]
            reason = "Faltan condiciones: " + ", ".join(missing) + "."

        return {
            "strategy": "PROJECT_EDGE_V3",
            "decision": decision,
            "direction": direction,
            "can_execute": can_execute,
            "reason": reason,
            "checks": checks,
            "states": states,
            "atr_15m": atr_15m,
            "diagnostics": self.diagnostic_snapshot(
                values,
                states,
                direction,
            ),
            "config": asdict(self.config),
        }

    def build_trade_plan(
        self,
        decision: dict[str, Any],
        entry_price: float,
        account_equity: float,
    ) -> dict[str, Any]:
        """Crea SL, TP y cantidad sin apalancamiento y con costos estimados."""
        if entry_price <= 0 or account_equity <= 0:
            raise ValueError("Precio y equity deben ser mayores que cero.")
        direction = decision.get("direction")
        if not decision.get("can_execute") or direction not in {"LONG", "SHORT"}:
            return {
                "approved": False,
                "reason": "La señal v3 todavía no esta confirmada.",
                "quantity": 0.0,
            }

        atr = self._clean_number(decision.get("atr_15m"))
        if atr is None or atr <= 0:
            return {
                "approved": False,
                "reason": "ATR 15M no disponible.",
                "quantity": 0.0,
            }

        stop_distance = max(
            atr * self.config.stop_atr_multiple,
            entry_price * self.config.minimum_stop_pct,
        )
        stop_pct = stop_distance / entry_price
        if stop_pct > self.config.maximum_stop_pct:
            return {
                "approved": False,
                "reason": f"Volatilidad excesiva: stop requerido {stop_pct:.2%}.",
                "quantity": 0.0,
            }

        estimated_cost_per_unit = (
            2.0
            * entry_price
            * (self.config.fee_rate + self.config.slippage_rate)
        )
        target_distance = max(
            stop_distance * self.config.gross_reward_risk,
            self.config.minimum_net_reward_risk
            * (stop_distance + estimated_cost_per_unit)
            + estimated_cost_per_unit,
        )
        if direction == "LONG":
            stop_price = entry_price - stop_distance
            target_price = entry_price + target_distance
        else:
            stop_price = entry_price + stop_distance
            target_price = entry_price - target_distance

        risk_budget = account_equity * self.config.risk_pct
        risk_per_unit = stop_distance + estimated_cost_per_unit
        risk_quantity = risk_budget / risk_per_unit
        exposure_cap = account_equity * self.config.max_exposure_pct
        exposure_quantity = exposure_cap / entry_price
        quantity = min(risk_quantity, exposure_quantity)
        estimated_risk = quantity * risk_per_unit
        estimated_net_reward = quantity * (
            target_distance - estimated_cost_per_unit
        )
        net_reward_risk = (
            estimated_net_reward / estimated_risk
            if estimated_risk > 0
            else 0.0
        )

        return {
            "approved": quantity > 0,
            "reason": "Riesgo v3 aprobado para PAPER.",
            "direction": direction,
            "entry_price": float(entry_price),
            "stop_price": float(stop_price),
            "target_price": float(target_price),
            "stop_distance": float(stop_distance),
            "target_distance": float(target_distance),
            "quantity": float(quantity),
            "exposure": float(quantity * entry_price),
            "risk_budget": float(risk_budget),
            "estimated_risk": float(estimated_risk),
            "estimated_cost": float(quantity * estimated_cost_per_unit),
            "gross_reward_risk": float(target_distance / stop_distance),
            "estimated_net_reward_risk": float(net_reward_risk),
            "leverage": 1,
        }


def loss_guard_remaining_minutes(
    closed_trades: Iterable[dict[str, Any]],
    now: datetime | None = None,
    consecutive_losses: int = 3,
    guard_minutes: int = 240,
) -> float:
    """Bloquea nuevas entradas tras N perdidas AUTO consecutivas."""
    if consecutive_losses < 1 or guard_minutes <= 0:
        return 0.0
    auto_trades = [
        trade
        for trade in closed_trades
        if str(trade.get("source", "")).upper() == "AUTO"
    ]
    if len(auto_trades) < consecutive_losses:
        return 0.0
    recent = auto_trades[-consecutive_losses:]
    if any(float(trade.get("pnl", 0.0)) >= 0 for trade in recent):
        return 0.0

    closed_at = recent[-1].get("closed_at") or recent[-1].get("exit_time")
    if not closed_at:
        return 0.0
    try:
        closed_time = datetime.fromisoformat(str(closed_at).replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if closed_time.tzinfo is None:
        closed_time = closed_time.replace(tzinfo=timezone.utc)
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    guard_end = closed_time + timedelta(minutes=guard_minutes)
    return max(0.0, (guard_end - current_time).total_seconds() / 60.0)
