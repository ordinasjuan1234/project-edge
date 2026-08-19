"""
PROJECT EDGE - Live Dashboard Builder

Genera dashboard_data.json con datos reales de BTCUSDT,
el estado multitemporal, la decisión del motor y el estado PAPER.
No envía órdenes reales.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from engine.data.binance_historical_data import BinanceHistoricalData
from engine.multitimeframe.multi_timeframe_structure_engine import (
    MultiTimeframeStructureEngine,
)
from engine.decision.decision_engine import DecisionEngine
from engine.decision.entry_readiness import EntryReadiness
from paper_state import PaperState


SYMBOL = "BTCUSDT"
INITIAL_BALANCE = 10000.0
OUTPUT_FILE = "dashboard_data.json"


def calculate_unrealized_pnl(position, current_price):
    if not position:
        return 0.0

    entry_price = float(position["entry_price"])
    quantity = float(position["quantity"])
    direction = position["direction"]

    if direction == "LONG":
        return (current_price - entry_price) * quantity
    return (entry_price - current_price) * quantity


def main():
    data = BinanceHistoricalData().fetch_project_edge_timeframes(
        SYMBOL,
        limit=500,
    )

    btc_price = float(data["5M"]["close"].iloc[-1])

    mtf = MultiTimeframeStructureEngine(
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

    state = PaperState(initial_balance=INITIAL_BALANCE)
    # Garantiza que exista un estado persistible desde la primera corrida.
    state.save()

    position = state.position
    unrealized_pnl = calculate_unrealized_pnl(position, btc_price)

    alignment = mtf.get("alignment", {})
    if isinstance(alignment, dict):
        alignment_value = alignment.get("alignment", "UNKNOWN")
    else:
        alignment_value = str(alignment)

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "symbol": SYMBOL,
        "price": btc_price,
        "timeframes": mtf.get("states", {}),
        "alignment": alignment_value,
        "decision": {
            "action": decision.get("decision"),
            "direction": decision.get("direction"),
            "can_execute": bool(decision.get("can_execute", False)),
        },
        "readiness": {
            "status": readiness.get("status"),
            "bias": readiness.get("bias"),
            "message": readiness.get("message", ""),
            "missing_conditions": readiness.get("missing_conditions", []),
        },
        "paper": {
            "initial_balance": float(state.data.get("initial_balance", INITIAL_BALANCE)),
            "balance": state.balance,
            "position": position,
            "unrealized_pnl": float(unrealized_pnl),
            "closed_trades": state.data.get("closed_trades", [])[-10:],
        },
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2, ensure_ascii=False)

    print(f"Dashboard actualizado: {OUTPUT_FILE}")
    print(f"BTC: {btc_price:.2f} | Decision: {payload['decision']['action']}")


if __name__ == "__main__":
    main()
