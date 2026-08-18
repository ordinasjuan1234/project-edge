"""
PROJECT EDGE
BTC Paper Trading v2

Paper Trading con estado persistente.

Funciones:
- Lee datos reales de BTCUSDT.
- Usa el motor multi-timeframe de PROJECT EDGE.
- Solo abre una operacion cuando hay confirmacion real.
- Recuerda una posicion paper abierta.
- Controla Stop Loss y Take Profit.
- Actualiza el saldo demo al cerrar.

IMPORTANTE:
- NO ejecuta ordenes reales.
- NO usa API key privada.
- NO mueve dinero real.
"""

from engine.data.binance_historical_data import BinanceHistoricalData
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


def calculate_levels(direction, entry_price):
    if direction == "LONG":
        stop_loss = entry_price * (1.0 - STOP_PCT)
        take_profit = entry_price * (1.0 + TAKE_PROFIT_PCT)

    elif direction == "SHORT":
        stop_loss = entry_price * (1.0 + STOP_PCT)
        take_profit = entry_price * (1.0 - TAKE_PROFIT_PCT)

    else:
        raise ValueError("Direccion invalida.")

    return stop_loss, take_profit


def calculate_unrealized_pnl(position, current_price):
    entry_price = float(position["entry_price"])
    quantity = float(position["quantity"])
    direction = position["direction"]

    if direction == "LONG":
        return (current_price - entry_price) * quantity

    return (entry_price - current_price) * quantity


def manage_open_position(state, current_price):
    position = state.position

    if position is None:
        return False

    direction = position["direction"]
    stop_loss = float(position["stop_loss"])
    take_profit = float(position["take_profit"])

    print("")
    print("=" * 60)
    print("PAPER POSITION - ABIERTA")
    print("=" * 60)

    print(f"Activo:       {position['symbol']}")
    print(f"Direccion:    {direction}")
    print(f"Entrada:      {float(position['entry_price']):.2f}")
    print(f"Precio actual:{current_price:.2f}")
    print(f"Cantidad:     {float(position['quantity']):.8f}")
    print(f"Stop Loss:    {stop_loss:.2f}")
    print(f"Take Profit:  {take_profit:.2f}")

    unrealized_pnl = calculate_unrealized_pnl(
        position,
        current_price,
    )

    print(f"PnL abierto:  {unrealized_pnl:.2f} USDT")
    print(f"Saldo:        {state.balance:.2f} USDT")

    if direction == "LONG":
        if current_price <= stop_loss:
            result = state.close_position(
                exit_price=stop_loss,
                reason="STOP_LOSS",
            )

            print("")
            print("PAPER POSITION - CERRADA")
            print(f"Motivo:       {result['reason']}")
            print(f"Salida:       {result['exit_price']:.2f}")
            print(f"PnL:          {result['pnl']:.2f} USDT")
            print(f"Saldo final:  {result['balance']:.2f} USDT")

            return True

        if current_price >= take_profit:
            result = state.close_position(
                exit_price=take_profit,
                reason="TAKE_PROFIT",
            )

            print("")
            print("PAPER POSITION - CERRADA")
            print(f"Motivo:       {result['reason']}")
            print(f"Salida:       {result['exit_price']:.2f}")
            print(f"PnL:          {result['pnl']:.2f} USDT")
            print(f"Saldo final:  {result['balance']:.2f} USDT")

            return True

    if direction == "SHORT":
        if current_price >= stop_loss:
            result = state.close_position(
                exit_price=stop_loss,
                reason="STOP_LOSS",
            )

            print("")
            print("PAPER POSITION - CERRADA")
            print(f"Motivo:       {result['reason']}")
            print(f"Salida:       {result['exit_price']:.2f}")
            print(f"PnL:          {result['pnl']:.2f} USDT")
            print(f"Saldo final:  {result['balance']:.2f} USDT")

            return True

        if current_price <= take_profit:
            result = state.close_position(
                exit_price=take_profit,
                reason="TAKE_PROFIT",
            )

            print("")
            print("PAPER POSITION - CERRADA")
            print(f"Motivo:       {result['reason']}")
            print(f"Salida:       {result['exit_price']:.2f}")
            print(f"PnL:          {result['pnl']:.2f} USDT")
            print(f"Saldo final:  {result['balance']:.2f} USDT")

            return True

    print("")
    print("La posicion sigue abierta.")
    print("No se abre una segunda operacion.")
    print("=" * 60)

    return True


