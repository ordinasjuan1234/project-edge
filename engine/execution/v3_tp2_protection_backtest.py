"""Backtest aislado de PROJECT EDGE v3 con protección solo después de TP2.

Mantiene exactamente las entradas, el plan de riesgo y el objetivo final de v3.
TP1 no modifica la posición.
Cuando TP2 (75% del recorrido entrada-TP3) se alcanza, el stop se mueve a TP1
(50% del recorrido). TP3 conserva el cierre final original.

La lógica es conservadora con velas OHLC: si stop y TP3 aparecen en la misma
vela, se asume stop primero. La protección solo se activa después de una vela
que alcanzó TP2 sin tocar previamente el stop ni TP3.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from engine.execution.historical_backtest import (
    HistoricalBacktestConfig,
    HistoricalBacktester,
)


class V3TP2ProtectionHistoricalBacktester(HistoricalBacktester):
    """V3 original con una única variación: TP2 protege el stop en TP1."""

    TP1_FRACTION = 0.50
    TP2_FRACTION = 0.75

    def __init__(
        self,
        config: HistoricalBacktestConfig,
        structure_engine_kwargs: dict[str, Any] | None = None,
    ) -> None:
        if str(config.strategy).upper() != "PROJECT_EDGE_V3":
            raise ValueError("La variante TP2 solo admite PROJECT_EDGE_V3.")
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

    @staticmethod
    def _stop_reason(position: dict[str, Any], gap: bool) -> str:
        if bool(position.get("tp2_protection_active")):
            return "PROTECTED_TP2_TP1_GAP" if gap else "PROTECTED_TP2_TP1"
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

        if direction == "LONG":
            if candle_open <= stop:
                return candle_open, self._stop_reason(position, gap=True)
            stop_hit = candle_low <= stop
            target_hit = candle_high >= target
        else:
            if candle_open >= stop:
                return candle_open, self._stop_reason(position, gap=True)
            stop_hit = candle_high >= stop
            target_hit = candle_low <= target

        if stop_hit:
            return stop, self._stop_reason(position, gap=False)
        if target_hit:
            return target, "TARGET"

        tp1, tp2 = self.milestone_prices(position)
        if direction == "LONG":
            tp1_hit = candle_high >= tp1
            tp2_hit = candle_high >= tp2
        else:
            tp1_hit = candle_low <= tp1
            tp2_hit = candle_low <= tp2

        if tp1_hit:
            position["tp1_reached"] = True
            position["tp1_price"] = float(tp1)

        if tp2_hit and not bool(position.get("tp2_reached")):
            position["tp1_reached"] = True
            position["tp2_reached"] = True
            position["tp1_price"] = float(tp1)
            position["tp2_price"] = float(tp2)
            if direction == "LONG":
                position["stop_price"] = max(float(position["stop_price"]), tp1)
            else:
                position["stop_price"] = min(float(position["stop_price"]), tp1)
            position["tp2_protection_active"] = True
            position["protected_stop_price"] = float(position["stop_price"])

        return None
