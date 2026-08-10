"""
PROJECT EDGE
BTC Historical Runner v1

Descarga velas públicas de BTCUSDT desde Binance y ejecuta:
Historical Data Loader -> Multi-Timeframe Structure Engine.

NO usa API key.
NO accede a saldo.
NO ejecuta órdenes.
"""

from __future__ import annotations

from engine.data.binance_historical_data import BinanceHistoricalData
from engine.multitimeframe.multi_timeframe_structure_engine import (
    MultiTimeframeStructureEngine,
)


def main() -> None:
    symbol = "BTCUSDT"
    limit = 500

    loader = BinanceHistoricalData()
    timeframe_data = loader.fetch_project_edge_timeframes(
        symbol=symbol,
        limit=limit,
    )

    engine = MultiTimeframeStructureEngine(
        structure_engine_kwargs={
            "pivot_left": 2,
            "pivot_right": 2,
            "atr_period": 14,
            "atr_multiplier": 1.5,
            "min_move_pct": 0.0025,
            "max_move_pct": 0.05,
        }
    )

    result = engine.analyze(timeframe_data)

    print("=" * 60)
    print("PROJECT EDGE — BTCUSDT Historical Analysis")
    print("=" * 60)

    for timeframe, state in result["states"].items():
        print(f"{timeframe:>3}: {state}")

    alignment = result["alignment"]

    print("-" * 60)
    print(f"Alignment:   {alignment['alignment']}")
    print(f"Entry ready: {alignment['entry_ready']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
