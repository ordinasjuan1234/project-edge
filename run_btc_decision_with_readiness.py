"""
PROJECT EDGE
BTC Real Decision + Entry Readiness v1

Datos públicos de BTCUSDT:
Historical Data -> Multi-Timeframe -> Decision Engine -> Entry Readiness.

NO usa API key.
NO accede a saldo.
NO ejecuta órdenes.
"""

from engine.data.binance_historical_data import BinanceHistoricalData
from engine.multitimeframe.multi_timeframe_structure_engine import (
    MultiTimeframeStructureEngine,
)
from engine.decision.decision_engine import DecisionEngine
from engine.decision.entry_readiness import EntryReadiness
from engine.structure.swing_detector import detect_swings
from engine.structure.support_resistance import calculate_structural_levels


def main():
    data = BinanceHistoricalData().fetch_project_edge_timeframes(
        "BTCUSDT",
        limit=500,
    )
btc_price = float(data["5M"]["close"].iloc[-1])

structural_levels = {}

for timeframe in ("30M", "15M"):
    swings = detect_swings(data[timeframe].copy())
    levels = calculate_structural_levels(swings)
    structural_levels[timeframe] = levels.iloc[-1] 
    
 mtf     = MultiTimeframeStructureEngine(
        structure_engine_kwargs={
            "pivot_left": 2,
            "pivot_right": 2,
            "atr_period": 14,
            "atr_multiplier": 1.5,
            "min_move_pct": 0.0025,
            "max_move_pct": 0.05,
        }
    ).analyze(data)

    decision = DecisionEngine().decide(mtf)
    readiness = EntryReadiness().evaluate(
        mtf_result=mtf,
        decision_result=decision,
    )

    print("=" * 60)
    print("PROJECT EDGE — BTCUSDT REAL DECISION + READINESS")
    print("=" * 60)

    for timeframe, state in mtf["states"].items():
        print(f"{timeframe:>3}: {state}")

    print("-" * 60)
    print(f"Alignment:   {mtf['alignment']['alignment']}")
    print(f"Entry ready: {mtf['alignment']['entry_ready']}")
    print(f"BTC price:   {btc_price}")

    print("-" * 60)
    print(f"Decision:    {decision.get('decision')}")
    print(f"Direction:   {decision.get('direction')}")
    print(f"Can execute: {decision.get('can_execute')}")

    print("-" * 60)
    print("ENTRY READINESS")
    print(f"Status:      {readiness.get('status')}")
    print(f"Bias:        {readiness.get('bias')}")
    print(f"Message:     {readiness.get('message')}")

    missing = readiness.get("missing_conditions", [])
    if missing:
        print("Missing conditions:")
        for condition in missing:
            print(f"- {condition}")
    else:
        print("Missing conditions: none")

    print("=" * 60)
    print("STRUCTURAL LEVELS")
    for timeframe, levels in structural_levels.items():
        print(
            f"{timeframe}: "
            f"Support={levels.get('structural_support')} | "
            f"Resistance={levels.get('structural_resistance')}"
        )
    print("=" * 60)

if __name__ == "__main__":
    main()
