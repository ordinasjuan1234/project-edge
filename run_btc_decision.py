"""
PROJECT EDGE — BTC Real Decision Runner v1
Datos públicos -> Multi-Timeframe -> Decision Engine.
No usa API key ni ejecuta órdenes.
"""
from engine.data.binance_historical_data import BinanceHistoricalData
from engine.multitimeframe.multi_timeframe_structure_engine import MultiTimeframeStructureEngine
from engine.decision.decision_engine import DecisionEngine

def main():
    data = BinanceHistoricalData().fetch_project_edge_timeframes("BTCUSDT", limit=500)
    mtf = MultiTimeframeStructureEngine(structure_engine_kwargs={
        "pivot_left": 2, "pivot_right": 2, "atr_period": 14,
        "atr_multiplier": 1.5, "min_move_pct": 0.0025, "max_move_pct": 0.05,
    }).analyze(data)
    decision = DecisionEngine().evaluate(mtf)

    print("=" * 60)
    print("PROJECT EDGE — BTCUSDT REAL DECISION")
    print("=" * 60)
    for timeframe, state in mtf["states"].items():
        print(f"{timeframe:>3}: {state}")
    print("-" * 60)
    print(f"Alignment:   {mtf['alignment']['alignment']}")
    print(f"Entry ready: {mtf['alignment']['entry_ready']}")
    print("-" * 60)
    print(f"Decision:    {decision.get('decision')}")
    print(f"Direction:   {decision.get('direction')}")
    print(f"Can execute: {decision.get('can_execute')}")
    print("=" * 60)

if __name__ == "__main__":
    main()
