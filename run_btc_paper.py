"""
PROJECT EDGE
BTC Paper Trading v3

Paper Trading con estado persistente.

Funciones:
- Lee datos reales de BTCUSDT.
- Usa el motor multi-timeframe de PROJECT EDGE.
- Solo abre una operacion cuando hay confirmacion real.
- Recuerda una posicion PAPER abierta.
- Controla Stop Loss y Take Profit.
- Gestiona Trailing Stop persistente.
- Puede gestionar una posicion manual BTC o ETH.
- Actualiza el saldo demo al cerrar.

IMPORTANTE:
- NO ejecuta ordenes reales.
- NO usa API key privada.
- NO mueve dinero real.
"""

from engine.data.binance_historical_data import (
    BinanceHistoricalData,
)
from engine.multitimeframe.multi_timeframe_structure_engine import (
    MultiTimeframeStructureEngine,
)
from engine.decision.decision_engine import DecisionEngine
from engine.decision.entry_readiness import EntryReadiness

from paper_state import PaperState


SYMBOL = "BTCUSDT"
INITIAL_BALANCE = 10000.0

STOP_PCT = 0.005
TAKE_PROFIT_PCT = 0.01


def calculate_levels(
    direction,
    entry_price,
):
    if direction == "LONG":
        stop_loss = (
            entry_price *
            (1.0 - STOP_PCT)
        )

        take_profit = (
            entry_price *
            (1.0 + TAKE_PROFIT_PCT)
        )

    elif direction == "SHORT":
        stop_loss = (
            entry_price *
            (1.0 + STOP_PCT)
        )

        take_profit = (
            entry_price *
            (1.0 - TAKE_PROFIT_PCT)
        )

    else:
        raise ValueError(
            "Direccion invalida."
        )

    return (
        stop_loss,
        take_profit,
    )


def calculate_unrealized_pnl(
    position,
    current_price,
):
    entry_price = float(
        position["entry_price"]
    )

    quantity = float(
        position["quantity"]
    )

    direction = position["direction"]

    if direction == "LONG":
        return (
            current_price -
            entry_price
        ) * quantity

    return (
        entry_price -
        current_price
    ) * quantity


def update_trailing_stop(
    state,
    current_price,
):
    """
    Actualiza el Trailing Stop si esta activado.

    LONG:
    - el ancla solo puede subir
    - el Stop Loss solo puede subir

    SHORT:
    - el ancla solo puede bajar
    - el Stop Loss solo puede bajar

    Nunca afloja un Stop Loss existente.
    """

    position = state.position

    if position is None:
        return False

    trailing_enabled = bool(
        position.get(
            "trailing_enabled",
            False,
        )
    )

    if not trailing_enabled:
        return False

    trailing_pct = position.get(
        "trailing_pct"
    )

    if trailing_pct is None:
        print(
            "TRAILING activo sin porcentaje. "
            "No se modifica el Stop."
        )
        return False

    trailing_pct = float(
        trailing_pct
    )

    if trailing_pct <= 0:
        print(
            "TRAILING con porcentaje invalido. "
            "No se modifica el Stop."
        )
        return False

    direction = position[
        "direction"
    ]

    current_stop = float(
        position["stop_loss"]
    )

    anchor_value = position.get(
        "trailing_anchor"
    )

    if anchor_value is None:
        old_anchor = float(
            current_price
        )
    else:
        old_anchor = float(
            anchor_value
        )

    distance = (
        trailing_pct /
        100.0
    )

    if direction == "LONG":
        new_anchor = max(
            old_anchor,
            float(current_price),
        )

        candidate_stop = (
            new_anchor *
            (1.0 - distance)
        )

        new_stop = max(
            current_stop,
            candidate_stop,
        )

    elif direction == "SHORT":
        new_anchor = min(
            old_anchor,
            float(current_price),
        )

        candidate_stop = (
            new_anchor *
            (1.0 + distance)
        )

        new_stop = min(
            current_stop,
            candidate_stop,
        )

    else:
        raise ValueError(
            "Direccion invalida "
            "en Trailing Stop."
        )

    anchor_changed = (
        abs(
            new_anchor -
            old_anchor
        ) > 0.00000001
    )

    stop_changed = (
        abs(
            new_stop -
            current_stop
        ) > 0.00000001
    )

    if not (
        anchor_changed or
        stop_changed
    ):
        print("")
        print(
            "TRAILING STOP: "
            "sin nuevo avance."
        )
        print(
            f"Ancla:        "
            f"{old_anchor:.2f}"
        )
        print(
            f"Stop actual:  "
            f"{current_stop:.2f}"
        )

        return False

    position[
        "trailing_anchor"
    ] = new_anchor

    position[
        "stop_loss"
    ] = new_stop

    state.data[
        "position"
    ] = position

    state.save()

    print("")
    print(
        "-" * 60
    )
    print(
        "TRAILING STOP - ACTUALIZADO"
    )
    print(
        "-" * 60
    )

    print(
        f"Direccion:    "
        f"{direction}"
    )

    print(
        f"Precio:       "
        f"{current_price:.2f}"
    )

    print(
        f"Trailing:     "
        f"{trailing_pct:.2f}%"
    )

    print(
        f"Ancla previa: "
        f"{old_anchor:.2f}"
    )

    print(
        f"Nueva ancla:  "
        f"{new_anchor:.2f}"
    )

    print(
        f"Stop previo:  "
        f"{current_stop:.2f}"
    )

    print(
        f"Nuevo Stop:   "
        f"{new_stop:.2f}"
    )

    return True


