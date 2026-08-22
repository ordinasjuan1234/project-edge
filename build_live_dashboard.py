"""
PROJECT EDGE - Live Dashboard Builder v5

Genera dashboard_data.json con:
- datos reales de BTCUSDT
- estado multitemporal
- Fair Value Gaps activos por temporalidad
- decisión del motor
- scanner MANUAL para BTCUSDT y ETHUSDT
- estado PAPER
- posición abierta
- orden LIMIT pendiente
- estado AUTO activo / pausado / emergencia
- rendimiento MANUAL / AUTO
- historial reciente

El scanner MANUAL NO ejecuta órdenes.
Solo traduce la lectura del motor a:
- LONG
- SHORT
- WAIT

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


PRIMARY_SYMBOL = "BTCUSDT"
SCANNER_SYMBOLS = ("BTCUSDT", "ETHUSDT")
INITIAL_BALANCE = 10000.0
OUTPUT_FILE = "dashboard_data.json"

STRUCTURE_ENGINE_KWARGS = {
    "pivot_left": 2,
    "pivot_right": 2,
    "atr_period": 14,
    "atr_multiplier": 1.5,
    "min_move_pct": 0.0025,
    "max_move_pct": 0.05,
}


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


def extract_alignment_value(
    mtf,
):
    alignment = mtf.get(
        "alignment",
        {},
    )

    if isinstance(
        alignment,
        dict,
    ):
        return alignment.get(
            "alignment",
            "UNKNOWN",
        )

    return str(
        alignment
    )


def scanner_signal(
    decision,
):
    """
    Traduce la decisión técnica del motor
    a una lectura simple para la mesa MANUAL.

    READY_LONG  -> LONG
    READY_SHORT -> SHORT
    Todo lo demás -> WAIT

    Importante:
    WATCH_LONG / WATCH_SHORT indican sesgo,
    pero NO habilitan una entrada del scanner.
    """

    decision_name = str(
        decision.get(
            "decision",
            "WAIT",
        )
    ).upper()

    if (
        decision_name == "READY_LONG"
        and bool(
            decision.get(
                "can_execute",
                False,
            )
        )
    ):
        return "LONG"

    if (
        decision_name == "READY_SHORT"
        and bool(
            decision.get(
                "can_execute",
                False,
            )
        )
    ):
        return "SHORT"

    return "WAIT"


def analyze_symbol(
    symbol,
):
    """
    Ejecuta el mismo motor estructural para un símbolo
    sin abrir ni cerrar ninguna operación.
    """

    data = (
        BinanceHistoricalData()
        .fetch_project_edge_timeframes(
            symbol,
            limit=500,
        )
    )

    price = float(
        data[
            "5M"
        ][
            "close"
        ].iloc[-1]
    )

    mtf = (
        MultiTimeframeStructureEngine(
            structure_engine_kwargs=(
                STRUCTURE_ENGINE_KWARGS
            )
        )
        .analyze(
            data
        )
    )

    decision = (
        DecisionEngine()
        .decide(
            mtf
        )
    )

    readiness = (
        EntryReadiness()
        .evaluate(
            mtf_result=mtf,
            decision_result=decision,
        )
    )

    alignment_value = (
        extract_alignment_value(
            mtf
        )
    )

    return {
        "symbol": symbol,
        "price": price,
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
            "reason": (
                decision.get(
                    "reason",
                    "",
                )
            ),
            "fvg_required": bool(
                decision.get(
                    "fvg_required",
                    False,
                )
            ),
            "fvg_confirmed": (
                decision.get(
                    "fvg_confirmed"
                )
            ),
            "fvg_expected_type": (
                decision.get(
                    "fvg_expected_type"
                )
            ),
            "fvg_timeframes": (
                decision.get(
                    "fvg_timeframes",
                    [],
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
        "scanner_signal": (
            scanner_signal(
                decision
            )
        ),
    }


def fetch_symbol_price(
    symbol,
    scanner_data,
):
    """
    Reutiliza el precio ya calculado por el scanner.
    Si el símbolo no está dentro del scanner,
    descarga solamente los datos necesarios.
    """

    if (
        symbol
        in scanner_data
    ):
        return float(
            scanner_data[
                symbol
            ][
                "price"
            ]
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


def build_manual_scanner():
    """
    Analiza BTC y ETH con el mismo motor.
    Un error en un símbolo no debe impedir
    que el dashboard completo se genere.
    """

    result = {}

    for symbol in SCANNER_SYMBOLS:
        try:
            result[
                symbol
            ] = analyze_symbol(
                symbol
            )
        except Exception as exc:
            result[
                symbol
            ] = {
                "symbol": symbol,
                "price": None,
                "timeframes": {},
                "fvg": {},
                "alignment": "ERROR",
                "decision": {
                    "action": "WAIT",
                    "direction": None,
                    "can_execute": False,
                    "reason": (
                        "No se pudo completar "
                        "la lectura del scanner."
                    ),
                    "fvg_required": False,
                    "fvg_confirmed": None,
                    "fvg_expected_type": None,
                    "fvg_timeframes": [],
                },
                "readiness": {
                    "status": "NOT_READY",
                    "bias": None,
                    "message": str(
                        exc
                    ),
                    "missing_conditions": [
                        (
                            "Reintentar la lectura "
                            "en el próximo ciclo."
                        )
                    ],
                },
                "scanner_signal": "WAIT",
                "error": str(
                    exc
                ),
            }

    return result


def main():
    scanner_data = (
        build_manual_scanner()
    )

    primary = scanner_data.get(
        PRIMARY_SYMBOL,
        {},
    )

    if (
        primary.get(
            "price"
        )
        is None
    ):
        raise RuntimeError(
            "No se pudo construir "
            "la lectura principal BTCUSDT."
        )

    btc_price = float(
        primary[
            "price"
        ]
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

    if (
        not auto_enabled
        and auto_pause_reason
        == "EMERGENCY_STOP"
    ):
        auto_status = (
            "EMERGENCY_STOP"
        )
    elif auto_enabled:
        auto_status = (
            "ACTIVE"
        )
    else:
        auto_status = (
            "PAUSED"
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
                scanner_data=(
                    scanner_data
                ),
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
                scanner_data=(
                    scanner_data
                ),
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

    # Conservamos las claves antiguas de BTC
    # para no romper el dashboard actual.
    payload = {
        "timestamp": (
            datetime.now(
                timezone.utc
            ).isoformat(
                timespec="seconds"
            )
        ),
        "symbol": PRIMARY_SYMBOL,
        "price": btc_price,
        "timeframes": (
            primary.get(
                "timeframes",
                {},
            )
        ),
        "fvg": (
            primary.get(
                "fvg",
                {},
            )
        ),
        "alignment": (
            primary.get(
                "alignment",
                "UNKNOWN",
            )
        ),
        "decision": (
            primary.get(
                "decision",
                {}
            )
        ),
        "readiness": (
            primary.get(
                "readiness",
                {}
            )
        ),

        # Nuevo bloque para puntos 39 y 40.
        "manual_scanner": (
            scanner_data
        ),

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
        f"Scanner: "
        f"{primary.get('scanner_signal', 'WAIT')}"
    )

    eth = scanner_data.get(
        "ETHUSDT",
        {},
    )

    if (
        eth.get(
            "price"
        )
        is not None
    ):
        print(
            f"ETH: "
            f"{float(eth['price']):.2f} | "
            f"Scanner: "
            f"{eth.get('scanner_signal', 'WAIT')}"
        )

    print(
        "AUTO: "
        + (
            "EMERGENCY STOP"
            if auto_status
            == "EMERGENCY_STOP"
            else (
                "ACTIVO"
                if auto_enabled
                else "PAUSADO"
            )
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
            f"@ "
            f"{float(pending_snapshot['limit_price']):.2f}"
        )

    else:
        print(
            "PAPER: sin posición "
            "y sin LIMIT pendiente"
        )


if __name__ == "__main__":
    main()
