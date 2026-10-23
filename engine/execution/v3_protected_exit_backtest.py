"""Backtest aislado de PROJECT EDGE v3 con protección de ganancias.

Mantiene exactamente las entradas, el plan de riesgo y el objetivo final de v3.
Solo cambia la gestión del stop una vez alcanzados los hitos visuales:
- TP1 (50% del recorrido a TP3): stop a break-even neto de costos estimados.
- TP2 (75% del recorrido a TP3): stop a TP1.
- TP3: cierre final sin cambios.

La lógica es conservadora con velas OHLC: si stop y objetivo aparecen en la
misma vela, se asume stop primero. Los hitos solo ajustan el stop al cierre de
una vela que no haya tocado previamente el stop ni TP3.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from engine.execution.historical_backtest import (
    HistoricalBacktestConfig,
    HistoricalBacktester,
)


class V3ProtectedExitHistoricalBacktester(HistoricalBacktester):
    """V3 con la misma entrada y riesgo, pero salida protegida tras TP1/TP2."""

    TP1_FRACTION = 0.50
    TP2_FRACTION = 0.75

    def __init__(
        self,
        config: HistoricalBacktestConfig,
        structure_engine_kwargs: dict[str, Any] | None = None,
    ) -> None:
        if str(config.strategy).upper() != "PROJECT_EDGE_V3":
            raise ValueError("La variante protegida solo admite PROJECT_EDGE_V3.")
        super().__init__(config, structure_engine_kwargs=structure_engine_kwargs)

    @classmethod
    def milestone_prices(cls, position: dict[str, Any]) -> tuple[float, float]:
        entry = float(position["entry_price"])
        target = float(position["target_price"])
        distance = target - entry
        return (
            entry + distance * cls.TP1_FRACTION,
            entry + distance * cls.TP2_FRACTION,
        )

    def _break_even_raw_price(self, position: dict[str, Any]) -> float:
        """Precio crudo que cubre fees y slippage del cierre en el backtest."""
        direction = str(position["direction"])
        entry = float(position["entry_price"])
        quantity = float(position["position_size"])
        entry_fee = float(position.get("entry_fee", 0.0))
        if quantity <= 0:
            raise ValueError("position_size debe ser mayor que cero.")

        fee = float(self.config.fee_rate)
        slippage = float(self.config.slippage_rate)
        entry_fee_per_unit = entry_fee / quantity

        if direction == "LONG":
            executed_break_even = (entry + entry_fee_per_unit) / (1.0 - fee)
            return executed_break_even / (1.0 - slippage)
        if direction == "SHORT":
            executed_break_even = (entry - entry_fee_per_unit) / (1.0 + fee)
            return executed_break_even / (1.0 + slippage)
        raise ValueError(f"Dirección inválida: {direction}")

    @staticmethod
    def _protected_stop_reason(position: dict[str, Any], gap: bool) -> str:
        stage = str(position.get("protected_stop_stage", ""))
        if stage == "TP2_TO_TP1":
            return "PROTECTED_TP2_TP1_GAP" if gap else "PROTECTED_TP2_TP1"
        if stage == "TP1_TO_BE_COSTS":
            return "PROTECTED_TP1_BE_GAP" if gap else "PROTECTED_TP1_BE"
        return "STOP_GAP" if gap else "STOP"

    def _raw_exit(
        self,
        position: dict[str, Any],
        candle: pd.Series,
    ) -> tuple[float, str] | None:
        direction = str(position["direction"])
        stop = float(position["stop_price"])
        target = float(position["target_price"])
        candle_open = float(candle["open"])
        candle_high = float(candle["high"])
        candle_low = float(candle["low"])

        # Conservador: si stop y objetivo aparecen en la misma vela, stop primero.
        if direction == "LONG":
            if candle_open <= stop:
                return candle_open, self._protected_stop_reason(position, gap=True)
            stop_hit = candle_low <= stop
            target_hit = candle_high >= target
        else:
            if candle_open >= stop:
                return candle_open, self._protected_stop_reason(position, gap=True)
            stop_hit = candle_high >= stop
            target_hit = candle_low <= target

        if stop_hit:
            return stop, self._protected_stop_reason(position, gap=False)
        if target_hit:
            return target, "TARGET"

        tp1, tp2 = self.milestone_prices(position)
        if direction == "LONG":
            tp1_hit = candle_high >= tp1
            tp2_hit = candle_high >= tp2
        else:
            tp1_hit = candle_low <= tp1
            tp2_hit = candle_low <= tp2

        if tp2_hit and not bool(position.get("tp2_reached")):
            position["tp1_reached"] = True
            position["tp2_reached"] = True
            position["tp1_price"] = float(tp1)
            position["tp2_price"] = float(tp2)
            if direction == "LONG":
                position["stop_price"] = max(float(position["stop_price"]), tp1)
            else:
                position["stop_price"] = min(float(position["stop_price"]), tp1)
            position["protected_stop_stage"] = "TP2_TO_TP1"
            position["protected_stop_price"] = float(position["stop_price"])
            return None

        if tp1_hit and not bool(position.get("tp1_reached")):
            position["tp1_reached"] = True
            position["tp1_price"] = float(tp1)
            position["tp2_price"] = float(tp2)
            break_even = self._break_even_raw_price(position)
            if direction == "LONG":
                position["stop_price"] = max(float(position["stop_price"]), break_even)
            else:
                position["stop_price"] = min(float(position["stop_price"]), break_even)
            position["protected_stop_stage"] = "TP1_TO_BE_COSTS"
            position["protected_stop_price"] = float(position["stop_price"])

        return None
