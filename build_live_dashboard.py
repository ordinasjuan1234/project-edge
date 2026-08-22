"""
PROJECT EDGE - Live Dashboard Builder v4

Genera dashboard_data.json con:
- datos reales de BTCUSDT
- estado multitemporal
- Fair Value Gaps activos por temporalidad
- decisión del motor
- estado PAPER
- posición abierta
- orden LIMIT pendiente
- estado AUTO activo / pausado
- rendimiento MANUAL / AUTO
- historial reciente

No envía órdenes reales.
"""

from __future__ import annotations

import json
import math
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


def calculate_unrealized_pnl(
    position,
    current_price,
):
    if not position:
        return 0.0

    entry_price = float(
        position["entry_price"]
    )
    quantity = float(
        position["quantity"]
    )
    direction = position[
        "direction"
    ]

    if direction == "LONG":
        return (
            current_price
            - entry_price
        ) * quantity

    return (
        entry_price
        - current_price
    ) * quantity


def calculate_performance(
    trades,
    source,
):
    source = source.upper()

    selected = [
        trade
        for trade in trades
        if str(
            trade.get(
                "source",
                "UNCLASSIFIED",
            )
        ).upper() == source
    ]

    total = len(
        selected
    )

    wins = sum(
        1
        for trade in selected
        if float(
            trade.get(
                "pnl",
                0.0,
            )
        ) > 0
    )

    losses = sum(
        1
        for trade in selected
        if float(
            trade.get(
                "pnl",
                0.0,
            )
        ) < 0
    )

    pnl = sum(
        float(
            trade.get(
                "pnl",
                0.0,
            )
        )
        for trade in selected
    )

    win_rate = (
        wins
        / total
        * 100.0
        if total > 0
        else 0.0
    )

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "pnl": pnl,
    }


def clean_value(
    value,
):
    if value is None:
        return None

    try:
        if math.isnan(
            value
        ):
            return None
    except (
        TypeError,
        ValueError,
    ):
        pass

    if hasattr(
        value,
        "item",
    ):
        value = value.item()

    return value


def extract_fvg_by_timeframe(
    mtf,
):
    result = {}
    analyses = mtf.get(
        "analyses",
        {},
    )

    for (
        timeframe,
        analysis,
    ) in analyses.items():

        if (
            analysis is None
            or analysis.empty
        ):
            result[
                timeframe
            ] = None
            continue

        row = (
            analysis.iloc[-1]
        )

        fvg_type = clean_value(
            row.get(
                "active_fvg_type"
            )
        )

        lower = clean_value(
            row.get(
                "active_fvg_lower"
            )
        )

        upper = clean_value(
            row.get(
                "active_fvg_upper"
            )
        )

        mid = clean_value(
            row.get(
                "active_fvg_mid"
            )
        )

        state = clean_value(
            row.get(
                "active_fvg_state"
            )
        )

        distance_pct = (
            clean_value(
                row.get(
                    "active_fvg_distance_pct"
                )
            )
        )

        created_index = (
            clean_value(
                row.get(
                    "active_fvg_created_index"
                )
            )
        )

        if fvg_type is None:
            result[
                timeframe
            ] = None
            continue

        result[
            timeframe
        ] = {
            "type": str(
                fvg_type
            ),
            "lower": (
                float(lower)
                if lower
                is not None
                else None
            ),
            "upper": (
                float(upper)
                if upper
                is not None
                else None
            ),
            "mid": (
                float(mid)
                if mid
                is not None
                else None
            ),
            "state": (
                str(state)
                if state
                is not None
                else None
            ),
            "distance_pct": (
                float(
                    distance_pct
                )
                if distance_pct
                is not None
                else None
            ),
            "created_index": (
                int(
                    created_index
                )
                if created_index
                is not None
                else None
            ),
        }

    return result


def fetch_symbol_price(
    symbol,
    btc_data,
    btc_price,
):
    """
    Devuelve un precio de referencia backend
    para la posición abierta o LIMIT pendiente.

    BTC reutiliza los datos ya descargados.
    ETH descarga solo lo necesario.
    """

    if symbol == SYMBOL:
        return float(
            btc_price
        )

    symbol_data = (
        BinanceHistoricalData()
        .fetch_project_edge_timeframes(
            symbol,
            limit=100,
        )
    )

    return float(
        symbol_data[
            "5M"
        ][
            "close"
        ].iloc[-1]
    )


def pending_order_snapshot(
    pending_order,
    current_price,
):
    if not pending_order:
        return None

    order = dict(
        pending_order
    )

    limit_price = float(
        order["limit_price"]
    )

    current_price = float(
        current_price
    )

    direction = order[
        "direction"
    ]

    if direction == "LONG":
        triggered_now = (
            current_price
            <= limit_price
        )
    else:
        triggered_now = (
            current_price
            >= limit_price
        )

    distance_pct = (
        (
            limit_price
            - current_price
        )
        / current_price
        * 100.0
        if current_price != 0
        else 0.0
    )

    order[
        "current_price"
    ] = current_price

    order[
        "distance_pct"
    ] = float(
        distance_pct
    )

    order[
        "triggered_now"
    ] = bool(
        triggered_now
    )

    return order


