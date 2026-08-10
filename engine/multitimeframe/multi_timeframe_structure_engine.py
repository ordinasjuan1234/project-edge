"""
PROJECT EDGE
Multi-Timeframe Structure Engine v1

Conecta StructureEngine con MultiTimeframeEngine.

Recibe OHLC por temporalidad, ejecuta el análisis estructural completo
en cada marco temporal y toma el último estado conocido de cada uno.

No ejecuta órdenes ni envía señales al broker.
"""

from __future__ import annotations

import pandas as pd

from engine.structure.structure_engine import StructureEngine
from engine.multitimeframe.multi_timeframe_engine import MultiTimeframeEngine


class MultiTimeframeStructureEngine:
    REQUIRED_TIMEFRAMES = ("4H", "1H", "30M", "15M", "5M")

    def __init__(self, structure_engine_kwargs: dict | None = None) -> None:
        self.structure_engine_kwargs = structure_engine_kwargs or {}
        self.multi_timeframe_engine = MultiTimeframeEngine()

    @staticmethod
    def _latest_structure(result: pd.DataFrame) -> str:
        if "market_structure" not in result.columns or result.empty:
            return "UNDEFINED"

        values = result["market_structure"].dropna()
        if values.empty:
            return "UNDEFINED"

        return str(values.iloc[-1]).upper()

    def analyze(
        self,
        timeframe_data: dict[str, pd.DataFrame],
    ) -> dict[str, object]:
        normalized = {
            str(timeframe).upper(): df
            for timeframe, df in timeframe_data.items()
        }

        missing = [
            timeframe
            for timeframe in self.REQUIRED_TIMEFRAMES
            if timeframe not in normalized
        ]
        if missing:
            raise ValueError(f"Faltan temporalidades requeridas: {missing}")

        states: dict[str, str] = {}
        analyses: dict[str, pd.DataFrame] = {}

        for timeframe in self.REQUIRED_TIMEFRAMES:
            engine = StructureEngine(**self.structure_engine_kwargs)
            result = engine.analyze(normalized[timeframe])

            analyses[timeframe] = result
            states[timeframe] = self._latest_structure(result)

        alignment = self.multi_timeframe_engine.analyze(states)

        return {
            "states": states,
            "alignment": alignment,
            "analyses": analyses,
        }


def analyze_multi_timeframe_structure(
    timeframe_data: dict[str, pd.DataFrame],
    structure_engine_kwargs: dict | None = None,
) -> dict[str, object]:
    return MultiTimeframeStructureEngine(
        structure_engine_kwargs=structure_engine_kwargs
    ).analyze(timeframe_data)
