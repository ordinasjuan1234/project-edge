"""
PROJECT EDGE
BTC Paper Trading v1

Usa datos reales de BTCUSDT y el motor de PROJECT EDGE.

IMPORTANTE:
- NO ejecuta ordenes reales.
- NO usa API key privada.
- NO mueve dinero.
- Solo abre una posicion simulada si PROJECT EDGE confirma entrada.
"""

from engine.data.binance_historical_data import BinanceHistoricalData
from engine.multitimeframe.multi_timeframe_structure_engine import (
    MultiTimeframeStructureEngine,
)
from engine.decision.decision_engine import DecisionEngine
from engine.decision.entry_readiness import EntryReadiness

from paper_trader import PaperTrader


SYMBOL = "BTCUSDT"

INITIAL_BALANCE = 10000.0

# Para esta primera version:
# Stop = 0.5%
# Objetivo = 1.0%
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


def main():
    print("=" * 60)
    print("PROJECT EDGE - BTC PAPER TRADING")
    print("=" * 60)

    print("")
    print("Descargando datos reales de BTCUSDT...")

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

    print("")
    print("ESTADO DEL MERCADO")
    print("-" * 60)

    for timeframe, state in mtf["states"].items():
        print(f"{timeframe:>3}: {state}")

    print("-" * 60)
    print(f"BTC price:   {btc_price}")
    print(f"Alignment:   {mtf['alignment']['alignment']}")
    print(f"Decision:    {decision.get('decision')}")
    print(f"Direction:   {decision.get('direction')}")
    print(f"Can execute: {decision.get('can_execute')}")
    print(f"Readiness:   {readiness.get('status')}")
    print(f"Bias:        {readiness.get('bias')}")

    missing = readiness.get("missing_conditions", [])

    if missing:
        print("")
        print("Faltan confirmaciones:")

        for condition in missing:
            print(f"- {condition}")

    direction = decision.get("direction")
    decision_status = decision.get("decision")
    readiness_status = readiness.get("status")
    can_execute = bool(decision.get("can_execute"))

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
        print("PROJECT EDGE no confirmo una entrada.")
        print("No se abre ninguna posicion simulada.")
        print("=" * 60)
        return

    trader = PaperTrader(
        initial_balance=INITIAL_BALANCE
    )

    entry_price = btc_price

    stop_loss, take_profit = calculate_levels(
        direction,
        entry_price,
    )

    # Sin apalancamiento:
    # el valor maximo de la posicion no supera el saldo demo.
    quantity = trader.balance / entry_price

    position = trader.open_position(
        symbol=SYMBOL,
        direction=direction,
        entry_price=entry_price,
        quantity=quantity,
        stop_loss=stop_loss,
        take_profit=take_profit,
    )

    risk_usdt = abs(
        position.entry_price - position.stop_loss
    ) * position.quantity

    target_usdt = abs(
        position.take_profit - position.entry_price
    ) * position.quantity

    print("PAPER TRADE: ENTRADA CONFIRMADA")
    print("-" * 60)

    print(f"Activo:       {position.symbol}")
    print(f"Direccion:    {position.direction}")
    print(f"Entrada:      {position.entry_price:.2f}")
    print(f"Cantidad:     {position.quantity:.8f}")
    print(f"Stop Loss:    {position.stop_loss:.2f}")
    print(f"Take Profit:  {position.take_profit:.2f}")
    print(f"Riesgo demo:  {risk_usdt:.2f} USDT")
    print(f"Objetivo:     {target_usdt:.2f} USDT")
    print(f"Saldo demo:   {trader.balance:.2f} USDT")

    print("")
    print("POSICION PAPER ABIERTA")
    print("NO se envio ninguna orden real.")

    print("=" * 60)


if __name__ == "__main__":
    main()