def manage_open_position(
    state,
    current_price,
):
    position = state.position

    if position is None:
        return False

    # Primero actualiza el Trailing,
    # si la posicion lo tiene activado.
    update_trailing_stop(
        state,
        current_price,
    )

    # Volvemos a leer la posicion
    # porque el Trailing pudo mover el SL.
    position = state.position

    if position is None:
        return False

    direction = position[
        "direction"
    ]

    stop_loss = float(
        position["stop_loss"]
    )

    take_profit = float(
        position["take_profit"]
    )

    trailing_enabled = bool(
        position.get(
            "trailing_enabled",
            False,
        )
    )

    trailing_pct = position.get(
        "trailing_pct"
    )

    trailing_anchor = position.get(
        "trailing_anchor"
    )

    print("")
    print("=" * 60)
    print(
        "PAPER POSITION - ABIERTA"
    )
    print("=" * 60)

    print(
        f"Activo:       "
        f"{position['symbol']}"
    )

    print(
        f"Origen:       "
        f"{position.get('source', 'UNCLASSIFIED')}"
    )

    print(
        f"Direccion:    "
        f"{direction}"
    )

    print(
        f"Entrada:      "
        f"{float(position['entry_price']):.2f}"
    )

    print(
        f"Precio actual:"
        f"{current_price:.2f}"
    )

    print(
        f"Cantidad:     "
        f"{float(position['quantity']):.8f}"
    )

    print(
        f"Stop Loss:    "
        f"{stop_loss:.2f}"
    )

    print(
        f"Take Profit:  "
        f"{take_profit:.2f}"
    )

    if trailing_enabled:
        print(
            "Trailing:     ACTIVO"
        )

        if trailing_pct is not None:
            print(
                f"Distancia:    "
                f"{float(trailing_pct):.2f}%"
            )

        if trailing_anchor is not None:
            print(
                f"Ancla:        "
                f"{float(trailing_anchor):.2f}"
            )

    else:
        print(
            "Trailing:     DESACTIVADO"
        )

    unrealized_pnl = (
        calculate_unrealized_pnl(
            position,
            current_price,
        )
    )

    print(
        f"PnL abierto:  "
        f"{unrealized_pnl:.2f} USDT"
    )

    print(
        f"Saldo:        "
        f"{state.balance:.2f} USDT"
    )

    if direction == "LONG":

        if current_price <= stop_loss:
            reason = (
                "TRAILING_STOP"
                if trailing_enabled
                else "STOP_LOSS"
            )

            result = (
                state.close_position(
                    exit_price=stop_loss,
                    reason=reason,
                )
            )

            print("")
            print(
                "PAPER POSITION - CERRADA"
            )

            print(
                f"Motivo:       "
                f"{result['reason']}"
            )

            print(
                f"Salida:       "
                f"{result['exit_price']:.2f}"
            )

            print(
                f"PnL:          "
                f"{result['pnl']:.2f} USDT"
            )

            print(
                f"Saldo final:  "
                f"{result['balance']:.2f} USDT"
            )

            return True

        if current_price >= take_profit:
            result = (
                state.close_position(
                    exit_price=take_profit,
                    reason="TAKE_PROFIT",
                )
            )

            print("")
            print(
                "PAPER POSITION - CERRADA"
            )

            print(
                f"Motivo:       "
                f"{result['reason']}"
            )

            print(
                f"Salida:       "
                f"{result['exit_price']:.2f}"
            )

            print(
                f"PnL:          "
                f"{result['pnl']:.2f} USDT"
            )

            print(
                f"Saldo final:  "
                f"{result['balance']:.2f} USDT"
            )

            return True

    if direction == "SHORT":

        if current_price >= stop_loss:
            reason = (
                "TRAILING_STOP"
                if trailing_enabled
                else "STOP_LOSS"
            )

            result = (
                state.close_position(
                    exit_price=stop_loss,
                    reason=reason,
                )
            )

            print("")
            print(
                "PAPER POSITION - CERRADA"
            )

            print(
                f"Motivo:       "
                f"{result['reason']}"
            )

            print(
                f"Salida:       "
                f"{result['exit_price']:.2f}"
            )

            print(
                f"PnL:          "
                f"{result['pnl']:.2f} USDT"
            )

            print(
                f"Saldo final:  "
                f"{result['balance']:.2f} USDT"
            )

            return True

        if current_price <= take_profit:
            result = (
                state.close_position(
                    exit_price=take_profit,
                    reason="TAKE_PROFIT",
                )
            )

            print("")
            print(
                "PAPER POSITION - CERRADA"
            )

            print(
                f"Motivo:       "
                f"{result['reason']}"
            )

            print(
                f"Salida:       "
                f"{result['exit_price']:.2f}"
            )

            print(
                f"PnL:          "
                f"{result['pnl']:.2f} USDT"
            )

            print(
                f"Saldo final:  "
                f"{result['balance']:.2f} USDT"
            )

            return True

    print("")
    print(
        "La posicion sigue abierta."
    )

    print(
        "No se abre una segunda operacion."
    )

    print("=" * 60)

    return True