def main():
    data = (
        BinanceHistoricalData()
        .fetch_project_edge_timeframes(
            SYMBOL,
            limit=500,
        )
    )

    btc_price = float(
        data[
            "5M"
        ][
            "close"
        ].iloc[-1]
    )

    mtf = (
        MultiTimeframeStructureEngine(
            structure_engine_kwargs={
                "pivot_left": 2,
                "pivot_right": 2,
                "atr_period": 14,
                "atr_multiplier": 1.5,
                "min_move_pct": 0.0025,
                "max_move_pct": 0.05,
            }
        )
        .analyze(data)
    )

    decision = (
        DecisionEngine()
        .decide(mtf)
    )

    readiness = (
        EntryReadiness()
        .evaluate(
            mtf_result=mtf,
            decision_result=decision,
        )
    )

    state = PaperState(
        initial_balance=INITIAL_BALANCE
    )

    # Al cargar una versión vieja del estado,
    # PaperState puede migrar campos nuevos.
    # Guardamos la migración.
    state.save()

    position = (
        state.position
    )

    pending_order = (
        state.pending_order
    )

    # Estado persistente del modo AUTO.
    auto_enabled = bool(
        state.auto_enabled
    )

    auto_pause_reason = (
        state.data.get(
            "auto_pause_reason"
        )
    )

    auto_updated_at = (
        state.data.get(
            "auto_updated_at"
        )
    )

    auto_status = (
        "ACTIVE"
        if auto_enabled
        else "PAUSED"
    )

    position_price = (
        btc_price
    )

    if position:
        position_price = (
            fetch_symbol_price(
                symbol=position[
                    "symbol"
                ],
                btc_data=data,
                btc_price=btc_price,
            )
        )

    unrealized_pnl = (
        calculate_unrealized_pnl(
            position,
            position_price,
        )
    )

    pending_price = None
    pending_snapshot = None

    if pending_order:
        pending_price = (
            fetch_symbol_price(
                symbol=pending_order[
                    "symbol"
                ],
                btc_data=data,
                btc_price=btc_price,
            )
        )

        pending_snapshot = (
            pending_order_snapshot(
                pending_order,
                pending_price,
            )
        )

    closed_trades = (
        state.data.get(
            "closed_trades",
            [],
        )
    )

    manual_performance = (
        calculate_performance(
            closed_trades,
            "MANUAL",
        )
    )

    auto_performance = (
        calculate_performance(
            closed_trades,
            "AUTO",
        )
    )

    alignment = mtf.get(
        "alignment",
        {},
    )

    if isinstance(
        alignment,
        dict,
    ):
        alignment_value = (
            alignment.get(
                "alignment",
                "UNKNOWN",
            )
        )
    else:
        alignment_value = str(
            alignment
        )

    payload = {
        "timestamp": (
            datetime.now(
                timezone.utc
            ).isoformat(
                timespec="seconds"
            )
        ),
        "symbol": SYMBOL,
        "price": btc_price,
        "timeframes": mtf.get(
            "states",
            {},
        ),
        "fvg": (
            extract_fvg_by_timeframe(
                mtf
            )
        ),
        "alignment": (
            alignment_value
        ),
        "decision": {
            "action": (
                decision.get(
                    "decision"
                )
            ),
            "direction": (
                decision.get(
                    "direction"
                )
            ),
            "can_execute": bool(
                decision.get(
                    "can_execute",
                    False,
                )
            ),
        },
        "readiness": {
            "status": (
                readiness.get(
                    "status"
                )
            ),
            "bias": (
                readiness.get(
                    "bias"
                )
            ),
            "message": (
                readiness.get(
                    "message",
                    "",
                )
            ),
            "missing_conditions": (
                readiness.get(
                    "missing_conditions",
                    [],
                )
            ),
        },
        "paper": {
            "initial_balance": float(
                state.data.get(
                    "initial_balance",
                    INITIAL_BALANCE,
                )
            ),
            "balance": (
                state.balance
            ),
            "position": (
                position
            ),
            "position_price": (
                float(
                    position_price
                )
                if position
                else None
            ),
            "unrealized_pnl": float(
                unrealized_pnl
            ),
            "pending_order": (
                pending_snapshot
            ),
            "pending_order_price": (
                float(
                    pending_price
                )
                if pending_price
                is not None
                else None
            ),
            "has_open_position": bool(
                position
            ),
            "has_pending_order": bool(
                pending_order
            ),
            "auto_enabled": (
                auto_enabled
            ),
            "auto_status": (
                auto_status
            ),
            "auto_pause_reason": (
                auto_pause_reason
            ),
            "auto_updated_at": (
                auto_updated_at
            ),
            "manual_performance": (
                manual_performance
            ),
            "auto_performance": (
                auto_performance
            ),
            "closed_trades": (
                closed_trades[-10:]
            ),
        },
    }

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            payload,
            file,
            indent=2,
            ensure_ascii=False,
        )

    print(
        f"Dashboard actualizado: "
        f"{OUTPUT_FILE}"
    )

    print(
        f"BTC: {btc_price:.2f} | "
        f"Decision: "
        f"{payload['decision']['action']}"
    )

    print(
        "AUTO: "
        + (
            "ACTIVO"
            if auto_enabled
            else "PAUSADO"
        )
    )

    if position:
        print(
            "PAPER: posición abierta "
            f"{position['symbol']} "
            f"{position['direction']}"
        )

    elif pending_snapshot:
        print(
            "PAPER: LIMIT pendiente "
            f"{pending_snapshot['symbol']} "
            f"{pending_snapshot['direction']} "
            f"@ {float(pending_snapshot['limit_price']):.2f}"
        )

    else:
        print(
            "PAPER: sin posición "
            "y sin LIMIT pendiente"
        )


if __name__ == "__main__":
    main()