def analyze_market(data, btc_price):
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

    print("")
    print("ESTADO DEL MERCADO")
    print("-" * 60)

    for timeframe, market_state in mtf["states"].items():
        print(f"{timeframe:>3}: {market_state}")

    print("-" * 60)
    print(f"BTC price:   {btc_price:.2f}")
    print(f"Alignment:   {mtf['alignment']['alignment']}")
    print(f"Decision:    {decision.get('decision')}")
    print(f"Direction:   {decision.get('direction')}")
    print(f"Can execute: {decision.get('can_execute')}")
    print(f"Readiness:   {readiness.get('status')}")
    print(f"Bias:        {readiness.get('bias')}")

    missing = readiness.get(
        "missing_conditions",
        [],
    )

    if missing:
        print("")
        print("Faltan confirmaciones:")

        for condition in missing:
            print(f"- {condition}")

    return decision, readiness


def main():
    print("=" * 60)
    print("PROJECT EDGE - BTC PAPER TRADING v2")
    print("=" * 60)

    state = PaperState(
        initial_balance=INITIAL_BALANCE,
    )

    print("")
    print(f"Saldo paper: {state.balance:.2f} USDT")

    print("")
    print("Descargando datos reales de BTCUSDT...")

    data = BinanceHistoricalData().fetch_project_edge_timeframes(
        SYMBOL,
        limit=500,
    )

    btc_price = float(
        data["5M"]["close"].iloc[-1]
    )

    print(f"BTC actual: {btc_price:.2f}")

    if state.has_open_position:
        manage_open_position(
            state,
            btc_price,
        )
        return

    decision, readiness = analyze_market(
        data,
        btc_price,
    )

    direction = decision.get("direction")
    decision_status = decision.get("decision")
    readiness_status = readiness.get("status")
    can_execute = bool(
        decision.get("can_execute")
    )

    entry_confirmed = (
        readiness_status == "READY"
        and decision_status != "BLOCKED"
        and direction in ("LONG", "SHORT")
        and can_execute
    )

    print("")
    print("=" * 60)

    if not entry_confirmed:
        print("PAPER TRADE: SIN ENTRADA")
        print("")
        print(
            "PROJECT EDGE no confirmo una entrada."
        )
        print(
            "No se abre ninguna posicion simulada."
        )
        print(
            f"Saldo paper: {state.balance:.2f} USDT"
        )
        print("=" * 60)
        return

    entry_price = btc_price

    stop_loss, take_profit = calculate_levels(
        direction,
        entry_price,
    )

    quantity = state.balance / entry_price

    position = state.open_position(
        symbol=SYMBOL,
        direction=direction,
        entry_price=entry_price,
        quantity=quantity,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )

    risk_usdt = abs(
        position["entry_price"]
        - position["stop_loss"]
    ) * position["quantity"]

    target_usdt = abs(
        position["take_profit"]
        - position["entry_price"]
    ) * position["quantity"]

    print("PAPER TRADE: ENTRADA CONFIRMADA")
    print("-" * 60)

    print(f"Activo:       {position['symbol']}")
    print(f"Direccion:    {position['direction']}")
    print(f"Entrada:      {position['entry_price']:.2f}")
    print(f"Cantidad:     {position['quantity']:.8f}")
    print(f"Stop Loss:    {position['stop_loss']:.2f}")
    print(
        f"Take Profit:  {position['take_profit']:.2f}"
    )
    print(f"Riesgo demo:  {risk_usdt:.2f} USDT")
    print(f"Objetivo:     {target_usdt:.2f} USDT")
    print(f"Saldo paper:  {state.balance:.2f} USDT")

    print("")
    print("POSICION PAPER GUARDADA.")
    print(
        "En la proxima ejecucion se controlara "
        "Stop Loss / Take Profit."
    )
    print("")
    print("NO se envio ninguna orden real.")
    print("=" * 60)


if __name__ == "__main__":
    main()