def analyze_market(
    data,
    btc_price,
):
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

    print("")
    print(
        "ESTADO DEL MERCADO"
    )
    print("-" * 60)

    for (
        timeframe,
        market_state,
    ) in mtf["states"].items():

        print(
            f"{timeframe:>3}: "
            f"{market_state}"
        )

    print("-" * 60)

    print(
        f"BTC price:   "
        f"{btc_price:.2f}"
    )

    print(
        f"Alignment:   "
        f"{mtf['alignment']['alignment']}"
    )

    print(
        f"Decision:    "
        f"{decision.get('decision')}"
    )

    print(
        f"Direction:   "
        f"{decision.get('direction')}"
    )

    print(
        f"Can execute: "
        f"{decision.get('can_execute')}"
    )

    print(
        f"Readiness:   "
        f"{readiness.get('status')}"
    )

    print(
        f"Bias:        "
        f"{readiness.get('bias')}"
    )

    missing = readiness.get(
        "missing_conditions",
        [],
    )

    if missing:
        print("")
        print(
            "Faltan confirmaciones:"
        )

        for condition in missing:
            print(
                f"- {condition}"
            )

    return (
        decision,
        readiness,
    )


def main():
    print("=" * 60)
    print(
        "PROJECT EDGE - BTC PAPER TRADING v3"
    )
    print("=" * 60)

    state = PaperState(
        initial_balance=INITIAL_BALANCE,
    )

    print("")
    print(
        f"Saldo paper: "
        f"{state.balance:.2f} USDT"
    )

    print("")
    print(
        "Descargando datos reales "
        "de BTCUSDT..."
    )

    data = (
        BinanceHistoricalData()
        .fetch_project_edge_timeframes(
            SYMBOL,
            limit=500,
        )
    )

    btc_price = float(
        data["5M"]["close"].iloc[-1]
    )

    print(
        f"BTC actual: "
        f"{btc_price:.2f}"
    )

    # Si hay cualquier posicion abierta
    # (AUTO o MANUAL, BTC o ETH),
    # primero se gestiona esa posicion.
    if state.has_open_position:

        position_symbol = (
            state.position["symbol"]
        )

        if position_symbol == SYMBOL:
            position_price = (
                btc_price
            )

        else:
            position_data = (
                BinanceHistoricalData()
                .fetch_project_edge_timeframes(
                    position_symbol,
                    limit=100,
                )
            )

            position_price = float(
                position_data[
                    "5M"
                ]["close"].iloc[-1]
            )

        print(
            f"Precio actual de "
            f"{position_symbol}: "
            f"{position_price:.2f}"
        )

        manage_open_position(
            state,
            position_price,
        )

        return

    decision, readiness = (
        analyze_market(
            data,
            btc_price,
        )
    )

    direction = decision.get(
        "direction"
    )

    decision_status = decision.get(
        "decision"
    )

    readiness_status = readiness.get(
        "status"
    )

    can_execute = bool(
        decision.get(
            "can_execute"
        )
    )

    entry_confirmed = (
        readiness_status == "READY"
        and decision_status != "BLOCKED"
        and direction in (
            "LONG",
            "SHORT",
        )
        and can_execute
    )

    print("")
    print("=" * 60)

    if not entry_confirmed:
        print(
            "PAPER TRADE: SIN ENTRADA"
        )

        print("")

        print(
            "PROJECT EDGE no confirmo "
            "una entrada."
        )

        print(
            "No se abre ninguna "
            "posicion simulada."
        )

        print(
            f"Saldo paper: "
            f"{state.balance:.2f} USDT"
        )

        print("=" * 60)

        return

    entry_price = btc_price

    stop_loss, take_profit = (
        calculate_levels(
            direction,
            entry_price,
        )
    )

    quantity = (
        state.balance /
        entry_price
    )

    position = (
        state.open_position(
            symbol=SYMBOL,
            direction=direction,
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss,
            take_profit=take_profit,
            source="AUTO",
        )
    )

    # Toda operacion AUTO nueva
    # comienza con Trailing apagado.
    position[
        "trailing_enabled"
    ] = False

    position[
        "trailing_pct"
    ] = None

    position[
        "trailing_anchor"
    ] = None

    state.data[
        "position"
    ] = position

    state.save()

    risk_usdt = (
        abs(
            position["entry_price"]
            - position["stop_loss"]
        )
        * position["quantity"]
    )

    target_usdt = (
        abs(
            position["take_profit"]
            - position["entry_price"]
        )
        * position["quantity"]
    )

    print(
        "PAPER TRADE: "
        "ENTRADA CONFIRMADA"
    )

    print("-" * 60)

    print(
        f"Activo:       "
        f"{position['symbol']}"
    )

    print(
        f"Direccion:    "
        f"{position['direction']}"
    )

    print(
        f"Entrada:      "
        f"{position['entry_price']:.2f}"
    )

    print(
        f"Cantidad:     "
        f"{position['quantity']:.8f}"
    )

    print(
        f"Stop Loss:    "
        f"{position['stop_loss']:.2f}"
    )

    print(
        f"Take Profit:  "
        f"{position['take_profit']:.2f}"
    )

    print(
        "Trailing:     DESACTIVADO"
    )

    print(
        f"Riesgo demo:  "
        f"{risk_usdt:.2f} USDT"
    )

    print(
        f"Objetivo:     "
        f"{target_usdt:.2f} USDT"
    )

    print(
        f"Saldo paper:  "
        f"{state.balance:.2f} USDT"
    )

    print("")
    print(
        "POSICION PAPER GUARDADA."
    )

    print(
        "En la proxima ejecucion "
        "se controlara SL / TP "
        "y Trailing si esta activo."
    )

    print("")
    print(
        "NO se envio ninguna "
        "orden real."
    )

    print("=" * 60)


if __name__ == "__main__":
    main()
